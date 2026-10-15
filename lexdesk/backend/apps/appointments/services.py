from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.accounts.models import FEE_EARNERS, User
from apps.audit.services import record
from apps.clients.models import Client
from apps.clients.services import ensure_portal_account
from apps.firm.models import Firm
from apps.matters.models import CourtEvent
from apps.notifications import reminders
from apps.notifications.services import preferences_for

from .models import Appointment




class BookingPaused(APIException):
    status_code = 400
    default_code = "booking_paused"


def busy_periods(lawyer, day):
    """Everything already in this lawyer's day: appointments and court."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)

    periods = list(
        Appointment.objects.filter(
            lawyer=lawyer, status__in=Appointment.ACTIVE, starts_at__lt=end, ends_at__gt=start
        ).values_list("starts_at", "ends_at")
    )
    for event in CourtEvent.objects.filter(attendees=lawyer, starts_at__gte=start, starts_at__lt=end, outcome="pending"):
        # A hearing with no end time blocks the rest of the morning or
        # afternoon. Courts rarely finish when the cause list says they will.
        periods.append((event.starts_at, event.ends_at or event.starts_at + timedelta(hours=3)))
    return periods


def available_slots(lawyer, day):
    # Office hours, working days and slot length are set by the firm's
    # partners in Settings > Firm, and take effect immediately.
    firm = Firm.of(lawyer)
    if day.weekday() not in firm.working_days:
        return []

    tz = timezone.get_current_timezone()
    step = timedelta(minutes=firm.slot_minutes)
    cursor = timezone.make_aware(datetime.combine(day, firm.office_opens), tz)
    close_at = timezone.make_aware(datetime.combine(day, firm.office_closes), tz)
    earliest = timezone.now() + timedelta(hours=1)  # no booking for five minutes from now
    busy = busy_periods(lawyer, day)

    slots = []
    while cursor + step <= close_at:
        slot_end = cursor + step
        clashes = any(b_start < slot_end and b_end > cursor for b_start, b_end in busy)
        if cursor >= earliest and not clashes:
            slots.append({"starts_at": cursor, "ends_at": slot_end})
        cursor = slot_end
    return slots


def assert_lawyer_free(lawyer, starts_at, ends_at, *, exclude=None):
    if lawyer.role not in FEE_EARNERS:
        raise ValidationError({"lawyer": "Appointments can only be booked with a lawyer."})
    if ends_at <= starts_at:
        raise ValidationError({"ends_at": "The appointment must end after it starts."})

    clash = Appointment.objects.select_for_update().filter(
        lawyer=lawyer, status__in=Appointment.ACTIVE, starts_at__lt=ends_at, ends_at__gt=starts_at
    )
    if exclude is not None:
        clash = clash.exclude(pk=exclude.pk)
    if clash.exists():
        raise ValidationError({"starts_at": f"{lawyer.full_name} is already booked at that time."})


@transaction.atomic
def public_booking(*, firm, name, email, phone, lawyer_id, starts_at, mode, purpose, practice_area="", whatsapp_opt_in=False):
    """
    A member of the public books a consultation from the firm's website.

    The system creates the client record and their portal account itself,
    and emails them an activation link. Nobody at reception has to type
    anything in, and nobody has to set a password on the client's behalf.
    """
    if not firm.booking_enabled:
        raise BookingPaused(f"Online booking is paused. Please call us on {firm.phone or 'the office number'}.")
    lawyer = User.objects.filter(firm=firm, pk=lawyer_id, is_active=True, role__in=FEE_EARNERS).first()
    if lawyer is None:
        raise ValidationError({"lawyer": "Please choose a lawyer from the list."})

    ends_at = starts_at + timedelta(minutes=firm.slot_minutes)
    if starts_at < timezone.now() + timedelta(hours=1):
        raise ValidationError({"starts_at": "Please choose a time at least an hour from now."})
    if not any(s["starts_at"] == starts_at for s in available_slots(lawyer, timezone.localtime(starts_at).date())):
        raise ValidationError({"starts_at": "That time is no longer available. Please pick another slot."})
    assert_lawyer_free(lawyer, starts_at, ends_at)

    client = Client.objects.filter(firm=firm, email__iexact=email).first()
    if client is None:
        client = Client.objects.create(firm=firm, name=name, email=email.lower(), phone=phone, source=Client.Source.WEBSITE)
        record("client.created", target=client, via="public_booking")
    portal_user = ensure_portal_account(client)
    if whatsapp_opt_in and portal_user:
        # Ticking "remind me on WhatsApp" on the booking form is the consent
        # WhatsApp requires, and it is recorded with its time.
        prefs = preferences_for(portal_user)
        prefs.whatsapp_number = prefs.whatsapp_number or phone
        prefs.whatsapp_opted_in_at, prefs.whatsapp_opted_out_at = timezone.now(), None
        prefs.save(update_fields=["whatsapp_number", "whatsapp_opted_in_at", "whatsapp_opted_out_at", "updated_at"])

    appointment = Appointment.objects.create(
        firm=firm, client=client, lawyer=lawyer, starts_at=starts_at, ends_at=ends_at, mode=mode,
        purpose=purpose, practice_area=practice_area,
    )
    record("appointment.requested", target=appointment, via="public_booking")

    transaction.on_commit(lambda: reminders.announce_appointment(appointment, "requested"))
    return appointment
