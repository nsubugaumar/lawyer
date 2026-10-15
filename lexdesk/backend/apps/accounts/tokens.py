"""
How sessions are handed out.

The web app and the mobile app get the same tokens, delivered differently:

* Web: the refresh token goes into an HttpOnly, Secure, SameSite=Strict
  cookie scoped to /api/v1/auth/. Browser JavaScript can never read it, so an
  XSS bug cannot steal a long-lived session. The 10-minute access token lives
  only in memory.
* Mobile: there is no cookie jar worth trusting, so the refresh token is
  returned in the body and the app keeps it in the OS keychain/keystore
  (expo-secure-store).

The mobile app identifies itself with the header `X-LexDesk-Client: mobile`.
"""

from django.conf import settings
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer

MOBILE_HEADER = "HTTP_X_LEXDESK_CLIENT"


def is_mobile(request) -> bool:
    return request.META.get(MOBILE_HEADER, "").lower() == "mobile"


def mfa_setup_required(user, used_mfa: bool) -> bool:
    return settings.LEXDESK_REQUIRE_MFA_FOR_STAFF and user.is_firm_staff and not used_mfa


def build_refresh(user, *, used_mfa: bool) -> RefreshToken:
    refresh = RefreshToken.for_user(user)
    # Claims on the refresh token are copied to every access token minted
    # from it, so these survive refreshes.
    refresh["role"] = user.role
    refresh["mfa"] = used_mfa
    return refresh


def session_response(request, user, *, used_mfa: bool, status=200) -> Response:
    refresh = build_refresh(user, used_mfa=used_mfa)
    return token_response(request, refresh, user=user, status=status)


def token_response(request, refresh, *, user=None, status=200) -> Response:
    body = {"access": str(refresh.access_token)}
    if user is not None:
        body["user"] = UserSerializer(user).data
        body["mfa_setup_required"] = mfa_setup_required(user, bool(refresh.get("mfa")))
    if is_mobile(request):
        body["refresh"] = str(refresh)

    response = Response(body, status=status)
    if not is_mobile(request):
        set_refresh_cookie(response, str(refresh))
    return response


def set_refresh_cookie(response, value: str):
    response.set_cookie(
        settings.LEXDESK_REFRESH_COOKIE,
        value,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Strict",
        path=settings.LEXDESK_REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(settings.LEXDESK_REFRESH_COOKIE, path=settings.LEXDESK_REFRESH_COOKIE_PATH, samesite="Strict")


def refresh_from_request(request) -> str | None:
    return request.data.get("refresh") or request.COOKIES.get(settings.LEXDESK_REFRESH_COOKIE)
