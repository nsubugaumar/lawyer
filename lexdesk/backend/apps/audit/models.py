import hashlib
import json

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

GENESIS_HASH = "0" * 64


class AuditEvent(models.Model):
    """
    An append-only record of who did what, and when.

    Each event stores the hash of the event before it, forming a chain. If
    anyone edits or deletes a row directly in the database, every hash after
    it stops matching, and `manage.py verify_audit_chain` points at the exact
    spot. That is the property a court or regulator cares about: not just
    "we have logs", but "we can prove the logs were not altered".
    """

    id = models.BigAutoField(primary_key=True)
    at = models.DateTimeField(db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Copied, not joined: the record must still say who it was if the user
    # account is later removed.
    actor_email = models.CharField(max_length=254, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    matter_id = models.CharField(max_length=64, blank=True, db_index=True)
    # Which firm's trail this line belongs to. Partners see only their own.
    firm_id = models.CharField(max_length=64, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)
    details = models.JSONField(default=dict, blank=True)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.actor_email or 'system'} {self.action}"

    def compute_hash(self) -> str:
        payload = {
            "at": self.at.isoformat(),
            "actor_email": self.actor_email,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "matter_id": self.matter_id,
            "ip_address": self.ip_address,
            "details": self.details,
            "prev_hash": self.prev_hash,
        }
        if self.firm_id:
            # Added later; left out when empty so earlier lines still verify.
            payload["firm_id"] = self.firm_id
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), cls=DjangoJSONEncoder)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionDenied("Audit events cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Audit events cannot be deleted.")
