from rest_framework import serializers

from apps.matters.models import PracticeArea
from apps.matters.serializers import PersonSerializer

from .models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    lawyer_detail = PersonSerializer(source="lawyer", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    mode_display = serializers.CharField(source="get_mode_display", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id", "client", "client_name", "matter", "lawyer", "lawyer_detail", "starts_at", "ends_at",
            "mode", "mode_display", "status", "status_display", "practice_area", "purpose", "location",
            "video_link", "internal_notes", "cancellation_reason", "created_at",
        ]
        read_only_fields = ["id", "status", "cancellation_reason", "created_at"]


class ClientAppointmentSerializer(AppointmentSerializer):
    """Clients book for themselves and never see the firm's internal notes."""

    class Meta(AppointmentSerializer.Meta):
        fields = [f for f in AppointmentSerializer.Meta.fields if f not in {"internal_notes", "client", "matter"}]
        read_only_fields = AppointmentSerializer.Meta.read_only_fields + ["location", "video_link"]


class PublicBookingSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32)
    lawyer = serializers.UUIDField()
    starts_at = serializers.DateTimeField()
    mode = serializers.ChoiceField(choices=Appointment.Mode.choices, default=Appointment.Mode.IN_PERSON)
    practice_area = serializers.ChoiceField(choices=PracticeArea.choices, required=False, allow_blank=True)
    purpose = serializers.CharField(max_length=2000)
    whatsapp_opt_in = serializers.BooleanField(default=False, help_text="Send me reminders on WhatsApp")
    # A field humans never see. Bots fill in every field they find.
    website = serializers.CharField(required=False, allow_blank=True)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=250, required=False, allow_blank=True)
