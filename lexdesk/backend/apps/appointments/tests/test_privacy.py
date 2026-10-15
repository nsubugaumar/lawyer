from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role
from apps.appointments.models import Appointment
from apps.core.testing import api_as, make_client, make_user
from apps.notifications.models import Notification


class AppointmentGoesToItsLawyerTests(TestCase):
    def setUp(self):
        self.grace = make_user(Role.LAWYER)
        self.brian = make_user(Role.LAWYER)
        self.reception = make_user(Role.RECEPTIONIST)
        self.partner = make_user(Role.PARTNER)
        self.client_record = make_client()
        start = timezone.now() + timedelta(days=2)
        Appointment.objects.create(client=self.client_record, lawyer=self.grace, starts_at=start, ends_at=start + timedelta(minutes=30),
                                   purpose="Private matter", status="confirmed")

    def count(self, user):
        return api_as(user).get("/api/v1/appointments/").data["count"]

    def test_only_the_chosen_lawyer_sees_it(self):
        self.assertEqual(self.count(self.grace), 1)
        self.assertEqual(self.count(self.brian), 0)
        self.assertEqual(self.count(make_user(Role.ACCOUNTANT)), 0)

    def test_front_desk_and_partners_keep_the_firm_diary(self):
        self.assertEqual(self.count(self.reception), 1)
        self.assertEqual(self.count(self.partner), 1)

    def test_booking_notifies_only_that_lawyer(self):
        start = timezone.now() + timedelta(days=3)
        with self.captureOnCommitCallbacks(execute=True):
            api_as(self.reception).post("/api/v1/appointments/", {
                "client": str(self.client_record.pk), "lawyer": str(self.grace.pk), "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(), "purpose": "Advice",
            }, format="json")
        self.assertTrue(Notification.objects.filter(recipient=self.grace, category="appointment").exists())
        self.assertFalse(Notification.objects.filter(recipient=self.brian).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.partner).exists())
