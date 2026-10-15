from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import FirmActive, HasRole, MFASatisfied

from .models import AuditEvent
from .serializers import AuditEventSerializer
from .services import verify_chain


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """The firm's audit trail. Read-only, for administrators and partners."""

    serializer_class = AuditEventSerializer
    permission_classes = [MFASatisfied, FirmActive, HasRole.of(Role.ADMIN, Role.PARTNER)]
    filterset_fields = ["action", "actor_email", "target_type", "target_id", "matter_id"]
    search_fields = ["action", "actor_email", "target_id"]

    def get_queryset(self):
        return AuditEvent.objects.filter(firm_id=str(self.request.user.firm_id or "-"))

    @action(detail=False, methods=["get"])
    def verify(self, request):
        ok, broken_at, checked = verify_chain()
        return Response({"intact": ok, "broken_at": broken_at, "events_checked": checked})
