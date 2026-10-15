from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, ReferenceCounter

CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class TimeEntry(BaseModel):
    """Six-minute units are the profession's habit; we store plain minutes."""

    matter = models.ForeignKey("matters.Matter", on_delete=models.PROTECT, related_name="time_entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="time_entries")
    date = models.DateField(default=timezone.localdate, db_index=True)
    minutes = models.PositiveIntegerField()
    description = models.CharField(max_length=500)
    rate = models.DecimalField(max_digits=12, decimal_places=2, help_text="Hourly rate at the time of the work")
    billable = models.BooleanField(default=True)
    invoice = models.ForeignKey("Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="time_entries")

    class Meta(BaseModel.Meta):
        ordering = ["-date", "-created_at"]
        verbose_name_plural = "time entries"

    @property
    def amount(self) -> Decimal:
        return money(self.rate * Decimal(self.minutes) / Decimal(60)) if self.billable else Decimal("0.00")


class Invoice(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PART_PAID = "part_paid", "Part paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    number = models.CharField(max_length=32, unique=True, editable=False)
    matter = models.ForeignKey("matters.Matter", on_delete=models.PROTECT, related_name="invoices")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    currency = models.CharField(max_length=3, default=settings.LEXDESK_CURRENCY)
    issue_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"), help_text="VAT %")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            code = self.matter.firm.code if self.matter.firm_id else ""
            self.number = ReferenceCounter.next(f"{code}-INV" if code and code != "LD" else "INV", timezone.localdate().year)
        super().save(*args, **kwargs)

    @property
    def subtotal(self) -> Decimal:
        return money(sum((line.amount for line in self.lines.all()), Decimal("0")))

    @property
    def tax(self) -> Decimal:
        return money(self.subtotal * self.tax_rate / Decimal(100))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax

    @property
    def paid(self) -> Decimal:
        return money(sum((p.amount for p in self.payments.all()), Decimal("0")))

    @property
    def balance(self) -> Decimal:
        return self.total - self.paid


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    @property
    def amount(self) -> Decimal:
        return money(self.quantity * self.unit_price)


class Payment(BaseModel):
    class Method(models.TextChoices):
        MOBILE_MONEY = "mobile_money", "Mobile Money"
        BANK = "bank", "Bank transfer"
        CARD = "card", "Card"
        CASH = "cash", "Cash"
        CHEQUE = "cheque", "Cheque"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    reference = models.CharField(max_length=100, blank=True, help_text="Transaction ID, cheque number, etc.")
    received_on = models.DateField(default=timezone.localdate)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")


class OnlinePayment(BaseModel):
    """One attempt to pay an invoice online. See online.py."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for payment"
        SUCCESSFUL = "successful", "Paid"
        FAILED = "failed", "Failed or cancelled"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="online_payments")
    firm = models.ForeignKey("firm.Firm", on_delete=models.PROTECT, related_name="+")
    tx_ref = models.CharField(max_length=40, unique=True)
    provider = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    checkout_url = models.URLField(max_length=500, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True)
    failure_reason = models.CharField(max_length=300, blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    payment = models.OneToOneField(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="online")
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tx_ref} {self.status}"

