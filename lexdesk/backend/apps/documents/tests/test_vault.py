import shutil

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.core.testing import TINY_PDF, api_as, make_client, make_matter, make_user, pdf_upload
from apps.documents.models import DocumentVersion


class VaultTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.lawyer = make_user(Role.LAWYER)
        self.client_user = make_user(Role.CLIENT)
        self.matter = make_matter(self.lawyer, make_client(portal_user=self.client_user))
        self.api = api_as(self.lawyer)

    def _upload(self, **extra):
        data = {"matter": self.matter.id, "title": "Plaint", "category": "pleading", "file": pdf_upload(), **extra}
        r = self.api.post("/api/v1/documents/", data, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def test_upload_is_encrypted_at_rest_and_downloads_identically(self):
        doc = self._upload()
        version = DocumentVersion.objects.get(document_id=doc["id"])
        with version.blob.open("rb") as fh:
            stored = fh.read()
        self.assertNotIn(b"%PDF", stored)

        r = self.api.get(f"/api/v1/documents/{doc['id']}/download/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content) if r.streaming else r.content, TINY_PDF)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertEqual(r["Cache-Control"], "private, no-store")
        self.assertTrue(AuditEvent.objects.filter(action="document.downloaded", target_id=doc["id"]).exists())

    def test_tampered_file_is_withheld(self):
        doc = self._upload()
        version = DocumentVersion.objects.get(document_id=doc["id"])
        path = version.blob.path
        with open(path, "r+b") as fh:
            fh.seek(-1, 2)
            last = fh.read(1)
            fh.seek(-1, 2)
            fh.write(bytes([last[0] ^ 1]))
        r = self.api.get(f"/api/v1/documents/{doc['id']}/download/")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.data["error"]["code"], "integrity_failure")

    def test_program_disguised_as_pdf_is_rejected(self):
        fake = SimpleUploadedFile("evidence.pdf", b"MZ\x90\x00 this is really an .exe", content_type="application/pdf")
        r = self.api.post("/api/v1/documents/", {"matter": self.matter.id, "title": "x", "file": fake}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_disallowed_extension_is_rejected(self):
        bad = SimpleUploadedFile("run.html", b"<script>alert(1)</script>")
        r = self.api.post("/api/v1/documents/", {"matter": self.matter.id, "title": "x", "file": bad}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_versions_accumulate_and_old_ones_stay_readable(self):
        doc = self._upload()
        v2 = TINY_PDF.replace(b"1.4", b"1.7")
        r = self.api.post(f"/api/v1/documents/{doc['id']}/versions/",
                          {"file": pdf_upload(content=v2), "comment": "Amended"}, format="multipart")
        self.assertEqual(r.data["number"], 2)
        old = self.api.get(f"/api/v1/documents/{doc['id']}/download/?version=1")
        self.assertEqual(old.content, TINY_PDF)
        new = self.api.get(f"/api/v1/documents/{doc['id']}/download/")
        self.assertEqual(new.content, v2)

    def test_client_cannot_see_or_download_unshared_documents(self):
        doc = self._upload()
        client_api = api_as(self.client_user)
        self.assertEqual(client_api.get("/api/v1/documents/").data["count"], 0)
        self.assertEqual(client_api.get(f"/api/v1/documents/{doc['id']}/download/").status_code, 404)

    def test_client_sees_shared_documents(self):
        doc = self._upload(shared_with_client=True)
        r = api_as(self.client_user).get(f"/api/v1/documents/{doc['id']}/download/?inline=1")
        self.assertEqual(r.status_code, 200)
        self.assertIn("inline", r["Content-Disposition"])

    def test_client_uploads_land_in_the_review_tray(self):
        r = api_as(self.client_user).post(
            "/api/v1/documents/",
            {"matter": self.matter.id, "title": "My land title", "category": "evidence", "court_bundle": True, "file": pdf_upload()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["category"], "client_upload")

    def test_outsider_lawyer_cannot_download(self):
        doc = self._upload()
        outsider = api_as(make_user(Role.LAWYER))
        self.assertEqual(outsider.get(f"/api/v1/documents/{doc['id']}/download/").status_code, 404)

    def test_court_bundle_lists_flagged_documents_with_fingerprints(self):
        self._upload(court_bundle=True)
        self._upload(title="Internal memo")
        r = self.api.get(f"/api/v1/documents/court-bundle/?matter={self.matter.id}")
        self.assertEqual(len(r.data), 1)
        self.assertEqual(len(r.data[0]["latest"]["sha256"]), 64)

    def test_delete_archives_instead(self):
        doc = self._upload()
        self.assertEqual(self.api.delete(f"/api/v1/documents/{doc['id']}/").status_code, 204)
        self.assertEqual(self.api.get("/api/v1/documents/").data["count"], 0)
        self.assertEqual(self.api.get("/api/v1/documents/?is_archived=true").data["count"], 1)
