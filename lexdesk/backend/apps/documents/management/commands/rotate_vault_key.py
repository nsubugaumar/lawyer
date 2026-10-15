from django.core.management.base import BaseCommand

from apps.core.crypto import SealedBlob, active_vault_key, rewrap
from apps.documents.models import DocumentVersion


class Command(BaseCommand):
    help = (
        "Re-wrap every document key under the current vault master key. "
        "Run after putting a new key first in LEXDESK_VAULT_KEYS; once it reports "
        "zero remaining, the old key can be retired."
    )

    def handle(self, *args, **options):
        active_id, _ = active_vault_key()
        stale = DocumentVersion.objects.exclude(key_id=active_id)
        total = stale.count()
        for version in stale.iterator(chunk_size=500):
            sealed = rewrap(SealedBlob(ciphertext=b"", wrapped_key=bytes(version.wrapped_key), key_id=version.key_id))
            DocumentVersion.objects.filter(pk=version.pk).update(wrapped_key=sealed.wrapped_key, key_id=sealed.key_id)
        remaining = DocumentVersion.objects.exclude(key_id=active_id).count()
        self.stdout.write(self.style.SUCCESS(f"Re-wrapped {total} document keys under '{active_id}'. Remaining: {remaining}."))
