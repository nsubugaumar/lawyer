import logging

from django.db import transaction
from django.utils import timezone

from .context import request_ip, request_user_agent
from .models import GENESIS_HASH, AuditEvent

logger = logging.getLogger("lexdesk.security")


def record(action: str, *, actor=None, target=None, matter=None, **details) -> AuditEvent:
    """
    Write one line in the firm's permanent record.

        record("document.downloaded", actor=request.user, target=doc, matter=doc.matter, version=3)

    Keep `details` free of confidential content. Log that a note was edited,
    not what the note says.
    """
    actor = actor if getattr(actor, "is_authenticated", False) else None

    with transaction.atomic():
        # Lock the tail of the chain so two simultaneous events cannot both
        # claim the same predecessor. (A no-op on SQLite, which serialises
        # writes anyway.)
        last = AuditEvent.objects.select_for_update().order_by("-id").only("hash").first()
        event = AuditEvent(
            at=timezone.now(),
            actor=actor,
            actor_email=getattr(actor, "email", "") or "",
            action=action,
            target_type=type(target).__name__ if target is not None else "",
            target_id=str(target.pk) if target is not None else "",
            matter_id=str(matter.pk) if matter is not None else "",
            firm_id=_firm_of(actor, target, matter),
            ip_address=request_ip.get(),
            user_agent=request_user_agent.get(),
            details=details,
            prev_hash=last.hash if last else GENESIS_HASH,
        )
        event.hash = event.compute_hash()
        event.save()

    logger.info("audit %s actor=%s target=%s:%s", action, event.actor_email or "-", event.target_type, event.target_id)
    return event


def _firm_of(*things) -> str:
    for thing in things:
        firm_id = getattr(thing, "firm_id", None)
        if firm_id:
            return str(firm_id)
        if thing is not None and thing.__class__.__name__ == "Firm" and getattr(thing, "pk", None):
            return str(thing.pk)
    return ""


def verify_chain() -> tuple[bool, int | None, int]:
    """
    Walk the whole chain. Returns (ok, first_broken_id, events_checked).
    """
    expected_prev = GENESIS_HASH
    checked = 0
    for event in AuditEvent.objects.order_by("id").iterator(chunk_size=2000):
        if event.prev_hash != expected_prev or event.compute_hash() != event.hash:
            return False, event.id, checked
        expected_prev = event.hash
        checked += 1
    return True, None, checked
