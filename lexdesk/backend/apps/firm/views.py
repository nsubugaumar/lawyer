from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import FirmActive, HasRole, MFASatisfied
from apps.audit.services import record

from .serializers import SECRET_FIELDS, FirmSettingsSerializer, LogoSerializer, PublicFirmSerializer
from .tenancy import firm_for, public_firm

IsManager = HasRole.of(Role.ADMIN, Role.PARTNER)
LOGO_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def _own_firm(request):
    firm = request.user.firm
    if firm is None:
        raise Http404("You do not belong to a firm.")
    return firm


class FirmSettingsView(APIView):
    """The firm's control panel: profile, contacts, social media, hours, look, reminders, WhatsApp."""

    permission_classes = [IsAuthenticated, MFASatisfied, FirmActive, IsManager]

    def get(self, request):
        return Response(FirmSettingsSerializer(_own_firm(request), context={"request": request}).data)

    def patch(self, request):
        firm = _own_firm(request)
        serializer = FirmSettingsSerializer(firm, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        firm = serializer.save(updated_by=request.user)
        # Which fields changed is audited; secret values never are.
        record("firm.settings_changed", actor=request.user, target=firm, fields=sorted(request.data),
               secrets_changed=sorted(f for f in SECRET_FIELDS if request.data.get(f)))
        return Response(FirmSettingsSerializer(firm, context={"request": request}).data)


class FirmLogoView(APIView):
    parser_classes = [MultiPartParser]

    def get_permissions(self):
        return [AllowAny()] if getattr(self.request, "method", "GET") == "GET" else [IsAuthenticated(), MFASatisfied(), FirmActive(), IsManager()]

    def get_authenticators(self):
        return [] if getattr(self.request, "method", "GET") == "GET" else super().get_authenticators()

    def get(self, request):
        firm = public_firm(request)
        if not firm.logo:
            raise Http404
        extension = firm.logo.name.rsplit(".", 1)[-1].lower()
        with firm.logo.open("rb") as handle:
            response = HttpResponse(handle.read(), content_type=LOGO_TYPES.get(extension, "application/octet-stream"))
        response["Cache-Control"] = "public, max-age=86400"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def post(self, request):
        data = LogoSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["logo"]
        extension = {v: k for k, v in LOGO_TYPES.items()}[upload.detected_type]
        firm = _own_firm(request)
        if firm.logo:
            firm.logo.delete(save=False)
        firm.logo.save(f"{firm.slug}/logo.{extension}", ContentFile(upload.read()), save=False)
        firm.updated_by = request.user
        firm.save()
        record("firm.logo_changed", actor=request.user, target=firm)
        return Response(FirmSettingsSerializer(firm, context={"request": request}).data)

    def delete(self, request):
        firm = _own_firm(request)
        if firm.logo:
            firm.logo.delete(save=False)
            firm.logo = ""
            firm.save()
            record("firm.logo_removed", actor=request.user, target=firm)
        return Response(status=204)


class PublicFirmView(APIView):
    """
    Everything a firm's website needs, in one call. Signed in, it is your own
    firm; otherwise the firm at the address the visitor used.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        response = Response(PublicFirmSerializer(firm_for(request)).data)
        response["Cache-Control"] = "private, max-age=60"
        response["Vary"] = "Authorization, X-LexDesk-Firm, X-LexDesk-Host"
        return response


class TlsAskView(APIView):
    """
    Caddy asks here before getting an https certificate for a domain, so
    certificates are issued only for real firms: their own domain, or their
    sub-domain of the platform's base domain. Internal to the server.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        from django.conf import settings

        from .models import Firm

        domain = (request.query_params.get("domain") or "").lower().strip().rstrip(".")
        base = settings.LEXDESK_BASE_DOMAIN.lower()
        active = Firm.objects.filter(is_active=True)
        allowed = bool(domain) and (
            domain in {base, f"www.{base}", f"app.{base}"}
            or active.filter(domain__iexact=domain).exists()
            or active.filter(domain__iexact=domain.removeprefix("www.")).exists()
            or (base and domain.endswith(f".{base}") and active.filter(slug=domain[: -len(base) - 1]).exists())
        )
        return HttpResponse(status=200 if allowed else 404)
