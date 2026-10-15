from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "status", "email", "phone", "responsible_lawyer", "created_at")
    list_filter = ("status", "kind", "source")
    search_fields = ("name", "contact_person", "email", "phone")
    raw_id_fields = ("responsible_lawyer", "portal_user", "created_by")
