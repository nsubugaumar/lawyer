from datetime import time

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from apps.core.fields import EncryptedTextField


def default_working_days():
    return [0, 1, 2, 3, 4]  # Monday to Friday


def default_practice_areas():
    return ["litigation", "corporate", "land", "family", "employment", "criminal"]


def default_court_offsets():
    return [7 * 24 * 60, 24 * 60, 120]


def default_appointment_offsets():
    return [24 * 60, 60]


class Firm(models.Model):
    """
    A law firm on LexDesk, and the wall around its data.

    Every person, client, matter, appointment and audit record belongs to
    exactly one firm, and every query starts from the signed-in person's firm.
    Hearings, documents, notes, tasks and invoices hang off a matter, so they
    inherit its firm. Nobody at one firm can see anything of another.

    It also holds everything the firm's partners can change without a
    developer: who the firm is, how to reach it, its social media, office
    hours, look, and how it reminds people.
    """

    class Theme(models.TextChoices):
        NAVY_BRASS = "navy_brass", "Navy & brass"
        ROYAL_IVORY = "royal_ivory", "Royal blue & ivory"
        OXFORD_BURGUNDY = "oxford_burgundy", "Oxford blue & burgundy"
        SLATE_SKY = "slate_sky", "Slate & sky blue"

    class WhatsAppMode(models.TextChoices):
        OFF = "off", "Off"
        TEST = "test", "Test mode (messages are logged, not sent)"
        LIVE = "live", "Live (WhatsApp Business)"

    # Identity on the platform
    slug = models.SlugField(max_length=60, unique=True, help_text="Web address name, e.g. namubiru-ssempala")
    code = models.CharField(
        max_length=6, unique=True,
        validators=[RegexValidator(r"^[A-Z]{2,6}$", "Two to six capital letters, e.g. NSC.")],
        help_text="Starts every case and invoice number, e.g. NSC-2026-0001",
    )
    domain = models.CharField(max_length=200, blank=True, help_text="The firm's own website domain, if any, e.g. www.nsc-advocates.co.ug")
    is_active = models.BooleanField(default=True, help_text="A suspended firm cannot sign in")
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    # Who we are
    name = models.CharField(max_length=150)
    tagline = models.CharField(max_length=200, blank=True, default="Trusted counsel. Clear answers. Every step of the way.")
    about = models.TextField(blank=True)
    founded_year = models.PositiveSmallIntegerField(null=True, blank=True)
    logo = models.FileField(upload_to="firm/", blank=True)
    theme = models.CharField(max_length=30, choices=Theme.choices, default=Theme.NAVY_BRASS)
    practice_areas = models.JSONField(default=default_practice_areas, blank=True)
    # Real words from real clients, added by the manager with their consent.
    # The website shows the section only when there is at least one.
    testimonials = models.JSONField(default=list, blank=True, help_text='[{"quote", "name", "detail"}]')

    # How to reach us
    phone = models.CharField(max_length=32, blank=True)
    whatsapp_number = models.CharField(max_length=32, blank=True, help_text="The number clients can chat with on WhatsApp")
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    map_url = models.URLField(blank=True, help_text="Google Maps link to the office")

    # Social media
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)

    # Office hours and booking
    office_opens = models.TimeField(default=time(8, 30))
    office_closes = models.TimeField(default=time(17, 30))
    working_days = models.JSONField(default=default_working_days)
    slot_minutes = models.PositiveSmallIntegerField(default=30)
    booking_enabled = models.BooleanField(default=True, help_text="Let the public book consultations on the website")
    booking_days_ahead = models.PositiveSmallIntegerField(default=90)

    # Notification defaults for new people (each person can change their own)
    court_offsets = models.JSONField(default=default_court_offsets)
    appointment_offsets = models.JSONField(default=default_appointment_offsets)
    quiet_hours_start = models.TimeField(null=True, blank=True, default=time(21, 0))
    quiet_hours_end = models.TimeField(null=True, blank=True, default=time(7, 0))
    daily_agenda_at = models.TimeField(default=time(6, 30))
    staff_whatsapp_default = models.BooleanField(default=True, help_text="Staff get WhatsApp reminders from day one")

    # WhatsApp Business connection. Secrets are encrypted at rest and never
    # sent back to the browser.
    whatsapp_mode = models.CharField(max_length=10, choices=WhatsAppMode.choices, blank=True, help_text="Blank: use the server setting")
    whatsapp_phone_number_id = models.CharField(max_length=64, blank=True)
    whatsapp_access_token = EncryptedTextField(blank=True)
    whatsapp_app_secret = EncryptedTextField(blank=True)
    whatsapp_verify_token = EncryptedTextField(blank=True)
    whatsapp_template = models.CharField(max_length=100, blank=True, default="lexdesk_notice")
    whatsapp_template_language = models.CharField(max_length=10, blank=True, default="en")
    whatsapp_template_has_button = models.BooleanField(default=False)

    # SMS through Africa's Talking (the firm's own account and sender ID).
    sms_mode = models.CharField(max_length=10, choices=WhatsAppMode.choices, blank=True, help_text="Blank: use the server setting")
    at_username = models.CharField(max_length=100, blank=True, help_text="Africa's Talking username ('sandbox' to test)")
    at_api_key = EncryptedTextField(blank=True)
    at_sender_id = models.CharField(max_length=11, blank=True, help_text="Approved sender name, e.g. NSCADVOC")

    # Online payments (Mobile Money and cards) through Flutterwave.
    payments_mode = models.CharField(max_length=10, choices=WhatsAppMode.choices, blank=True, help_text="Off, test, or live")
    flutterwave_public_key = models.CharField(max_length=120, blank=True)
    flutterwave_secret_key = EncryptedTextField(blank=True)
    flutterwave_webhook_hash = EncryptedTextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def of(cls, user) -> "Firm":
        """
        The firm a person belongs to. Platform operators belong to none; they
        get an unsaved stand-in carrying the server's defaults, so code that
        sends them a message still knows what to call itself.
        """
        firm = getattr(user, "firm", None)
        return firm if firm is not None else cls.platform_default()

    @classmethod
    def platform_default(cls) -> "Firm":
        return cls(
            name=settings.LEXDESK_FIRM_NAME,
            office_opens=time.fromisoformat(settings.LEXDESK_OFFICE_OPENS),
            office_closes=time.fromisoformat(settings.LEXDESK_OFFICE_CLOSES),
            slot_minutes=settings.LEXDESK_SLOT_MINUTES,
            staff_whatsapp_default=settings.LEXDESK_WHATSAPP_STAFF_OPTED_IN,
        )

    # ---- effective WhatsApp configuration (firm settings, else server) ------

    @property
    def whatsapp_backend(self) -> str:
        """"off", "console" or "meta"."""
        return {"off": "off", "test": "console", "live": "meta"}.get(self.whatsapp_mode, settings.LEXDESK_WHATSAPP_BACKEND)

    def whatsapp(self, name: str) -> str:
        """A WhatsApp credential: the one saved here, else the server's."""
        env = {
            "phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID,
            "access_token": settings.WHATSAPP_ACCESS_TOKEN,
            "app_secret": settings.WHATSAPP_APP_SECRET,
            "verify_token": settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
            "template": settings.LEXDESK_WHATSAPP_TEMPLATE,
            "template_language": settings.LEXDESK_WHATSAPP_TEMPLATE_LANGUAGE,
        }[name]
        return getattr(self, f"whatsapp_{name}") or env

    @property
    def sms_backend(self) -> str:
        """"off", "console" or "africastalking"."""
        return {"off": "off", "test": "console", "live": "africastalking"}.get(self.sms_mode, settings.LEXDESK_SMS_BACKEND)

    def sms(self, name: str) -> str:
        env = {
            "username": settings.AFRICASTALKING_USERNAME,
            "api_key": settings.AFRICASTALKING_API_KEY,
            "sender_id": settings.AFRICASTALKING_SENDER_ID,
        }[name]
        return getattr(self, f"at_{name}") or env

    @property
    def payments_backend(self) -> str:
        """"off", "test" (simulated checkout) or "flutterwave"."""
        return {"off": "off", "test": "test", "live": "flutterwave"}.get(self.payments_mode, "off")

    @property
    def whatsapp_has_button(self) -> bool:
        return self.whatsapp_template_has_button or settings.LEXDESK_WHATSAPP_TEMPLATE_HAS_BUTTON
