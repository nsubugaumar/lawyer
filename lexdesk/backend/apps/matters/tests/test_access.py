"""
Who can see which matter. If any test in this file fails, stop and fix it
before shipping anything else.
"""

from django.test import TestCase

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.core.testing import api_as, make_client, make_matter, make_user


class MatterVisibilityTests(TestCase):
    def setUp(self):
        self.lead = make_user(Role.LAWYER)
        self.other_lawyer = make_user(Role.LAWYER)
        self.partner = make_user(Role.PARTNER)
        self.receptionist = make_user(Role.RECEPTIONIST)
        self.client_user = make_user(Role.CLIENT)
        self.matter = make_matter(self.lead, make_client(portal_user=self.client_user))
        self.walled = make_matter(self.lead, restricted=True, title="Sensitive v. Firm Partner")

    def _ids(self, user):
        r = api_as(user).get("/api/v1/matters/")
        self.assertEqual(r.status_code, 200)
        return {m["id"] for m in r.data["results"]}

    def test_lead_sees_both_of_their_matters(self):
        self.assertEqual(self._ids(self.lead), {str(self.matter.id), str(self.walled.id)})

    def test_lawyer_not_on_the_team_sees_nothing(self):
        self.assertEqual(self._ids(self.other_lawyer), set())
        r = api_as(self.other_lawyer).get(f"/api/v1/matters/{self.matter.id}/")
        self.assertEqual(r.status_code, 404)  # not 403: we do not confirm it exists

    def test_partner_sees_everything_except_ethical_walls(self):
        self.assertEqual(self._ids(self.partner), {str(self.matter.id)})

    def test_receptionist_sees_no_case_files(self):
        self.assertEqual(self._ids(self.receptionist), set())

    def test_client_sees_only_their_own_matter_and_none_of_its_internals(self):
        r = api_as(self.client_user).get(f"/api/v1/matters/{self.matter.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("is_restricted", r.data)
        self.assertNotIn("description", r.data)
        self.assertEqual(self._ids(self.client_user), {str(self.matter.id)})

    def test_client_cannot_read_private_notes_but_can_read_shared_ones(self):
        api = api_as(self.lead)
        api.post("/api/v1/notes/", {"matter": self.matter.id, "body": "Strategy: settle below 40m."})
        api.post("/api/v1/notes/", {"matter": self.matter.id, "body": "Hearing went well.", "shared_with_client": True})
        r = api_as(self.client_user).get(f"/api/v1/notes/?matter={self.matter.id}")
        bodies = [n["body"] for n in r.data["results"]]
        self.assertEqual(bodies, ["Hearing went well."])

    def test_notes_are_encrypted_in_the_database(self):
        api_as(self.lead).post("/api/v1/notes/", {"matter": self.matter.id, "body": "Client admits the debt."})
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT body FROM matters_note")
            raw = cursor.fetchone()[0]
        self.assertNotIn("admits", raw)

    def test_outsider_cannot_add_items_to_someone_elses_matter(self):
        r = api_as(self.other_lawyer).post("/api/v1/tasks/", {"matter": self.matter.id, "title": "Snoop"})
        self.assertEqual(r.status_code, 403)

    def test_clients_cannot_write_to_the_file(self):
        r = api_as(self.client_user).post("/api/v1/notes/", {"matter": self.matter.id, "body": "hi"})
        self.assertEqual(r.status_code, 403)

    def test_matters_cannot_be_deleted(self):
        r = api_as(self.partner).delete(f"/api/v1/matters/{self.matter.id}/")
        self.assertEqual(r.status_code, 403)

    def test_only_partners_build_ethical_walls(self):
        r = api_as(self.lead).patch(f"/api/v1/matters/{self.matter.id}/", {"is_restricted": True})
        self.assertEqual(r.status_code, 403)

    def test_opening_a_matter_is_audited_and_numbered(self):
        api = api_as(self.lead)
        client = make_client(name="New Co Ltd", email="ops@newco.test")
        r = api.post("/api/v1/matters/", {"title": "New Co acquisition", "client": client.id, "practice_area": "corporate"})
        self.assertEqual(r.status_code, 201)
        self.assertRegex(r.data["reference"], r"^TC-\d{4}-\d{4}$")
        self.assertTrue(AuditEvent.objects.filter(action="matter.opened", matter_id=r.data["id"]).exists())

    def test_conflict_check_finds_opposing_parties(self):
        api_as(self.lead).post("/api/v1/parties/", {"matter": self.matter.id, "name": "Kampala Traders Ltd", "role": "defendant"})
        r = api_as(self.receptionist).get("/api/v1/clients/conflict-check/?q=kampala traders")
        self.assertFalse(r.data["clear"])
        self.assertEqual(r.data["hits"][0]["type"], "party")
