import uuid

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel


def vault_path(instance, filename):
    # The stored name says nothing about the file: no client name, no title,
    # no extension. Someone browsing the bucket learns nothing.
    return f"vault/{instance.document_id.hex[:2]}/{uuid.uuid4().hex}"


class Document(BaseModel):
    class Category(models.TextChoices):
        PLEADING = "pleading", "Pleading"
        EVIDENCE = "evidence", "Evidence / exhibit"
        AUTHORITY = "authority", "Legal authority"
        CORRESPONDENCE = "correspondence", "Correspondence"
        CONTRACT = "contract", "Contract / agreement"
        COURT_ORDER = "court_order", "Court order / judgment"
        CLIENT_UPLOAD = "client_upload", "From client"
        INTERNAL = "internal", "Internal memo"
        OTHER = "other", "Other"

    matter = models.ForeignKey("matters.Matter", on_delete=models.PROTECT, related_name="documents")
    title = models.CharField(max_length=250)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER, db_index=True)
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=250, blank=True, help_text="Comma separated")
    shared_with_client = models.BooleanField(default=False)
    court_bundle = models.BooleanField(
        default=False, help_text="Include in the offline Courtroom Mode bundle on lawyers' phones and tablets"
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    current_version = models.PositiveIntegerField(default=0)
    is_archived = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["matter", "category"]), models.Index(fields=["matter", "court_bundle"])]

    def __str__(self):
        return self.title

    @property
    def latest(self):
        return self.versions.filter(number=self.current_version).first()


class DocumentVersion(BaseModel):
    """
    One immutable upload. New edits create a new version; old ones stay, so
    you can always show the court exactly what was filed on a given day.
    """

    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    blob = models.FileField(upload_to=vault_path, max_length=200)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField(help_text="Plaintext size in bytes")
    sha256 = models.CharField(max_length=64, help_text="Fingerprint of the original file, for integrity checks")
    wrapped_key = models.BinaryField()
    key_id = models.CharField(max_length=32)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    comment = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["document", "number"], name="unique_version_number")]

    def __str__(self):
        return f"{self.document.title} v{self.number}"

    @property
    def associated_data(self) -> bytes:
        # Binds the ciphertext to this exact database row.
        return f"lexdesk:docver:{self.pk}".encode()


class DocumentSearchToken(models.Model):
    """One keyed fingerprint of one word in a document. See search.py."""

    id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="search_tokens")
    token = models.CharField(max_length=32, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["token", "document"])]


class DocumentTemplate(BaseModel):
    """
    A firm's standard letter or pleading. Placeholders such as
    {{client.name}} are filled from the matter when a draft is made.
    """

    firm = models.ForeignKey("firm.Firm", on_delete=models.CASCADE, related_name="document_templates")
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=Document.Category.choices, default=Document.Category.CORRESPONDENCE)
    description = models.CharField(max_length=250, blank=True)
    body = models.TextField(help_text="Plain text. Blank lines separate paragraphs; **text** on its own line is bold.")
    letterhead = models.BooleanField(default=True, help_text="Start with the firm's name, address and contacts")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(BaseModel.Meta):
        ordering = ["name"]

    def __str__(self):
        return self.name


class SignatureRequest(BaseModel):
    """
    A client asked to sign a document electronically (an engagement letter,
    a settlement). The signature binds to the exact version's SHA-256, so
    changing the document afterwards cannot carry the signature with it.
    Recognised under Uganda's Electronic Signatures Act, 2011.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for signature"
        SIGNED = "signed", "Signed"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="signature_requests")
    version_number = models.PositiveIntegerField()
    document_sha256 = models.CharField(max_length=64)
    signer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="signature_requests")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    message = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    signed_at = models.DateTimeField(null=True, blank=True)
    signer_name = models.CharField(max_length=200, blank=True, help_text="Full name as typed by the signer")
    signature_image = EncryptedTextField(blank=True, help_text="The drawn signature (PNG data URL), encrypted")
    signature_sha256 = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)
    decline_reason = models.CharField(max_length=500, blank=True)
    certificate = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta(BaseModel.Meta):
        indexes = [models.Index(fields=["signer", "status"])]

    def __str__(self):
        return f"Signature on {self.document} by {self.signer}"
