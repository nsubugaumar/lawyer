from decimal import Decimal

from rest_framework import serializers

from apps.matters.serializers import PersonSerializer

from .models import Invoice, InvoiceLine, Payment, TimeEntry


class TimeEntrySerializer(serializers.ModelSerializer):
    user = PersonSerializer(read_only=True)
    matter_reference = serializers.CharField(source="matter.reference", read_only=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_billed = serializers.SerializerMethodField()
    # Explicit default: in form posts an absent checkbox otherwise means False,
    # which would silently make time unbillable.
    billable = serializers.BooleanField(default=True)

    class Meta:
        model = TimeEntry
        fields = [
            "id", "matter", "matter_reference", "user", "date", "minutes", "description", "rate",
            "billable", "amount", "is_billed", "created_at",
        ]
        read_only_fields = ["id", "user", "rate", "created_at"]

    def get_is_billed(self, obj):
        return obj.invoice_id is not None

    def validate_minutes(self, value):
        if not 1 <= value <= 24 * 60:
            raise serializers.ValidationError("Enter between 1 minute and 24 hours.")
        return value


class InvoiceLineSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = InvoiceLine
        fields = ["id", "description", "quantity", "unit_price", "amount", "position"]


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "amount", "method", "method_display", "reference", "received_on", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_amount(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("A payment must be more than zero.")
        return value


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, required=False)
    payments = PaymentSerializer(many=True, read_only=True)
    matter_reference = serializers.CharField(source="matter.reference", read_only=True)
    client_name = serializers.CharField(source="matter.client.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    tax = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    paid = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "number", "matter", "matter_reference", "client_name", "status", "status_display", "currency",
            "issue_date", "due_date", "tax_rate", "notes", "lines", "payments",
            "subtotal", "tax", "total", "paid", "balance", "created_at",
        ]
        read_only_fields = ["id", "number", "status", "issue_date", "created_at"]

    def _write_lines(self, invoice, lines):
        invoice.lines.all().delete()
        InvoiceLine.objects.bulk_create(
            [InvoiceLine(invoice=invoice, position=i, **line) for i, line in enumerate(lines)]
        )

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        invoice = super().create(validated_data)
        self._write_lines(invoice, lines)
        return invoice

    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        invoice = super().update(instance, validated_data)
        if lines is not None:
            self._write_lines(invoice, lines)
        return invoice


class GenerateInvoiceSerializer(serializers.Serializer):
    matter = serializers.UUIDField()
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
