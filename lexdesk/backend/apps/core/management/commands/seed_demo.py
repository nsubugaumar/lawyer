from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.appointments.models import Appointment
from apps.billing.models import TimeEntry
from apps.clients.models import Client
from apps.documents.models import Document
from apps.documents.services import add_version
from apps.firm.models import Firm
from apps.matters.models import CourtEvent, Matter, MatterMember, Note, Party, Task

# Demo data only, on a developer machine. Real accounts must meet the
# 12-character policy; this one is set directly and never validated.
DEMO_PASSWORD = "2000"


def pdf(text: str) -> bytes:
    """A real, minimal, valid one-page PDF with a line of text on it."""
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


class Command(BaseCommand):
    help = "Fill a development database with a believable small firm. Refuses to run in production."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with LEXDESK_DEBUG=1. Never seed a real firm's database.")
        with transaction.atomic():
            if User.objects.filter(email="admin@demo.lexdesk").exists():
                self.stdout.write("First demo firm already present.")
            else:
                self._seed()
            self._second_firm()
            self._operator()

    def _person(self, email, first, last, role, title="", rate=None, firm=None):
        return User.objects.create_user(
            email=email, password=DEMO_PASSWORD, first_name=first, last_name=last, role=role, title=title,
            hourly_rate=rate, phone="+256700000000", firm=firm or self.firm,
        )

    def _at(self, days, hour, minute=0):
        day = timezone.localdate() + timedelta(days=days)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        return timezone.make_aware(datetime.combine(day, time(hour, minute)))

    def _seed(self):
        self.firm = self._firm()
        admin = self._person("admin@demo.lexdesk", "Ruth", "Achieng", Role.ADMIN, "Practice Manager")
        partner = self._person("partner@demo.lexdesk", "David", "Ssempala", Role.PARTNER, "Managing Partner", Decimal("500000"))
        lawyer = self._person("lawyer@demo.lexdesk", "Grace", "Namubiru", Role.LAWYER, "Senior Associate", Decimal("300000"))
        paralegal = self._person("paralegal@demo.lexdesk", "Brian", "Okot", Role.PARALEGAL, "Paralegal", Decimal("120000"))
        self._person("reception@demo.lexdesk", "Esther", "Nalwoga", Role.RECEPTIONIST, "Front Desk")
        self._person("accounts@demo.lexdesk", "Moses", "Kato", Role.ACCOUNTANT, "Accounts")
        client_user = self._person("client@demo.lexdesk", "Jane", "Okello", Role.CLIENT)

        jane = Client.objects.create(firm=self.firm, name="Jane Okello", email=client_user.email, phone="+256772111222",
                                     status=Client.Status.ACTIVE, portal_user=client_user, responsible_lawyer=lawyer,
                                     national_id="CF85012345ABCD")
        nile = Client.objects.create(firm=self.firm, kind=Client.Kind.ORGANISATION, name="Nile Breweries Distribution Ltd",
                                     contact_person="Samuel Mwesigwa", email="legal@nile.example", status=Client.Status.ACTIVE)
        estate = Client.objects.create(firm=self.firm, name="Estate of the late Peter Mukasa", email="family@mukasa.example",
                                       status=Client.Status.ACTIVE)

        def matter(title, client, area, lead, team, **kw):
            m = Matter.objects.create(title=title, client=client, practice_area=area, lead_lawyer=lead, **kw)
            MatterMember.objects.create(matter=m, user=lead, role=MatterMember.Role.LEAD)
            for person in team:
                MatterMember.objects.get_or_create(matter=m, user=person)
            return m

        m1 = matter("Okello v. Kampala Traders Ltd", jane, "litigation", lawyer, [paralegal, partner],
                    court="High Court (Commercial Division), Kampala", case_number="HCCS 412 of 2026",
                    judge="Hon. Justice A. Mugenyi", opposing_counsel="Kyazze & Co. Advocates",
                    description="Breach of supply contract; claim for UGX 86,000,000 plus interest.")
        m2 = matter("Nile Breweries: distributor agreements review", nile, "corporate", partner, [lawyer])
        m3 = matter("Mukasa succession: letters of administration", estate, "family", lawyer, [paralegal],
                    court="High Court (Family Division)", case_number="AC 77 of 2026")

        Party.objects.create(matter=m1, name="Kampala Traders Ltd", role=Party.Role.DEFENDANT, represented_by="Kyazze & Co.")
        Party.objects.create(matter=m1, name="John Byaruhanga", role=Party.Role.WITNESS)

        CourtEvent.objects.create(matter=m1, kind="hearing", title="Hearing of the main suit", starts_at=self._at(1, 9, 30),
                                  location="Court Room 4, Commercial Court")
        CourtEvent.objects.create(matter=m1, kind="filing_deadline", title="File reply to written statement of defence",
                                  starts_at=self._at(3, 17))
        CourtEvent.objects.create(matter=m3, kind="mention", title="Mention for grant", starts_at=self._at(5, 11),
                                  location="Family Division, Room 2")
        for e in CourtEvent.objects.all():
            e.attendees.add(e.matter.lead_lawyer)

        Task.objects.create(matter=m1, title="Prepare trial bundle", assigned_to=paralegal, due_on=timezone.localdate(),
                            priority="high", created_by=lawyer)
        Task.objects.create(matter=m1, title="Draft witness statement for J. Byaruhanga", assigned_to=lawyer,
                            due_on=timezone.localdate() + timedelta(days=2), created_by=lawyer)
        Task.objects.create(matter=m2, title="Redline clause 14 (exclusivity)", assigned_to=lawyer,
                            due_on=timezone.localdate() - timedelta(days=1), priority="urgent", created_by=partner)

        Note.objects.create(matter=m1, author=lawyer, body="Client confirms delivery notes for March are in her office. Collect Thursday.")
        Note.objects.create(matter=m1, author=lawyer, shared_with_client=True,
                            body="Your hearing is set for tomorrow at 9:30. Please arrive by 9:00 with your ID.")

        for title, cat, bundle, shared in [
            ("Plaint", "pleading", True, True),
            ("Supply contract dated 3 Feb 2025", "evidence", True, True),
            ("Written statement of defence", "pleading", True, False),
            ("Authority: Mulindwa v. Uganda Breweries", "authority", True, False),
            ("Internal strategy memo", "internal", False, False),
        ]:
            doc = Document.objects.create(matter=m1, title=title, category=cat, court_bundle=bundle,
                                          shared_with_client=shared, uploaded_by=lawyer)
            add_version(doc, SimpleUploadedFile(f"{title[:30]}.pdf", pdf(title)), user=lawyer)

        Appointment.objects.create(client=jane, matter=m1, lawyer=lawyer, starts_at=self._at(2, 14), ends_at=self._at(2, 14, 30),
                                   mode="in_person", status="confirmed", purpose="Prepare for trial", location="Office, Boardroom")
        Appointment.objects.create(client=nile, lawyer=partner, starts_at=self._at(1, 15), ends_at=self._at(1, 15, 30),
                                   mode="video", status="requested", purpose="Distributor contract walkthrough")

        for days, mins, text in [(0, 90, "Drafting reply to WSD"), (1, 45, "Call with client"), (2, 120, "Research on damages")]:
            TimeEntry.objects.create(matter=m1, user=lawyer, date=timezone.localdate() - timedelta(days=days),
                                     minutes=mins, description=text, rate=lawyer.hourly_rate)

        self.stdout.write(self.style.SUCCESS("Demo firm created. Everyone's password is: " + DEMO_PASSWORD))
        for u in User.objects.order_by("role"):
            self.stdout.write(f"  {u.get_role_display():<14} {u.email}")
        self.stdout.write(f"Practice manager: {admin.email}")

    def _firm(self):
        firm = Firm.objects.filter(people__email="partner@demo.lexdesk").first() or Firm(slug="namubiru-ssempala", code="NSC")
        firm.name = "Namubiru, Ssempala & Co. Advocates"
        firm.tagline = "Trusted counsel. Clear answers. Every step of the way."
        firm.about = (
            "For over fifteen years we have stood beside families, entrepreneurs and companies across Uganda. "
            "We listen first, explain plainly, and fight hard when it matters. Every client has a named lawyer "
            "who answers their calls, and every case is run on a secure, paperless file you can follow from your phone."
        )
        firm.founded_year = 2010
        firm.phone = "+256414123456"
        firm.whatsapp_number = "+256772123456"
        firm.email = "hello@demo.lexdesk"
        firm.address = "Plot 14, Kampala Road, Workers House, 6th Floor, Kampala, Uganda"
        firm.map_url = "https://maps.google.com/?q=Workers+House+Kampala"
        firm.facebook_url = "https://www.facebook.com/lexdeskdemo"
        firm.instagram_url = "https://www.instagram.com/lexdeskdemo"
        firm.x_url = "https://x.com/lexdeskdemo"
        firm.linkedin_url = "https://www.linkedin.com/company/lexdeskdemo"
        firm.save()
        return firm

    def _second_firm(self):
        """A second, completely separate firm, to see that neither sees the other."""
        if User.objects.filter(email="partner@kato.demo").exists():
            return
        firm = Firm.objects.create(
            slug="kato-associates", code="KAA", name="Kato & Associates Advocates", theme=Firm.Theme.OXFORD_BURGUNDY,
            tagline="Sound advice for growing businesses.", phone="+256414765432", whatsapp_number="+256701765432",
            email="info@kato.demo", address="Plot 3, Lumumba Avenue, Kampala", founded_year=2016,
            practice_areas=["corporate", "employment", "tax", "land"],
        )
        partner = self._person("partner@kato.demo", "Moses", "Kato", Role.PARTNER, "Managing Partner", Decimal("450000"), firm=firm)
        lawyer = self._person("lawyer@kato.demo", "Aisha", "Nantongo", Role.LAWYER, "Associate", Decimal("250000"), firm=firm)
        client = Client.objects.create(firm=firm, kind=Client.Kind.ORGANISATION, name="Rwenzori Coffee Exporters Ltd",
                                       contact_person="Paul Mugisha", email="legal@rwenzori.example", status=Client.Status.ACTIVE)
        matter = Matter.objects.create(firm=firm, title="Rwenzori Coffee: employment dispute", client=client,
                                       practice_area="employment", lead_lawyer=lawyer, court="Industrial Court, Kampala",
                                       case_number="LDR 101 of 2026")
        MatterMember.objects.create(matter=matter, user=lawyer, role=MatterMember.Role.LEAD)
        event = CourtEvent.objects.create(matter=matter, kind="mention", title="Mention", starts_at=self._at(2, 10),
                                          location="Industrial Court, Room 1")
        event.attendees.add(lawyer)
        Note.objects.create(matter=matter, author=lawyer, body="Kato firm only: client willing to mediate.")
        self.stdout.write(f"Second firm: {firm.name} ({partner.email}, {lawyer.email})")

    def _operator(self):
        """The platform owner: adds and suspends firms, sees no firm's files."""
        if not User.objects.filter(email="owner@lexdesk.local").exists():
            User.objects.create_superuser("owner@lexdesk.local", DEMO_PASSWORD, first_name="Platform", last_name="Owner")
            self.stdout.write("Platform owner: owner@lexdesk.local")
