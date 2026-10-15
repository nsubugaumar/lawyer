from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.matters.models import PracticeArea


class Appointment(BaseModel):
    class Mode(models.TextChoices):
        IN_PERSON = "in_person", "In person"
        VIDEO = "video", "Video call"
        PHONE = "phone", "Phone call"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No-show"

    # Statuses that occupy the lawyer's time.
    ACTIVE = (Status.REQUESTED, Status.CONFIRMED)

    firm = models.ForeignKey("firm.Firm", null=True, on_delete=models.PROTECT, related_name="appointments")
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="appointments")
    matter = models.ForeignKey("matters.Matter", null=True, blank=True, on_delete=models.SET_NULL, related_name="appointments")
    lawyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments")
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.IN_PERSON)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    practice_area = models.CharField(max_length=20, choices=PracticeArea.choices, blank=True)
    purpose = models.TextField(help_text="What the client would like to discuss")
    location = models.CharField(max_length=250, blank=True)
    video_link = models.URLField(blank=True)
    internal_notes = models.TextField(blank=True)
    booked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cancellation_reason = models.CharField(max_length=250, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["lawyer", "starts_at"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="appointment_ends_after_start"),
        ]

    def __str__(self):
        return f"{self.client} with {self.lawyer} at {self.starts_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if not self.firm_id and self.client_id:
            self.firm_id = self.client.firm_id
        super().save(*args, **kwargs)
