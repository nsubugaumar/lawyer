from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel


class Message(BaseModel):
    """
    One message in a matter's conversation between the client and the
    lawyers on the matter. Privileged, so it is encrypted at rest and
    readable only by the client and the matter team (partners included only
    when they are on the team). It is part of the file, so it is kept.
    """

    matter = models.ForeignKey("matters.Matter", on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    body = EncryptedTextField()
    document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                 help_text="A document shared in the conversation")

    class Meta(BaseModel.Meta):
        ordering = ["created_at"]
        indexes = [models.Index(fields=["matter", "created_at"])]


class ReadMarker(models.Model):
    """How far each person has read each conversation."""

    matter = models.ForeignKey("matters.Matter", on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    read_at = models.DateTimeField()

    class Meta:
        unique_together = [("matter", "user")]
