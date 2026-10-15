"""
Who can see which matter. This is the most important file in LexDesk.

Every other module (documents, diary, tasks, billing) asks this one question:
"which matters may this person see?", and filters by the answer. Keeping the
rule in one place means there is one thing to get right, one thing to test,
and no forgotten endpoint that quietly shows a document to the wrong person.

The rules:
  * Nobody ever sees a matter of another firm. Everything below happens
    inside the person's own firm.
  * Clients see only matters belonging to their own client record.
  * Administrators and partners see every matter except restricted ones
    (ethical walls) they are not personally on.
  * Accountants see every unrestricted matter, for billing.
  * Lawyers and paralegals see only matters they are members of.
  * Receptionists see no matters at all; they handle clients and diaries.

Seeing a matter is not the same as reading its privileged file notes: those
are for the matter team only (see `can_read_privileged`).
"""

from django.db.models import Q, QuerySet

from apps.accounts.models import SEES_ALL_MATTERS, Role

from .models import Matter


def visible_matters(user) -> QuerySet[Matter]:
    if not user or not user.is_authenticated or not user.is_active:
        return Matter.objects.none()

    if not user.firm_id:
        return Matter.objects.none()  # platform operators manage firms, not files

    qs = Matter.objects.filter(firm_id=user.firm_id)
    is_member = Q(memberships__user=user) | Q(lead_lawyer=user)

    if user.role == Role.CLIENT:
        return qs.filter(client__portal_user=user, status__in=["open", "on_hold", "closed"])

    if user.role in SEES_ALL_MATTERS or user.role == Role.ACCOUNTANT:
        return qs.filter(Q(is_restricted=False) | is_member).distinct()

    if user.role in (Role.LAWYER, Role.PARALEGAL):
        return qs.filter(is_member).distinct()

    return qs.none()


def is_on_team(user, matter) -> bool:
    return matter.lead_lawyer_id == user.id or matter.memberships.filter(user=user).exists()


def can_read_privileged(user, matter) -> bool:
    """
    File notes record what lawyer and client discussed and how the case will
    be run. Partners oversee every matter, but these stay with the lawyers on
    the matter team (and with the client, for notes shared with them).
    """
    if user.role == Role.CLIENT:
        return can_see_matter(user, matter)
    return matter.firm_id == user.firm_id and is_on_team(user, matter)


def can_see_matter(user, matter) -> bool:
    return visible_matters(user).filter(pk=matter.pk).exists()


def can_work_on_matter(user, matter) -> bool:
    """Write access: staff (not clients, not accountants) who can see the matter."""
    if user.role in (Role.CLIENT, Role.ACCOUNTANT, Role.RECEPTIONIST):
        return False
    return can_see_matter(user, matter)
