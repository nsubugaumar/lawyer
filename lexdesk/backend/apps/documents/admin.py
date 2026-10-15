from django.contrib import admin

from .models import Document, DocumentVersion


class VersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    fields = ("number", "original_filename", "content_type", "size", "sha256", "uploaded_by", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Metadata only. File contents are reachable through the audited API, never the admin."""

    list_display = ("title", "matter", "category", "current_version", "shared_with_client", "court_bundle", "is_archived")
    list_filter = ("category", "shared_with_client", "court_bundle", "is_archived")
    search_fields = ("title", "matter__reference")
    raw_id_fields = ("matter", "uploaded_by")
    inlines = [VersionInline]

    def has_delete_permission(self, request, obj=None):
        return False
