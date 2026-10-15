import hashlib
import secrets
from datetime import time

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel


class Category(models.TextChoices):
    DIARY = "diary", "Court dates & deadlines"
    APPOINTMENT = "appointment", "Appointments"
    MESSAGES = "messages", "Messages from clients & lawyers"
    AGENDA = "agenda", "Daily agenda"
    BILLING = "billing", "Invoices & payments"
    SECURITY = "security", "Account & security"
    GENERAL = "general", "Other updates"


class Channel(models.TextChoices):
    IN_APP = "in_app", "In the app"
    EMAIL = "email", "Email"
    WHATSAPP = "whatsapp", "WhatsApp"
    SMS = "sms", "SMS"


# What each person gets unless they change it. Court dates and appointments
# go everywhere: a missed hearing costs far more than one message too many.
DEFAULT_CHANNELS = {
    Category.DIARY: [Channel.IN_APP, Channel.EMAIL, Channel.WHATSAPP],
    Category.APPOINTMENT: [Channel.IN_APP, Channel.EMAIL, Channel.WHATSAPP],
    Category.MESSAGES: [Channel.IN_APP, Channel.EMAIL, Channel.WHATSAPP],
    Category.AGENDA: [Channel.EMAIL, Channel.WHATSAPP],
    Category.BILLING: [Channel.IN_APP, Channel.EMAIL],
    Category.SECURITY: [Channel.IN_APP, Channel.EMAIL],
    Category.GENERAL: [Channel.IN_APP, Channel.EMAIL],
}

# Security mail (password resets, new sign-ins) always arrives by email,
# whatever the preferences say, and never travels over WhatsApp: a reset link
# in a chat history is a reset link on every linked device.
LOCKED_CHANNELS = {Category.SECURITY: {Channel.EMAIL}}
FORBIDDEN_CHANNELS = {Category.SECURITY: {Channel.WHATSAPP}}

# Minutes before the event. 7 days, 1 day, 2 hours for court; 1 day and
# 1 hour for appointments.
DEFAULT_COURT_OFFSETS = [7 * 24 * 60, 24 * 60, 120]
DEFAULT_APPOINTMENT_OFFSETS = [24 * 60, 60]
MAX_OFFSET_MINUTES = 30 * 24 * 60


def default_channels():
    return {category: list(channels) for category, channels in DEFAULT_CHANNELS.items()}


def default_court_offsets():
    return list(DEFAULT_COURT_OFFSETS)


def default_appointment_offsets():
    return list(DEFAULT_APPOINTMENT_OFFSETS)


class Notification(BaseModel):
    """
    One thing we told one person. The bell icon lists the ones marked
    `in_app`; every message, shown in the bell or not, keeps a delivery
    record per channel so the firm can prove a hearing reminder went out.
    """

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL, db_index=True)
    title = models.CharField(max_length=200)
    # Encrypted: bodies carry hearing details, client names and, for security
    # mail, single-use links.
    body = EncryptedTextField(blank=True)
    short_text = models.CharField(max_length=320, blank=True, help_text="SMS / WhatsApp version of the message")
    link = models.CharField(max_length=300, blank=True, help_text="In-app route, e.g. /matters/<id>")
    in_app = models.BooleanField(default=True)
    urgent = models.BooleanField(default=False, help_text="Ignores quiet hours")
    # "court_event:<uuid>" or "appointment:<uuid>": email attaches an
    # up-to-date calendar invitation for it.
    calendar_ref = models.CharField(max_length=80, blank=True)
    calendar_cancelled = models.BooleanField(default=False)
    dedupe_key = models.CharField(max_length=200, blank=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["recipient", "in_app", "read_at"])]

    def __str__(self):
        return self.title


class NotificationPreference(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preference")
    channels = models.JSONField(default=default_channels, help_text="Category -> list of channels")

    whatsapp_number = models.CharField(max_length=32, blank=True, help_text="Leave blank to use the account's phone number")
    # WhatsApp only allows business messages to people who agreed to them.
    whatsapp_opted_in_at = models.DateTimeField(null=True, blank=True)
    whatsapp_opted_out_at = models.DateTimeField(null=True, blank=True)
    sms_fallback = models.BooleanField(default=True, help_text="Send an SMS when WhatsApp cannot be delivered")

    court_offsets = models.JSONField(default=default_court_offsets, help_text="Minutes before a court date")
    appointment_offsets = models.JSONField(default=default_appointment_offsets, help_text="Minutes before an appointment")

    quiet_hours_start = models.TimeField(null=True, blank=True, default=time(21, 0))
    quiet_hours_end = models.TimeField(null=True, blank=True, default=time(7, 0))

    daily_agenda = models.BooleanField(default=True)
    daily_agenda_at = models.TimeField(default=time(6, 30))
    last_agenda_on = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Notification preferences for {self.user}"

    @property
    def whatsapp_active(self):
        return bool(self.whatsapp_opted_in_at) and not (
            self.whatsapp_opted_out_at and self.whatsapp_opted_out_at >= self.whatsapp_opted_in_at
        )

    def channels_for(self, category) -> set[str]:
        chosen = set(self.channels.get(category, DEFAULT_CHANNELS.get(category, [Channel.IN_APP])))
        chosen |= LOCKED_CHANNELS.get(category, set())
        chosen -= FORBIDDEN_CHANNELS.get(category, set())
        return chosen

    def in_quiet_hours(self, local_time) -> bool:
        start, end = self.quiet_hours_start, self.quiet_hours_end
        if start is None or end is None or start == end:
            return False
        if start < end:
            return start <= local_time < end
        return local_time >= start or local_time < end  # spans midnight


class Delivery(BaseModel):
    """One attempt to get one notification through one channel."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    FINAL = (Status.DELIVERED, Status.READ, Status.FAILED, Status.SKIPPED)
    MAX_ATTEMPTS = 5

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(max_length=20, choices=Channel.choices)
    address = models.CharField(max_length=254, blank=True, help_text="Email address or phone number")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    provider_message_id = models.CharField(max_length=200, blank=True, db_index=True)
    last_error = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    is_fallback = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        verbose_name_plural = "deliveries"
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    def __str__(self):
        return f"{self.get_channel_display()} · {self.get_status_display()}"


class ScheduledReminder(BaseModel):
    """
    A reminder booked for an exact moment. Rows are rewritten whenever the
    court date or appointment changes, so moving a hearing moves its
    reminders, and vacating it cancels them.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        CANCELLED = "cancelled", "Cancelled"
        SKIPPED = "skipped", "Skipped (too late)"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scheduled_reminders")
    court_event = models.ForeignKey("matters.CourtEvent", null=True, blank=True, on_delete=models.CASCADE, related_name="scheduled_reminders")
    appointment = models.ForeignKey("appointments.Appointment", null=True, blank=True, on_delete=models.CASCADE, related_name="scheduled_reminders")
    offset_minutes = models.PositiveIntegerField()
    send_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ["send_at"]
        indexes = [models.Index(fields=["status", "send_at"])]
        constraints = [
            models.UniqueConstraint(fields=["recipient", "court_event", "offset_minutes"], condition=models.Q(court_event__isnull=False), name="one_reminder_per_court_offset"),
            models.UniqueConstraint(fields=["recipient", "appointment", "offset_minutes"], condition=models.Q(appointment__isnull=False), name="one_reminder_per_appointment_offset"),
            models.CheckConstraint(
                condition=models.Q(court_event__isnull=False, appointment__isnull=True) | models.Q(court_event__isnull=True, appointment__isnull=False),
                name="reminder_has_exactly_one_subject",
            ),
        ]

    def __str__(self):
        return f"Reminder for {self.recipient} at {self.send_at:%Y-%m-%d %H:%M}"


class CalendarFeed(models.Model):
    """
    A private calendar subscription URL (Google, Apple, Outlook). Only a hash
    of the token is stored; the URL is shown once, and can be revoked.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_feed")
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def issue_for(cls, user) -> str:
        token = secrets.token_urlsafe(32)
        cls.objects.update_or_create(user=user, defaults={"token_hash": cls.hash(token), "last_used_at": None})
        return token
