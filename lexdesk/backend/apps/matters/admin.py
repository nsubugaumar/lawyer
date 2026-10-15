from django.contrib import admin

from .models import CourtEvent, Matter, MatterMember, Party, Task


class MemberInline(admin.TabularInline):
    model = MatterMember
    extra = 0
    raw_id_fields = ("user",)


class PartyInline(admin.TabularInline):
    model = Party
    extra = 0


@admin.register(Matter)
class MatterAdmin(admin.ModelAdmin):
    list_display = ("reference", "title", "client", "practice_area", "status", "lead_lawyer", "is_restricted", "opened_on")
    list_filter = ("status", "practice_area", "is_restricted")
    search_fields = ("reference", "title", "case_number", "client__name")
    raw_id_fields = ("client", "lead_lawyer")
    inlines = [MemberInline, PartyInline]


@admin.register(CourtEvent)
class CourtEventAdmin(admin.ModelAdmin):
    list_display = ("starts_at", "kind", "title", "matter", "location", "outcome")
    list_filter = ("kind", "outcome")
    date_hierarchy = "starts_at"
    raw_id_fields = ("matter", "next_event")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "matter", "assigned_to", "due_on", "status", "priority")
    list_filter = ("status", "priority")
    raw_id_fields = ("matter", "assigned_to", "created_by")


# File notes are deliberately absent: they are privileged, and the admin site
# would bypass ethical walls. They are only reachable through the API.
