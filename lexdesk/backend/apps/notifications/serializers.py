from django.utils import timezone
from rest_framework import serializers

from .channels import normalise_phone
from .models import (
    FORBIDDEN_CHANNELS,
    LOCKED_CHANNELS,
    MAX_OFFSET_MINUTES,
    Category,
    Channel,
    Delivery,
    Notification,
    NotificationPreference,
)


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        # The address is deliberately absent: the person knows their own.
        fields = ["channel", "status", "is_fallback", "sent_at", "delivered_at", "read_at"]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    deliveries = DeliverySerializer(many=True, read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "category", "title", "body", "link", "urgent", "read_at", "created_at", "deliveries"]
        read_only_fields = fields


def _offsets(value, label):
    if not isinstance(value, list) or len(value) > 6:
        raise serializers.ValidationError(f"Give up to six {label} reminder times.")
    cleaned = set()
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool) or not 5 <= item <= MAX_OFFSET_MINUTES:
            raise serializers.ValidationError("Each reminder must be between 5 minutes and 30 days before.")
        cleaned.add(item)
    return sorted(cleaned, reverse=True)


class PreferenceSerializer(serializers.ModelSerializer):
    whatsapp_enabled = serializers.BooleanField(write_only=True, required=False)
    whatsapp_active = serializers.BooleanField(read_only=True)
    whatsapp_number_in_use = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()

    class Meta:
        model = NotificationPreference
        fields = [
            "channels", "categories", "whatsapp_enabled", "whatsapp_active", "whatsapp_number", "whatsapp_number_in_use",
            "sms_fallback", "court_offsets", "appointment_offsets", "quiet_hours_start", "quiet_hours_end",
            "daily_agenda", "daily_agenda_at",
        ]

    def get_whatsapp_number_in_use(self, obj):
        return normalise_phone(obj.whatsapp_number or obj.user.phone)

    def get_categories(self, obj):
        """What the settings screen needs to draw its grid."""
        return [
            {
                "key": key,
                "label": label,
                "locked": sorted(LOCKED_CHANNELS.get(key, set())),
                "unavailable": sorted(FORBIDDEN_CHANNELS.get(key, set())),
            }
            for key, label in Category.choices
        ]

    def validate_channels(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected a mapping of category to channels.")
        cleaned = dict(self.instance.channels if self.instance else {})
        for category, channels in value.items():
            if category not in Category.values:
                raise serializers.ValidationError(f"Unknown category {category!r}.")
            if not isinstance(channels, list) or any(c not in Channel.values for c in channels):
                raise serializers.ValidationError(f"Unknown channel for {category}.")
            cleaned[category] = sorted(set(channels) - FORBIDDEN_CHANNELS.get(category, set()))
        return cleaned

    def validate_whatsapp_number(self, value):
        if value and not normalise_phone(value):
            raise serializers.ValidationError("That does not look like a phone number. Include the country code, e.g. +256 772 123456.")
        return normalise_phone(value) if value else ""

    def validate_court_offsets(self, value):
        return _offsets(value, "court")

    def validate_appointment_offsets(self, value):
        return _offsets(value, "appointment")

    def update(self, instance, validated_data):
        enabled = validated_data.pop("whatsapp_enabled", None)
        now = timezone.now()
        if enabled is True and not instance.whatsapp_active:
            # Switching it on in the app is the consent WhatsApp requires.
            instance.whatsapp_opted_in_at = now
            instance.whatsapp_opted_out_at = None
        elif enabled is False and instance.whatsapp_active:
            instance.whatsapp_opted_out_at = now
        return super().update(instance, validated_data)


class TestMessageSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=Channel.choices)
