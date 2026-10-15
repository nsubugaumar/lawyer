from django.db import transaction

from apps.accounts.models import Role
from apps.accounts.provisioning import AccountInOtherFirm, provision_user
from apps.audit.services import record

from .models import Client


@transaction.atomic
def ensure_portal_account(client: Client, *, invited_by=None):
    """
    Give a client their portal login, automatically.

    Called whenever a client with an email address is registered. If the email
    already belongs to a client account (a returning client), we link to that
    instead of creating a second one.
    """
    if client.portal_user_id or not client.email:
        return client.portal_user

    try:
        user, _ = provision_user(
            email=client.email,
            first_name=client.first_name,
            last_name=client.last_name,
            role=Role.CLIENT,
            firm=client.firm,
            phone=client.phone,
            invited_by=invited_by,
        )
    except AccountInOtherFirm:
        # The same person is a client of another firm too. Their logins stay
        # separate; this firm can still act for them without a portal.
        record("client.portal_skipped_other_firm", actor=invited_by, target=client)
        return None
    if user.role != Role.CLIENT:
        # The email belongs to a member of staff. Never merge the two: a
        # client portal must not inherit a lawyer's access.
        record("client.portal_skipped_staff_email", actor=invited_by, target=client)
        return None

    client.portal_user = user
    client.save(update_fields=["portal_user"])
    return user


def conflict_search(term: str, firm):
    """
    Before taking on a new matter a firm must check it has not acted against
    this person before. We look in clients and in every party on every matter
    (opposing parties, witnesses, co-defendants).
    """
    from apps.matters.models import Party

    term = term.strip()
    if len(term) < 3:
        return []

    hits = []
    for c in Client.objects.filter(firm=firm, name__icontains=term)[:50]:
        hits.append({"type": "client", "name": c.name, "client_id": str(c.id), "status": c.status})
    for p in Party.objects.filter(matter__firm=firm, name__icontains=term).select_related("matter", "matter__client")[:50]:
        hits.append({
            "type": "party",
            "name": p.name,
            "role": p.get_role_display(),
            "matter_id": str(p.matter_id),
            "matter_reference": p.matter.reference,
            "acting_for": p.matter.client.name,
        })
    return hits
