from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from apps.audit.services import record
from apps.matters.models import PracticeArea

from .models import Authority


class AuthoritySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    added_by_name = serializers.CharField(source="added_by.full_name", read_only=True, default="")

    class Meta:
        model = Authority
        fields = [
            "id", "kind", "kind_display", "title", "citation", "court", "year", "practice_area", "summary", "key_points",
            "tags", "url", "document", "added_by_name", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_practice_area(self, value):
        if value and value not in PracticeArea.values:
            raise serializers.ValidationError("Choose a practice area from the list.")
        return value

    def validate_document(self, value):
        user = self.context["request"].user
        if value is not None and value.matter.firm_id != user.firm_id:
            raise serializers.ValidationError("That document is not in your firm.")
        return value


class AuthorityViewSet(viewsets.ModelViewSet):
    """The firm's research library. Staff only; each firm sees its own."""

    serializer_class = AuthoritySerializer
    filterset_fields = ["kind", "practice_area", "year"]
    search_fields = ["title", "citation", "court", "summary", "key_points", "tags"]
    ordering_fields = ["year", "title", "created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.is_client or not user.firm_id:
            return Authority.objects.none()
        return Authority.objects.filter(firm_id=user.firm_id).select_related("added_by")

    def _require_staff(self):
        if self.request.user.role in ("client", "receptionist", "accountant"):
            raise PermissionDenied("The library is kept by the lawyers.")

    def perform_create(self, serializer):
        self._require_staff()
        item = serializer.save(firm_id=self.request.user.firm_id, added_by=self.request.user)
        record("library.added", actor=self.request.user, target=item)

    def perform_update(self, serializer):
        self._require_staff()
        record("library.updated", actor=self.request.user, target=serializer.save())

    def perform_destroy(self, instance):
        self._require_staff()
        record("library.removed", actor=self.request.user, target=instance)
        instance.delete()
