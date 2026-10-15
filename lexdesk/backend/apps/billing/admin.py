from django.contrib import admin

from .models import Invoice, InvoiceLine, Payment, TimeEntry


class LineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("recorded_by",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "matter", "status", "issue_date", "due_date")
    list_filter = ("status",)
    search_fields = ("number", "matter__reference")
    raw_id_fields = ("matter", "created_by")
    inlines = [LineInline, PaymentInline]


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "matter", "minutes", "billable", "invoice")
    list_filter = ("billable",)
    raw_id_fields = ("matter", "user", "invoice")
