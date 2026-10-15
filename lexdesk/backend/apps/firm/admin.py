from django.contrib import admin

from .models import Firm


@admin.register(Firm)
class FirmAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "slug", "domain", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "code", "domain")
    # Secrets are excluded: they are set through the app, never shown back.
    exclude = ("whatsapp_access_token", "whatsapp_app_secret", "whatsapp_verify_token")

    def has_delete_permission(self, request, obj=None):
        return False  # firms are suspended, never deleted: their files must be kept
