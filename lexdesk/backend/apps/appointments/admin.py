from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("starts_at", "client", "lawyer", "mode", "status")
    list_filter = ("status", "mode")
    date_hierarchy = "starts_at"
    raw_id_fields = ("client", "matter", "lawyer", "booked_by")
