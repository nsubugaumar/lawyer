"""
Keep booked reminders in step with the diary, whichever way it changes: the
API, the admin site, a data import. Announcements to people are made by the
views, deliberately, so a bulk import does not text the whole firm.
"""

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.matters.models import CourtEvent, Matter

from . import reminders


@receiver(post_save, sender=CourtEvent)
def court_event_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        reminders.sync_court_event(instance)


@receiver(m2m_changed, sender=CourtEvent.attendees.through)
def court_event_attendees_changed(sender, instance, action, reverse=False, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if reverse:
        # user.court_events.add(...): resync each affected event.
        for event in CourtEvent.objects.filter(pk__in=kwargs.get("pk_set") or []):
            reminders.sync_court_event(event)
    else:
        reminders.sync_court_event(instance)


@receiver(post_save, sender=Appointment)
def appointment_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        reminders.sync_appointment(instance)


@receiver(post_save, sender=Matter)
def matter_saved(sender, instance, created=False, raw=False, update_fields=None, **kwargs):
    # A new lead lawyer inherits the matter's upcoming court dates.
    if raw or created or (update_fields and "lead_lawyer" not in update_fields):
        return
    for event in CourtEvent.objects.filter(matter=instance, outcome="pending", starts_at__gt=timezone.now()):
        reminders.sync_court_event(event)
