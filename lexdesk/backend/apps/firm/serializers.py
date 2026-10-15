import re
import secrets

from rest_framework import serializers

from apps.core.urls_public import public_url
from apps.matters.models import PracticeArea
from apps.notifications.channels import normalise_phone
from apps.notifications.serializers import _offsets

from .models import Firm

SECRET_FIELDS = (
    "whatsapp_access_token", "whatsapp_app_secret", "whatsapp_verify_token",
    "at_api_key", "flutterwave_secret_key", "flutterwave_webhook_hash",
)

# Where a bare handle ("@kampalalaw") points on each network.
SOCIAL = {
    "facebook_url": ("Facebook", "https://www.facebook.com/{}", "facebook.com"),
    "instagram_url": ("Instagram", "https://www.instagram.com/{}", "instagram.com"),
    "x_url": ("X", "https://x.com/{}", ("x.com", "twitter.com")),
    "linkedin_url": ("LinkedIn", "https://www.linkedin.com/company/{}", "linkedin.com"),
    "youtube_url": ("YouTube", "https://www.youtube.com/@{}", ("youtube.com", "youtu.be")),
    "tiktok_url": ("TikTok", "https://www.tiktok.com/@{}", "tiktok.com"),
}


def _social(field, value):
    value = (value or "").strip()
    if not value:
        return ""
    label, template, domains = SOCIAL[field]
    if re.fullmatch(r"@?[A-Za-z0-9._-]{1,100}", value):
        return template.format(value.lstrip("@"))
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    value = value.replace("http://", "https://", 1)
    host = re.sub(r"^https://(www\.|m\.)?", "", value).split("/")[0].lower()
    domains = (domains,) if isinstance(domains, str) else domains
    if not any(host == d or host.endswith("." + d) for d in domains):
        raise serializers.ValidationError(f"That is not a {label} link. Paste the address of the firm's {label} page, or just the handle.")
    return value


def logo_url(firm):
    return f"/api/v1/firm/logo/?firm={firm.slug}&v={int(firm.updated_at.timestamp())}" if firm.logo else ""


class FirmSettingsSerializer(serializers.ModelSerializer):
    """For the managing partner and practice manager."""

    whatsapp_access_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    whatsapp_app_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    whatsapp_verify_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    at_api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    flutterwave_secret_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    flutterwave_webhook_hash = serializers.CharField(write_only=True, required=False, allow_blank=True)
    whatsapp_status = serializers.SerializerMethodField()
    sms_status = serializers.SerializerMethodField()
    payments_status = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    practice_area_choices = serializers.SerializerMethodField()
    theme_choices = serializers.SerializerMethodField()
    updated_by_name = serializers.CharField(source="updated_by.full_name", read_only=True, default=None)
    # Plain text, so a bare "@handle" reaches validate() and becomes a link.
    facebook_url = serializers.CharField(required=False, allow_blank=True)
    instagram_url = serializers.CharField(required=False, allow_blank=True)
    x_url = serializers.CharField(required=False, allow_blank=True)
    linkedin_url = serializers.CharField(required=False, allow_blank=True)
    youtube_url = serializers.CharField(required=False, allow_blank=True)
    tiktok_url = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Firm
        exclude = ["id", "logo", "updated_by", "is_active", "created_at"]
        # The platform sets these when the firm joins; case numbers depend on them.
        read_only_fields = ["updated_at", "slug", "code"]

    def get_logo_url(self, obj):
        return logo_url(obj)

    def get_practice_area_choices(self, obj):
        return [{"key": k, "label": label} for k, label in PracticeArea.choices]

    def get_theme_choices(self, obj):
        return [{"key": k, "label": label} for k, label in Firm.Theme.choices]

    def get_whatsapp_status(self, obj):
        request = self.context.get("request")
        webhook = public_url(request, f"/api/v1/notifications/whatsapp/webhook/{obj.slug}/") if request else ""
        return {
            "backend": obj.whatsapp_backend,
            "access_token_set": bool(obj.whatsapp("access_token")),
            "app_secret_set": bool(obj.whatsapp("app_secret")),
            "verify_token_set": bool(obj.whatsapp("verify_token")),
            "phone_number_id_set": bool(obj.whatsapp("phone_number_id")),
            "webhook_url": webhook,
            # Shown so the manager can paste it into Meta; it is not a key
            # that sends anything.
            "verify_token": obj.whatsapp("verify_token"),
        }

    def get_sms_status(self, obj):
        request = self.context.get("request")
        return {
            "backend": obj.sms_backend,
            "username_set": bool(obj.sms("username")),
            "api_key_set": bool(obj.sms("api_key")),
            "delivery_url": public_url(request, f"/api/v1/notifications/sms/delivery/{obj.slug}/") if request else "",
        }

    def get_payments_status(self, obj):
        request = self.context.get("request")
        return {
            "backend": obj.payments_backend,
            "secret_key_set": bool(obj.flutterwave_secret_key),
            "webhook_hash_set": bool(obj.flutterwave_webhook_hash),
            "webhook_url": public_url(request, f"/api/v1/billing/flutterwave/webhook/{obj.slug}/") if request else "",
        }

    def validate_at_sender_id(self, value):
        if value and not re.fullmatch(r"[A-Za-z0-9 ]{3,11}", value):
            raise serializers.ValidationError("Sender IDs are 3 to 11 letters or digits, as approved by Africa's Talking.")
        return value

    def validate_practice_areas(self, value):
        if not isinstance(value, list) or any(v not in PracticeArea.values for v in value):
            raise serializers.ValidationError("Choose from the listed practice areas.")
        return list(dict.fromkeys(value))

    def validate_domain(self, value):
        value = re.sub(r"^https?://", "", (value or "").strip().lower()).split("/")[0]
        if value and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", value):
            raise serializers.ValidationError("Enter a domain like www.yourfirm.co.ug")
        # Two firms on one address would let one firm's website show the other's.
        if value and Firm.objects.filter(domain__iexact=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("Another firm on LexDesk already uses that address.")
        return value

    def validate_testimonials(self, value):
        if not isinstance(value, list) or len(value) > 12:
            raise serializers.ValidationError("Add up to twelve testimonials.")
        cleaned = []
        for item in value:
            if not isinstance(item, dict) or not str(item.get("quote", "")).strip() or not str(item.get("name", "")).strip():
                raise serializers.ValidationError("Each testimonial needs the client's words and a name.")
            cleaned.append({
                "quote": str(item["quote"]).strip()[:600],
                "name": str(item["name"]).strip()[:80],
                "detail": str(item.get("detail", "")).strip()[:120],
            })
        return cleaned

    def validate_working_days(self, value):
        if not isinstance(value, list) or not value or any(not isinstance(d, int) or not 0 <= d <= 6 for d in value):
            raise serializers.ValidationError("Choose at least one working day.")
        return sorted(set(value))

    def validate_slot_minutes(self, value):
        if value not in (15, 20, 30, 45, 60, 90):
            raise serializers.ValidationError("Choose 15, 20, 30, 45, 60 or 90 minutes.")
        return value

    def validate_booking_days_ahead(self, value):
        if not 1 <= value <= 365:
            raise serializers.ValidationError("Between 1 and 365 days.")
        return value

    def validate_court_offsets(self, value):
        return _offsets(value, "court")

    def validate_appointment_offsets(self, value):
        return _offsets(value, "appointment")

    def _phone(self, value):
        if value and not normalise_phone(value):
            raise serializers.ValidationError("That does not look like a phone number.")
        return normalise_phone(value) if value else ""

    def validate_phone(self, value):
        return self._phone(value)

    def validate_whatsapp_number(self, value):
        return self._phone(value)

    def validate(self, attrs):
        for field in SOCIAL:
            if field in self.initial_data:
                try:
                    attrs[field] = _social(field, self.initial_data.get(field))
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError({field: exc.detail}) from None

        opens = attrs.get("office_opens", getattr(self.instance, "office_opens", None))
        closes = attrs.get("office_closes", getattr(self.instance, "office_closes", None))
        if opens and closes and closes <= opens:
            raise serializers.ValidationError({"office_closes": "Closing time must be after opening time."})

        mode = attrs.get("whatsapp_mode", getattr(self.instance, "whatsapp_mode", ""))
        if mode == Firm.WhatsAppMode.LIVE:
            def has(name):
                return bool(attrs.get(f"whatsapp_{name}") or (self.instance and self.instance.whatsapp(name)))
            missing = [label for name, label in (("phone_number_id", "Phone number ID"), ("access_token", "Access token"), ("app_secret", "App secret")) if not has(name)]
            if missing:
                raise serializers.ValidationError({"whatsapp_mode": f"To go live, add: {', '.join(missing)}."})
        sms_mode = attrs.get("sms_mode", getattr(self.instance, "sms_mode", ""))
        if sms_mode == Firm.WhatsAppMode.LIVE:
            def has_sms(name):
                return bool(attrs.get(f"at_{name}") or (self.instance and self.instance.sms(name)))
            if not (has_sms("username") and has_sms("api_key")):
                raise serializers.ValidationError({"sms_mode": "To go live, add your Africa's Talking username and API key."})
        pay_mode = attrs.get("payments_mode", getattr(self.instance, "payments_mode", ""))
        if pay_mode == Firm.WhatsAppMode.LIVE:
            has_key = attrs.get("flutterwave_secret_key") or (self.instance and self.instance.flutterwave_secret_key)
            has_hash = attrs.get("flutterwave_webhook_hash") or (self.instance and self.instance.flutterwave_webhook_hash)
            if not (has_key and has_hash):
                raise serializers.ValidationError({"payments_mode": "To go live, add your Flutterwave secret key and webhook secret hash."})
        return attrs

    def update(self, instance, validated_data):
        for field in SECRET_FIELDS:
            # A blank secret means "leave it as it is", so the form never has
            # to show (or resend) the stored value.
            if not validated_data.get(field):
                validated_data.pop(field, None)
        if validated_data.get("whatsapp_mode") == Firm.WhatsAppMode.LIVE and not instance.whatsapp("verify_token"):
            validated_data["whatsapp_verify_token"] = secrets.token_urlsafe(24)
        return super().update(instance, validated_data)


class PublicFirmSerializer(serializers.ModelSerializer):
    """What the website shows. Nothing private."""

    logo_url = serializers.SerializerMethodField()
    practice_areas = serializers.SerializerMethodField()
    socials = serializers.SerializerMethodField()
    whatsapp_link = serializers.SerializerMethodField()
    office_hours = serializers.SerializerMethodField()

    class Meta:
        model = Firm
        fields = [
            "slug", "name", "tagline", "about", "founded_year", "theme", "logo_url", "practice_areas", "testimonials",
            "phone", "whatsapp_number", "whatsapp_link", "email", "address", "map_url", "socials",
            "office_hours", "booking_enabled", "slot_minutes", "booking_days_ahead",
        ]

    def get_logo_url(self, obj):
        return logo_url(obj)

    def get_practice_areas(self, obj):
        labels = dict(PracticeArea.choices)
        return [{"key": k, "label": labels[k]} for k in obj.practice_areas if k in labels]

    def get_socials(self, obj):
        return [
            {"network": field.removesuffix("_url"), "label": label, "url": getattr(obj, field)}
            for field, (label, _, _) in SOCIAL.items()
            if getattr(obj, field)
        ]

    def get_whatsapp_link(self, obj):
        number = obj.whatsapp_number or obj.phone
        return f"https://wa.me/{number.lstrip('+')}" if number else ""

    def get_office_hours(self, obj):
        return {"opens": obj.office_opens.strftime("%H:%M"), "closes": obj.office_closes.strftime("%H:%M"), "days": obj.working_days}


class LogoSerializer(serializers.Serializer):
    logo = serializers.FileField()

    SIGNATURES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp"}

    def validate_logo(self, value):
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("The logo must be under 2 MB.")
        head = value.read(12)
        value.seek(0)
        for magic, kind in self.SIGNATURES.items():
            if head.startswith(magic) and (kind != "image/webp" or head[8:12] == b"WEBP"):
                value.detected_type = kind
                return value
        # SVG is refused on purpose: it can carry script.
        raise serializers.ValidationError("Upload a PNG, JPEG or WebP image.")
