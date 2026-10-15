"""
Paying invoices online: MTN and Airtel Mobile Money, and cards, through
Flutterwave's hosted checkout.

The flow:
  1. The client taps "Pay now". We create an OnlinePayment with a unique
     reference and ask Flutterwave for a checkout link.
  2. The client pays on Flutterwave's page (their phone gets the Mobile
     Money prompt) and is sent back to LexDesk.
  3. We never trust the browser's word that it paid. Both the return and
     Flutterwave's webhook make us ask Flutterwave directly; only a verified,
     successful transaction for the right amount and currency is recorded,
     once, as a payment on the invoice.

In test mode no money moves: a simulated checkout page lets the firm try
the whole flow end to end.
"""

import json
import logging
import secrets
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.firm.models import Firm
from apps.notifications.models import Category
from apps.notifications.services import notify

from .models import Invoice, OnlinePayment, Payment

logger = logging.getLogger(__name__)
API = "https://api.flutterwave.com/v3"


def _call(firm: Firm, method: str, path: str, payload=None) -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {firm.flutterwave_secret_key}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed https URL
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read()).get("message", "")
        except ValueError:
            message = ""
        logger.warning("Flutterwave %s %s failed: %s %s", method, path, exc.code, message)
        raise ValidationError(f"The payment service said: {message or exc.reason}. Please try again.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValidationError("The payment service could not be reached. Please try again in a moment.") from exc


def start_checkout(invoice: Invoice, *, user, phone: str = "") -> OnlinePayment:
    firm = invoice.matter.firm
    backend = firm.payments_backend
    if backend == "off":
        raise ValidationError("Online payment is not available yet. Please pay by bank transfer or Mobile Money, quoting the invoice number.")
    if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.PART_PAID) or invoice.balance <= 0:
        raise ValidationError("This invoice has nothing left to pay.")

    payment = OnlinePayment.objects.create(
        invoice=invoice, firm=firm, tx_ref=f"LD-{secrets.token_hex(8)}", amount=invoice.balance,
        currency=invoice.currency, started_by=user, provider=backend,
    )
    return_url = f"{settings.LEXDESK_WEB_URL}/billing?payment={payment.tx_ref}"
    if backend == "test":
        payment.checkout_url = f"{settings.LEXDESK_WEB_URL}/pay/test?ref={payment.tx_ref}"
    else:
        client = invoice.matter.client
        data = _call(firm, "POST", "/payments", {
            "tx_ref": payment.tx_ref,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "redirect_url": return_url,
            "payment_options": "mobilemoneyuganda,card",
            "customer": {"email": client.email or user.email, "name": client.name, "phonenumber": phone or client.phone},
            "customizations": {"title": firm.name, "description": f"Invoice {invoice.number}"},
            "meta": {"invoice": invoice.number},
        })
        payment.checkout_url = (data.get("data") or {}).get("link", "")
        if not payment.checkout_url:
            raise ValidationError("The payment service did not return a checkout page. Please try again.")
    payment.save(update_fields=["checkout_url"])
    record("payment.online_started", actor=user, target=invoice, matter=invoice.matter, amount=str(payment.amount), tx_ref=payment.tx_ref)
    return payment


def verify(payment: OnlinePayment, *, simulated_success: bool | None = None) -> OnlinePayment:
    """Ask the provider what really happened, and record it once."""
    if payment.status != OnlinePayment.Status.PENDING:
        return payment
    firm = payment.firm

    if payment.provider == "test":
        if simulated_success is None:
            return payment  # the test checkout page has not been answered yet
        ok, provider_id, paid_amount, currency = simulated_success, f"TEST-{payment.tx_ref}", payment.amount, payment.currency
        method = Payment.Method.MOBILE_MONEY
    else:
        data = _call(firm, "GET", f"/transactions/verify_by_reference?tx_ref={payment.tx_ref}").get("data") or {}
        status = data.get("status")
        if status not in ("successful", "failed", "cancelled"):
            return payment  # still in progress at the provider
        ok = status == "successful"
        provider_id = str(data.get("id", ""))
        paid_amount = Decimal(str(data.get("amount", "0")))
        currency = data.get("currency", "")
        method = Payment.Method.CARD if data.get("payment_type") == "card" else Payment.Method.MOBILE_MONEY

    with transaction.atomic():
        payment = OnlinePayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != OnlinePayment.Status.PENDING:
            return payment  # the webhook and the return raced; one recorded it
        payment.provider_reference = provider_id
        payment.completed_at = timezone.now()
        if not ok:
            payment.status = OnlinePayment.Status.FAILED
            payment.save(update_fields=["status", "provider_reference", "completed_at", "updated_at"])
            return payment
        if currency != payment.currency or paid_amount < payment.amount:
            payment.status = OnlinePayment.Status.FAILED
            payment.failure_reason = f"Paid {currency} {paid_amount}, expected {payment.currency} {payment.amount}. Check with Flutterwave."
            payment.save(update_fields=["status", "provider_reference", "completed_at", "failure_reason", "updated_at"])
            logger.error("Online payment %s amount mismatch", payment.tx_ref)
            return payment

        invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
        amount = min(payment.amount, invoice.balance)
        recorded = Payment.objects.create(
            invoice=invoice, amount=amount, method=method, reference=f"{provider_id} ({payment.tx_ref})",
            received_on=timezone.localdate(), recorded_by=payment.started_by,
        )
        invoice = Invoice.objects.prefetch_related("payments", "lines").get(pk=invoice.pk)
        invoice.status = Invoice.Status.PAID if invoice.balance <= 0 else Invoice.Status.PART_PAID
        invoice.save(update_fields=["status", "updated_at"])
        payment.status = OnlinePayment.Status.SUCCESSFUL
        payment.payment = recorded
        payment.save(update_fields=["status", "provider_reference", "completed_at", "payment", "updated_at"])
        record("payment.online_received", target=invoice, matter=invoice.matter, amount=str(amount), tx_ref=payment.tx_ref)

        def tell():
            payer = payment.started_by
            if payer:
                notify(payer, subject=f"Payment received: {invoice.currency} {amount:,.0f}",
                       body=f"Thank you. We received {invoice.currency} {amount:,.2f} for invoice {invoice.number}.",
                       sms=f"{firm.name}: payment of {invoice.currency} {amount:,.0f} for {invoice.number} received. Thank you.",
                       link="/billing", category=Category.BILLING)
            from apps.accounts.models import MANAGES_BILLING, User

            for person in User.objects.filter(firm=firm, is_active=True, role__in=MANAGES_BILLING):
                notify(person, subject=f"Online payment: {invoice.number} · {invoice.currency} {amount:,.0f}",
                       body=f"{invoice.matter.client.name} paid {invoice.currency} {amount:,.2f} online for invoice {invoice.number}.",
                       link="/billing", category=Category.BILLING)

        transaction.on_commit(tell)
    return payment
