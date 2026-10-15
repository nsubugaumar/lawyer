"""
Time-based one-time passwords (the six digits from Google Authenticator,
Microsoft Authenticator, 1Password, etc.).
"""

import time

import pyotp
from django.core import signing

ISSUER = "LexDesk"
CHALLENGE_SALT = "lexdesk.mfa.challenge"
CHALLENGE_MAX_AGE = 300  # five minutes to type the code


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=f"{ISSUER} · {_firm_name(user)}")


def verify_code(user, secret: str, code: str) -> bool:
    """
    Accept the current code and one step either side for clock drift, and
    refuse to accept the same code twice. Without the replay check, someone
    shoulder-surfing a code could reuse it within its 30-second window.
    """
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False

    totp = pyotp.TOTP(secret)
    now_step = int(time.time()) // totp.interval
    for step in (now_step - 1, now_step, now_step + 1):
        if user.mfa_last_used_step is not None and step <= user.mfa_last_used_step:
            continue
        if totp.at(step * totp.interval) == code:
            user.mfa_last_used_step = step
            user.save(update_fields=["mfa_last_used_step"])
            return True
    return False


def issue_challenge(user) -> str:
    """A short-lived, signed ticket proving the password step was passed."""
    return signing.dumps({"uid": str(user.pk)}, salt=CHALLENGE_SALT)


def read_challenge(token: str) -> str | None:
    try:
        return signing.loads(token, salt=CHALLENGE_SALT, max_age=CHALLENGE_MAX_AGE)["uid"]
    except (signing.BadSignature, KeyError, TypeError):
        return None


def _firm_name(user):
    from apps.firm.models import Firm

    return Firm.of(user).name
