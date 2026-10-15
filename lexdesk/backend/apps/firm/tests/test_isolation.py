"""
The promise LexDesk makes to every firm: nobody outside the firm sees
anything of it. These tests try every door from the outside.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.appointments.models import Appointment
from apps.audit.services import record
from apps.core.testing import PASSWORD, api_as, make_client, make_firm, make_matter, make_user, pdf_upload
from apps.firm.models import Firm
from apps.matters.models import CourtEvent, MatterMember, Note


class TwoFirms(TestCase):
    def setUp(self):
        self.a = make_firm("Akello & Co Advocates", slug="akello", code="AKC")
        self.b = make_firm("Byaruhanga Chambers", slug="byaruhanga", code="BYC")
        self.a_partner = make_user(Role.PARTNER, firm=self.a)
        self.a_lawyer = make_user(Role.LAWYER, firm=self.a)
        self.b_partner = make_user(Role.PARTNER, firm=self.b)
        self.b_lawyer = make_user(Role.LAWYER, firm=self.b)
        self.b_reception = make_user(Role.RECEPTIONIST, firm=self.b)
        self.a_matter = make_matter(self.a_lawyer, title="Akello client v. Bank")
        self.a_event = CourtEvent.objects.create(matter=self.a_matter, title="Hearing", starts_at=timezone.now() + timedelta(days=3))
        Note.objects.create(matter=self.a_matter, author=self.a_lawyer, body="Strategy: settle below 40m")
        Appointment.objects.create(
            client=self.a_matter.client, lawyer=self.a_lawyer, starts_at=timezone.now() + timedelta(days=2),
            ends_at=timezone.now() + timedelta(days=2, minutes=30), purpose="Advice", status="confirmed",
        )


class IsolationTests(TwoFirms):
    def test_case_numbers_belong_to_each_firm(self):
        self.assertTrue(self.a_matter.reference.startswith("AKC-"))
        self.assertTrue(make_matter(self.b_lawyer).reference.startswith("BYC-"))

    def test_another_firm_sees_nothing_in_any_list(self):
        for user in (self.b_partner, self.b_lawyer, self.b_reception):
            api = api_as(user)
            for path in ("/api/v1/matters/", "/api/v1/clients/", "/api/v1/diary/", "/api/v1/appointments/",
                         "/api/v1/documents/", "/api/v1/notes/", "/api/v1/tasks/", "/api/v1/billing/invoices/"):
                response = api.get(path)
                rows = response.data["results"] if isinstance(response.data, dict) and "results" in response.data else response.data
                self.assertIn(response.status_code, (200, 403), (user.role, path))
                if response.status_code == 200:
                    self.assertEqual(len(rows), 0, (user.role, path))

    def test_another_firm_cannot_open_records_by_id(self):
        api = api_as(self.b_partner)
        self.assertEqual(api.get(f"/api/v1/matters/{self.a_matter.pk}/").status_code, 404)
        self.assertEqual(api.get(f"/api/v1/clients/{self.a_matter.client_id}/").status_code, 404)
        self.assertEqual(api.get(f"/api/v1/diary/{self.a_event.pk}/").status_code, 404)
        self.assertEqual(api.get(f"/api/v1/diary/{self.a_event.pk}/brief/").status_code, 404)

    def test_another_firms_receptionist_cannot_diarise_on_our_matter(self):
        response = api_as(self.b_reception).post("/api/v1/diary/", {
            "matter": str(self.a_matter.pk), "kind": "hearing", "title": "x", "starts_at": (timezone.now() + timedelta(days=5)).isoformat(),
        }, format="json")
        self.assertIn(response.status_code, (400, 403))
        self.assertEqual(CourtEvent.objects.filter(matter=self.a_matter).count(), 1)

    def test_cannot_pull_another_firms_people_into_our_work(self):
        api = api_as(self.a_lawyer)
        team = api.post(f"/api/v1/matters/{self.a_matter.pk}/team/", {"user_id": str(self.b_lawyer.pk), "role": "associate"}, format="json")
        self.assertEqual(team.status_code, 400)
        diary = api.post("/api/v1/diary/", {
            "matter": str(self.a_matter.pk), "title": "x", "starts_at": (timezone.now() + timedelta(days=5)).isoformat(),
            "attendees": [str(self.b_lawyer.pk)],
        }, format="json")
        self.assertEqual(diary.status_code, 400)
        task = api.post("/api/v1/tasks/", {"matter": str(self.a_matter.pk), "title": "x", "assigned_to": str(self.b_lawyer.pk)}, format="json")
        self.assertEqual(task.status_code, 400)
        b_client = make_client(email="b@client.test", firm=self.b)
        matter = api.post("/api/v1/matters/", {"title": "x", "client": str(b_client.pk)}, format="json")
        self.assertEqual(matter.status_code, 400)

    def test_team_lists_and_conflict_checks_stay_inside_the_firm(self):
        team = api_as(self.b_partner).get("/api/v1/auth/team/").data["results"]
        self.assertEqual({row["email"] for row in team}, {self.b_partner.email, self.b_lawyer.email, self.b_reception.email})
        hits = api_as(self.b_partner).get("/api/v1/clients/conflict-check/", {"q": "Okello"}).data
        self.assertTrue(hits["clear"])  # firm A's client is not firm B's business

    def test_firm_settings_are_each_firms_own(self):
        api_as(self.b_partner).patch("/api/v1/firm/settings/", {"tagline": "Firm B tagline"}, format="json")
        self.assertNotEqual(Firm.objects.get(pk=self.a.pk).tagline, "Firm B tagline")
        self.assertEqual(api_as(self.a_partner).get("/api/v1/firm/settings/").data["name"], self.a.name)

    def test_public_website_shows_the_firm_at_its_address(self):
        self.assertEqual(self.client.get("/api/v1/firm/public/", {"firm": "byaruhanga"}).json()["name"], self.b.name)
        self.assertEqual(self.client.get("/api/v1/firm/public/", HTTP_X_LEXDESK_HOST="akello.lexdesk.app").json()["name"], self.a.name)
        Firm.objects.filter(pk=self.a.pk).update(domain="www.akello.co.ug")
        self.assertEqual(self.client.get("/api/v1/firm/public/", HTTP_X_LEXDESK_HOST="www.akello.co.ug").json()["name"], self.a.name)
        lawyers = self.client.get("/api/v1/appointments/public/lawyers/", {"firm": "byaruhanga"}).json()
        self.assertEqual({row["id"] for row in lawyers}, {str(self.b_partner.pk), str(self.b_lawyer.pk)})

    def test_public_booking_cannot_book_another_firms_lawyer(self):
        response = self.client.post("/api/v1/appointments/public/book/?firm=byaruhanga", {
            "name": "Visitor", "email": "v@x.test", "phone": "0772000000", "lawyer": str(self.a_lawyer.pk),
            "starts_at": (timezone.now() + timedelta(days=3)).isoformat(), "purpose": "x",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_audit_trail_is_per_firm(self):
        record("matter.viewed", actor=self.a_partner, target=self.a_matter, matter=self.a_matter)
        actions = api_as(self.b_partner).get("/api/v1/audit/events/").data["results"]
        self.assertFalse(any(row.get("matter_id") == str(self.a_matter.pk) for row in actions))
        self.assertTrue(api_as(self.a_partner).get("/api/v1/audit/events/").data["results"])

    def test_suspended_firm_cannot_use_its_public_site(self):
        Firm.objects.filter(pk=self.b.pk).update(is_active=False)
        self.assertEqual(self.client.get("/api/v1/firm/public/", {"firm": "byaruhanga"}).status_code, 404)
        self.assertEqual(api_as(self.b_partner).get("/api/v1/matters/").status_code, 403)
        login = self.client.post("/api/v1/auth/login/", {"email": self.b_partner.email, "password": PASSWORD}, content_type="application/json")
        self.assertEqual(login.status_code, 401)

    def test_an_email_belongs_to_one_firm(self):
        response = api_as(self.b_partner).post("/api/v1/auth/team/", {
            "email": self.a_lawyer.email, "first_name": "X", "last_name": "Y", "role": "lawyer",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.get(pk=self.a_lawyer.pk).firm_id, self.a.pk)


class PartnerOversightTests(TwoFirms):
    def test_partner_oversees_every_matter_and_the_diary(self):
        api = api_as(self.a_partner)
        self.assertEqual(api.get(f"/api/v1/matters/{self.a_matter.pk}/").status_code, 200)
        self.assertEqual(len(api.get("/api/v1/diary/").data["results"]), 1)
        self.assertEqual(len(api.get("/api/v1/appointments/").data["results"]), 1)

    def test_privileged_notes_stay_with_the_matter_team(self):
        partner = api_as(self.a_partner)
        self.assertEqual(partner.get("/api/v1/notes/", {"matter": str(self.a_matter.pk)}).data["count"], 0)
        self.assertFalse(partner.get(f"/api/v1/matters/{self.a_matter.pk}/").data["on_team"])
        refused = partner.post("/api/v1/notes/", {"matter": str(self.a_matter.pk), "body": "x"}, format="json")
        self.assertEqual(refused.status_code, 403)

        brief = partner.get(f"/api/v1/diary/{self.a_event.pk}/brief/").data
        self.assertFalse(brief["privileged"])
        self.assertEqual(brief["file_notes"], [])
        self.assertNotIn("settle", str(brief))

        # Once the partner joins the matter team, they read the file.
        MatterMember.objects.create(matter=self.a_matter, user=self.a_partner)
        self.assertEqual(partner.get("/api/v1/notes/", {"matter": str(self.a_matter.pk)}).data["count"], 1)

    def test_partners_manage_the_team(self):
        response = api_as(self.a_partner).post("/api/v1/auth/team/", {
            "email": "new.associate@akello.test", "first_name": "New", "last_name": "Associate", "role": "lawyer",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(User.objects.get(email="new.associate@akello.test").firm_id, self.a.pk)


class CourtBriefTests(TwoFirms):
    def test_brief_holds_everything_for_court(self):
        api = api_as(self.a_lawyer)
        api.post("/api/v1/notes/", {"matter": str(self.a_matter.pk), "court_event": str(self.a_event.pk), "body": "Ask for costs"}, format="json")
        api.post("/api/v1/documents/", {"matter": str(self.a_matter.pk), "title": "Plaint", "court_bundle": "true", "file": pdf_upload()}, format="multipart")
        brief = api.get(f"/api/v1/diary/{self.a_event.pk}/brief/").data
        self.assertTrue(brief["privileged"])
        self.assertEqual([n["body"] for n in brief["hearing_notes"]], ["Ask for costs"])
        self.assertEqual([n["body"] for n in brief["file_notes"]], ["Strategy: settle below 40m"])
        self.assertEqual([d["title"] for d in brief["documents"]], ["Plaint"])
        self.assertEqual(brief["matter"]["reference"], self.a_matter.reference)

    def test_record_outcome_and_next_date_in_one_step(self):
        new_date = timezone.now() + timedelta(days=30)
        with self.captureOnCommitCallbacks(execute=True):
            response = api_as(self.a_lawyer).post(f"/api/v1/diary/{self.a_event.pk}/record-outcome/", {
                "outcome": "adjourned", "outcome_notes": "Judge on leave", "next": {"starts_at": new_date.isoformat()},
            }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.a_event.refresh_from_db()
        self.assertEqual(self.a_event.outcome, "adjourned")
        self.assertEqual(self.a_event.next_event.starts_at.date(), new_date.date())
        self.assertEqual(self.a_event.next_event.matter_id, self.a_matter.pk)

    def test_a_note_cannot_point_at_another_matters_hearing(self):
        other = make_matter(self.a_lawyer, title="Other")
        response = api_as(self.a_lawyer).post("/api/v1/notes/", {"matter": str(other.pk), "court_event": str(self.a_event.pk), "body": "x"}, format="json")
        self.assertEqual(response.status_code, 400)


class PlatformTests(TwoFirms):
    def setUp(self):
        super().setUp()
        self.operator = User.objects.create_superuser("ops@lexdesk.test", "Ops-Password-2026!", first_name="Ops", last_name="Team")

    def test_operator_adds_a_firm_and_its_partner_is_invited(self):
        response = api_as(self.operator).post("/api/v1/platform/firms/", {
            "name": "Kato Legal", "code": "KTL", "partner_email": "kato@katolegal.test", "partner_first_name": "Moses", "partner_last_name": "Kato",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        firm = Firm.objects.get(code="KTL")
        self.assertEqual(firm.slug, "kato-legal")
        partner = User.objects.get(email="kato@katolegal.test")
        self.assertEqual((partner.firm_id, partner.role), (firm.pk, Role.PARTNER))

    def test_operator_sees_no_firms_files(self):
        api = api_as(self.operator)
        self.assertEqual(len(api.get("/api/v1/matters/").data["results"]), 0)
        self.assertEqual(len(api.get("/api/v1/clients/").data["results"]), 0)

    def test_firm_staff_cannot_use_the_platform_console_or_django_admin(self):
        self.assertEqual(api_as(self.a_partner).get("/api/v1/platform/firms/").status_code, 403)
        admin_user = make_user(Role.ADMIN, firm=self.a)
        admin_user.is_staff = admin_user.is_superuser = True
        admin_user.save()
        self.client.force_login(admin_user)
        self.assertNotEqual(self.client.get("/admin/").status_code, 200)
