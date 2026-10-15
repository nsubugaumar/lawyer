from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel


class Client(BaseModel):
    class Kind(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        ORGANISATION = "organisation", "Organisation"

    class Status(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        ACTIVE = "active", "Active"
        FORMER = "former", "Former"

    class Engagement(models.TextChoices):
        RETAINER = "retainer", "On retainer"
        ONE_OFF = "one_off", "One-off service"

    class Source(models.TextChoices):
        WALK_IN = "walk_in", "Walk-in"
        WEBSITE = "website", "Website booking"
        REFERRAL = "referral", "Referral"
        PHONE = "phone", "Phone"
        OTHER = "other", "Other"

    firm = models.ForeignKey("firm.Firm", null=True, on_delete=models.PROTECT, related_name="clients")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INDIVIDUAL)
    name = models.CharField(max_length=200, db_index=True, help_text="Full name, or the organisation's registered name")
    contact_person = models.CharField(max_length=200, blank=True, help_text="For organisations")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)

    # Identity numbers are exactly what an identity thief wants from a leaked
    # backup, so they are encrypted at rest.
    national_id = EncryptedTextField(blank=True, help_text="National ID / passport / company registration number")
    notes = EncryptedTextField(blank=True, help_text="Private intake notes. Encrypted.")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROSPECT)
    # On retainer: an ongoing relationship with a regular fee. One-off: the
    # client came for a particular service and leaves when it is done.
    engagement = models.CharField(max_length=20, choices=Engagement.choices, default=Engagement.ONE_OFF, db_index=True)
    retainer_fee = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, help_text="Per month")
    retainer_start = models.DateField(null=True, blank=True)
    retainer_end = models.DateField(null=True, blank=True, help_text="Leave blank if open-ended")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.WALK_IN)
    responsible_lawyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="responsible_for_clients"
    )
    portal_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="client_profile"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta(BaseModel.Meta):
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def first_name(self):
        source = self.contact_person if self.kind == self.Kind.ORGANISATION and self.contact_person else self.name
        return source.split(" ")[0]

    @property
    def last_name(self):
        source = self.contact_person if self.kind == self.Kind.ORGANISATION and self.contact_person else self.name
        return " ".join(source.split(" ")[1:])
