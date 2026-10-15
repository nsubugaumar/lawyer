"""
iCalendar (RFC 5545) for court dates and appointments.

Two uses: an "add to calendar" attachment on every diary email, and a private
subscription feed so a lawyer's phone calendar always mirrors the firm diary,
with its own alarms, even when they are offline in a courtroom.
"""

from datetime import UTC, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.firm.models import Firm

PRODID = "-//LexDesk//Court Diary//EN"


def _escape(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a space."""
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, chunk = [], b""
    for char in line:
        encoded = char.encode()
        if len(chunk) + len(encoded) > (75 if not parts else 74):
            parts.append(chunk.decode())
            chunk = b""
        chunk += encoded
    parts.append(chunk.decode())
    return "\r\n ".join(parts)


def _utc(dt) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _vevent(*, uid, start, end, all_day, summary, location="", description="", url="", alarms=(), updated, cancelled=False):
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@{settings.LEXDESK_EMAIL_DOMAIN}",
        f"DTSTAMP:{_utc(timezone.now())}",
        f"LAST-MODIFIED:{_utc(updated)}",
        # Must grow with every change so calendars replace the old copy.
        f"SEQUENCE:{int(updated.timestamp())}",
    ]
    if all_day:
        day = timezone.localtime(start).date()
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    else:
        lines += [f"DTSTART:{_utc(start)}", f"DTEND:{_utc(end)}"]
    lines.append(f"SUMMARY:{_escape(summary)}")
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if url:
        lines.append(f"URL:{url}")
    lines.append("STATUS:CANCELLED" if cancelled else "STATUS:CONFIRMED")
    lines.append("TRANSP:OPAQUE")
    if not cancelled:
        for minutes in sorted(set(alarms)):
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"TRIGGER:-PT{int(minutes)}M",
                f"DESCRIPTION:{_escape(summary)}",
                "END:VALARM",
            ]
    lines.append("END:VEVENT")
    return lines


def _calendar(vevents, *, name=None):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    if name:
        lines += [f"X-WR-CALNAME:{_escape(name)}", f"X-WR-TIMEZONE:{settings.TIME_ZONE}", "REFRESH-INTERVAL;VALUE=DURATION:PT15M", "X-PUBLISHED-TTL:PT15M"]
    for vevent in vevents:
        lines += vevent
    lines.append("END:VCALENDAR")
    return ("\r\n".join(_fold(line) for line in lines) + "\r\n").encode()


def _web(path):
    return f"{settings.LEXDESK_WEB_URL}{path}" if settings.LEXDESK_WEB_URL else ""


def court_vevent(event, user, *, cancelled=False):
    from .services import preferences_for

    matter = event.matter
    is_client = user.is_client
    if is_client:
        summary = f"{event.get_kind_display()} · {matter.reference}"
        description = f"{matter.title}\nYour lawyer: {matter.lead_lawyer.full_name if matter.lead_lawyer else Firm.of(user).name}"
        url = _web("/portal")
    else:
        # A walled matter shows only its reference on a phone's lock screen.
        label = matter.reference if matter.is_restricted else f"{matter.reference} {matter.title}"
        summary = f"{event.get_kind_display()} · {label}"
        description = "" if matter.is_restricted else f"{event.title}\n{matter.court}".strip()
        url = _web(f"/matters/{matter.pk}")
    return _vevent(
        uid=f"court-{event.pk}", start=event.starts_at, end=event.ends_at or event.starts_at + timedelta(hours=1),
        all_day=event.all_day, summary=summary, location=event.location, description=description, url=url,
        alarms=preferences_for(user).court_offsets, updated=event.updated_at, cancelled=cancelled,
    )


def appointment_vevent(appointment, user, *, cancelled=False):
    from .services import preferences_for

    if user.is_client:
        summary = f"Appointment with {appointment.lawyer.full_name} ({Firm.of(user).name})"
        url = _web("/portal")
    else:
        summary = f"Consultation · {appointment.client.name}"
        url = _web("/appointments")
    description = appointment.get_mode_display()
    if appointment.video_link:
        description += f"\nJoin: {appointment.video_link}"
    return _vevent(
        uid=f"appointment-{appointment.pk}", start=appointment.starts_at, end=appointment.ends_at, all_day=False,
        summary=summary, location=appointment.location or appointment.video_link, description=description, url=url,
        alarms=preferences_for(user).appointment_offsets, updated=appointment.updated_at, cancelled=cancelled,
    )


def invite(calendar_ref: str, user, *, cancelled=False) -> bytes | None:
    """The attachment for one email. None if the event no longer exists."""
    from apps.appointments.models import Appointment
    from apps.matters.models import CourtEvent

    from apps.core.ids import as_uuid

    kind, _, pk = calendar_ref.partition(":")
    if not as_uuid(pk):
        return None
    if kind == "court_event":
        event = CourtEvent.objects.select_related("matter", "matter__lead_lawyer").filter(pk=pk).first()
        return _calendar([court_vevent(event, user, cancelled=cancelled)]) if event else None
    if kind == "appointment":
        appointment = Appointment.objects.select_related("client", "lawyer").filter(pk=pk).first()
        return _calendar([appointment_vevent(appointment, user, cancelled=cancelled)]) if appointment else None
    return None


def feed(user) -> bytes:
    """Everything in this person's diary from 60 days ago to a year ahead."""
    from apps.appointments.models import Appointment
    from apps.matters.models import CourtEvent

    now = timezone.now()
    window = Q(starts_at__gte=now - timedelta(days=60), starts_at__lte=now + timedelta(days=366))
    vevents = []

    if user.is_client:
        events = CourtEvent.objects.filter(window, matter__client__portal_user=user, notify_client=True)
        appointments = Appointment.objects.filter(window, client__portal_user=user)
    else:
        events = CourtEvent.objects.filter(window).filter(Q(attendees=user) | Q(matter__lead_lawyer=user)).distinct()
        appointments = Appointment.objects.filter(window, lawyer=user)

    for event in events.select_related("matter", "matter__lead_lawyer").exclude(outcome="vacated"):
        vevents.append(court_vevent(event, user))
    for appointment in appointments.select_related("client", "lawyer").exclude(status="cancelled"):
        vevents.append(appointment_vevent(appointment, user))
    return _calendar(vevents, name=f"{Firm.of(user).name} diary")
