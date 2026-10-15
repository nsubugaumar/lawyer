import logging

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import record
from apps.notifications.models import Category
from apps.notifications.services import notify

from . import mfa
from .models import RecoveryCode, Role, User
from .permissions import FirmActive, IsFirmManager, MFASatisfied
from .provisioning import activation_link, provision_user, send_invitation, user_from_link
from .serializers import (
    ActivateSerializer,
    CodeSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    MFAVerifySerializer,
    PasswordChangeSerializer,
    PasswordConfirmSerializer,
    TeamMemberSerializer,
    UserSerializer,
)
from .tokens import clear_refresh_cookie, refresh_from_request, session_response, token_response

logger = logging.getLogger("lexdesk.security")

# Hashing a throwaway password when the email is unknown makes a miss take as
# long as a hit, so response timing cannot reveal who has an account.
_TIMING_DUMMY = make_password("lexdesk-timing-equaliser")

GENERIC_LOGIN_ERROR = (
    "Those details did not work. For your security, accounts pause for a few minutes after repeated attempts."
)


def _refuse(message=GENERIC_LOGIN_ERROR, code="invalid_credentials", status_code=401):
    return Response({"error": {"code": code, "message": message}}, status=status_code)


class LoginView(APIView):
    """Step one: email and password. Returns a session, or an MFA challenge."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email, password = data.validated_data["email"].lower(), data.validated_data["password"]

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            User(password=_TIMING_DUMMY).check_password(password)
            record("auth.login_failed", reason="unknown_email", email=email)
            return _refuse()

        if not user.is_active or user.is_locked or not user.has_usable_password() or (user.firm_id and not user.firm.is_active):
            record("auth.login_refused", target=user, reason="inactive_or_locked")
            return _refuse()

        if not user.check_password(password):
            user.register_failed_login()
            record("auth.login_failed", target=user, reason="bad_password", locked=user.is_locked)
            return _refuse()

        user.clear_failed_logins()

        if user.mfa_enabled:
            record("auth.password_ok_mfa_pending", actor=user)
            return Response({"mfa_required": True, "mfa_token": mfa.issue_challenge(user)})

        record("auth.login", actor=user, mfa=False)
        return session_response(request, user, used_mfa=False)


class MFAVerifyView(APIView):
    """Step two: the six-digit code (or a one-time recovery code)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "mfa"

    def post(self, request):
        data = MFAVerifySerializer(data=request.data)
        data.is_valid(raise_exception=True)

        uid = mfa.read_challenge(data.validated_data["mfa_token"])
        user = User.objects.filter(pk=uid, is_active=True).first() if uid else None
        if user is None or not user.mfa_enabled or user.is_locked:
            return _refuse("This sign-in attempt has expired. Please start again.", code="mfa_expired")

        code = data.validated_data["code"]
        if mfa.verify_code(user, user.mfa_secret, code):
            method = "totp"
        elif "-" in code and RecoveryCode.redeem(user, code):
            method = "recovery_code"
            remaining = user.recovery_codes.filter(used_at__isnull=True).count()
            notify(
                user,
                subject="A recovery code was used to sign in",
                category=Category.SECURITY,
                body=f"A one-time recovery code was just used on your account. {remaining} remain. "
                "If this was not you, contact your administrator immediately.",
            )
        else:
            user.register_failed_login()
            record("auth.mfa_failed", target=user)
            return _refuse("That code is not valid. Please try again.", code="invalid_code")

        user.clear_failed_logins()
        record("auth.login", actor=user, mfa=True, method=method)
        return session_response(request, user, used_mfa=True)


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw = refresh_from_request(request)
        if not raw:
            return _refuse("Your session has ended. Please sign in again.", code="session_expired")

        serializer = TokenRefreshSerializer(data={"refresh": raw})
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:  # noqa: BLE001 - any failure here means "sign in again"
            response = _refuse("Your session has ended. Please sign in again.", code="session_expired")
            clear_refresh_cookie(response)
            return response

        new_refresh = RefreshToken(serializer.validated_data["refresh"])
        return token_response(request, new_refresh)


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw = refresh_from_request(request)
        if raw:
            try:
                token = RefreshToken(raw)
                token.blacklist()
                record("auth.logout", target=User.objects.filter(pk=token.get("user_id")).first())
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    allow_without_mfa = True  # so a new lawyer can see who they are while setting up MFA

    def get_object(self):
        return self.request.user


class PasswordChangeView(APIView):
    allow_without_mfa = True

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        record("auth.password_changed", actor=user)
        notify(user, subject="Your password was changed", body="If this was not you, contact your administrator now.",
               category=Category.SECURITY)
        # Every older token is now dead (revoke claim). Hand back a fresh session.
        return session_response(request, user, used_mfa=bool(request.auth.get("mfa")))


class ActivateView(APIView):
    """
    Used both for first-time activation and for password resets. The link in
    the email carries uid + token; the person chooses their password here.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def get(self, request):
        user = user_from_link(request.query_params.get("uid", ""), request.query_params.get("token", ""))
        if user is None:
            return _refuse("This link has expired or was already used.", code="invalid_link", status_code=400)
        return Response({"first_name": user.first_name, "email": user.email, "mfa_enabled": user.mfa_enabled})

    def post(self, request):
        data = ActivateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = user_from_link(data.validated_data["uid"], data.validated_data["token"])
        if user is None:
            return _refuse("This link has expired or was already used.", code="invalid_link", status_code=400)

        try:
            password_validation.validate_password(data.validated_data["password"], user)
        except DjangoValidationError as exc:
            return Response(
                {"error": {"code": "invalid", "message": "Please choose a stronger password.", "fields": {"password": exc.messages}}},
                status=400,
            )

        first_time = not user.has_usable_password()
        user.set_password(data.validated_data["password"])
        user.clear_failed_logins()
        user.locked_until = None
        user.save()
        record("auth.account_activated" if first_time else "auth.password_reset", actor=user)
        return Response({"detail": "Your password is set. You can now sign in."})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def post(self, request):
        data = ForgotPasswordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=data.validated_data["email"], is_active=True).first()
        if user:
            link = activation_link(user, purpose="reset-password")
            notify(
                user,
                subject="Reset your LexDesk password",
                body=f"Use this link to choose a new password. It works once and expires in 3 days:\n{link}\n\n"
                "If you did not ask for this, ignore this email. Your password has not changed.",
                in_app=False,
                category=Category.SECURITY,
            )
            record("auth.password_reset_requested", target=user)
        # Same answer either way: we do not confirm who has an account.
        return Response({"detail": "If that email belongs to an account, a reset link is on its way."}, status=202)


# --------------------------------------------------------------------------
# Two-factor setup
# --------------------------------------------------------------------------


class MFASetupView(APIView):
    """Start enrolment: returns a secret and the otpauth:// URI for the QR code."""

    allow_without_mfa = True

    def post(self, request):
        user = request.user
        if user.mfa_enabled:
            return _refuse("Two-factor is already on.", code="mfa_already_enabled", status_code=400)
        secret = mfa.new_secret()
        user.mfa_pending_secret = secret
        user.save(update_fields=["mfa_pending_secret"])
        return Response({"secret": secret, "otpauth_uri": mfa.provisioning_uri(user, secret)})


class MFAConfirmView(APIView):
    """Finish enrolment by proving the authenticator app works."""

    allow_without_mfa = True
    throttle_scope = "mfa"

    def post(self, request):
        data = CodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        if not user.mfa_pending_secret:
            return _refuse("Start two-factor setup first.", code="mfa_not_started", status_code=400)
        if not mfa.verify_code(user, user.mfa_pending_secret, data.validated_data["code"]):
            return _refuse("That code did not match. Check your phone's clock and try again.", code="invalid_code", status_code=400)

        with transaction.atomic():
            user.mfa_secret, user.mfa_pending_secret, user.mfa_enabled = user.mfa_pending_secret, "", True
            user.save(update_fields=["mfa_secret", "mfa_pending_secret", "mfa_enabled"])
            codes = RecoveryCode.issue_for(user)

        record("auth.mfa_enabled", actor=user)
        response = session_response(request, user, used_mfa=True)
        response.data["recovery_codes"] = codes
        return response


class MFADisableView(APIView):
    def post(self, request):
        data = PasswordConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = request.user
        if user.is_firm_staff and settings.LEXDESK_REQUIRE_MFA_FOR_STAFF:
            return _refuse("Firm policy requires two-factor for staff.", code="mfa_required_by_policy", status_code=403)
        if not user.check_password(data.validated_data["password"]) or not mfa.verify_code(
            user, user.mfa_secret, data.validated_data["code"]
        ):
            return _refuse("Password or code incorrect.", code="invalid_credentials", status_code=400)

        user.mfa_enabled, user.mfa_secret = False, ""
        user.save(update_fields=["mfa_enabled", "mfa_secret"])
        user.recovery_codes.all().delete()
        record("auth.mfa_disabled", actor=user)
        return Response(status=204)


# --------------------------------------------------------------------------
# Team management (administrators)
# --------------------------------------------------------------------------


class TeamViewSet(viewsets.ModelViewSet):
    """
    Administrators add staff here. Creating someone does not set a password:
    LexDesk creates the account and emails them an activation link.
    """

    serializer_class = TeamMemberSerializer
    # Partners run the firm: they add, change and deactivate colleagues too.
    permission_classes = [IsAuthenticated, MFASatisfied, FirmActive, IsFirmManager]
    filterset_fields = ["role", "is_active"]
    search_fields = ["first_name", "last_name", "email", "title"]
    http_method_names = ["get", "post", "patch", "head", "options"]  # deactivate, never delete

    def get_queryset(self):
        if not self.request.user.firm_id:
            return User.objects.none()
        return User.objects.filter(firm_id=self.request.user.firm_id).exclude(role=Role.CLIENT)

    def perform_create(self, serializer):
        data = serializer.validated_data
        user, _ = provision_user(
            email=data["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=data["role"],
            phone=data.get("phone", ""),
            title=data.get("title", ""),
            firm=self.request.user.firm,
            invited_by=self.request.user,
        )
        if "hourly_rate" in data:
            user.hourly_rate = data["hourly_rate"]
            user.save(update_fields=["hourly_rate"])
        serializer.instance = user

    def perform_update(self, serializer):
        before = {"role": serializer.instance.role, "is_active": serializer.instance.is_active}
        user = serializer.save()
        changes = {k: [v, getattr(user, k)] for k, v in before.items() if getattr(user, k) != v}
        if changes:
            record("account.updated", actor=self.request.user, target=user, changes=changes)
        if changes.get("is_active") == [True, False]:
            # Deactivation is immediate: blacklist every outstanding session.
            from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

            for token in OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()):
                BlacklistedToken.objects.get_or_create(token=token)

    @action(detail=True, methods=["post"])
    def resend_invitation(self, request, pk=None):
        user = self.get_object()
        if user.has_usable_password():
            return _refuse("This person has already activated their account.", code="already_active", status_code=400)
        send_invitation(user, invited_by=request.user)
        return Response({"detail": "Invitation sent."})

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        user = self.get_object()
        user.clear_failed_logins()
        record("account.unlocked", actor=request.user, target=user)
        return Response({"detail": "Account unlocked."})

    @action(detail=True, methods=["post"])
    def reset_mfa(self, request, pk=None):
        """For the lawyer who lost their phone and their recovery codes."""
        user = self.get_object()
        user.mfa_enabled, user.mfa_secret, user.mfa_pending_secret = False, "", ""
        user.save(update_fields=["mfa_enabled", "mfa_secret", "mfa_pending_secret"])
        user.recovery_codes.all().delete()
        record("account.mfa_reset_by_admin", actor=request.user, target=user)
        notify(user, subject="Your two-factor was reset", body="An administrator reset two-factor on your account. "
               "You will be asked to set it up again at your next sign-in.", category=Category.SECURITY)
        return Response({"detail": "Two-factor reset."})
