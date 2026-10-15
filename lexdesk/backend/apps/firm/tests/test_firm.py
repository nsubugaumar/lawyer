from datetime import date, time
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import Role
from apps.appointments.services import available_slots
from apps.core.testing import api_as, make_user
from apps.firm.models import Firm
from apps.notifications import channels

URL = "/api/v1/firm/settings/"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FirmSettingsTests(TestCase):
    def firm(self):
        return Firm.objects.get(pk=self.manager.firm_id)

    def setUp(self):
        self.manager = make_user(Role.ADMIN)
        self.api = api_as(self.manager)

    def test_only_managers_can_change_the_firm(self):
        for role in (Role.LAWYER, Role.RECEPTIONIST, Role.CLIENT):
            self.assertEqual(api_as(make_user(role)).get(URL).status_code, 403, role)
        self.assertEqual(api_as(make_user(Role.PARTNER)).get(URL).status_code, 200)

    def test_update_profile_contacts_and_social_media(self):
        response = self.api.patch(URL, {
            "name": "Kampala Associated Advocates",
            "phone": "0414 123456",
            "whatsapp_number": "0772 123 456",
            "instagram_url": "@kampalaadvocates",
            "facebook_url": "facebook.com/kampalaadvocates",
            "x_url": "https://twitter.com/kaa_law",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["instagram_url"], "https://www.instagram.com/kampalaadvocates")
        self.assertEqual(response.data["facebook_url"], "https://facebook.com/kampalaadvocates")
        self.assertEqual(response.data["whatsapp_number"], "+256772123456")

        public = self.client.get("/api/v1/firm/public/").json()
        self.assertEqual(public["name"], "Kampala Associated Advocates")
        self.assertEqual(public["whatsapp_link"], "https://wa.me/256772123456")
        self.assertEqual({s["network"] for s in public["socials"]}, {"instagram", "facebook", "x"})
        self.assertNotIn("whatsapp_access_token", public)

    def test_a_link_to_the_wrong_network_is_refused(self):
        response = self.api.patch(URL, {"facebook_url": "https://evil.example/facebook.com"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_office_hours_drive_booking_slots(self):
        self.api.patch(URL, {"office_opens": "09:00", "office_closes": "11:00", "slot_minutes": 60, "working_days": [5]}, format="json")
        lawyer = make_user(Role.LAWYER)
        saturday, monday = date(2030, 1, 5), date(2030, 1, 7)
        self.assertEqual([s["starts_at"].hour for s in available_slots(lawyer, saturday)], [9, 10])
        self.assertEqual(available_slots(lawyer, monday), [])

    def test_closing_must_follow_opening(self):
        self.assertEqual(self.api.patch(URL, {"office_opens": "17:00", "office_closes": "09:00"}, format="json").status_code, 400)

    def test_whatsapp_secrets_are_write_only_and_encrypted(self):
        response = self.api.patch(URL, {
            "whatsapp_mode": "live", "whatsapp_phone_number_id": "1234567890",
            "whatsapp_access_token": "EAAG-secret", "whatsapp_app_secret": "app-secret",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("EAAG-secret", response.content.decode())
        status = response.data["whatsapp_status"]
        self.assertTrue(status["access_token_set"])
        self.assertTrue(status["verify_token"])  # generated for the Meta webhook form
        self.assertTrue(status["webhook_url"].endswith("/api/v1/notifications/whatsapp/webhook/test-chambers/"))

        # Saving the form again with blank secrets keeps them.
        self.api.patch(URL, {"whatsapp_access_token": "", "tagline": "New"}, format="json")
        self.assertEqual(self.firm().whatsapp_access_token, "EAAG-secret")

        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT whatsapp_access_token FROM firm_firm")
            self.assertNotIn("EAAG", cursor.fetchone()[0])

    def test_going_live_needs_credentials(self):
        with self.settings(WHATSAPP_ACCESS_TOKEN="", WHATSAPP_PHONE_NUMBER_ID="", WHATSAPP_APP_SECRET=""):
            response = self.api.patch(URL, {"whatsapp_mode": "live"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Access token", response.data["error"]["fields"]["whatsapp_mode"][0])

    def test_live_mode_sends_through_meta_with_the_saved_token(self):
        firm = self.firm()
        firm.whatsapp_mode, firm.whatsapp_phone_number_id, firm.whatsapp_access_token = "live", "PN1", "TOKEN"
        firm.save()
        fake = mock.MagicMock()
        fake.__enter__.return_value.read.return_value = b'{"messages": [{"id": "wamid.1"}]}'
        with mock.patch("urllib.request.urlopen", return_value=fake) as urlopen:
            self.assertEqual(channels.send_whatsapp(to="+256772123456", headline="H", details="D", firm=self.firm()), "wamid.1")
        request = urlopen.call_args[0][0]
        self.assertIn("/PN1/messages", request.full_url)
        self.assertEqual(request.headers["Authorization"], "Bearer TOKEN")

    def test_switching_whatsapp_off_firm_wide(self):
        self.api.patch(URL, {"whatsapp_mode": "off"}, format="json")
        from apps.notifications.models import Category, Delivery
        from apps.notifications.services import notify

        lawyer = make_user(Role.LAWYER, phone="0772123456")
        with mock.patch("django.utils.timezone.now", return_value=self.firm().updated_at.replace(hour=8)):
            notify(lawyer, subject="x", body="x", sms="x", category=Category.DIARY)
        self.assertFalse(Delivery.objects.filter(channel="whatsapp").exists())

    def test_new_staff_inherit_the_firm_reminder_defaults(self):
        self.api.patch(URL, {"court_offsets": [3 * 24 * 60, 60], "quiet_hours_start": "22:00"}, format="json")
        from apps.notifications.services import preferences_for

        prefs = preferences_for(make_user(Role.LAWYER))
        self.assertEqual(prefs.court_offsets, [3 * 24 * 60, 60])
        self.assertEqual(prefs.quiet_hours_start, time(22, 0))

    def test_logo_upload_and_public_fetch(self):
        response = self.api.post("/api/v1/firm/logo/", {"logo": SimpleUploadedFile("logo.png", PNG, "image/png")}, format="multipart")
        self.assertEqual(response.status_code, 200, response.content)
        logo = self.client.get("/api/v1/firm/logo/")
        self.assertEqual((logo.status_code, logo["Content-Type"]), (200, "image/png"))

    def test_svg_and_fake_images_are_refused(self):
        for name, content in (("logo.svg", b"<svg onload=alert(1)>"), ("logo.png", b"not really a png")):
            response = self.api.post("/api/v1/firm/logo/", {"logo": SimpleUploadedFile(name, content)}, format="multipart")
            self.assertEqual(response.status_code, 400, name)

    def test_booking_can_be_paused(self):
        self.api.patch(URL, {"booking_enabled": False, "phone": "0414123456"}, format="json")
        lawyer = make_user(Role.LAWYER)
        response = self.client.post("/api/v1/appointments/public/book/", {
            "name": "A", "email": "a@b.test", "phone": "0772000000", "lawyer": str(lawyer.pk),
            "starts_at": "2030-01-07T10:00:00+03:00", "purpose": "x",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("paused", response.content.decode())
