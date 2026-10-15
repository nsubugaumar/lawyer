"""
Drafting from the firm's templates.

A template is ordinary text with placeholders. Choosing a matter fills them
in and files a Word draft in that matter's documents, ready to edit. The
placeholders a template may use are listed in PLACEHOLDERS, and the settings
screen shows them, so nobody has to guess.
"""

import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.services import record
from apps.core.filemakers import make_docx

from .models import Document, DocumentTemplate
from .services import add_version

PLACEHOLDERS = {
    "today": "Today's date, e.g. 15 October 2026",
    "client.name": "Client's full name",
    "client.address": "Client's address",
    "client.contact_person": "Contact person (organisations)",
    "matter.reference": "Our reference, e.g. NSC-2026-0004",
    "matter.title": "Matter title",
    "matter.court": "Court",
    "matter.case_number": "Case number",
    "matter.judge": "Judge",
    "matter.opposing_counsel": "Opposing counsel",
    "lawyer.name": "Lead lawyer's name",
    "lawyer.title": "Lead lawyer's title",
    "firm.name": "The firm's name",
    "firm.address": "The firm's address",
    "firm.phone": "The firm's phone",
    "firm.email": "The firm's email",
}

TOKEN = re.compile(r"\{\{\s*([a-z_.]+)\s*\}\}")


def context_for(matter) -> dict[str, str]:
    firm, client, lawyer = matter.firm, matter.client, matter.lead_lawyer
    return {
        "today": timezone.localdate().strftime("%d %B %Y").lstrip("0"),
        "client.name": client.name,
        "client.address": client.address,
        "client.contact_person": client.contact_person or client.name,
        "matter.reference": matter.reference,
        "matter.title": matter.title,
        "matter.court": matter.court,
        "matter.case_number": matter.case_number,
        "matter.judge": matter.judge,
        "matter.opposing_counsel": matter.opposing_counsel,
        "lawyer.name": lawyer.full_name if lawyer else "",
        "lawyer.title": lawyer.title if lawyer else "",
        "firm.name": firm.name if firm else "",
        "firm.address": firm.address if firm else "",
        "firm.phone": firm.phone if firm else "",
        "firm.email": firm.email if firm else "",
    }


def fill(text: str, values: dict[str, str]) -> str:
    # Unknown or empty placeholders become a visible blank to complete by hand.
    return TOKEN.sub(lambda m: values.get(m.group(1)) or "________", text)


def draft_from_template(template: DocumentTemplate, matter, *, user, title: str = "") -> Document:
    values = context_for(matter)
    firm = matter.firm
    letterhead = None
    if template.letterhead and firm:
        contact = " · ".join(x for x in (firm.phone, firm.email) if x)
        letterhead = [firm.name] + [x for x in (firm.address.replace("\n", ", "), contact) if x]
    content = make_docx(fill(template.body, values), letterhead=letterhead)

    title = title or f"{template.name} – {matter.client.name}"
    document = Document.objects.create(matter=matter, title=title[:250], category=template.category, uploaded_by=user,
                                       description=f"Drafted from the template “{template.name}”")
    safe = re.sub(r"[^\w\- ]", "", title)[:80].strip() or "draft"
    add_version(document, SimpleUploadedFile(f"{safe}.docx", content), user=user, comment="Draft from template")
    record("document.drafted_from_template", actor=user, target=document, matter=matter, template=str(template.pk))
    return document


STARTER_TEMPLATES = [
    {
        "name": "Engagement letter",
        "category": "contract",
        "description": "Terms of engagement for a new client, ready for e-signature.",
        "body": """{{today}}

{{client.name}}
{{client.address}}

Dear {{client.contact_person}},

**ENGAGEMENT LETTER: {{matter.title}} (Our ref: {{matter.reference}})**

Thank you for instructing {{firm.name}}. This letter sets out the terms on which we will act for you.

**1. The work**
We will advise and represent you in the matter described above. {{lawyer.name}}, {{lawyer.title}}, will be responsible for your matter and will keep you informed at every stage.

**2. Fees**
Our fees will be charged at the rates agreed with you, together with disbursements and VAT. We will send you invoices regularly, and you can follow them in your client portal.

**3. Confidentiality**
Everything you tell us is confidential and protected by legal professional privilege.

**4. Your consent**
Please sign this letter electronically in your client portal to confirm you accept these terms.

Yours faithfully,

{{lawyer.name}}
For and on behalf of {{firm.name}}""",
    },
    {
        "name": "Letter of demand",
        "category": "correspondence",
        "description": "Formal demand before filing suit.",
        "body": """{{today}}

**WITHOUT PREJUDICE**

To: ________

Dear Sir/Madam,

**RE: DEMAND ON BEHALF OF {{client.name}} (Our ref: {{matter.reference}})**

We act for {{client.name}}, on whose instructions we write.

Our client's claim is as follows: ________

We hereby demand payment of UGX ________ within seven (7) days of the date of this letter, failing which we have firm instructions to commence legal proceedings against you without further notice, at your cost.

Yours faithfully,

{{lawyer.name}}
{{firm.name}}""",
    },
    {
        "name": "Letter to the court registrar",
        "category": "correspondence",
        "description": "Request a hearing date or a certified copy.",
        "body": """{{today}}

The Registrar
{{matter.court}}

Dear Sir/Madam,

**RE: {{matter.case_number}}: {{matter.title}}**

We act for {{client.name}} in the above matter.

We respectfully request ________

We shall be grateful for your assistance.

Yours faithfully,

{{lawyer.name}}
{{firm.name}}""",
    },
    {
        "name": "Affidavit (skeleton)",
        "category": "pleading",
        "description": "Heading and jurat for a supporting affidavit.",
        "letterhead": False,
        "body": """**THE REPUBLIC OF UGANDA**
**IN THE {{matter.court}}**
**{{matter.case_number}}**

**{{matter.title}}**

**AFFIDAVIT**

I, ________, of ________, Uganda, make oath and state as follows:

1. That I am an adult of sound mind and the deponent herein, well versed with the facts of this matter, and swear this affidavit in that capacity.

2. That ________

3. That whatever is stated herein is true and correct to the best of my knowledge and belief.

SWORN at ________ this ____ day of ________ 20__

________
DEPONENT

BEFORE ME:

________
COMMISSIONER FOR OATHS

Drawn and filed by:
{{firm.name}}
{{firm.address}}""",
    },
]


def add_starter_templates(firm, user):
    created = []
    for spec in STARTER_TEMPLATES:
        if not DocumentTemplate.objects.filter(firm=firm, name=spec["name"]).exists():
            created.append(DocumentTemplate.objects.create(
                firm=firm, created_by=user, name=spec["name"], category=spec["category"], description=spec["description"],
                body=spec["body"], letterhead=spec.get("letterhead", True),
            ))
    return created
