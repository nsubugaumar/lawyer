from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel, ReferenceCounter


class PracticeArea(models.TextChoices):
    LITIGATION = "litigation", "Civil litigation"
    CRIMINAL = "criminal", "Criminal"
    CORPORATE = "corporate", "Corporate & commercial"
    LAND = "land", "Land & conveyancing"
    FAMILY = "family", "Family & succession"
    EMPLOYMENT = "employment", "Employment"
    IMMIGRATION = "immigration", "Immigration"
    TAX = "tax", "Tax"
    IP = "ip", "Intellectual property"
    OTHER = "other", "Other"


class Matter(BaseModel):
    """A case or piece of legal work. Everything else hangs off this."""

    class Status(models.TextChoices):
        INTAKE = "intake", "Intake"
        OPEN = "open", "Open"
        ON_HOLD = "on_hold", "On hold"
        CLOSED = "closed", "Closed"

    firm = models.ForeignKey("firm.Firm", null=True, on_delete=models.PROTECT, related_name="matters")
    reference = models.CharField(max_length=32, unique=True, editable=False)
    title = models.CharField(max_length=250, help_text="e.g. Okello v. Kampala Traders Ltd")
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="matters")
    practice_area = models.CharField(max_length=20, choices=PracticeArea.choices, default=PracticeArea.LITIGATION)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    description = models.TextField(blank=True)

    # Court details (blank for non-contentious work)
    court = models.CharField(max_length=200, blank=True, help_text="e.g. High Court (Commercial Division), Kampala")
    case_number = models.CharField(max_length=100, blank=True, db_index=True)
    judge = models.CharField(max_length=200, blank=True)
    opposing_counsel = models.CharField(max_length=200, blank=True)

    lead_lawyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="led_matters"
    )
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through="MatterMember", related_name="matters")

    # An ethical wall: when set, only the matter team can see this matter,
    # not even other partners. Used for conflicts, high-profile clients, and
    # matters involving firm staff.
    is_restricted = models.BooleanField(default=False)

    opened_on = models.DateField(default=timezone.localdate)
    closed_on = models.DateField(null=True, blank=True)
    hourly_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, help_text="Overrides each lawyer's default rate"
    )

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["status", "practice_area"])]

    def __str__(self):
        return f"{self.reference} · {self.title}"

    def save(self, *args, **kwargs):
        if not self.firm_id and self.client_id:
            self.firm_id = self.client.firm_id
        if not self.reference:
            # Each firm numbers its own files: NSC-2026-0001, KAA-2026-0001.
            prefix = self.firm.code if self.firm_id else "LD"
            self.reference = ReferenceCounter.next(prefix, timezone.localdate().year)
        super().save(*args, **kwargs)


class MatterMember(models.Model):
    class Role(models.TextChoices):
        LEAD = "lead", "Lead counsel"
        ASSOCIATE = "associate", "Associate"
        PARALEGAL = "paralegal", "Paralegal"
        SUPPORT = "support", "Support"

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matter_memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ASSOCIATE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("matter", "user")]


class Party(BaseModel):
    class Role(models.TextChoices):
        PLAINTIFF = "plaintiff", "Plaintiff / Applicant"
        DEFENDANT = "defendant", "Defendant / Respondent"
        OPPOSING = "opposing", "Opposing party"
        WITNESS = "witness", "Witness"
        EXPERT = "expert", "Expert"
        INTERESTED = "interested", "Interested party"

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="parties")
    name = models.CharField(max_length=200, db_index=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    represented_by = models.CharField(max_length=200, blank=True)
    contact = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        ordering = ["role", "name"]
        verbose_name_plural = "parties"

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"


class Task(BaseModel):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=250)
    details = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    due_on = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        ordering = ["status", "due_on", "-created_at"]

    def __str__(self):
        return self.title


class Note(BaseModel):
    """
    File notes: attendance notes, call notes, strategy. Often privileged, so
    the body is encrypted at rest. Clients only ever see notes explicitly
    shared with them.
    """

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    body = EncryptedTextField()
    shared_with_client = models.BooleanField(default=False)
    # Notes written for, or in, a particular hearing: preparation points,
    # what the judge said, what to do next. They appear in that hearing's
    # court brief and in the matter's file notes.
    court_event = models.ForeignKey("CourtEvent", null=True, blank=True, on_delete=models.SET_NULL, related_name="hearing_notes")

    def __str__(self):
        return f"Note on {self.matter.reference} by {self.author}"


class CourtEvent(BaseModel):
    """
    The court diary. A missed limitation date is the single most common cause
    of negligence claims against lawyers, so deadlines are first-class here.
    Everyone involved is told the moment a date is set or moved, and reminded
    at the times they chose (7 days, 1 day and 2 hours by default) by
    WhatsApp, email and in the app. See apps.notifications.reminders.
    """

    class Kind(models.TextChoices):
        HEARING = "hearing", "Hearing"
        MENTION = "mention", "Mention"
        TRIAL = "trial", "Trial"
        JUDGMENT = "judgment", "Judgment / ruling"
        FILING_DEADLINE = "filing_deadline", "Filing deadline"
        LIMITATION = "limitation", "Limitation date"
        MEDIATION = "mediation", "Mediation"
        OTHER = "other", "Other"

    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending"
        HELD = "held", "Held"
        ADJOURNED = "adjourned", "Adjourned"
        MET = "met", "Deadline met"
        VACATED = "vacated", "Vacated"

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.HEARING)
    title = models.CharField(max_length=250)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)
    location = models.CharField(max_length=250, blank=True, help_text="Court and room")
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="court_events")
    notes = models.TextField(blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.PENDING)
    outcome_notes = models.TextField(blank=True)
    next_event = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notify_client = models.BooleanField(default=False, help_text="Tell the client about this date and remind them too")

    class Meta(BaseModel.Meta):
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"

    @property
    def is_deadline(self):
        return self.kind in {self.Kind.FILING_DEADLINE, self.Kind.LIMITATION}
