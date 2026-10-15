from datetime import datetime, time, timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.appointments.models import Appointment
from apps.clients.models import Client
from apps.core.testing import api_as, make_client, make_user


def next_weekday_at(hour, minute=0):
    day = timezone.localdate() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


class PublicBookingTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER, title="Senior Associate")
        self.api = APIClient()

    def _book(self, **overrides):
        data = {
            "name": "Sarah Nakato", "email": "sarah@mail.test", "phone": "+256772000000",
            "lawyer": str(self.lawyer.id), "starts_at": next_weekday_at(10).isoformat(),
            "mode": "video", "purpose": "Land dispute with a neighbour", **overrides,
        }
        with self.captureOnCommitCallbacks(execute=True):
            return self.api.post("/api/v1/appointments/public/book/", data, format="json")

    def test_booking_creates_client_portal_account_and_request(self):
        r = self._book()
        self.assertEqual(r.status_code, 201, r.data)
        client = Client.objects.get(email="sarah@mail.test")
        self.assertEqual(client.source, Client.Source.WEBSITE)
        self.assertEqual(client.portal_user.role, Role.CLIENT)
        self.assertEqual(Appointment.objects.get().status, Appointment.Status.REQUESTED)
        self.assertTrue(any("client portal" in m.body for m in mail.outbox))

    def test_returning_client_does_not_get_a_second_account(self):
        self._book()
        self._book(starts_at=next_weekday_at(11).isoformat(), email="SARAH@mail.test")
        self.assertEqual(User.objects.filter(email__iexact="sarah@mail.test").count(), 1)
        self.assertEqual(Client.objects.count(), 1)

    def test_double_booking_is_refused(self):
        self._book()
        r = self._book(email="someone.else@mail.test")
        self.assertEqual(r.status_code, 400)

    def test_honeypot_silently_drops_bots(self):
        r = self._book(website="http://spam.example")
        self.assertEqual(r.status_code, 201)
        self.assertFalse(Appointment.objects.exists())

    def test_availability_hides_taken_slots(self):
        self._book()
        day = next_weekday_at(10).date()
        r = self.api.get(f"/api/v1/appointments/public/availability/?lawyer={self.lawyer.id}&date={day}")
        starts = {timezone.localtime(datetime.fromisoformat(s["starts_at"])).time() for s in r.json()["slots"]}
        self.assertNotIn(time(10, 0), starts)
        self.assertIn(time(11, 0), starts)

    def test_receptionist_confirms_and_client_is_told(self):
        self._book()
        appt = Appointment.objects.get()
        mail.outbox.clear()
        r = api_as(make_user(Role.RECEPTIONIST)).post(f"/api/v1/appointments/{appt.id}/confirm/")
        self.assertEqual(r.data["status"], "confirmed")
        self.assertTrue(any("confirmed" in m.subject for m in mail.outbox))


class ClientSelfServiceTests(TestCase):
    def test_client_books_for_themselves_only(self):
        lawyer = make_user(Role.LAWYER)
        user = make_user(Role.CLIENT)
        own = make_client(portal_user=user)
        other = make_client(name="Someone Else", email="else@mail.test")
        r = api_as(user).post("/api/v1/appointments/", {
            "client": str(other.id),  # ignored: clients always book as themselves
            "lawyer": str(lawyer.id), "starts_at": next_weekday_at(14).isoformat(),
            "ends_at": next_weekday_at(14, 30).isoformat(), "purpose": "Follow-up",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Appointment.objects.get().client, own)
        self.assertNotIn("internal_notes", r.data)
