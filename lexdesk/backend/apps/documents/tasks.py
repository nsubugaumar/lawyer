from celery import shared_task

from .models import DocumentVersion
from .search import index_document
from .services import read_version


@shared_task(ignore_result=True)
def index_version(version_id):
    version = DocumentVersion.objects.select_related("document").filter(pk=version_id).first()
    # Only the newest version is searchable; an older one may arrive late.
    if version is None or version.number != version.document.current_version:
        return
    index_document(version.document, read_version(version), version.content_type)
