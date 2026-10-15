"""
Database integrity: records stay correct, unique, and where they belong,
and history cannot be quietly rewritten.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceLine, Payment, TimeEntry
from apps.clients.models import Client
from apps.core.testing import api_as, make_client, make_firm, make_matter, make_user, pdf_upload
from apps.documents.models import Document, DocumentVersion
from apps.documents.services import add_version
from apps.firm.models import Firm
from apps.matters.models import CourtEvent, Matter, Note, Task


class UniquenessTests(TestCase):
    def test_case_numbers_never_repeat(self):
        lawyer = make_user(Role.LAWYER)
        refs = [make_matter(lawyer, title=f"Matter {i}").reference for i in range(25)]
        self.assertEqual(len(refs), len(set(refs)))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Matter.objects.create(firm=lawyer.firm, title="Copy", client=make_client(email="c@x.test", firm=lawyer.firm),
                                  reference=refs[0], lead_lawyer=lawyer)

    def test_one_login_per_email_whatever_the_capitals(self):
        make_user(Role.LAWYER, email="grace@firm.test")
        partner = make_user(Role.PARTNER)
        response = api_as(partner).post("/api/v1/auth/team/", {"email": "GRACE@Firm.Test", "first_name": "G", "last_name": "N", "role": "lawyer"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.filter(email__iexact="grace@firm.test").count(), 1)

    def test_firm_names_codes_and_addresses_are_unique(self):
        make_firm("First Firm", slug="first", code="FFA")
        for kwargs in ({"slug": "first", "code": "ZZZ"}, {"slug": "other", "code": "FFA"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Firm.objects.create(name="Dup", **kwargs)

    def test_a_returning_website_client_is_not_duplicated(self):
        lawyer = make_user(Role.LAWYER)
        from apps.appointments.services import public_booking

        start = timezone.now() + timedelta(days=7)
        start = start.replace(hour=10, minute=0, second=0, microsecond=0)
        while start.weekday() >= 5:
            start += timedelta(days=1)
        for i in range(2):
            public_booking(firm=lawyer.firm, name="Jane Okello", email="JANE@client.test", phone="0772000000", lawyer_id=lawyer.pk,
                           starts_at=start + timedelta(hours=i), mode="in_person", purpose="x")
        self.assertEqual(Client.objects.filter(email__iexact="jane@client.test").count(), 1)
        self.assertEqual(User.objects.filter(email__iexact="jane@client.test").count(), 1)

    def test_a_lawyer_cannot_be_double_booked(self):
        lawyer = make_user(Role.LAWYER)
        client = make_client(firm=lawyer.firm)
        start = timezone.now() + timedelta(days=3)
        body = {"client": str(client.pk), "lawyer": str(lawyer.pk), "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(), "purpose": "x"}
        api = api_as(make_user(Role.RECEPTIONIST, firm=lawyer.firm))
        self.assertEqual(api.post("/api/v1/appointments/", body, format="json").status_code, 201)
        self.assertEqual(api.post("/api/v1/appointments/", body, format="json").status_code, 400)

    def test_database_refuses_impossible_appointments(self):
        lawyer = make_user(Role.LAWYER)
        with self.assertRaises(IntegrityError), transaction.atomic():
            now = timezone.now()
            Appointment.objects.create(client=make_client(firm=lawyer.firm), lawyer=lawyer, starts_at=now, ends_at=now - timedelta(hours=1), purpose="x")


class RecordsStayWhereTheyBelong(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER)
        self.matter = make_matter(self.lawyer)
        self.other = make_matter(self.lawyer, client=make_client(email="o@x.test", firm=self.lawyer.firm), title="Other matter")
        self.api = api_as(self.lawyer)

    def test_items_cannot_be_moved_to_another_matter(self):
        task = Task.objects.create(matter=self.matter, title="t", created_by=self.lawyer)
        note = Note.objects.create(matter=self.matter, author=self.lawyer, body="n")
        doc = Document.objects.create(matter=self.matter, title="d", uploaded_by=self.lawyer)
        add_version(doc, pdf_upload(), user=self.lawyer)
        for url in (f"/api/v1/tasks/{task.pk}/", f"/api/v1/notes/{note.pk}/", f"/api/v1/documents/{doc.pk}/"):
            self.assertEqual(self.api.patch(url, {"matter": str(self.other.pk)}, format="json").status_code, 400, url)
        self.assertEqual(Task.objects.get(pk=task.pk).matter_id, self.matter.pk)
        self.assertEqual(Document.objects.get(pk=doc.pk).matter_id, self.matter.pk)

    def test_appointment_stays_with_its_client_and_only_their_matters(self):
        other_client = make_client(name="Someone else", email="else@x.test", firm=self.lawyer.firm)
        start = timezone.now() + timedelta(days=4)
        appt = Appointment.objects.create(client=self.matter.client, lawyer=self.lawyer, starts_at=start,
                                          ends_at=start + timedelta(minutes=30), purpose="x", status="confirmed")
        self.assertEqual(self.api.patch(f"/api/v1/appointments/{appt.pk}/", {"client": str(other_client.pk)}, format="json").status_code, 400)
        self.assertEqual(self.api.patch(f"/api/v1/appointments/{appt.pk}/", {"matter": str(self.other.pk)}, format="json").status_code, 400)
        foreign = make_matter(make_user(Role.LAWYER, firm=make_firm("Elsewhere", slug="elsewhere", code="ELS")))
        self.assertEqual(self.api.patch(f"/api/v1/appointments/{appt.pk}/", {"matter": str(foreign.pk)}, format="json").status_code, 400)
        appt.refresh_from_db()
        self.assertEqual((appt.client_id, appt.matter_id), (self.matter.client_id, None))

    def test_next_hearing_link_stays_on_the_same_matter(self):
        event = CourtEvent.objects.create(matter=self.matter, title="h", starts_at=timezone.now() + timedelta(days=5))
        elsewhere = CourtEvent.objects.create(matter=self.other, title="h2", starts_at=timezone.now() + timedelta(days=6))
        response = self.api.patch(f"/api/v1/diary/{event.pk}/", {"next_event": str(elsewhere.pk)}, format="json")
        self.assertEqual(response.status_code, 400)


class HistoryCannotBeRewritten(TestCase):
    def setUp(self):
        self.firm = make_firm("History Firm", slug="history", code="HIS")
        self.lawyer = make_user(Role.LAWYER, firm=self.firm)
        self.accountant = make_user(Role.ACCOUNTANT, firm=self.firm)
        self.matter = make_matter(self.lawyer)

    def test_matters_and_clients_are_never_deleted(self):
        partner = make_user(Role.PARTNER, firm=self.firm)
        self.assertEqual(api_as(partner).delete(f"/api/v1/matters/{self.matter.pk}/").status_code, 403)
        self.assertEqual(api_as(partner).delete(f"/api/v1/clients/{self.matter.client_id}/").status_code, 405)
        self.assertTrue(Matter.objects.filter(pk=self.matter.pk).exists())

    def test_issued_invoices_are_fixed_and_paid_ones_cannot_be_voided(self):
        invoice = Invoice.objects.create(matter=self.matter, status="issued", tax_rate=0, issue_date=timezone.localdate())
        InvoiceLine.objects.create(invoice=invoice, description="Advice", quantity=1, unit_price=Decimal("100000"))
        api = api_as(self.accountant)
        self.assertEqual(api.patch(f"/api/v1/billing/invoices/{invoice.pk}/", {"notes": "changed"}, format="json").status_code, 400)
        Payment.objects.create(invoice=invoice, amount=Decimal("1000"), method="cash", received_on=timezone.localdate())
        self.assertEqual(api.post(f"/api/v1/billing/invoices/{invoice.pk}/void/").status_code, 400)
        self.assertEqual(api.post(f"/api/v1/billing/invoices/{invoice.pk}/payments/", {"amount": "999999999", "method": "cash", "received_on": "2026-10-15"}, format="json").status_code, 400)

    def test_billed_time_cannot_be_changed(self):
        entry = TimeEntry.objects.create(matter=self.matter, user=self.lawyer, minutes=60, description="work", rate=Decimal("300000"))
        invoice = Invoice.objects.create(matter=self.matter, tax_rate=0)
        TimeEntry.objects.filter(pk=entry.pk).update(invoice=invoice)
        response = api_as(self.lawyer).patch(f"/api/v1/billing/time/{entry.pk}/", {"minutes": 600}, format="json")
        self.assertIn(response.status_code, {400, 403})
        self.assertEqual(TimeEntry.objects.get(pk=entry.pk).minutes, 60)

    def test_document_versions_are_kept_and_deleting_only_archives(self):
        api = api_as(self.lawyer)
        doc = Document.objects.create(matter=self.matter, title="Contract", uploaded_by=self.lawyer)
        add_version(doc, pdf_upload(), user=self.lawyer)
        add_version(doc, SimpleUploadedFile("v2.pdf", pdf_upload().read() + b"%v2"), user=self.lawyer)
        self.assertEqual(api.delete(f"/api/v1/documents/{doc.pk}/").status_code, 204)
        doc.refresh_from_db()
        self.assertTrue(doc.is_archived)
        self.assertEqual(DocumentVersion.objects.filter(document=doc).count(), 2)

    def test_only_the_author_edits_a_file_note(self):
        colleague = make_user(Role.LAWYER, firm=self.firm)
        from apps.matters.models import MatterMember

        MatterMember.objects.create(matter=self.matter, user=colleague)
        note = Note.objects.create(matter=self.matter, author=self.lawyer, body="original")
        self.assertEqual(api_as(colleague).patch(f"/api/v1/notes/{note.pk}/", {"body": "rewritten"}, format="json").status_code, 403)
        self.assertEqual(Note.objects.get(pk=note.pk).body, "original")
