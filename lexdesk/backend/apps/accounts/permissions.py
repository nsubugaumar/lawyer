from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import MANAGES_BILLING, MANAGES_CLIENTS, Role


class MFASatisfied(BasePermission):
    """
    Applied to every endpoint by default.

    When the firm requires two-factor for staff, a staff member who signed in
    without it gets exactly one thing they can do: set it up. Their token
    carries an `mfa` claim that tells us how they authenticated.
    """

    message = "Two-factor authentication must be set up before you can continue."
    code = "mfa_setup_required"

    def has_permission(self, request, view):
        if getattr(view, "allow_without_mfa", False):
            return True
        user = request.user
        if not (user and user.is_authenticated) or user.is_client:
            return True
        if not settings.LEXDESK_REQUIRE_MFA_FOR_STAFF:
            return True
        token = getattr(request, "auth", None)
        return bool(token and token.get("mfa"))


class FirmActive(BasePermission):
    """
    Applied to every endpoint. When the platform suspends a firm, its people
    lose access on their very next request, whatever tokens they hold.
    """

    message = "Your firm's LexDesk account is suspended. Please contact LexDesk."
    code = "firm_suspended"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated) or not getattr(user, "firm_id", None):
            return True
        return user.firm.is_active


class IsFirmStaff(BasePermission):
    message = "This area is for firm staff only."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_firm_staff


class HasRole(BasePermission):
    """Usage: permission_classes = [HasRole.of(Role.ADMIN, Role.PARTNER)]"""

    allowed: set = set()

    @classmethod
    def of(cls, *roles):
        return type("HasRole", (cls,), {"allowed": set(roles)})

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed


class ClientDataPermission(BasePermission):
    """Clients may read their own record; staff who manage clients may edit."""

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.role in MANAGES_CLIENTS


class BillingPermission(BasePermission):
    """Fee earners record their own time; only accounts staff touch invoices."""

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.role in MANAGES_BILLING or getattr(view, "fee_earners_may_write", False)


IsAdmin = HasRole.of(Role.ADMIN)
IsFirmManager = HasRole.of(Role.ADMIN, Role.PARTNER)
