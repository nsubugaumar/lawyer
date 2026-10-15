from rest_framework import serializers

from .models import Client


class ClientSerializer(serializers.ModelSerializer):
    has_portal_access = serializers.SerializerMethodField()
    responsible_lawyer_name = serializers.CharField(source="responsible_lawyer.full_name", read_only=True, default=None)
    create_portal_account = serializers.BooleanField(
        write_only=True, default=True, help_text="Automatically create the client's portal login and send an activation link."
    )

    class Meta:
        model = Client
        fields = [
            "id", "kind", "name", "contact_person", "email", "phone", "address", "national_id", "notes",
            "status", "source", "engagement", "retainer_fee", "retainer_start", "retainer_end",
            "responsible_lawyer", "responsible_lawyer_name", "has_portal_access",
            "create_portal_account", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_has_portal_access(self, obj):
        return bool(obj.portal_user_id)


class ClientPortalSerializer(serializers.ModelSerializer):
    """What a client sees of their own record: never the firm's private notes."""

    class Meta:
        model = Client
        fields = ["id", "kind", "name", "contact_person", "email", "phone", "address", "status"]
        read_only_fields = ["id", "status"]
