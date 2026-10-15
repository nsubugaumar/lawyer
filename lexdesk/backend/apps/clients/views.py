from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.models import MANAGES_CLIENTS
from apps.accounts.permissions import ClientDataPermission, FirmActive, MFASatisfied
from apps.audit.services import record

from .models import Client
from .serializers import ClientPortalSerializer, ClientSerializer
from .services import conflict_search, ensure_portal_account


class ClientViewSet(viewsets.ModelViewSet):
    permission_classes = [MFASatisfied, FirmActive, ClientDataPermission]
    filterset_fields = ["status", "kind", "source", "responsible_lawyer", "engagement"]
    search_fields = ["name", "contact_person", "email", "phone"]
    ordering_fields = ["name", "created_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]  # client records are never hard-deleted

    def get_queryset(self):
        user = self.request.user
        qs = Client.objects.filter(firm_id=user.firm_id).select_related("responsible_lawyer") if user.firm_id else Client.objects.none()
        if user.is_client:
            return qs.filter(portal_user=user)
        if user.role in MANAGES_CLIENTS or user.role == "accountant":
            return qs
        return qs.none()

    def get_serializer_class(self):
        return ClientPortalSerializer if getattr(self.request.user, "is_client", False) else ClientSerializer

    def retrieve(self, request, *args, **kwargs):
        client = self.get_object()
        if not request.user.is_client:
            # Opening a client file reveals encrypted personal data, so it is logged.
            record("client.viewed", actor=request.user, target=client)
        return Response(self.get_serializer(client).data)

    def perform_create(self, serializer):
        create_portal = serializer.validated_data.pop("create_portal_account", True)
        lawyer = serializer.validated_data.get("responsible_lawyer")
        if lawyer is not None and lawyer.firm_id != self.request.user.firm_id:
            raise PermissionDenied("Choose a lawyer from your own firm.")
        client = serializer.save(created_by=self.request.user, firm_id=self.request.user.firm_id)
        record("client.created", actor=self.request.user, target=client)
        if create_portal:
            ensure_portal_account(client, invited_by=self.request.user)

    def perform_update(self, serializer):
        serializer.validated_data.pop("create_portal_account", None)
        lawyer = serializer.validated_data.get("responsible_lawyer")
        if lawyer is not None and lawyer.firm_id != self.request.user.firm_id:
            raise PermissionDenied("Choose a lawyer from your own firm.")
        client = serializer.save()
        record("client.updated", actor=self.request.user, target=client, fields=sorted(serializer.validated_data))

    @action(detail=True, methods=["post"])
    def grant_portal_access(self, request, pk=None):
        if request.user.is_client:
            raise PermissionDenied()
        client = self.get_object()
        if not client.email:
            return Response({"error": {"code": "no_email", "message": "Add the client's email address first."}}, status=400)
        user = ensure_portal_account(client, invited_by=request.user)
        if user is None:
            return Response(
                {"error": {"code": "staff_email", "message": "That email belongs to a member of staff."}}, status=400
            )
        return Response({"detail": "Portal access granted. The client has been emailed an activation link."})

    @action(detail=False, methods=["get"], url_path="conflict-check")
    def conflict_check(self, request):
        if request.user.is_client:
            raise PermissionDenied()
        term = request.query_params.get("q", "")
        hits = conflict_search(term, self.request.user.firm)
        record("client.conflict_check", actor=request.user, term=term, hits=len(hits))
        return Response({"query": term, "clear": not hits, "hits": hits})
