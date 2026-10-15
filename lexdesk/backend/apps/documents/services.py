from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F

from apps.audit.services import record
from apps.core.crypto import DecryptionError, SealedBlob, seal, sha256_hex, unseal

from .models import Document, DocumentVersion
from .validation import inspect_upload


@transaction.atomic
def add_version(document: Document, uploaded, *, user, comment="") -> DocumentVersion:
    content, filename, content_type = inspect_upload(uploaded)

    # Lock the document row so two people uploading at once get v4 and v5,
    # not two v4s.
    Document.objects.select_for_update().filter(pk=document.pk).update(current_version=F("current_version") + 1)
    document.refresh_from_db(fields=["current_version"])

    version = DocumentVersion(
        document=document,
        number=document.current_version,
        original_filename=filename,
        content_type=content_type,
        size=len(content),
        sha256=sha256_hex(content),
        uploaded_by=user,
        comment=comment,
    )
    sealed = seal(content, associated_data=version.associated_data)
    version.wrapped_key = sealed.wrapped_key
    version.key_id = sealed.key_id
    version.blob.save("blob", ContentFile(sealed.ciphertext), save=False)
    version.save()

    _index_later(document, version, content, content_type)
    record(
        "document.uploaded" if version.number == 1 else "document.version_added",
        actor=user, target=document, matter=document.matter,
        version=version.number, size=version.size, sha256=version.sha256,
    )
    return version


def read_version(version: DocumentVersion) -> bytes:
    """Decrypt a version and prove it is byte-for-byte what was uploaded."""
    with version.blob.open("rb") as fh:
        ciphertext = fh.read()

    plaintext = unseal(
        SealedBlob(ciphertext=ciphertext, wrapped_key=bytes(version.wrapped_key), key_id=version.key_id),
        associated_data=version.associated_data,
    )
    if sha256_hex(plaintext) != version.sha256:
        # GCM already guarantees this, but a second, independent check costs
        # microseconds and catches bugs as well as attacks.
        raise DecryptionError("Document fingerprint mismatch.")
    return plaintext


def _index_later(document, version, content, content_type):
    """
    Make the document searchable. Inline on a developer's machine; in
    production a worker does it, so a 300-page scan never slows an upload.
    """
    from django.conf import settings

    from .search import index_document

    if settings.CELERY_TASK_ALWAYS_EAGER:
        index_document(document, content, content_type)
        return
    from .tasks import index_version

    transaction.on_commit(lambda: index_version.delay(str(version.pk)))
