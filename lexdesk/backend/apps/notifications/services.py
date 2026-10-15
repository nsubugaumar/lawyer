"""
One function to tell a person something: `notify(user, ...)`.

It records the notification (the bell in the app), then queues a delivery
for every channel the person has chosen for that kind of message: email,
WhatsApp, SMS. Each delivery is retried with back-off when a provider is
down, a WhatsApp that cannot be delivered falls back to SMS, and texts wait
for the end of the person's quiet hours unless they are urgent.

Delivery never raises. A hearing reminder that cannot reach WhatsApp must
not crash the request that scheduled the hearing.
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.firm.models import Firm

from . import channels as wire
from .models import Category, Channel, Delivery, Notification, NotificationPreference

logger = logging.getLogger(__name__)

# Minutes to wait after each failed attempt.
BACKOFF_MINUTES = [1, 5, 15, 60]
# How long a worker holds a delivery while sending it. If it dies mid-send,
# another picks the delivery up once this lapses.
LEASE = timedelta(minutes=10)


def preferences_for(user) -> NotificationPreference:
    cached = getattr(user, "_lexdesk_notification_prefs", None)
    if cached is not None:
        return cached
    firm = Firm.of(user)
    # New people start from the firm's defaults; they can change their own.
    defaults = {
        "court_offsets": list(firm.court_offsets),
        "appointment_offsets": list(firm.appointment_offsets),
        "quiet_hours_start": firm.quiet_hours_start,
        "quiet_hours_end": firm.quiet_hours_end,
        "daily_agenda_at": firm.daily_agenda_at,
    }
    if user.is_firm_staff and firm.staff_whatsapp_default:
        # The firm records staff consent once, in the employment contract,
        # so lawyers get WhatsApp reminders from their first day.
        defaults["whatsapp_opted_in_at"] = timezone.now()
    if user.is_client:
        # Clients see appointments and their own hearings; a morning agenda
        # is a lawyer's tool.
        defaults["daily_agenda"] = False
    prefs, _ = NotificationPreference.objects.get_or_create(user=user, defaults=defaults)
    user._lexdesk_notification_prefs = prefs
    return prefs


def whatsapp_number_for(user, prefs=None) -> str:
    prefs = prefs or preferences_for(user)
    return wire.normalise_phone(prefs.whatsapp_number or user.phone)


def notify(
    user,
    *,
    subject: str,
    body: str,
    sms: str | None = None,
    link: str = "",
    in_app: bool = True,
    category: str = Category.GENERAL,
    urgent: bool = False,
    calendar_ref: str = "",
    calendar_cancelled: bool = False,
    dedupe_key: str = "",
    only: set[str] | None = None,
):
    """
    `sms` is the short version for SMS and WhatsApp. Leave it out and the
    message goes by email and in-app only. `dedupe_key` makes the call
    idempotent per person: a second call with the same key does nothing.
    `only` sends through exactly these channels, whatever the preferences
    (used by "send me a test message").
    """
    if not user.is_active:
        return None
    if dedupe_key and Notification.objects.filter(recipient=user, dedupe_key=dedupe_key).exists():
        return None

    prefs = preferences_for(user)
    chosen = set(only) if only is not None else prefs.channels_for(category)

    notification = Notification.objects.create(
        recipient=user,
        category=category,
        title=subject[:200],
        body=body[:5000],
        short_text=(sms or "")[:320],
        link=link,
        # Accounts still waiting for activation have no app to look at.
        in_app=in_app and Channel.IN_APP in chosen and user.has_usable_password(),
        urgent=urgent,
        calendar_ref=calendar_ref,
        calendar_cancelled=calendar_cancelled,
        dedupe_key=dedupe_key,
    )

    planned = []
    if Channel.EMAIL in chosen and user.email:
        planned.append(Delivery(notification=notification, channel=Channel.EMAIL, address=user.email))

    number = whatsapp_number_for(user, prefs)
    if sms and number:
        whatsapp_ok = Channel.WHATSAPP in chosen and prefs.whatsapp_active and Firm.of(user).whatsapp_backend != "off"
        if whatsapp_ok:
            planned.append(Delivery(notification=notification, channel=Channel.WHATSAPP, address=number))
        if Channel.SMS in chosen or category == Category.SECURITY:
            planned.append(Delivery(notification=notification, channel=Channel.SMS, address=number))
        elif Channel.WHATSAPP in chosen and not whatsapp_ok and prefs.sms_fallback and Firm.of(user).sms_backend != "off":
            # They want a message on their phone; WhatsApp is not possible.
            planned.append(Delivery(notification=notification, channel=Channel.SMS, address=number, is_fallback=True))

    now = timezone.now()
    for delivery in planned:
        delivery.next_attempt_at = _earliest_send(delivery.channel, prefs, urgent, now)
    Delivery.objects.bulk_create(planned)
    _kick([d.pk for d in planned if d.next_attempt_at <= now])
    return notification


def _earliest_send(channel, prefs, urgent, now):
    """Phones stay quiet overnight unless the message cannot wait."""
    if urgent or channel not in (Channel.WHATSAPP, Channel.SMS):
        return now
    local = timezone.localtime(now)
    if not prefs.in_quiet_hours(local.time()):
        return now
    end = timezone.make_aware(datetime.combine(local.date(), prefs.quiet_hours_end))
    if end <= now:
        end += timedelta(days=1)
    return end


def _kick(delivery_ids):
    if not delivery_ids:
        return
    if settings.CELERY_TASK_ALWAYS_EAGER:
        for pk in delivery_ids:
            deliver(pk)
        return

    from .tasks import deliver_task

    transaction.on_commit(lambda: [deliver_task.delay(str(pk)) for pk in delivery_ids])


def deliver(delivery_id):
    """Send one delivery now. Safe to call twice: only one caller sends."""
    now = timezone.now()
    with transaction.atomic():
        delivery = (
            Delivery.objects.select_for_update(skip_locked=True)
            .filter(pk=delivery_id, status=Delivery.Status.QUEUED, next_attempt_at__lte=now)
            .first()
        )
        if delivery is None:
            return
        delivery.attempts += 1
        delivery.next_attempt_at = now + LEASE
        delivery.save(update_fields=["attempts", "next_attempt_at", "updated_at"])

    notification = Notification.objects.select_related("recipient").get(pk=delivery.notification_id)
    try:
        delivery.provider_message_id = _send(delivery, notification)
    except wire.PermanentFailure as exc:
        _fail(delivery, notification, str(exc))
    except Exception as exc:  # noqa: BLE001 - TemporaryFailure, or a bug we must survive
        if not isinstance(exc, wire.TemporaryFailure):
            logger.exception("Unexpected error delivering %s", delivery.pk)
        if delivery.attempts >= Delivery.MAX_ATTEMPTS:
            _fail(delivery, notification, str(exc) or exc.__class__.__name__)
        else:
            delivery.last_error = (str(exc) or exc.__class__.__name__)[:500]
            delivery.next_attempt_at = timezone.now() + timedelta(minutes=BACKOFF_MINUTES[min(delivery.attempts, len(BACKOFF_MINUTES)) - 1])
            delivery.save(update_fields=["last_error", "next_attempt_at", "updated_at"])
            logger.warning("%s to %s failed (attempt %s), retrying", delivery.channel, wire.mask(delivery.address), delivery.attempts)
    else:
        delivery.status = Delivery.Status.SENT
        delivery.sent_at = timezone.now()
        delivery.next_attempt_at = None
        delivery.last_error = ""
        delivery.save(update_fields=["status", "sent_at", "next_attempt_at", "last_error", "provider_message_id", "updated_at"])


def _send(delivery, notification) -> str:
    if delivery.channel == Channel.EMAIL:
        from . import ics

        invite = ics.invite(notification.calendar_ref, notification.recipient, cancelled=notification.calendar_cancelled) if notification.calendar_ref else None
        return wire.send_email(to=delivery.address, subject=notification.title, body=notification.body, link=notification.link, ics=invite, firm=Firm.of(notification.recipient))
    if delivery.channel == Channel.WHATSAPP:
        return wire.send_whatsapp(to=delivery.address, headline=notification.title, details=notification.short_text, link=notification.link, firm=Firm.of(notification.recipient))
    if delivery.channel == Channel.SMS:
        return wire.send_sms(to=delivery.address, text=notification.short_text, firm=Firm.of(notification.recipient))
    raise wire.PermanentFailure(f"No sender for channel {delivery.channel}")


def _fail(delivery, notification, reason):
    delivery.status = Delivery.Status.FAILED
    delivery.last_error = reason[:500]
    delivery.next_attempt_at = None
    delivery.save(update_fields=["status", "last_error", "next_attempt_at", "updated_at"])
    logger.warning("%s to %s failed for good: %s", delivery.channel, wire.mask(delivery.address), reason)
    if delivery.channel == Channel.WHATSAPP:
        fall_back_to_sms(delivery, notification)


def fall_back_to_sms(delivery, notification):
    prefs = preferences_for(notification.recipient)
    if not (prefs.sms_fallback and notification.short_text):
        return
    if notification.deliveries.filter(channel=Channel.SMS).exists():
        return  # they are getting an SMS anyway
    fallback = Delivery.objects.create(
        notification=notification, channel=Channel.SMS, address=delivery.address, is_fallback=True, next_attempt_at=timezone.now(),
    )
    _kick([fallback.pk])


def retry_due_deliveries(limit=500):
    """Everything waiting out quiet hours, a back-off, or an expired lease."""
    due = Delivery.objects.filter(status=Delivery.Status.QUEUED, next_attempt_at__lte=timezone.now()).order_by("next_attempt_at")
    for pk in due.values_list("pk", flat=True)[:limit]:
        deliver(pk)


# --------------------------------------------------------------------------
# Provider receipts (WhatsApp "delivered" / "read" ticks)
# --------------------------------------------------------------------------

_RANK = {Delivery.Status.QUEUED: 0, Delivery.Status.SENT: 1, Delivery.Status.DELIVERED: 2, Delivery.Status.READ: 3}


def record_receipt(provider_message_id: str, status: str, error: str = ""):
    delivery = Delivery.objects.select_related("notification").filter(provider_message_id=provider_message_id).first()
    if delivery is None:
        return
    now = timezone.now()
    if status == "failed":
        if delivery.status != Delivery.Status.READ:
            _fail(delivery, delivery.notification, error or "Reported failed by WhatsApp")
        return
    new = {"sent": Delivery.Status.SENT, "delivered": Delivery.Status.DELIVERED, "read": Delivery.Status.READ}.get(status)
    if new is None or _RANK.get(new, 0) <= _RANK.get(delivery.status, 99):
        return  # receipts arrive out of order; never step backwards
    delivery.status = new
    if new == Delivery.Status.DELIVERED:
        delivery.delivered_at = now
    if new == Delivery.Status.READ:
        delivery.read_at = now
        delivery.delivered_at = delivery.delivered_at or now
    delivery.save(update_fields=["status", "delivered_at", "read_at", "updated_at"])


def opt_out_whatsapp(phone: str, firm=None):
    """Someone replied STOP. WhatsApp policy: stop, at once, everywhere."""
    from apps.accounts.models import User

    number = wire.normalise_phone(phone)
    if not number:
        return 0
    count = 0
    # Numbers are stored however people typed them ("0772 111 222"), so
    # compare normalised forms rather than filtering in SQL.
    candidates = User.objects.filter(is_active=True).exclude(phone="", notification_preference__whatsapp_number="")
    if firm is not None:
        candidates = candidates.filter(firm=firm)
    for user in candidates.select_related("notification_preference").distinct():
        if whatsapp_number_for(user) == number:
            prefs = preferences_for(user)
            prefs.whatsapp_opted_out_at = timezone.now()
            prefs.save(update_fields=["whatsapp_opted_out_at", "updated_at"])
            count += 1
    return count
