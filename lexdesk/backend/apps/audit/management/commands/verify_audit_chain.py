from django.core.management.base import BaseCommand, CommandError

from apps.audit.services import verify_chain


class Command(BaseCommand):
    help = "Prove the audit trail has not been altered. Run it nightly and alert on failure."

    def handle(self, *args, **options):
        ok, broken_at, checked = verify_chain()
        if not ok:
            raise CommandError(f"Audit chain BROKEN at event #{broken_at} (after {checked} good events).")
        self.stdout.write(self.style.SUCCESS(f"Audit chain intact: {checked} events verified."))
