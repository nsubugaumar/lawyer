"""
Court dates and appointments: who hears about them, and when.

  * The moment something goes into the diary, everyone involved is told,
    with an "add to calendar" invitation (`announce_*`).
  * Each person's reminders are booked as rows for exact times, from their
    own preferences (7 days / 1 day / 2 hours by default) (`sync_*`).
  * A worker sends whatever is due, every minute (`send_due_reminders`).
  * Each morning, lawyers get their day on one screen (`send_daily_agendas`).

Moving a hearing rewrites its reminders; vacating it cancels them. A
reminder whose moment passed while nothing was running is skipped, never
sent late in a burst.
"""

import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.firm.models import Firm

from .models import Category, ScheduledReminder
from .services import notify, preferences_for

logger = logging.getLogger(__name__)

# All-day items (filing deadlines, limitation dates) are anchored to the
# start of the working day, so "2 hours before" is 7am, not 10pm the night before.
ALL_DAY_ANCHOR = time(9, 0)
# A reminder more than this late is pointless: skip it.
GRACE = timedelta(minutes=30)


def _fmt(dt, *, all_day=False):
    local = timezone.localtime(dt)
    return f"{local:%a %d %b %Y}" if all_day else f"{local:%a %d %b %Y, %H:%M}"


def _ahead(minutes):
    if minutes % (24 * 60) == 0:
        days = minutes // (24 * 60)
        return "tomorrow" if days == 1 else f"in {days} days"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "in 1 hour" if hours == 1 else f"in {hours} hours"
    return f"in {minutes} minutes"


# --------------------------------------------------------------------------
# Court diary
# --------------------------------------------------------------------------


def court_anchor(event):
    if event.all_day:
        day = timezone.localtime(event.starts_at).date()
        return timezone.make_aware(datetime.combine(day, ALL_DAY_ANCHOR))
    return event.starts_at


def court_recipients(event):
    people = {u for u in event.attendees.all() if u.is_active}
    lead = event.matter.lead_lawyer
    if lead and lead.is_active:
        people.add(lead)
    if event.notify_client:
        client_user = event.matter.client.portal_user
        if client_user and client_user.is_active:
            people.add(client_user)
    return people


def _court_message(event, user, lead_in):
    matter = event.matter
    when = _fmt(event.starts_at, all_day=event.all_day)
    kind = event.get_kind_display()
    if user.is_client:
        lawyer = matter.lead_lawyer.full_name if matter.lead_lawyer else Firm.of(user).name
        subject = f"{lead_in}: your {kind.lower()} on {when}"
        body = (
            f"{lead_in}.\n\n{kind} in your matter {matter.reference} ({matter.title}).\n\n"
            f"When: {when}\nWhere: {event.location or 'To be confirmed'}\nYour lawyer: {lawyer}\n\n"
            "Please arrive at least 30 minutes early with your identity document. Call us if anything is unclear."
        )
        short = f"{Firm.of(user).name}: {kind} {matter.reference}, {when}, {event.location or 'venue TBC'}."
        return subject, body, short, "/portal"

    label = matter.reference if matter.is_restricted else f"{matter.reference} {matter.title}"
    subject = f"{lead_in}: {kind} · {matter.reference} · {when}"
    lines = [f"{lead_in}.", f"{kind}: {event.title}\nMatter: {label}"]
    details = [f"When: {when}"]
    if event.location:
        details.append(f"Where: {event.location}")
    if matter.court and not matter.is_restricted:
        details.append(f"Court: {matter.court}")
    if matter.case_number and not matter.is_restricted:
        details.append(f"Case no.: {matter.case_number}")
    if matter.judge and not matter.is_restricted:
        details.append(f"Before: {matter.judge}")
    lines.append("\n".join(details))
    if event.is_deadline:
        lines.append("This is a deadline. Missing it can be fatal to the client's case.")
    body = "\n\n".join(lines)
    short = f"{kind} {matter.reference} {when}" + (f" at {event.location}" if event.location else "") + "."
    return subject, body, short, f"/matters/{matter.pk}"


def sync_court_event(event):
    """Make the booked reminders match the event as it is now."""
    now = timezone.now()
    live = event.outcome == "pending" and event.starts_at > now
    anchor = court_anchor(event)
    wanted = {}
    if live:
        for person in court_recipients(event):
            for minutes in preferences_for(person).court_offsets:
                wanted[(person.pk, int(minutes))] = anchor - timedelta(minutes=int(minutes))
    _apply(ScheduledReminder.objects.filter(court_event=event), wanted, now, court_event=event)


def announce_court_event(event, change, *, previous_start=None, only_people=None):
    """
    Tell everyone involved, right now. `change` is "created", "moved",
    "updated" or "cancelled". `only_people` narrows it (people just added).
    """
    when = _fmt(event.starts_at, all_day=event.all_day)
    for person in only_people if only_people is not None else court_recipients(event):
        if change == "created":
            lead_in = f"Added to the diary: {event.get_kind_display()} on {when}"
        elif change == "moved":
            before = _fmt(previous_start, all_day=event.all_day) if previous_start else "its previous date"
            lead_in = f"Date changed: now {when} (was {before})"
        elif change == "cancelled":
            lead_in = f"{event.get_kind_display()} {event.get_outcome_display().lower()}: no longer on {when}"
        else:
            lead_in = f"Diary updated: {event.get_kind_display()} on {when}"
        subject, body, short, link = _court_message(event, person, lead_in)
        notify(
            person, subject=subject, body=body, sms=short, link=link, category=Category.DIARY,
            # A change close to the date must reach them even at night.
            urgent=change in {"moved", "cancelled"} and event.starts_at - timezone.now() < timedelta(days=1),
            calendar_ref=f"court_event:{event.pk}", calendar_cancelled=change == "cancelled",
        )


# --------------------------------------------------------------------------
# Appointments
# --------------------------------------------------------------------------


def appointment_recipients(appointment):
    people = set()
    if appointment.lawyer.is_active:
        people.add(appointment.lawyer)
    client_user = appointment.client.portal_user
    if client_user and client_user.is_active:
        people.add(client_user)
    return people


def _appointment_message(appointment, user, lead_in):
    when = _fmt(appointment.starts_at)
    how = appointment.get_mode_display()
    if user.is_client:
        subject = f"{lead_in}: {when}"
        details = [f"When: {when}", f"With: {appointment.lawyer.full_name}", f"How: {how}"]
        if appointment.location:
            details.append(f"Where: {appointment.location}")
        if appointment.video_link:
            details.append(f"Join: {appointment.video_link}")
        body = f"{lead_in}.\n\n" + "\n".join(details)
        short = f"{Firm.of(user).name}: {lead_in}. {when}, {appointment.lawyer.full_name}."
        return subject, body, short, "/portal"

    subject = f"{lead_in}: {appointment.client.name} · {when}"
    details = [f"When: {when}", f"Client: {appointment.client.name}", f"How: {how}"]
    if appointment.location:
        details.append(f"Where: {appointment.location}")
    if appointment.purpose:
        details.append(f"About: {appointment.purpose[:300]}")
    body = f"{lead_in}.\n\n" + "\n".join(details)
    short = f"{lead_in}: {appointment.client.name}, {when} ({how})."
    return subject, body, short, "/appointments"


def sync_appointment(appointment):
    now = timezone.now()
    wanted = {}
    if appointment.status == "confirmed" and appointment.starts_at > now:
        for person in appointment_recipients(appointment):
            for minutes in preferences_for(person).appointment_offsets:
                wanted[(person.pk, int(minutes))] = appointment.starts_at - timedelta(minutes=int(minutes))
    _apply(ScheduledReminder.objects.filter(appointment=appointment), wanted, now, appointment=appointment)


def announce_appointment(appointment, change, *, previous_start=None, include_client=True, include_lawyer=True):
    """`change`: "requested", "confirmed", "moved", "cancelled"."""
    when = _fmt(appointment.starts_at)
    lead_ins = {
        "requested": ("Consultation request received", "New consultation request"),
        "confirmed": ("Your appointment is confirmed", "Appointment confirmed"),
        "moved": (f"Your appointment has moved to {when}", f"Appointment moved to {when}"),
        "cancelled": ("Your appointment was cancelled", "Appointment cancelled"),
    }
    client_lead, lawyer_lead = lead_ins[change]
    if change == "moved" and previous_start:
        client_lead += f" (was {_fmt(previous_start)})"
        lawyer_lead += f" (was {_fmt(previous_start)})"
    if change == "cancelled" and appointment.cancellation_reason:
        client_lead += f": {appointment.cancellation_reason}"
        lawyer_lead += f": {appointment.cancellation_reason}"

    for person in appointment_recipients(appointment):
        if person.is_client and not include_client or not person.is_client and not include_lawyer:
            continue
        lead_in = client_lead if person.is_client else lawyer_lead
        subject, body, short, link = _appointment_message(appointment, person, lead_in)
        if person.is_client and change == "cancelled":
            body += "\n\nPlease contact us to arrange a new time."
        notify(
            person, subject=subject, body=body, sms=short, link=link, category=Category.APPOINTMENT,
            urgent=change in {"moved", "cancelled"} and appointment.starts_at - timezone.now() < timedelta(hours=12),
            calendar_ref=f"appointment:{appointment.pk}" if change != "requested" else "",
            calendar_cancelled=change == "cancelled",
        )


def announce_reassigned(appointment, previous_lawyer):
    if not previous_lawyer.is_active:
        return
    when = _fmt(appointment.starts_at)
    notify(
        previous_lawyer,
        subject=f"Appointment reassigned: {appointment.client.name} · {when}",
        body=f"Your appointment with {appointment.client.name} on {when} is now with {appointment.lawyer.full_name}. "
        "It has been removed from your diary.",
        sms=f"Appointment with {appointment.client.name} {when} reassigned to {appointment.lawyer.full_name}.",
        link="/appointments", category=Category.APPOINTMENT,
        calendar_ref=f"appointment:{appointment.pk}", calendar_cancelled=True,
    )


# --------------------------------------------------------------------------
# The booking ledger
# --------------------------------------------------------------------------


@transaction.atomic
def _apply(existing_qs, wanted, now, **subject):
    existing = {(r.recipient_id, r.offset_minutes): r for r in existing_qs.select_for_update()}

    for key, row in existing.items():
        if key not in wanted and row.status == ScheduledReminder.Status.PENDING:
            row.status = ScheduledReminder.Status.CANCELLED
            row.save(update_fields=["status", "updated_at"])

    for (user_id, minutes), send_at in wanted.items():
        row = existing.get((user_id, minutes))
        # Booking a hearing for the day after tomorrow must not fire the
        # 7-day reminder: the announcement already covered it.
        status = ScheduledReminder.Status.PENDING if send_at > now else ScheduledReminder.Status.SKIPPED
        if row is None:
            ScheduledReminder.objects.create(recipient_id=user_id, offset_minutes=minutes, send_at=send_at, status=status, **subject)
        elif row.send_at != send_at or row.status == ScheduledReminder.Status.CANCELLED:
            # Moved, or revived (e.g. an adjournment set back to pending).
            row.send_at, row.status, row.sent_at = send_at, status, None
            row.save(update_fields=["send_at", "status", "sent_at", "updated_at"])


def send_due_reminders(limit=500):
    now = timezone.now()
    due = (
        ScheduledReminder.objects.filter(status=ScheduledReminder.Status.PENDING, send_at__lte=now)
        .select_related("recipient", "court_event__matter__lead_lawyer", "court_event__matter__client", "appointment__client", "appointment__lawyer")
        .order_by("send_at")[:limit]
    )
    for reminder in due:
        with transaction.atomic():
            # Claim it first, so two workers never send the same reminder.
            claimed = ScheduledReminder.objects.filter(pk=reminder.pk, status=ScheduledReminder.Status.PENDING).update(
                status=ScheduledReminder.Status.SENT, sent_at=now
            )
        if not claimed:
            continue
        if now - reminder.send_at > GRACE:
            ScheduledReminder.objects.filter(pk=reminder.pk).update(status=ScheduledReminder.Status.SKIPPED)
            logger.warning("Skipped reminder %s: %s late", reminder.pk, now - reminder.send_at)
            continue
        try:
            _send_reminder(reminder)
        except Exception:  # noqa: BLE001 - one bad row must not block the rest
            logger.exception("Reminder %s failed", reminder.pk)


def _send_reminder(reminder):
    person = reminder.recipient
    minutes = reminder.offset_minutes
    if reminder.court_event_id:
        event = reminder.court_event
        if event.outcome != "pending":
            return
        lead_in = f"Reminder: {event.get_kind_display().lower()} {_ahead(minutes)}"
        subject, body, short, link = _court_message(event, person, lead_in)
        notify(
            person, subject=subject, body=body, sms=f"Reminder ({_ahead(minutes)}): {short}", link=link,
            category=Category.DIARY, urgent=minutes <= 180, calendar_ref=f"court_event:{event.pk}",
            dedupe_key=f"reminder:{reminder.pk}:{reminder.send_at.isoformat()}",
        )
    else:
        appointment = reminder.appointment
        if appointment.status != "confirmed":
            return
        lead_in = f"Reminder: appointment {_ahead(minutes)}"
        subject, body, short, link = _appointment_message(appointment, person, lead_in)
        notify(
            person, subject=subject, body=body, sms=short, link=link, category=Category.APPOINTMENT,
            urgent=minutes <= 120, calendar_ref=f"appointment:{appointment.pk}",
            dedupe_key=f"reminder:{reminder.pk}:{reminder.send_at.isoformat()}",
        )


# --------------------------------------------------------------------------
# Morning agenda
# --------------------------------------------------------------------------


def send_daily_agendas():
    from apps.accounts.models import User
    from apps.appointments.models import Appointment
    from apps.matters.models import CourtEvent

    local_now = timezone.localtime()
    today = local_now.date()
    if today.weekday() >= 5 and not settings.LEXDESK_AGENDA_ON_WEEKENDS:
        return
    start = timezone.make_aware(datetime.combine(today, time.min))
    end = start + timedelta(days=1)

    for user in User.objects.filter(is_active=True).exclude(role="client"):
        prefs = preferences_for(user)
        if not prefs.daily_agenda or prefs.last_agenda_on == today or local_now.time() < prefs.daily_agenda_at:
            continue

        events = list(
            CourtEvent.objects.filter(starts_at__gte=start, starts_at__lt=end, outcome="pending")
            .filter(Q(attendees=user) | Q(matter__lead_lawyer=user)).distinct().select_related("matter").order_by("starts_at")
        )
        appointments = list(
            Appointment.objects.filter(lawyer=user, starts_at__gte=start, starts_at__lt=end, status="confirmed")
            .select_related("client").order_by("starts_at")
        )
        # Mark first: if sending fails half-way, a second agenda is worse.
        prefs.last_agenda_on = today
        prefs.save(update_fields=["last_agenda_on", "updated_at"])
        if not events and not appointments:
            continue

        items = []
        for e in events:
            at = "All day" if e.all_day else f"{timezone.localtime(e.starts_at):%H:%M}"
            where = f" · {e.location}" if e.location else ""
            items.append((e.starts_at, f"{at}  {e.get_kind_display()} · {e.matter.reference}{where}"))
        for a in appointments:
            items.append((a.starts_at, f"{timezone.localtime(a.starts_at):%H:%M}  Consultation · {a.client.name} ({a.get_mode_display()})"))
        lines = [text for _, text in sorted(items, key=lambda pair: pair[0])]

        count = len(lines)
        subject = f"Your day, {today:%A %d %B}: {count} item{'s' if count != 1 else ''}"
        body = f"Good morning {user.first_name}.\n\n" + "\n".join(lines)
        if any(e.is_deadline for e in events):
            body += "\n\nA deadline falls today."
        notify(
            user, subject=subject, body=body, sms=" | ".join(lines)[:300], link="/diary", category=Category.AGENDA,
            in_app=False, dedupe_key=f"agenda:{today.isoformat()}",
        )
