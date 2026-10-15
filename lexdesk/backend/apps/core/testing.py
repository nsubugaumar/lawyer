"""Small helpers so tests read like the story they are telling."""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.tokens import build_refresh
from apps.clients.models import Client
from apps.matters.models import Matter, MatterMember

PASSWORD = "Correct-Horse-Battery-9"
TINY_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def make_firm(name="Okello & Partners Advocates", slug=None, code=None):
    from django.utils.text import slugify

    from apps.firm.models import Firm

    slug = slug or slugify(name)[:60]
    code = code or "".join(w[0] for w in name.split() if w[:1].isalpha()).upper()[:6]
    return Firm.objects.get_or_create(slug=slug, defaults={"name": name, "code": code})[0]


def default_firm():
    return make_firm("Test Chambers Advocates", slug="test-chambers", code="TC")


def make_user(role=Role.LAWYER, email=None, firm=None, **extra):
    email = email or f"{role}.{User.objects.count() + 1}@firm.test"
    extra.setdefault("hourly_rate", 300000)
    extra["firm"] = firm or default_firm()
    return User.objects.create_user(email=email, password=PASSWORD, first_name=role.title(), last_name="Tester", role=role, **extra)


def api_as(user, *, mfa=True) -> APIClient:
    client = APIClient()
    if user is not None:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {build_refresh(user, used_mfa=mfa).access_token}")
    return client


def make_client(name="Jane Okello", email="jane@client.test", portal_user=None, firm=None):
    firm = firm or (portal_user.firm if portal_user else None) or default_firm()
    return Client.objects.create(firm=firm, name=name, email=email, portal_user=portal_user, status=Client.Status.ACTIVE)


def make_matter(lead, client=None, *, restricted=False, title="Okello v. Kampala Traders Ltd"):
    client = client or make_client(email=f"client.{Matter.objects.count() + 1}@client.test", firm=lead.firm)
    matter = Matter.objects.create(firm=lead.firm, title=title, client=client, lead_lawyer=lead, is_restricted=restricted)
    MatterMember.objects.create(matter=matter, user=lead, role=MatterMember.Role.LEAD)
    return matter


def pdf_upload(name="plaint.pdf", content=TINY_PDF):
    return SimpleUploadedFile(name, content, content_type="application/pdf")
