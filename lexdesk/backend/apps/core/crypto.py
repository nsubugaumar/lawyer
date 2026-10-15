"""
Encryption for LexDesk.

Two jobs, two tools:

1. Documents use *envelope encryption*. Every file version gets its own random
   256-bit data key and is sealed with AES-256-GCM. That data key is then
   wrapped (encrypted) with the firm's master key and stored beside the file.
   The master key never touches the disk with the data, and rotating it means
   re-wrapping a few hundred bytes per document, not re-encrypting gigabytes.

   GCM is authenticated: if a single bit of the stored file is altered, the
   decrypt fails loudly instead of handing a lawyer a silently corrupted
   exhibit. We also bind each ciphertext to its database record (the
   "associated data"), so an attacker with storage access cannot swap one
   client's file for another's.

2. Sensitive database columns (national ID numbers, private notes, MFA
   secrets) use Fernet via MultiFernet, which supports key rotation out of
   the box.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

NONCE_BYTES = 12  # the size AES-GCM is designed around


class DecryptionError(Exception):
    """Raised when ciphertext is tampered with, or the key is missing."""


# --------------------------------------------------------------------------
# Key loading
# --------------------------------------------------------------------------


def _dev_key(purpose: str) -> bytes:
    # Deterministic so a developer's local vault survives a restart. Only ever
    # used when DEBUG is on; settings.py refuses to boot production without
    # real keys.
    return hashlib.sha256(f"{purpose}:{settings.SECRET_KEY}".encode()).digest()


@lru_cache(maxsize=1)
def vault_keys() -> dict[str, bytes]:
    """Master keys keyed by id. The first one is the active key."""
    raw = settings.LEXDESK_VAULT_KEYS
    if not raw:
        return {"dev": _dev_key("vault")}

    keys: dict[str, bytes] = {}
    for item in raw.split(","):
        key_id, _, encoded = item.strip().partition(":")
        key = base64.urlsafe_b64decode(encoded)
        if not key_id or len(key) != 32:
            raise ImproperlyConfigured("Each LEXDESK_VAULT_KEYS entry must be 'id:<32-byte base64 key>'.")
        keys[key_id] = key
    return keys


def active_vault_key() -> tuple[str, bytes]:
    key_id, key = next(iter(vault_keys().items()))
    return key_id, key


@lru_cache(maxsize=1)
def field_cipher() -> MultiFernet:
    raw = settings.LEXDESK_FIELD_KEYS
    if raw:
        fernets = [Fernet(k.strip()) for k in raw.split(",") if k.strip()]
    else:
        fernets = [Fernet(base64.urlsafe_b64encode(_dev_key("field")))]
    return MultiFernet(fernets)


@lru_cache(maxsize=1)
def search_key() -> bytes:
    """
    Key for the documents' blind search index (see documents/search.py).
    Separate from the vault keys so rotating those does not break search.
    """
    raw = settings.LEXDESK_SEARCH_KEY
    if raw:
        key = base64.urlsafe_b64decode(raw)
        if len(key) != 32:
            raise ImproperlyConfigured("LEXDESK_SEARCH_KEY must be a 32-byte base64 key.")
        return key
    return _dev_key("search")


def generate_vault_key() -> str:
    """Helper for ops: prints a fresh key in the format settings expect."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


# --------------------------------------------------------------------------
# Document envelope encryption
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SealedBlob:
    ciphertext: bytes
    wrapped_key: bytes  # nonce + encrypted data key
    key_id: str  # which master key wrapped it


def seal(plaintext: bytes, *, associated_data: bytes) -> SealedBlob:
    data_key = AESGCM.generate_key(bit_length=256)

    nonce = os.urandom(NONCE_BYTES)
    ciphertext = nonce + AESGCM(data_key).encrypt(nonce, plaintext, associated_data)

    key_id, master = active_vault_key()
    wrap_nonce = os.urandom(NONCE_BYTES)
    wrapped = wrap_nonce + AESGCM(master).encrypt(wrap_nonce, data_key, key_id.encode())

    return SealedBlob(ciphertext=ciphertext, wrapped_key=wrapped, key_id=key_id)


def unseal(blob: SealedBlob, *, associated_data: bytes) -> bytes:
    master = vault_keys().get(blob.key_id)
    if master is None:
        raise DecryptionError(f"Vault key '{blob.key_id}' is not loaded.")

    try:
        wrap_nonce, wrapped = blob.wrapped_key[:NONCE_BYTES], blob.wrapped_key[NONCE_BYTES:]
        data_key = AESGCM(master).decrypt(wrap_nonce, wrapped, blob.key_id.encode())

        nonce, body = blob.ciphertext[:NONCE_BYTES], blob.ciphertext[NONCE_BYTES:]
        return AESGCM(data_key).decrypt(nonce, body, associated_data)
    except InvalidTag as exc:
        raise DecryptionError("Document failed its integrity check.") from exc


def rewrap(blob: SealedBlob) -> SealedBlob:
    """Re-wrap a data key under the current master key (key rotation)."""
    old_master = vault_keys().get(blob.key_id)
    if old_master is None:
        raise DecryptionError(f"Vault key '{blob.key_id}' is not loaded.")

    wrap_nonce, wrapped = blob.wrapped_key[:NONCE_BYTES], blob.wrapped_key[NONCE_BYTES:]
    try:
        data_key = AESGCM(old_master).decrypt(wrap_nonce, wrapped, blob.key_id.encode())
    except InvalidTag as exc:
        raise DecryptionError("Wrapped key failed its integrity check.") from exc

    key_id, master = active_vault_key()
    new_nonce = os.urandom(NONCE_BYTES)
    new_wrapped = new_nonce + AESGCM(master).encrypt(new_nonce, data_key, key_id.encode())
    return SealedBlob(ciphertext=blob.ciphertext, wrapped_key=new_wrapped, key_id=key_id)


# --------------------------------------------------------------------------
# Field encryption
# --------------------------------------------------------------------------


def encrypt_text(value: str) -> str:
    return field_cipher().encrypt(value.encode()).decode()


def decrypt_text(token: str) -> str:
    try:
        return field_cipher().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("Encrypted field could not be decrypted.") from exc


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
