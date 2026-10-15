from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("at", "actor_email", "action", "target_type", "target_id", "ip_address")
    list_filter = ("action",)
    search_fields = ("actor_email", "action", "target_id", "matter_id")
    date_hierarchy = "at"

    # Visible to administrators, changeable by nobody.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
