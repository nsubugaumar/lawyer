from django.contrib import admin

from .models import Delivery, NotificationPreference, ScheduledReminder


class DeliveryInline(admin.TabularInline):
    model = Delivery
    extra = 0
    can_delete = False
    fields = ("channel", "status", "attempts", "is_fallback", "sent_at", "delivered_at", "read_at", "last_error")
    readonly_fields = fields


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    """The proof that a reminder went out, and the place to see why one did not."""

    list_display = ("created_at", "channel", "status", "attempts", "is_fallback", "sent_at", "delivered_at", "last_error")
    list_filter = ("channel", "status", "is_fallback")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in Delivery._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ScheduledReminder)
class ScheduledReminderAdmin(admin.ModelAdmin):
    list_display = ("send_at", "recipient", "court_event", "appointment", "offset_minutes", "status", "sent_at")
    list_filter = ("status",)
    date_hierarchy = "send_at"
    raw_id_fields = ("recipient", "court_event", "appointment")
    readonly_fields = ("sent_at",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "whatsapp_opted_in_at", "whatsapp_opted_out_at", "sms_fallback", "daily_agenda")
    raw_id_fields = ("user",)
    search_fields = ("user__email", "user__last_name")


# Notification bodies are deliberately not browsable in the admin: they carry
# hearing details and single-use links. Delivery records are enough to audit.
