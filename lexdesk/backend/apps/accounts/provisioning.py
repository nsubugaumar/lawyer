"""
Accounts are created by the system, never by self sign-up.

A lawyer is added by an administrator. A client account comes into being the
moment reception registers them, or when they book their first consultation
online. Either way the new account starts with no usable password. The person
receives a one-time activation link and chooses their own password, so a
password is never typed by someone else, emailed, or written on a sticky note.

The same link mechanism powers "forgot password".
"""

import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.audit.services import record
from apps.notifications.models import Category
from apps.notifications.services import notify

from .models import User

logger = logging.getLogger("lexdesk.security")


class ActivationTokenGenerator(PasswordResetTokenGenerator):
    """
    Django's reset tokens are tied to the password hash and last login, so a
    link dies the instant it is used. We add the active flag, so deactivating
    someone also kills any link they have not opened yet.
    """

    key_salt = "lexdesk.accounts.activation"

    def _make_hash_value(self, user, timestamp):
        return f"{super()._make_hash_value(user, timestamp)}{user.is_active}"


activation_tokens = ActivationTokenGenerator()

ACTIVATION_DAYS = 3


def activation_link(user, purpose="activate") -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = activation_tokens.make_token(user)
    base = getattr(settings, "LEXDESK_WEB_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/{purpose}?uid={uid}&token={token}"


def user_from_link(uid: str, token: str) -> User | None:
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None
    if not user.is_active or not activation_tokens.check_token(user, token):
        return None
    return user


def send_invitation(user, *, invited_by=None):
    link = activation_link(user)
    from apps.firm.models import Firm

    firm = Firm.of(user).name
    if user.is_client:
        greeting = f"{firm} has opened a secure client portal for you."
    else:
        greeting = f"You have been added to {firm} on LexDesk as {user.get_role_display()}."

    notify(
        user,
        subject=f"Your {firm} account is ready",
        body=(
            f"Hello {user.first_name},\n\n{greeting}\n\n"
            f"Please choose your password here (the link works once and expires in {ACTIVATION_DAYS} days):\n"
            f"{link}\n\n"
            "If you were not expecting this, you can safely ignore it.\n"
        ),
        sms=f"{firm}: your LexDesk account is ready. Check your email to activate it.",
        category=Category.SECURITY,
    )
    record("account.invitation_sent", actor=invited_by, target=user)


class AccountInOtherFirm(Exception):
    """The email already has a LexDesk login at a different firm."""


@transaction.atomic
def provision_user(*, email, first_name, last_name, role, firm=None, phone="", title="", invited_by=None, send=True) -> tuple[User, bool]:
    """
    Find or create the account for this email. Returns (user, created).

    Idempotent on purpose: registering the same client twice, or a client
    booking a second consultation, must not produce two logins.
    """
    email = email.strip().lower()
    if firm is None and invited_by is not None:
        firm = invited_by.firm
    user = User.objects.filter(email__iexact=email).first()
    if user:
        if user.firm_id != getattr(firm, "pk", None):
            # One login belongs to one firm. Never hand a firm someone else's account.
            raise AccountInOtherFirm(email)
        return user, False
    user = User(email=email, first_name=first_name, last_name=last_name, role=role, phone=phone, title=title, firm=firm)
    user.set_unusable_password()
    user.is_staff = False  # the Django admin is for platform operators only
    user.save()

    record("account.created", actor=invited_by, target=user, role=role)
    if send:
        # Only send once the database work has really committed, so nobody
        # gets a link to an account that was rolled back.
        transaction.on_commit(lambda: send_invitation(user, invited_by=invited_by))
    return user, True
