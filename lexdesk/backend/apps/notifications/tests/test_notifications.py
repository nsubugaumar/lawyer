import hashlib
import hmac
import json
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from unittest import mock

from urllib.parse import urlparse

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Role
from apps.appointments.models import Appointment
from apps.core.testing import api_as, make_client, make_matter, make_user
from apps.matters.models import CourtEvent
from apps.notifications import channels, ics, reminders, services
from apps.notifications.models import CalendarFeed, Category, Channel, Delivery, Notification, ScheduledReminder

# A Tuesday morning in Kampala, well outside quiet hours.
NOW = timezone.make_aware(datetime(2026, 10, 20, 10, 0))


@contextmanager
def at(moment):
    with mock.patch("django.utils.timezone.now", return_value=moment):
        yield


def deliveries(user, channel=None):
    qs = Delivery.objects.filter(notification__recipient=user)
    return qs.filter(channel=channel) if channel else qs


class NotifyTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER, phone="0772 123 456")

    def test_reaches_every_channel_the_person_chose(self):
        with at(NOW):
            services.notify(self.lawyer, subject="Hearing", body="Details", sms="Short", category=Category.DIARY)
        self.assertEqual(Notification.objects.get().in_app, True)
        self.assertEqual(deliveries(self.lawyer, Channel.EMAIL).get().status, Delivery.Status.SENT)
        whatsapp = deliveries(self.lawyer, Channel.WHATSAPP).get()
        self.assertEqual(whatsapp.status, Delivery.Status.SENT)
        self.assertEqual(whatsapp.address, "+256772123456")
        self.assertFalse(deliveries(self.lawyer, Channel.SMS).exists())  # WhatsApp worked; no SMS needed
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("<html", mail.outbox[0].alternatives[0][0])

    def test_security_mail_ignores_preferences_and_never_uses_whatsapp(self):
        prefs = services.preferences_for(self.lawyer)
        prefs.channels = {**prefs.channels, Category.SECURITY: [Channel.WHATSAPP]}
        prefs.save()
        with at(NOW):
            services.notify(self.lawyer, subject="Reset", body="link", sms="Check email", category=Category.SECURITY)
        self.assertTrue(deliveries(self.lawyer, Channel.EMAIL).exists())
        self.assertFalse(deliveries(self.lawyer, Channel.WHATSAPP).exists())

    def test_whatsapp_that_cannot_be_delivered_falls_back_to_sms(self):
        with at(NOW), mock.patch.object(channels, "send_whatsapp", side_effect=channels.PermanentFailure("131026 not on WhatsApp")):
            services.notify(self.lawyer, subject="Hearing", body="Details", sms="Short", category=Category.DIARY)
        self.assertEqual(deliveries(self.lawyer, Channel.WHATSAPP).get().status, Delivery.Status.FAILED)
        sms = deliveries(self.lawyer, Channel.SMS).get()
        self.assertTrue(sms.is_fallback)
        self.assertEqual(sms.status, Delivery.Status.SENT)

    def test_outage_is_retried_with_back_off(self):
        with at(NOW), mock.patch.object(channels, "send_whatsapp", side_effect=channels.TemporaryFailure("503")):
            services.notify(self.lawyer, subject="Hearing", body="Details", sms="Short", category=Category.DIARY)
        whatsapp = deliveries(self.lawyer, Channel.WHATSAPP).get()
        self.assertEqual((whatsapp.status, whatsapp.attempts), (Delivery.Status.QUEUED, 1))
        self.assertEqual(whatsapp.next_attempt_at, NOW + timedelta(minutes=1))

        with at(NOW + timedelta(seconds=30)):
            services.retry_due_deliveries()  # too early
        with at(NOW + timedelta(minutes=2)):
            services.retry_due_deliveries()
        whatsapp.refresh_from_db()
        self.assertEqual((whatsapp.status, whatsapp.attempts), (Delivery.Status.SENT, 2))

    def test_texts_wait_for_the_end_of_quiet_hours_unless_urgent(self):
        night = timezone.make_aware(datetime(2026, 10, 20, 23, 0))
        with at(night):
            services.notify(self.lawyer, subject="FYI", body="x", sms="x", category=Category.DIARY)
            services.notify(self.lawyer, subject="Hearing moved to 8am", body="x", sms="x", category=Category.DIARY, urgent=True)
        held, sent = deliveries(self.lawyer, Channel.WHATSAPP).order_by("notification__urgent")
        self.assertEqual(held.status, Delivery.Status.QUEUED)
        self.assertEqual(timezone.localtime(held.next_attempt_at), timezone.make_aware(datetime(2026, 10, 21, 7, 0)))
        self.assertEqual(sent.status, Delivery.Status.SENT)
        # Email is never held: it does not buzz anyone's phone at night.
        self.assertEqual(deliveries(self.lawyer, Channel.EMAIL).filter(status=Delivery.Status.SENT).count(), 2)

    def test_dedupe_key_makes_notify_idempotent(self):
        with at(NOW):
            services.notify(self.lawyer, subject="A", body="b", dedupe_key="k1")
            services.notify(self.lawyer, subject="A", body="b", dedupe_key="k1")
        self.assertEqual(Notification.objects.count(), 1)

    def test_clients_get_no_whatsapp_until_they_opt_in(self):
        client = make_user(Role.CLIENT, phone="+256700111222")
        with at(NOW):
            services.notify(client, subject="Appointment", body="x", sms="x", category=Category.APPOINTMENT)
        self.assertFalse(deliveries(client, Channel.WHATSAPP).exists())
        self.assertTrue(deliveries(client, Channel.SMS).get().is_fallback)

    def test_body_is_encrypted_at_rest(self):
        with at(NOW):
            services.notify(self.lawyer, subject="A", body="Privileged strategy")
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT body FROM notifications_notification")
            self.assertNotIn("Privileged", cursor.fetchone()[0])


class PhoneTests(TestCase):
    def test_normalise(self):
        cases = {
            "0772 123 456": "+256772123456",
            "+256 (772) 123-456": "+256772123456",
            "256772123456": "+256772123456",
            "00254712345678": "+254712345678",
            "772123456": "+256772123456",
            "12": "",
            "": "",
        }
        for raw, expected in cases.items():
            self.assertEqual(channels.normalise_phone(raw), expected, raw)


class CourtDiaryTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER, phone="0772123456")
        self.associate = make_user(Role.LAWYER, phone="0772999888")
        self.matter = make_matter(self.lawyer)
        self.api = api_as(self.lawyer)

    def _create(self, starts_at, **extra):
        payload = {"matter": str(self.matter.pk), "kind": "hearing", "title": "Hearing of the application",
                   "starts_at": starts_at.isoformat(), "location": "High Court, Room 4", **extra}
        with at(NOW), self.captureOnCommitCallbacks(execute=True):
            response = self.api.post("/api/v1/diary/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return CourtEvent.objects.get(pk=response.data["id"])

    def test_setting_a_date_notifies_the_lawyer_at_once_with_a_calendar_invite(self):
        event = self._create(NOW + timedelta(days=10))
        self.assertEqual(list(event.attendees.all()), [self.lawyer])  # the person diarising is going
        note = Notification.objects.get(recipient=self.lawyer)
        self.assertIn("Added to the diary", note.title)
        self.assertEqual(note.category, Category.DIARY)
        self.assertEqual(deliveries(self.lawyer, Channel.WHATSAPP).get().status, Delivery.Status.SENT)
        attachment = mail.outbox[-1].attachments[0]
        self.assertEqual(attachment[0], "invite.ics")
        self.assertIn("BEGIN:VEVENT", attachment[1].decode() if isinstance(attachment[1], bytes) else attachment[1])

    def test_reminders_are_booked_for_exact_times(self):
        starts = NOW + timedelta(days=10)
        event = self._create(starts)
        booked = {r.offset_minutes: r for r in ScheduledReminder.objects.filter(court_event=event, recipient=self.lawyer)}
        self.assertEqual(set(booked), {7 * 24 * 60, 24 * 60, 120})
        self.assertEqual(booked[120].send_at, starts - timedelta(hours=2))
        self.assertTrue(all(r.status == ScheduledReminder.Status.PENDING for r in booked.values()))

    def test_windows_already_passed_are_skipped_not_sent(self):
        event = self._create(NOW + timedelta(days=2))
        week = ScheduledReminder.objects.get(court_event=event, offset_minutes=7 * 24 * 60)
        self.assertEqual(week.status, ScheduledReminder.Status.SKIPPED)

    def test_due_reminder_goes_out_once(self):
        starts = NOW + timedelta(days=10)
        event = self._create(starts)
        Notification.objects.all().delete()
        moment = starts - timedelta(days=1)
        with at(moment):
            reminders.send_due_reminders()
            reminders.send_due_reminders()
        notes = Notification.objects.filter(recipient=self.lawyer)
        self.assertEqual(notes.count(), 1)
        self.assertIn("tomorrow", notes.get().title)
        self.assertEqual(ScheduledReminder.objects.get(court_event=event, offset_minutes=24 * 60).status, ScheduledReminder.Status.SENT)

    def test_a_reminder_found_hours_late_is_skipped(self):
        starts = NOW + timedelta(days=10)
        self._create(starts)
        Notification.objects.all().delete()
        with at(starts - timedelta(days=1) + timedelta(hours=3)):
            reminders.send_due_reminders()
        self.assertFalse(Notification.objects.exists())

    def test_moving_a_hearing_moves_its_reminders_and_tells_everyone(self):
        starts = NOW + timedelta(days=10)
        event = self._create(starts, attendees=[str(self.lawyer.pk), str(self.associate.pk)])
        new_start = starts + timedelta(days=7)
        with at(NOW), self.captureOnCommitCallbacks(execute=True):
            response = self.api.patch(f"/api/v1/diary/{event.pk}/", {"starts_at": new_start.isoformat()}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        two_hours = ScheduledReminder.objects.get(court_event=event, recipient=self.associate, offset_minutes=120)
        self.assertEqual(two_hours.send_at, new_start - timedelta(hours=2))
        for person in (self.lawyer, self.associate):
            self.assertTrue(Notification.objects.filter(recipient=person, title__startswith="Date changed").exists())

    def test_vacating_cancels_reminders(self):
        event = self._create(NOW + timedelta(days=10))
        with at(NOW), self.captureOnCommitCallbacks(execute=True):
            self.api.patch(f"/api/v1/diary/{event.pk}/", {"outcome": "vacated"}, format="json")
        self.assertFalse(ScheduledReminder.objects.filter(court_event=event, status=ScheduledReminder.Status.PENDING).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.lawyer, title__contains="vacated").exists())

    def test_someone_added_later_is_told_and_reminded(self):
        event = self._create(NOW + timedelta(days=10))
        with at(NOW), self.captureOnCommitCallbacks(execute=True):
            self.api.patch(f"/api/v1/diary/{event.pk}/", {"attendees": [str(self.lawyer.pk), str(self.associate.pk)]}, format="json")
        self.assertTrue(Notification.objects.filter(recipient=self.associate, title__startswith="Added to the diary").exists())
        self.assertEqual(Notification.objects.filter(recipient=self.lawyer).count(), 1)  # not told twice
        self.assertEqual(ScheduledReminder.objects.filter(court_event=event, recipient=self.associate).count(), 3)

    def test_client_is_told_only_when_asked(self):
        client_user = make_user(Role.CLIENT, email="jane@client.test")
        self.matter.client.portal_user = client_user
        self.matter.client.save()
        self._create(NOW + timedelta(days=10))
        self.assertFalse(Notification.objects.filter(recipient=client_user).exists())
        self._create(NOW + timedelta(days=12), notify_client=True)
        note = Notification.objects.get(recipient=client_user)
        self.assertEqual(note.link, "/portal")
        self.assertNotIn("Before:", note.body)  # internal detail stays internal

    def test_clients_cannot_be_attendees(self):
        client_user = make_user(Role.CLIENT)
        payload = {"matter": str(self.matter.pk), "kind": "hearing", "title": "x", "starts_at": (NOW + timedelta(days=3)).isoformat(),
                   "attendees": [str(client_user.pk)]}
        self.assertEqual(self.api.post("/api/v1/diary/", payload, format="json").status_code, 400)

    def test_all_day_deadline_reminders_anchor_to_the_working_day(self):
        day = (NOW + timedelta(days=5)).date()
        event = self._create(timezone.make_aware(datetime.combine(day, time(0, 0))), kind="filing_deadline", all_day=True)
        two_hours = ScheduledReminder.objects.get(court_event=event, offset_minutes=120)
        self.assertEqual(timezone.localtime(two_hours.send_at).time(), time(7, 0))


class AppointmentTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER, phone="0772123456")
        self.client_user = make_user(Role.CLIENT, email="jane@client.test", phone="0700111222")
        self.client_record = make_client(portal_user=self.client_user)

    def test_staff_booking_tells_both_sides_and_books_reminders(self):
        starts = NOW + timedelta(days=3)
        with at(NOW), self.captureOnCommitCallbacks(execute=True):
            response = api_as(self.lawyer).post("/api/v1/appointments/", {
                "client": str(self.client_record.pk), "lawyer": str(self.lawyer.pk), "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(minutes=30)).isoformat(), "purpose": "Land dispute",
            }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(Notification.objects.filter(recipient=self.client_user, title__startswith="Your appointment is confirmed").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.lawyer, title__startswith="Appointment confirmed").exists())
        appointment = Appointment.objects.get()
        self.assertEqual(ScheduledReminder.objects.filter(appointment=appointment).count(), 4)  # 2 people x (1 day, 1 hour)

        with at(NOW):
            api_as(self.lawyer).post(f"/api/v1/appointments/{appointment.pk}/cancel/", {"reason": "Court clash"}, format="json")
        self.assertFalse(ScheduledReminder.objects.filter(appointment=appointment, status=ScheduledReminder.Status.PENDING).exists())
        cancelled = Notification.objects.get(recipient=self.client_user, title__startswith="Your appointment was cancelled")
        self.assertIn("Court clash", cancelled.title)


class PreferenceTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER, phone="0772123456")
        self.api = api_as(self.lawyer)

    def test_read_and_update(self):
        data = self.api.get("/api/v1/notifications/preferences/").data
        self.assertTrue(data["whatsapp_active"])
        self.assertEqual(data["whatsapp_number_in_use"], "+256772123456")
        security = next(c for c in data["categories"] if c["key"] == "security")
        self.assertEqual((security["locked"], security["unavailable"]), (["email"], ["whatsapp"]))

        response = self.api.patch("/api/v1/notifications/preferences/", {"whatsapp_enabled": False, "court_offsets": [60, 3 * 24 * 60]}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["whatsapp_active"])
        self.assertEqual(response.data["court_offsets"], [3 * 24 * 60, 60])

    def test_changing_reminder_times_rebooks_upcoming_reminders(self):
        matter = make_matter(self.lawyer)
        with at(NOW):
            event = CourtEvent.objects.create(matter=matter, title="Mention", starts_at=NOW + timedelta(days=10))
            self.api.patch("/api/v1/notifications/preferences/", {"court_offsets": [30]}, format="json")
        pending = ScheduledReminder.objects.filter(court_event=event, status=ScheduledReminder.Status.PENDING)
        self.assertEqual(list(pending.values_list("offset_minutes", flat=True)), [30])

    def test_rejects_bad_values(self):
        for payload in ({"court_offsets": [1]}, {"court_offsets": "soon"}, {"channels": {"diary": ["pigeon"]}}, {"whatsapp_number": "call me"}):
            self.assertEqual(self.api.patch("/api/v1/notifications/preferences/", payload, format="json").status_code, 400, payload)

    def test_send_a_test_message(self):
        with at(NOW):
            response = self.api.post("/api/v1/notifications/test/", {"channel": "whatsapp"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["deliveries"][0]["status"], "sent")


class BellTests(TestCase):
    def test_unread_count_and_read_all(self):
        user = make_user(Role.LAWYER)
        with at(NOW):
            services.notify(user, subject="One", body="x")
            services.notify(user, subject="Hidden", body="x", in_app=False)
        api = api_as(user)
        self.assertEqual(api.get("/api/v1/notifications/unread-count/").data["unread"], 1)
        self.assertEqual(api.get("/api/v1/notifications/").data["count"], 1)
        api.post("/api/v1/notifications/read-all/")
        self.assertEqual(api.get("/api/v1/notifications/unread-count/").data["unread"], 0)

    def test_other_peoples_notifications_are_invisible(self):
        a, b = make_user(Role.LAWYER), make_user(Role.LAWYER)
        with at(NOW):
            services.notify(a, subject="Mine", body="x")
        self.assertEqual(api_as(b).get("/api/v1/notifications/").data["count"], 0)


class CalendarFeedTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER)
        self.matter = make_matter(self.lawyer, restricted=True, title="Secret v. Very Secret")
        CourtEvent.objects.create(matter=self.matter, title="Trial", starts_at=timezone.now() + timedelta(days=4), location="Court 1")

    def test_issue_fetch_revoke(self):
        api = api_as(self.lawyer)
        url = api.post("/api/v1/notifications/calendar-feed/").data["url"]
        path = urlparse(url).path
        self.assertTrue(url.startswith(settings.LEXDESK_WEB_URL))  # the firm's own address, not an internal host
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn(self.matter.reference, body)
        self.assertNotIn("Very Secret", body)  # walled matter: reference only
        self.assertIn("BEGIN:VALARM", body)
        self.assertTrue(all(len(line.encode()) <= 75 for line in body.split("\r\n")))
        self.assertFalse(CalendarFeed.objects.filter(token_hash__contains=path.rsplit("/", 1)[1][:-4]).exists())  # only the hash is kept

        api.delete("/api/v1/notifications/calendar-feed/")
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_long_lines_fold(self):
        folded = ics._fold("DESCRIPTION:" + "é" * 100)
        self.assertTrue(all(len(part.encode()) <= 75 for part in folded.split("\r\n")))
        self.assertEqual(folded.replace("\r\n ", ""), "DESCRIPTION:" + "é" * 100)


@override_settings(WHATSAPP_APP_SECRET="s3cret", WHATSAPP_WEBHOOK_VERIFY_TOKEN="verify-me")
class WhatsAppWebhookTests(TestCase):
    URL = "/api/v1/notifications/whatsapp/webhook/"

    def _post(self, payload, secret="s3cret"):
        body = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(self.URL, body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)

    def test_handshake(self):
        ok = self.client.get(self.URL, {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
        self.assertEqual((ok.status_code, ok.content), (200, b"42"))
        self.assertEqual(self.client.get(self.URL, {"hub.mode": "subscribe", "hub.verify_token": "nope"}).status_code, 403)

    def test_receipts_update_delivery_and_never_go_backwards(self):
        lawyer = make_user(Role.LAWYER, phone="0772123456")
        with at(NOW):
            services.notify(lawyer, subject="x", body="x", sms="x", category=Category.DIARY)
        delivery = deliveries(lawyer, Channel.WHATSAPP).get()
        for status in ("read", "delivered"):
            payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": delivery.provider_message_id, "status": status}]}}]}]}
            self.assertEqual(self._post(payload).status_code, 200)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, Delivery.Status.READ)

    def test_forged_requests_are_refused(self):
        self.assertEqual(self._post({"entry": []}, secret="wrong").status_code, 403)

    def test_stop_opts_out(self):
        lawyer = make_user(Role.LAWYER, phone="0772 123 456")
        payload = {"entry": [{"changes": [{"value": {"messages": [{"from": "256772123456", "text": {"body": "STOP"}}]}}]}]}
        self.assertEqual(self._post(payload).status_code, 200)
        self.assertFalse(services.preferences_for(type(lawyer).objects.get(pk=lawyer.pk)).whatsapp_active)


class DailyAgendaTests(TestCase):
    def test_one_agenda_per_morning_listing_the_day(self):
        lawyer = make_user(Role.LAWYER, phone="0772123456")
        matter = make_matter(lawyer)
        morning = timezone.make_aware(datetime(2026, 10, 20, 6, 45))
        with at(morning - timedelta(days=1)):
            CourtEvent.objects.create(matter=matter, title="Hearing", starts_at=morning.replace(hour=9, minute=0), location="Court 2")
        with at(morning):
            reminders.send_daily_agendas()
            reminders.send_daily_agendas()
        agenda = Notification.objects.get(recipient=lawyer, category=Category.AGENDA)
        self.assertIn("09:00", agenda.body)
        self.assertIn(matter.reference, agenda.body)
        self.assertFalse(agenda.in_app)

    def test_nothing_when_the_day_is_empty(self):
        make_user(Role.LAWYER)
        with at(timezone.make_aware(datetime(2026, 10, 20, 7, 0))):
            reminders.send_daily_agendas()
        self.assertFalse(Notification.objects.exists())
