from django.core.management.base import BaseCommand

from apps.documents.models import Document
from apps.documents.search import index_document
from apps.documents.services import read_version


class Command(BaseCommand):
    help = "Rebuild the blind search index for every document (after an upgrade or a search-key rotation)."

    def handle(self, *args, **options):
        done = 0
        for document in Document.objects.filter(current_version__gt=0).iterator():
            version = document.latest
            if version is None:
                continue
            index_document(document, read_version(version), version.content_type)
            done += 1
        self.stdout.write(f"Indexed {done} documents.")
