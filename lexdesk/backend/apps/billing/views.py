import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import FEE_EARNERS, MANAGES_BILLING
from apps.audit.services import record
from apps.matters.access import can_work_on_matter, visible_matters
from apps.firm.models import Firm
from apps.notifications.models import Category
from apps.notifications.services import notify

from .models import Invoice, InvoiceLine, Payment, TimeEntry
from .serializers import GenerateInvoiceSerializer, InvoiceSerializer, PaymentSerializer, TimeEntrySerializer


logger = logging.getLogger(__name__)


class TimeEntryViewSet(viewsets.ModelViewSet):
    serializer_class = TimeEntrySerializer
    filterset_fields = ["matter", "user", "billable", "date"]
    ordering_fields = ["date", "minutes"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.is_client:
            return TimeEntry.objects.none()
        qs = TimeEntry.objects.filter(matter__in=visible_matters(user)).select_related("matter", "user")
        if user.role not in MANAGES_BILLING:
            qs = qs.filter(user=user)  # lawyers see their own time sheet
        if self.request.query_params.get("unbilled") == "1":
            qs = qs.filter(invoice__isnull=True, billable=True)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        matter = serializer.validated_data["matter"]
        if user.role not in FEE_EARNERS or not can_work_on_matter(user, matter):
            raise PermissionDenied("You can only record time on matters you work on.")
        rate = matter.hourly_rate or user.hourly_rate or Decimal("0")
        entry = serializer.save(user=user, rate=rate)
        record("time.recorded", actor=user, target=entry, matter=matter, minutes=entry.minutes)

    def _check_editable(self, entry):
        if entry.invoice_id:
            raise ValidationError("This time has been invoiced and can no longer be changed.")
        if entry.user_id != self.request.user.id and self.request.user.role not in MANAGES_BILLING:
            raise PermissionDenied()

    def perform_update(self, serializer):
        self._check_editable(serializer.instance)
        if "matter" in serializer.validated_data and not can_work_on_matter(self.request.user, serializer.validated_data["matter"]):
            raise PermissionDenied()
        entry = serializer.save()
        record("time.updated", actor=self.request.user, target=entry, matter=entry.matter)

    def perform_destroy(self, entry):
        self._check_editable(entry)
        record("time.deleted", actor=self.request.user, target=entry, matter=entry.matter, minutes=entry.minutes)
        entry.delete()


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    filterset_fields = ["matter", "status"]
    search_fields = ["number", "matter__reference", "matter__client__name"]
    ordering_fields = ["created_at", "due_date", "issue_date"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = (
            Invoice.objects.filter(matter__in=visible_matters(user))
            .select_related("matter", "matter__client")
            .prefetch_related("lines", "payments")
        )
        if user.is_client:
            return qs.exclude(status__in=[Invoice.Status.DRAFT, Invoice.Status.VOID])
        if user.role not in MANAGES_BILLING:
            return qs.none()
        return qs

    def _require_billing(self):
        if self.request.user.role not in MANAGES_BILLING:
            raise PermissionDenied("Only accounts staff and partners handle invoices.")

    def perform_create(self, serializer):
        self._require_billing()
        if not visible_matters(self.request.user).filter(pk=serializer.validated_data["matter"].pk).exists():
            raise PermissionDenied()
        invoice = serializer.save(created_by=self.request.user)
        record("invoice.created", actor=self.request.user, target=invoice, matter=invoice.matter)

    def perform_update(self, serializer):
        self._require_billing()
        if serializer.instance.status != Invoice.Status.DRAFT:
            raise ValidationError("Issued invoices cannot be edited. Void it and raise a new one.")
        invoice = serializer.save()
        record("invoice.updated", actor=self.request.user, target=invoice, matter=invoice.matter)

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def generate(self, request):
        """Turn a matter's unbilled time into a draft invoice."""
        self._require_billing()
        data = GenerateInvoiceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        matter = visible_matters(request.user).filter(pk=data.validated_data["matter"]).first()
        if matter is None:
            raise ValidationError({"matter": "Matter not found."})

        entries = list(
            TimeEntry.objects.select_for_update().filter(matter=matter, invoice__isnull=True, billable=True).select_related("user")
        )
        if not entries:
            raise ValidationError("There is no unbilled time on this matter.")

        invoice = Invoice.objects.create(matter=matter, created_by=request.user, **(
            {"tax_rate": data.validated_data["tax_rate"]} if "tax_rate" in data.validated_data else {}
        ))
        InvoiceLine.objects.bulk_create([
            InvoiceLine(
                invoice=invoice,
                position=i,
                description=f"{e.date:%d %b %Y} · {e.user.full_name} · {e.description}",
                quantity=(Decimal(e.minutes) / Decimal(60)).quantize(Decimal("0.01")),
                unit_price=e.rate,
            )
            for i, e in enumerate(entries)
        ])
        TimeEntry.objects.filter(pk__in=[e.pk for e in entries]).update(invoice=invoice)
        record("invoice.generated", actor=request.user, target=invoice, matter=matter, entries=len(entries))
        return Response(self.get_serializer(invoice).data, status=201)

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        self._require_billing()
        invoice = self.get_object()
        if invoice.status != Invoice.Status.DRAFT:
            raise ValidationError("Only draft invoices can be issued.")
        if not invoice.lines.exists():
            raise ValidationError("Add at least one line before issuing.")
        invoice.status = Invoice.Status.ISSUED
        invoice.issue_date = timezone.localdate()
        invoice.due_date = invoice.due_date or invoice.issue_date + timedelta(days=30)
        invoice.save(update_fields=["status", "issue_date", "due_date", "updated_at"])
        record("invoice.issued", actor=request.user, target=invoice, matter=invoice.matter, total=str(invoice.total))

        portal_user = invoice.matter.client.portal_user
        if portal_user:
            notify(
                portal_user,
                subject=f"Invoice {invoice.number} from {Firm.of(portal_user).name}",
                body=f"Invoice {invoice.number} for {invoice.currency} {invoice.total:,.2f} is ready in your client portal. "
                f"It is due on {invoice.due_date:%d %B %Y}.",
                link="/billing",
                category=Category.BILLING,
            )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def void(self, request, pk=None):
        self._require_billing()
        invoice = self.get_object()
        if invoice.payments.exists():
            raise ValidationError("An invoice with payments cannot be voided. Issue a credit note instead.")
        invoice.status = Invoice.Status.VOID
        invoice.save(update_fields=["status", "updated_at"])
        invoice.time_entries.update(invoice=None)  # the time becomes billable again
        record("invoice.voided", actor=request.user, target=invoice, matter=invoice.matter)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def payments(self, request, pk=None):
        self._require_billing()
        invoice = Invoice.objects.select_for_update().get(pk=self.get_object().pk)
        if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.PART_PAID):
            raise ValidationError("Payments can only be recorded against issued invoices.")

        serializer = PaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["amount"] > invoice.balance:
            raise ValidationError({"amount": f"That is more than the balance of {invoice.balance:,.2f}."})

        payment = serializer.save(invoice=invoice, recorded_by=request.user)
        invoice = Invoice.objects.prefetch_related("payments", "lines").get(pk=invoice.pk)
        invoice.status = Invoice.Status.PAID if invoice.balance <= 0 else Invoice.Status.PART_PAID
        invoice.save(update_fields=["status", "updated_at"])
        record("invoice.payment_recorded", actor=request.user, target=invoice, matter=invoice.matter,
               amount=str(payment.amount), method=payment.method)
        return Response(self.get_serializer(invoice).data, status=201)

    @action(detail=True, methods=["post"], url_path="pay-online")
    def pay_online(self, request, pk=None):
        """The client (or the office, on their behalf) starts an online payment."""
        from .online import start_checkout

        invoice = self.get_object()
        payment = start_checkout(invoice, user=request.user, phone=str(request.data.get("phone", "")))
        return Response({"tx_ref": payment.tx_ref, "checkout_url": payment.checkout_url}, status=201)


class OnlinePaymentView(APIView):
    """The return from checkout: check with the provider and report back."""

    def get(self, request, tx_ref):
        from .online import verify

        payment = _visible_online_payment(request, tx_ref)
        payment = verify(payment)
        return Response(_payment_status(payment))

    def post(self, request, tx_ref):
        """Test mode only: the simulated checkout page answers here."""
        from .online import verify

        payment = _visible_online_payment(request, tx_ref)
        if payment.provider != "test":
            raise PermissionDenied("Only test payments can be simulated.")
        payment = verify(payment, simulated_success=request.data.get("outcome") == "success")
        return Response(_payment_status(payment))


def _visible_online_payment(request, tx_ref):
    from django.http import Http404

    from .models import OnlinePayment

    payment = OnlinePayment.objects.select_related("invoice", "invoice__matter", "firm").filter(tx_ref=tx_ref).first()
    if payment is None or not visible_matters(request.user).filter(pk=payment.invoice.matter_id).exists():
        raise Http404
    return payment


def _payment_status(payment):
    return {
        "tx_ref": payment.tx_ref, "status": payment.status, "amount": str(payment.amount), "currency": payment.currency,
        "invoice": str(payment.invoice_id), "invoice_number": payment.invoice.number, "firm": payment.firm.name,
        "failure_reason": payment.failure_reason,
    }


class FlutterwaveWebhookView(APIView):
    """
    Flutterwave tells us a payment finished. The secret hash proves it is
    Flutterwave; we still verify the transaction with them before recording.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request, slug):
        import hmac

        from django.http import HttpResponse

        from apps.firm.models import Firm

        from .models import OnlinePayment
        from .online import verify

        firm = Firm.objects.filter(slug=slug, is_active=True).first()
        expected = firm.flutterwave_webhook_hash if firm else ""
        if not expected or not hmac.compare_digest(request.headers.get("verif-hash", ""), expected):
            return HttpResponse(status=401)
        tx_ref = ((request.data or {}).get("data") or {}).get("tx_ref") or (request.data or {}).get("txRef")
        payment = OnlinePayment.objects.filter(firm=firm, tx_ref=tx_ref).first() if tx_ref else None
        if payment is not None:
            try:
                verify(payment)
            except Exception:  # noqa: BLE001 - answer 200 so Flutterwave does not retry forever; the return path verifies too
                logger.exception("Webhook verification failed for %s", tx_ref)
        return HttpResponse(status=200)

