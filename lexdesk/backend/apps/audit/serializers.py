from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id", "at", "actor_email", "action", "target_type", "target_id",
            "matter_id", "ip_address", "user_agent", "details", "hash",
        ]
        read_only_fields = fields
