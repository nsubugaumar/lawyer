"""
Security tests: an attacker's-eye sweep of LexDesk.

Each test tries something an attacker (or a curious colleague) would try,
and asserts that it fails at the server, not just in the interface. They
run on every change, so a regression is caught before release.

Mapped to OWASP Top 10 (2021) and OWASP ASVS 4.0; see SECURITY.md.
"""

import base64
from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Role, User
from apps.appointments.models import Appointment
from apps.audit.models import AuditEvent
from apps.audit.services import record, verify_chain
from apps.billing.models import Invoice, InvoiceLine, OnlinePayment
from apps.core.testing import PASSWORD, api_as, make_client, make_firm, make_matter, make_user, pdf_upload
from apps.documents.models import Document, DocumentTemplate, SignatureRequest
from apps.documents.services import add_version
from apps.firm.models import Firm
from apps.library.models import Authority
from apps.matters.models import CourtEvent, Note, Party, Task
from apps.messaging.models import Message

ALLOWED_DENIALS = {401, 403, 404, 405}


class VictimFirm(TestCase):
    """Firm A, full of data; firm B and every role try to reach it."""

    def setUp(self):
        self.a = make_firm("Victim Advocates", slug="victim", code="VIC")
        self.b = make_firm("Intruder Chambers", slug="intruder", code="INT")
        self.lawyer = make_user(Role.LAWYER, firm=self.a)
        self.client_user = make_user(Role.CLIENT, email="victim-client@x.test", firm=self.a)
        self.client_record = make_client(portal_user=self.client_user, email="victim-client@x.test", firm=self.a)
        self.matter = make_matter(self.lawyer, client=self.client_record, title="Sensitive v. Secret")
        now = timezone.now()
        self.event = CourtEvent.objects.create(matter=self.matter, title="Hearing", starts_at=now + timedelta(days=3))
        self.note = Note.objects.create(matter=self.matter, author=self.lawyer, body="privileged strategy")
        self.task = Task.objects.create(matter=self.matter, title="Draft", created_by=self.lawyer)
        self.party = Party.objects.create(matter=self.matter, name="Opponent Ltd", role="defendant")
        self.doc = Document.objects.create(matter=self.matter, title="Evidence", uploaded_by=self.lawyer, shared_with_client=True)
        add_version(self.doc, pdf_upload(), user=self.lawyer)
        self.signature = SignatureRequest.objects.create(document=self.doc, version_number=1, document_sha256=self.doc.latest.sha256,
                                                         signer=self.client_user, requested_by=self.lawyer)
        self.invoice = Invoice.objects.create(matter=self.matter, status="issued", tax_rate=0, issue_date=timezone.localdate())
        InvoiceLine.objects.create(invoice=self.invoice, description="Advice", quantity=1, unit_price=Decimal("100"))
        self.payment = OnlinePayment.objects.create(invoice=self.invoice, firm=self.a, tx_ref="LD-victim01", provider="test",
                                                    amount=Decimal("100"), currency="UGX")
        self.appointment = Appointment.objects.create(client=self.client_record, lawyer=self.lawyer, starts_at=now + timedelta(days=2),
                                                      ends_at=now + timedelta(days=2, minutes=30), purpose="x", status="confirmed")
        self.message = Message.objects.create(matter=self.matter, sender=self.lawyer, body="privileged message")
        self.authority = Authority.objects.create(firm=self.a, title="Victim research", added_by=self.lawyer)
        self.template = DocumentTemplate.objects.create(firm=self.a, name="Victim template", body="x")

        self.intruders = [make_user(role, firm=self.b) for role in (Role.ADMIN, Role.PARTNER, Role.LAWYER, Role.PARALEGAL,
                                                                    Role.RECEPTIONIST, Role.ACCOUNTANT, Role.CLIENT)]

    def object_urls(self):
        """Every address that names one of firm A's records."""
        return [
            f"/api/v1/matters/{self.matter.pk}/", f"/api/v1/matters/{self.matter.pk}/team/", f"/api/v1/matters/{self.matter.pk}/timeline/",
            f"/api/v1/clients/{self.client_record.pk}/", f"/api/v1/diary/{self.event.pk}/", f"/api/v1/diary/{self.event.pk}/brief/",
            f"/api/v1/notes/{self.note.pk}/", f"/api/v1/tasks/{self.task.pk}/", f"/api/v1/parties/{self.party.pk}/",
            f"/api/v1/documents/{self.doc.pk}/", f"/api/v1/documents/{self.doc.pk}/download/", f"/api/v1/documents/{self.doc.pk}/versions/",
            f"/api/v1/documents/signatures/{self.signature.pk}/", f"/api/v1/billing/invoices/{self.invoice.pk}/",
            f"/api/v1/billing/online-payments/{self.payment.tx_ref}/", f"/api/v1/appointments/{self.appointment.pk}/",
            f"/api/v1/library/{self.authority.pk}/", f"/api/v1/documents/templates/{self.template.pk}/",
            f"/api/v1/auth/team/{self.lawyer.pk}/", f"/api/v1/messages/?matter={self.matter.pk}",
        ]

    def action_urls(self):
        """State-changing actions on firm A's records."""
        return [
            (f"/api/v1/diary/{self.event.pk}/record-outcome/", {"outcome": "vacated"}),
            (f"/api/v1/documents/{self.doc.pk}/request-signature/", {}),
            (f"/api/v1/documents/signatures/{self.signature.pk}/sign/", {"full_name": "X Y", "signature": "", "agreed": True}),
            (f"/api/v1/documents/signatures/{self.signature.pk}/cancel/", {}),
            (f"/api/v1/billing/invoices/{self.invoice.pk}/payments/", {"amount": "1", "method": "cash", "received_on": "2026-01-01"}),
            (f"/api/v1/billing/invoices/{self.invoice.pk}/void/", {}),
            (f"/api/v1/billing/invoices/{self.invoice.pk}/pay-online/", {}),
            (f"/api/v1/appointments/{self.appointment.pk}/cancel/", {"reason": "x"}),
            (f"/api/v1/matters/{self.matter.pk}/team/", {"user_id": "x", "role": "associate"}),
            (f"/api/v1/clients/{self.client_record.pk}/grant_portal_access/", {}),
            (f"/api/v1/auth/team/{self.lawyer.pk}/reset_mfa/", {}),
            ("/api/v1/messages/", {"matter": str(self.matter.pk), "body": "hello"}),
            ("/api/v1/notes/", {"matter": str(self.matter.pk), "body": "x"}),
            ("/api/v1/diary/", {"matter": str(self.matter.pk), "title": "x", "starts_at": "2030-01-01T09:00:00+03:00"}),
            ("/api/v1/documents/", {"matter": str(self.matter.pk), "title": "x"}),
            (f"/api/v1/documents/templates/{self.template.pk}/draft/", {"matter": str(self.matter.pk)}),
        ]


class CrossFirmAccessTests(VictimFirm):
    """OWASP A01 Broken Access Control: BOLA / IDOR across firms."""

    def test_no_intruder_can_read_any_record_by_its_id(self):
        for intruder in self.intruders:
            api = api_as(intruder)
            for url in self.object_urls():
                status = api.get(url).status_code
                self.assertIn(status, ALLOWED_DENIALS, f"{intruder.role} read {url} -> {status}")

    def test_no_intruder_can_change_or_delete_any_record(self):
        for intruder in self.intruders:
            api = api_as(intruder)
            for url in self.object_urls():
                for method in ("patch", "delete"):
                    status = getattr(api, method)(url, {"title": "pwned", "status": "closed"}, format="json").status_code
                    self.assertIn(status, ALLOWED_DENIALS, f"{intruder.role} {method} {url} -> {status}")
        self.matter.refresh_from_db()
        self.assertEqual(self.matter.title, "Sensitive v. Secret")
        self.assertTrue(Note.objects.filter(pk=self.note.pk).exists())

    def test_no_intruder_can_trigger_actions(self):
        for intruder in self.intruders:
            api = api_as(intruder)
            for url, body in self.action_urls():
                status = api.post(url, body, format="json").status_code
                self.assertIn(status, ALLOWED_DENIALS | {400}, f"{intruder.role} POST {url} -> {status}")
        self.event.refresh_from_db()
        self.assertEqual(self.event.outcome, "pending")
        self.assertEqual(self.invoice.payments.count(), 0)
        self.assertEqual(Message.objects.filter(matter=self.matter).count(), 1)
        self.assertEqual(CourtEvent.objects.filter(matter=self.matter).count(), 1)

    def test_lists_and_searches_never_leak(self):
        for intruder in self.intruders:
            api = api_as(intruder)
            for url in ("/api/v1/matters/?search=Secret", "/api/v1/clients/?search=victim", "/api/v1/documents/?q=evidence",
                        "/api/v1/library/?search=Victim", "/api/v1/messages/threads/", "/api/v1/audit/events/",
                        "/api/v1/documents/signatures/", "/api/v1/notifications/"):
                response = api.get(url)
                if response.status_code == 200:
                    self.assertNotIn("Secret", response.content.decode(), f"{intruder.role} {url}")
                    self.assertNotIn("Victim", response.content.decode(), f"{intruder.role} {url}")
                    self.assertNotIn(str(self.matter.pk), response.content.decode(), f"{intruder.role} {url}")


class RoleAccessTests(VictimFirm):
    """OWASP A01: each role inside the firm gets exactly what it should."""

    def test_client_sees_only_their_own_shared_things(self):
        api = api_as(self.client_user)
        self.assertEqual(api.get("/api/v1/notes/").data["count"], 0)  # not shared with them
        self.assertEqual(api.get("/api/v1/tasks/").data["count"], 0)
        for url in ("/api/v1/auth/team/", "/api/v1/reports/", "/api/v1/firm/settings/", "/api/v1/audit/events/", "/api/v1/platform/firms/"):
            self.assertIn(api.get(url).status_code, {403, 404}, url)
        self.assertEqual(api.get("/api/v1/library/").data["count"], 0)
        other_client = make_client(name="Another client", email="other@x.test", firm=self.a)
        self.assertEqual(api.get(f"/api/v1/clients/{other_client.pk}/").status_code, 404)

    def test_receptionist_keeps_diary_but_not_files(self):
        api = api_as(make_user(Role.RECEPTIONIST, firm=self.a))
        self.assertEqual(api.get(f"/api/v1/matters/{self.matter.pk}/").status_code, 404)
        self.assertEqual(api.get("/api/v1/notes/").data["count"], 0)
        self.assertEqual(api.get(f"/api/v1/documents/{self.doc.pk}/download/").status_code, 404)
        self.assertEqual(api.get("/api/v1/diary/").data["count"], 1)

    def test_lawyer_off_the_matter_sees_nothing_of_it(self):
        api = api_as(make_user(Role.LAWYER, firm=self.a))
        self.assertEqual(api.get(f"/api/v1/matters/{self.matter.pk}/").status_code, 404)
        self.assertEqual(api.get(f"/api/v1/documents/{self.doc.pk}/download/").status_code, 404)
        self.assertEqual(api.get(f"/api/v1/appointments/{self.appointment.pk}/").status_code, 404)

    def test_ethical_wall_blocks_even_partners(self):
        self.matter.is_restricted = True
        self.matter.save()
        api = api_as(make_user(Role.PARTNER, firm=self.a))
        self.assertEqual(api.get(f"/api/v1/matters/{self.matter.pk}/").status_code, 404)
        self.assertEqual(api.get(f"/api/v1/documents/{self.doc.pk}/").status_code, 404)

    def test_accountant_cannot_change_case_files(self):
        api = api_as(make_user(Role.ACCOUNTANT, firm=self.a))
        self.assertIn(api.patch(f"/api/v1/matters/{self.matter.pk}/", {"title": "x"}, format="json").status_code, {403, 404})
        self.assertIn(api.post("/api/v1/notes/", {"matter": str(self.matter.pk), "body": "x"}, format="json").status_code, {403, 404})


class PrivilegeEscalationTests(VictimFirm):
    """OWASP A01 / ASVS V4: nobody can grant themselves more power."""

    def test_cannot_promote_yourself_through_your_profile(self):
        api = api_as(self.lawyer)
        api.patch("/api/v1/auth/me/", {"role": "admin", "is_staff": True, "is_superuser": True, "firm": self.b.pk, "email": "x@x.test"}, format="json")
        me = User.objects.get(pk=self.lawyer.pk)
        self.assertEqual((me.role, me.is_staff, me.is_superuser, me.firm_id, me.email), (Role.LAWYER, False, False, self.a.pk, self.lawyer.email))

    def test_only_partners_and_the_manager_run_the_firm(self):
        api = api_as(self.lawyer)
        self.assertEqual(api.post("/api/v1/auth/team/", {"email": "x@x.test", "first_name": "x", "last_name": "y", "role": "admin"}, format="json").status_code, 403)
        self.assertEqual(api.patch("/api/v1/firm/settings/", {"name": "Taken over"}, format="json").status_code, 403)
        self.assertEqual(api.get("/api/v1/reports/").status_code, 403)
        self.assertEqual(Firm.objects.get(pk=self.a.pk).name, "Victim Advocates")

    def test_partner_cannot_move_a_colleague_to_another_firm_or_create_clients(self):
        api = api_as(make_user(Role.PARTNER, firm=self.a))
        api.patch(f"/api/v1/auth/team/{self.lawyer.pk}/", {"firm": self.b.pk}, format="json")
        self.assertEqual(User.objects.get(pk=self.lawyer.pk).firm_id, self.a.pk)
        self.assertEqual(api.post("/api/v1/auth/team/", {"email": "c@x.test", "first_name": "c", "last_name": "d", "role": "client"}, format="json").status_code, 400)

    def test_firm_staff_cannot_reach_platform_powers(self):
        partner = make_user(Role.PARTNER, firm=self.a)
        self.assertEqual(api_as(partner).get("/api/v1/platform/firms/").status_code, 403)
        self.assertEqual(api_as(partner).patch(f"/api/v1/platform/firms/{self.b.pk}/", {"is_active": False}, format="json").status_code, 403)
        self.assertTrue(Firm.objects.get(pk=self.b.pk).is_active)

    def test_client_cannot_book_with_another_firms_lawyer_or_change_bookings(self):
        api = api_as(self.client_user)
        other_lawyer = make_user(Role.LAWYER, firm=self.b)
        start = timezone.now() + timedelta(days=4)
        response = api.post("/api/v1/appointments/", {"lawyer": str(other_lawyer.pk), "starts_at": start.isoformat(),
                                                      "ends_at": (start + timedelta(minutes=30)).isoformat(), "purpose": "x"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(api.patch(f"/api/v1/appointments/{self.appointment.pk}/", {"starts_at": start.isoformat()}, format="json").status_code, 403)


class AuthenticationTests(TestCase):
    """OWASP A07 Identification and Authentication Failures / ASVS V2, V3."""

    def setUp(self):
        self.user = make_user(Role.LAWYER)

    def test_tampered_and_unsigned_tokens_are_rejected(self):
        token = str(AccessToken.for_user(self.user))
        header, payload, signature = token.split(".")
        forged = f"{header}.{payload}.{signature[:-4]}AAAA"
        none_alg = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=") + f".{payload}."
        for bad in (forged, none_alg, "garbage"):
            self.client.credentials = None
            response = self.client.get("/api/v1/matters/", HTTP_AUTHORIZATION=f"Bearer {bad}")
            self.assertEqual(response.status_code, 401, bad[:20])

    def test_expired_token_is_rejected(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=-timedelta(seconds=1))
        self.assertEqual(self.client.get("/api/v1/matters/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code, 401)

    def test_deactivated_people_lose_access_at_once(self):
        api = api_as(self.user)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(api.get("/api/v1/matters/").status_code, 401)

    def test_password_policy_refuses_weak_passwords(self):
        api = api_as(self.user)
        for weak in ("password", "12345678901234", "short1!"):
            response = api.post("/api/v1/auth/password/change/", {"current_password": PASSWORD, "new_password": weak}, format="json")
            self.assertEqual(response.status_code, 400, weak)

    def test_passwords_are_stored_with_a_slow_hash(self):
        from django.conf import settings

        self.assertTrue(settings.PASSWORD_HASHERS[-3].endswith("Argon2PasswordHasher") or "Argon2" in settings.PASSWORD_HASHERS[1])
        self.assertNotIn(PASSWORD, User.objects.get(pk=self.user.pk).password)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "throttle-test"}})
    def test_login_is_rate_limited(self):
        statuses = [
            self.client.post("/api/v1/auth/login/", {"email": "nobody@x.test", "password": "wrong"}, content_type="application/json").status_code
            for _ in range(12)
        ]
        self.assertIn(429, statuses)

    def test_refresh_cookie_is_httponly_strict_and_scoped(self):
        response = self.client.post("/api/v1/auth/login/", {"email": self.user.email, "password": PASSWORD}, content_type="application/json")
        cookie = response.cookies["lexdesk_refresh"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/api/v1/auth/")
        self.assertNotIn("refresh", response.json())  # never readable by page scripts


class InjectionTests(VictimFirm):
    """OWASP A03 Injection (SQL, header, file name) and stored XSS."""

    PAYLOADS = ["' OR '1'='1", "'; DROP TABLE matters_matter; --", "\" OR 1=1 --", "%' UNION SELECT password FROM accounts_user --", "<script>alert(1)</script>"]

    def test_search_and_filters_treat_input_as_data(self):
        api = api_as(self.lawyer)
        for payload in self.PAYLOADS:
            for url in ("/api/v1/matters/", "/api/v1/clients/", "/api/v1/library/", "/api/v1/documents/"):
                response = api.get(url, {"search": payload, "q": payload, "ordering": payload})
                self.assertEqual(response.status_code, 200, (url, payload))
                self.assertNotIn("pbkdf2", response.content.decode())
                self.assertNotIn("argon2", response.content.decode())
        self.assertTrue(type(self.matter).objects.filter(pk=self.matter.pk).exists())

    def test_script_in_data_is_escaped_in_emails(self):
        self.client_record.name = "<script>alert('x')</script>"
        self.client_record.save()
        from apps.notifications.services import notify

        notify(self.lawyer, subject="Test", body="Client: <script>alert('x')</script>")
        html = mail.outbox[-1].alternatives[0][0]
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_download_filename_cannot_inject_headers_or_paths(self):
        evil = Document.objects.create(matter=self.matter, title="x", uploaded_by=self.lawyer)
        add_version(evil, SimpleUploadedFile("../../etc/passwd\r\nX-Evil: 1.pdf", pdf_upload().read()), user=self.lawyer)
        response = api_as(self.lawyer).get(f"/api/v1/documents/{evil.pk}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("X-Evil", response.headers)
        self.assertNotIn("../", response["Content-Disposition"])


class UploadTests(VictimFirm):
    """OWASP A04/A05: only genuine, allowed files enter the vault."""

    def upload(self, name, content):
        return api_as(self.lawyer).post("/api/v1/documents/", {"matter": str(self.matter.pk), "title": "x", "file": SimpleUploadedFile(name, content)}, format="multipart")

    def test_disguised_and_dangerous_files_are_refused(self):
        self.assertEqual(self.upload("invoice.pdf", b"MZ\x90\x00 this is a Windows program").status_code, 400)
        self.assertEqual(self.upload("page.html", b"<html><script>x</script></html>").status_code, 400)
        self.assertEqual(self.upload("logo.svg", b"<svg onload=alert(1)>").status_code, 400)
        self.assertEqual(self.upload("run.exe", b"MZ").status_code, 400)
        self.assertEqual(self.upload("empty.pdf", b"").status_code, 400)

    @override_settings(LEXDESK_MAX_UPLOAD_MB=1)
    def test_oversized_files_are_refused(self):
        self.assertEqual(self.upload("big.pdf", b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10)).status_code, 400)


class DataProtectionTests(VictimFirm):
    """OWASP A02 Cryptographic Failures: sensitive data is unreadable at rest."""

    def raw(self, table, column, where_id):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {column} FROM {table} WHERE id = %s", [str(where_id).replace("-", "")])
            row = cursor.fetchone()
            if row is None:
                cursor.execute(f"SELECT {column} FROM {table} WHERE id = %s", [str(where_id)])
                row = cursor.fetchone()
        return str(row[0])

    def test_privileged_text_is_encrypted_in_the_database(self):
        self.client_record.national_id = "CM90012345ABCD"
        self.client_record.save()
        self.assertNotIn("privileged strategy", self.raw("matters_note", "body", self.note.pk))
        self.assertNotIn("privileged message", self.raw("messaging_message", "body", self.message.pk))
        self.assertNotIn("CM90012345ABCD", self.raw("clients_client", "national_id", self.client_record.pk))

    def test_documents_are_ciphertext_on_disk(self):
        version = self.doc.latest
        with version.blob.open("rb") as fh:
            stored = fh.read()
        self.assertNotIn(b"%PDF", stored)
        self.assertNotIn(b"trailer", stored)

    def test_tampered_document_is_withheld_not_served(self):
        version = self.doc.latest
        with version.blob.open("rb") as fh:
            data = bytearray(fh.read())
        data[-1] ^= 0xFF
        with open(version.blob.path, "wb") as fh:
            fh.write(bytes(data))
        response = api_as(self.lawyer).get(f"/api/v1/documents/{self.doc.pk}/download/")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "integrity_failure")

    def test_secrets_never_come_back_from_the_api(self):
        Firm.objects.filter(pk=self.a.pk).update(whatsapp_access_token="EAAG-very-secret", flutterwave_secret_key="FLWSECK-secret", at_api_key="atsk-secret")
        partner = make_user(Role.PARTNER, firm=self.a)
        body = api_as(partner).get("/api/v1/firm/settings/").content.decode()
        for secret in ("EAAG-very-secret", "FLWSECK-secret", "atsk-secret"):
            self.assertNotIn(secret, body)
        mfa_user = make_user(Role.LAWYER, firm=self.a)
        mfa_user.mfa_secret = "JBSWY3DPEHPK3PXP"
        mfa_user.save()
        self.assertNotIn("JBSWY3DPEHPK3PXP", api_as(mfa_user).get("/api/v1/auth/me/").content.decode())

    def test_api_responses_are_never_cached(self):
        response = api_as(self.lawyer).get(f"/api/v1/matters/{self.matter.pk}/")
        self.assertEqual(response["Cache-Control"], "no-store")


class AuditTrailTests(VictimFirm):
    """OWASP A09 Security Logging and Monitoring Failures."""

    def test_sensitive_actions_are_recorded(self):
        api_as(self.lawyer).get(f"/api/v1/documents/{self.doc.pk}/download/")
        api_as(self.lawyer).get(f"/api/v1/matters/{self.matter.pk}/")
        actions = set(AuditEvent.objects.values_list("action", flat=True))
        self.assertTrue({"document.downloaded", "matter.viewed"} <= actions)

    def test_tampering_with_history_is_detected(self):
        for i in range(3):
            record("test.event", actor=self.lawyer, n=i)
        self.assertTrue(verify_chain()[0])
        middle = AuditEvent.objects.order_by("id")[1]
        with connection.cursor() as cursor:
            cursor.execute("UPDATE audit_auditevent SET action = 'innocent.event' WHERE id = %s", [middle.id])
        ok, broken_at, _ = verify_chain()
        self.assertFalse(ok)
        self.assertEqual(broken_at, middle.id)

    def test_audit_trail_is_read_only(self):
        event = record("test.event", actor=self.lawyer)
        with self.assertRaises(Exception):
            event.action = "changed"
            event.save()
        with self.assertRaises(Exception):
            event.delete()
        api = api_as(make_user(Role.PARTNER, firm=self.a))
        self.assertEqual(api.post("/api/v1/audit/events/", {"action": "x"}, format="json").status_code, 405)
        self.assertEqual(api.delete(f"/api/v1/audit/events/{event.pk}/").status_code, 405)

    def test_audit_never_stores_content(self):
        api_as(self.lawyer).post("/api/v1/notes/", {"matter": str(self.matter.pk), "body": "Top secret plan"}, format="json")
        self.assertFalse(any("Top secret plan" in str(d) for d in AuditEvent.objects.values_list("details", flat=True)))


class PublicSurfaceTests(VictimFirm):
    """What a stranger on the internet can reach, and nothing more."""

    def test_public_lawyer_list_shows_names_only(self):
        rows = self.client.get("/api/v1/appointments/public/lawyers/", {"firm": "victim"}).json()
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(set(row), {"id", "name", "title"})

    def test_public_firm_page_has_no_secrets_or_internals(self):
        body = self.client.get("/api/v1/firm/public/", {"firm": "victim"}).content.decode()
        for word in ("token", "secret", "api_key", "hash", "flutterwave", "at_username", "whatsapp_phone_number_id"):
            self.assertNotIn(word, body.lower(), word)

    def test_everything_else_needs_a_session(self):
        for url in ("/api/v1/matters/", "/api/v1/clients/", "/api/v1/documents/", "/api/v1/diary/", "/api/v1/messages/threads/",
                    "/api/v1/reports/", "/api/v1/library/", "/api/v1/notifications/", "/api/v1/auth/me/", "/api/v1/billing/invoices/"):
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_unknown_firm_is_not_guessed(self):
        self.assertEqual(self.client.get("/api/v1/firm/public/", {"firm": "does-not-exist"}).status_code, 404)

    def test_security_headers_are_present(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", response["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_errors_do_not_leak_internals(self):
        response = api_as(self.lawyer).get("/api/v1/matters/not-a-uuid/")
        self.assertIn(response.status_code, {400, 404})
        self.assertNotIn("Traceback", response.content.decode())
        self.assertNotIn("django", response.content.decode().lower())


class BackupAndKeyTests(VictimFirm):
    """Recovery: a restored copy works with the keys, and is useless without them."""

    def test_restored_vault_copy_decrypts_with_the_right_keys_only(self):
        import shutil
        import tempfile

        from apps.core import crypto
        from apps.core.crypto import DecryptionError
        from apps.documents.services import read_version

        version = self.doc.latest
        original = read_version(version)
        backup_dir = tempfile.mkdtemp()
        try:
            # "Backup": copy the stored ciphertext elsewhere, then "lose" the original.
            backup_path = shutil.copy(version.blob.path, backup_dir)
            with open(version.blob.path, "wb") as fh:
                fh.write(b"disk failure")
            # "Restore": put the backup back.
            shutil.copy(backup_path, version.blob.path)
            self.assertEqual(read_version(version), original)

            # The same backup with the wrong keys (a thief's copy) is unreadable.
            other_key = crypto.generate_vault_key()
            with self.settings(LEXDESK_VAULT_KEYS=f"k9:{other_key}"):
                crypto.vault_keys.cache_clear()
                with self.assertRaises(DecryptionError):
                    read_version(version)
        finally:
            crypto.vault_keys.cache_clear()
            shutil.rmtree(backup_dir, ignore_errors=True)
