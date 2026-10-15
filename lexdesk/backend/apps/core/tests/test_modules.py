import base64
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.billing.models import Invoice, InvoiceLine, OnlinePayment
from apps.clients.models import Client
from apps.core.filemakers import make_docx, make_pdf
from apps.core.testing import api_as, make_client, make_firm, make_matter, make_user
from apps.documents.models import Document, DocumentSearchToken, SignatureRequest
from apps.documents.services import add_version
from apps.firm.models import Firm
from apps.matters.models import MatterMember
from apps.notifications import channels
from apps.notifications.models import Delivery, Notification

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40).decode()


class SearchInsideDocumentsTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER)
        self.matter = make_matter(self.lawyer)
        self.api = api_as(self.lawyer)

    def upload(self, name, content, title):
        doc = Document.objects.create(matter=self.matter, title=title, uploaded_by=self.lawyer)
        add_version(doc, SimpleUploadedFile(name, content), user=self.lawyer)
        return doc

    def test_finds_words_inside_pdfs_and_word_files(self):
        pdf = self.upload("contract.pdf", make_pdf("Supply agreement", ["The distributor shall pay within thirty days."]), "Contract")
        docx = self.upload("letter.docx", make_docx("We demand immediate payment of the arrears."), "Letter")
        found = lambda q: {d["id"] for d in self.api.get("/api/v1/documents/", {"q": q}).data["results"]}
        self.assertEqual(found("distributor thirty"), {str(pdf.pk)})
        self.assertEqual(found("arrears"), {str(docx.pk)})
        self.assertEqual(found("payment"), {str(docx.pk)})
        self.assertEqual(found("nonexistentword"), set())

    def test_index_holds_no_readable_words(self):
        doc = self.upload("note.txt", b"confidential settlement figure", "Note")
        tokens = list(DocumentSearchToken.objects.filter(document=doc).values_list("token", flat=True))
        self.assertTrue(tokens)
        self.assertFalse(any("settlement" in t for t in tokens))

    def test_search_never_crosses_firms(self):
        self.upload("x.txt", b"secret merger kampala", "Firm A doc")
        other = make_user(Role.LAWYER, firm=make_firm("Other Firm", slug="other", code="OTH"))
        make_matter(other)
        self.assertEqual(api_as(other).get("/api/v1/documents/", {"q": "merger"}).data["count"], 0)


class TemplatesAndSignaturesTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER, title="Senior Associate")
        self.client_user = make_user(Role.CLIENT, email="jane@client.test")
        self.matter = make_matter(self.lawyer, client=make_client(portal_user=self.client_user))
        self.api = api_as(self.lawyer)

    def test_starter_templates_draft_a_filled_word_document(self):
        templates = self.api.post("/api/v1/documents/templates/starter/").data
        engagement = next(t for t in templates if t["name"] == "Engagement letter")
        response = self.api.post(f"/api/v1/documents/templates/{engagement['id']}/draft/", {"matter": str(self.matter.pk)}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        doc = Document.objects.get(pk=response.data["id"])
        from apps.documents.services import read_version

        import io
        import zipfile

        xml = zipfile.ZipFile(io.BytesIO(read_version(doc.latest))).read("word/document.xml").decode()
        self.assertIn(self.matter.reference, xml)
        self.assertIn(self.matter.client.name, xml)
        self.assertNotIn("{{", xml)

    def test_client_signs_and_a_certificate_is_filed(self):
        doc = Document.objects.create(matter=self.matter, title="Engagement letter", uploaded_by=self.lawyer)
        add_version(doc, SimpleUploadedFile("letter.pdf", make_pdf("Letter", ["Terms"])), user=self.lawyer)
        with self.captureOnCommitCallbacks(execute=True):
            req = self.api.post(f"/api/v1/documents/{doc.pk}/request-signature/", {"message": "Please sign"}, format="json").data
        self.assertTrue(Notification.objects.filter(recipient=self.client_user, title__startswith="Please sign").exists())

        client_api = api_as(self.client_user)
        self.assertEqual(client_api.get("/api/v1/documents/signatures/").data["count"], 1)
        refused = client_api.post(f"/api/v1/documents/signatures/{req['id']}/sign/", {"full_name": "Jane Okello", "signature": PNG, "agreed": False}, format="json")
        self.assertEqual(refused.status_code, 400)
        with self.captureOnCommitCallbacks(execute=True):
            signed = client_api.post(f"/api/v1/documents/signatures/{req['id']}/sign/", {"full_name": "Jane Okello", "signature": PNG, "agreed": True}, format="json")
        self.assertEqual(signed.status_code, 200, signed.content)
        r = SignatureRequest.objects.get(pk=req["id"])
        self.assertEqual(r.status, "signed")
        self.assertEqual(r.document_sha256, doc.latest.sha256)
        self.assertTrue(r.certificate.title.startswith("Signature certificate"))
        self.assertTrue(Notification.objects.filter(recipient=self.lawyer, title__startswith="Signed:").exists())

    def test_a_changed_document_cannot_carry_an_old_signature_request(self):
        doc = Document.objects.create(matter=self.matter, title="Letter", uploaded_by=self.lawyer)
        add_version(doc, SimpleUploadedFile("a.txt", b"version one"), user=self.lawyer)
        req = self.api.post(f"/api/v1/documents/{doc.pk}/request-signature/", {}, format="json").data
        add_version(doc, SimpleUploadedFile("a.txt", b"version two"), user=self.lawyer)
        response = api_as(self.client_user).post(f"/api/v1/documents/signatures/{req['id']}/sign/", {"full_name": "Jane Okello", "signature": PNG, "agreed": True}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_someone_else_cannot_sign(self):
        doc = Document.objects.create(matter=self.matter, title="Letter", uploaded_by=self.lawyer)
        add_version(doc, SimpleUploadedFile("a.txt", b"terms"), user=self.lawyer)
        req = self.api.post(f"/api/v1/documents/{doc.pk}/request-signature/", {}, format="json").data
        response = self.api.post(f"/api/v1/documents/signatures/{req['id']}/sign/", {"full_name": "X Y", "signature": PNG, "agreed": True}, format="json")
        self.assertEqual(response.status_code, 403)


class MessagingTests(TestCase):
    def setUp(self):
        self.lawyer = make_user(Role.LAWYER, phone="0772123456")
        self.partner = make_user(Role.PARTNER)
        self.client_user = make_user(Role.CLIENT, email="jane@client.test", phone="0700111222")
        self.matter = make_matter(self.lawyer, client=make_client(portal_user=self.client_user))

    def test_client_and_lawyer_talk_and_alerts_never_carry_the_words(self):
        with self.captureOnCommitCallbacks(execute=True):
            sent = api_as(self.client_user).post("/api/v1/messages/", {"matter": str(self.matter.pk), "body": "The bank called me about the loan"}, format="json")
        self.assertEqual(sent.status_code, 201, sent.content)
        alert = Notification.objects.get(recipient=self.lawyer, category="messages")
        self.assertNotIn("bank", alert.body + alert.short_text + alert.title)

        threads = api_as(self.lawyer).get("/api/v1/messages/threads/").data
        self.assertEqual(threads["unread_total"], 1)
        messages = api_as(self.lawyer).get("/api/v1/messages/", {"matter": str(self.matter.pk)}).data
        self.assertEqual(messages[0]["body"], "The bank called me about the loan")
        api_as(self.lawyer).post("/api/v1/messages/read/", {"matter": str(self.matter.pk)}, format="json")
        self.assertEqual(api_as(self.lawyer).get("/api/v1/messages/threads/").data["unread_total"], 0)

    def test_partner_outside_the_team_cannot_read_or_write(self):
        api_as(self.client_user).post("/api/v1/messages/", {"matter": str(self.matter.pk), "body": "private"}, format="json")
        partner = api_as(self.partner)
        self.assertEqual(partner.get("/api/v1/messages/", {"matter": str(self.matter.pk)}).status_code, 403)
        self.assertEqual(partner.post("/api/v1/messages/", {"matter": str(self.matter.pk), "body": "x"}, format="json").status_code, 403)
        MatterMember.objects.create(matter=self.matter, user=self.partner)
        self.assertEqual(partner.get("/api/v1/messages/", {"matter": str(self.matter.pk)}).status_code, 200)

    def test_body_is_encrypted(self):
        api_as(self.lawyer).post("/api/v1/messages/", {"matter": str(self.matter.pk), "body": "Settle at 40 million"}, format="json")
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT body FROM messaging_message")
            self.assertNotIn("Settle", cursor.fetchone()[0])


class LibraryTests(TestCase):
    def test_each_firm_keeps_its_own_library(self):
        a = make_user(Role.LAWYER)
        b = make_user(Role.LAWYER, firm=make_firm("Other Chambers", slug="other", code="OTC"))
        created = api_as(a).post("/api/v1/library/", {"kind": "case", "title": "Mulindwa v. Uganda Breweries", "citation": "[2019] UGCA 42",
                                                      "summary": "Damages for breach of a distribution agreement."}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(api_as(a).get("/api/v1/library/", {"search": "distribution"}).data["count"], 1)
        self.assertEqual(api_as(b).get("/api/v1/library/").data["count"], 0)
        self.assertEqual(api_as(make_user(Role.CLIENT)).get("/api/v1/library/").data["count"], 0)


class ReportsTests(TestCase):
    def test_partner_sees_workload_counts_and_retainers_without_details(self):
        partner = make_user(Role.PARTNER)
        lawyer = make_user(Role.LAWYER)
        make_matter(lawyer, title="Secret matter one")
        make_matter(lawyer, title="Secret matter two")
        Client.objects.create(firm=lawyer.firm, name="Retained Co", responsible_lawyer=lawyer, status="active", engagement="retainer", retainer_fee=Decimal("2000000"))
        Client.objects.create(firm=lawyer.firm, name="Walk-in", responsible_lawyer=lawyer, status="active", engagement="one_off")

        data = api_as(partner).get("/api/v1/reports/").data
        row = next(r for r in data["workload"] if r["id"] == str(lawyer.pk))
        self.assertEqual((row["leading"], row["retainer_clients"], row["one_off_clients"]), (2, 1, 1))
        self.assertEqual(data["summary"]["monthly_retainer_income"], Decimal("2000000"))
        self.assertNotIn("Secret matter", json.dumps(data, default=str))
        self.assertEqual(api_as(lawyer).get("/api/v1/reports/").status_code, 403)


class OnlinePaymentTests(TestCase):
    def setUp(self):
        self.firm = make_firm("Pay Firm", slug="payfirm", code="PAY")
        self.lawyer = make_user(Role.LAWYER, firm=self.firm)
        self.accountant = make_user(Role.ACCOUNTANT, firm=self.firm)
        self.client_user = make_user(Role.CLIENT, email="payer@client.test", firm=self.firm)
        self.matter = make_matter(self.lawyer, client=make_client(portal_user=self.client_user, email="payer@client.test"))
        self.invoice = Invoice.objects.create(matter=self.matter, status=Invoice.Status.ISSUED, tax_rate=0, issue_date=timezone.localdate(),
                                              due_date=timezone.localdate() + timedelta(days=30))
        InvoiceLine.objects.create(invoice=self.invoice, description="Advice", quantity=1, unit_price=Decimal("150000"))

    def test_off_by_default(self):
        response = api_as(self.client_user).post(f"/api/v1/billing/invoices/{self.invoice.pk}/pay-online/")
        self.assertEqual(response.status_code, 400)

    def test_test_mode_end_to_end(self):
        Firm.objects.filter(pk=self.firm.pk).update(payments_mode="test")
        start = api_as(self.client_user).post(f"/api/v1/billing/invoices/{self.invoice.pk}/pay-online/").data
        self.assertIn("/pay/test?ref=", start["checkout_url"])
        with self.captureOnCommitCallbacks(execute=True):
            done = api_as(self.client_user).post(f"/api/v1/billing/online-payments/{start['tx_ref']}/", {"outcome": "success"}, format="json").data
        self.assertEqual(done["status"], "successful")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "paid")
        self.assertTrue(Notification.objects.filter(recipient=self.accountant, title__startswith="Online payment").exists())

    def test_live_flutterwave_is_verified_before_recording_and_only_once(self):
        Firm.objects.filter(pk=self.firm.pk).update(payments_mode="live", flutterwave_secret_key="FLWSECK-x", flutterwave_webhook_hash="hash123")
        with mock.patch("apps.billing.online._call", return_value={"data": {"link": "https://checkout.flutterwave.com/abc"}}):
            start = api_as(self.client_user).post(f"/api/v1/billing/invoices/{self.invoice.pk}/pay-online/").data
        tx = start["tx_ref"]
        # A forged webhook is refused.
        self.assertEqual(self.client.post("/api/v1/billing/flutterwave/webhook/payfirm/", {"data": {"tx_ref": tx}}, content_type="application/json", HTTP_VERIF_HASH="wrong").status_code, 401)
        # Underpaid: not recorded.
        wrong = {"data": {"status": "successful", "id": 1, "amount": 1000, "currency": "UGX", "payment_type": "mobilemoneyuganda"}}
        with mock.patch("apps.billing.online._call", return_value=wrong):
            self.client.post("/api/v1/billing/flutterwave/webhook/payfirm/", {"data": {"tx_ref": tx}}, content_type="application/json", HTTP_VERIF_HASH="hash123")
        self.assertEqual(OnlinePayment.objects.get(tx_ref=tx).status, "failed")
        self.assertEqual(self.invoice.payments.count(), 0)

    def test_full_payment_recorded_once(self):
        Firm.objects.filter(pk=self.firm.pk).update(payments_mode="live", flutterwave_secret_key="FLWSECK-x", flutterwave_webhook_hash="hash123")
        with mock.patch("apps.billing.online._call", return_value={"data": {"link": "https://checkout.flutterwave.com/abc"}}):
            tx = api_as(self.client_user).post(f"/api/v1/billing/invoices/{self.invoice.pk}/pay-online/").data["tx_ref"]
        ok = {"data": {"status": "successful", "id": 99, "amount": 150000, "currency": "UGX", "payment_type": "mobilemoneyuganda"}}
        with mock.patch("apps.billing.online._call", return_value=ok):
            self.client.post("/api/v1/billing/flutterwave/webhook/payfirm/", {"data": {"tx_ref": tx}}, content_type="application/json", HTTP_VERIF_HASH="hash123")
            api_as(self.client_user).get(f"/api/v1/billing/online-payments/{tx}/")
        self.assertEqual(self.invoice.payments.count(), 1)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "paid")


class SmsTests(TestCase):
    def test_africastalking_live_send(self):
        firm = make_firm("Sms Firm", slug="smsfirm", code="SMS")
        Firm.objects.filter(pk=firm.pk).update(sms_mode="live", at_username="nscadv", at_api_key="atsk_x", at_sender_id="NSCADVOC")
        firm.refresh_from_db()
        reply = mock.MagicMock()
        reply.__enter__.return_value.read.return_value = json.dumps(
            {"SMSMessageData": {"Recipients": [{"statusCode": 101, "status": "Success", "messageId": "ATXid_1"}]}}
        ).encode()
        with mock.patch("urllib.request.urlopen", return_value=reply) as urlopen:
            self.assertEqual(channels.send_sms(to="+256772123456", text="Hearing tomorrow", firm=firm), "ATXid_1")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://api.africastalking.com/version1/messaging")
        self.assertEqual(request.headers["Apikey"], "atsk_x")
        self.assertIn(b"from=NSCADVOC", request.data)

    def test_invalid_number_is_permanent(self):
        firm = make_firm("Sms Firm", slug="smsfirm", code="SMS")
        Firm.objects.filter(pk=firm.pk).update(sms_mode="live", at_username="u", at_api_key="k")
        firm.refresh_from_db()
        reply = mock.MagicMock()
        reply.__enter__.return_value.read.return_value = json.dumps({"SMSMessageData": {"Recipients": [{"statusCode": 403, "status": "InvalidPhoneNumber"}]}}).encode()
        with mock.patch("urllib.request.urlopen", return_value=reply):
            with self.assertRaises(channels.PermanentFailure):
                channels.send_sms(to="+256700000000", text="x", firm=firm)


class FirmSignupTests(TestCase):
    URL = "/api/v1/firm/register/"
    FORM = {
        "firm_name": "Mugisha & Partners Advocates", "firm_phone": "0414 555 000", "first_name": "Paul", "last_name": "Mugisha",
        "email": "paul@mugisha.test", "phone": "0772 555 111", "agree": True,
    }

    def test_partner_registers_firm_activates_then_adds_staff(self):
        owner = User.objects.create_superuser("owner@lexdesk.test", "Owner-Pass-2026!", first_name="O", last_name="W")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.URL, self.FORM, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        firm = Firm.objects.get(name="Mugisha & Partners Advocates")
        self.assertEqual(firm.slug, "mugisha-partners-advocates")
        partner = User.objects.get(email="paul@mugisha.test")
        self.assertEqual((partner.firm_id, partner.role), (firm.pk, Role.PARTNER))
        self.assertFalse(partner.has_usable_password())  # must activate from the email first
        self.assertTrue(Notification.objects.filter(recipient=owner, title__startswith="New firm registered").exists())
        self.assertTrue(Delivery.objects.filter(notification__recipient=partner, channel="email").exists())

        partner.set_password("A-Strong-Password-2026")
        partner.save()
        added = api_as(partner).post("/api/v1/auth/team/", {"email": "clerk@mugisha.test", "first_name": "C", "last_name": "K", "role": "paralegal"}, format="json")
        self.assertEqual(added.status_code, 201, added.content)
        self.assertEqual(User.objects.get(email="clerk@mugisha.test").firm_id, firm.pk)

    def test_duplicates_and_bots_are_refused(self):
        make_user(Role.LAWYER, email="paul@mugisha.test")
        self.assertEqual(self.client.post(self.URL, self.FORM, content_type="application/json").status_code, 400)
        bot = self.client.post(self.URL, {**self.FORM, "email": "bot@x.test", "website": "spam"}, content_type="application/json")
        self.assertEqual(bot.status_code, 201)
        self.assertFalse(Firm.objects.filter(name=self.FORM["firm_name"]).exists())

    def test_can_be_closed(self):
        with self.settings(LEXDESK_ALLOW_FIRM_SIGNUP=False):
            self.assertEqual(self.client.post(self.URL, self.FORM, content_type="application/json").status_code, 403)
