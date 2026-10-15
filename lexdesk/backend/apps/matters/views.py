from datetime import timedelta

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.models import FEE_EARNERS, SEES_ALL_MATTERS, Role
from apps.audit.models import AuditEvent
from apps.audit.serializers import AuditEventSerializer
from apps.audit.services import record
from apps.core.ids import as_uuid
from apps.notifications import reminders

from .access import can_read_privileged, can_work_on_matter, visible_matters
from .models import CourtEvent, Matter, MatterMember, Note, Party, Task
from .serializers import (
    ClientMatterSerializer,
    CourtEventSerializer,
    MatterMemberSerializer,
    MatterSerializer,
    NoteSerializer,
    PartySerializer,
    TaskSerializer,
)


class MatterViewSet(viewsets.ModelViewSet):
    filterset_fields = ["status", "practice_area", "client", "lead_lawyer", "is_restricted"]
    search_fields = ["reference", "title", "case_number", "client__name", "court", "judge"]
    ordering_fields = ["opened_on", "reference", "title", "updated_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return (
            visible_matters(self.request.user)
            .select_related("client", "lead_lawyer")
            .prefetch_related(Prefetch("memberships", queryset=MatterMember.objects.select_related("user")))
        )

    def get_serializer_class(self):
        return ClientMatterSerializer if getattr(self.request.user, "is_client", False) else MatterSerializer

    def _require_fee_earner(self):
        if self.request.user.role not in FEE_EARNERS | SEES_ALL_MATTERS:
            raise PermissionDenied("Only lawyers can open or change matters.")

    def retrieve(self, request, *args, **kwargs):
        matter = self.get_object()
        record("matter.viewed", actor=request.user, target=matter, matter=matter)
        return Response(self.get_serializer(matter).data)

    @transaction.atomic
    def perform_create(self, serializer):
        self._require_fee_earner()
        user = self.request.user
        if serializer.validated_data.get("is_restricted") and user.role not in SEES_ALL_MATTERS:
            raise PermissionDenied("Only partners can wall off a matter.")

        client = serializer.validated_data["client"]
        lead = serializer.validated_data.get("lead_lawyer") or user
        if client.firm_id != user.firm_id or lead.firm_id != user.firm_id:
            raise ValidationError("Choose a client and lead lawyer from your own firm.")
        matter = serializer.save(lead_lawyer=lead, firm_id=user.firm_id)
        # The person opening the matter and the lead are always on the team,
        # otherwise a lawyer could open a restricted matter and lock themselves out.
        MatterMember.objects.get_or_create(matter=matter, user=matter.lead_lawyer, defaults={"role": MatterMember.Role.LEAD})
        MatterMember.objects.get_or_create(matter=matter, user=user)
        if matter.client.status == "prospect":
            matter.client.status = "active"
            matter.client.save(update_fields=["status"])
        record("matter.opened", actor=user, target=matter, matter=matter)

    def perform_update(self, serializer):
        self._require_fee_earner()
        matter = serializer.instance
        if not can_work_on_matter(self.request.user, matter):
            raise PermissionDenied()
        if "is_restricted" in serializer.validated_data and self.request.user.role not in SEES_ALL_MATTERS:
            raise PermissionDenied("Only partners can change an ethical wall.")
        for field in ("client", "lead_lawyer"):
            other = serializer.validated_data.get(field)
            if other is not None and other.firm_id != self.request.user.firm_id:
                raise ValidationError({field: "Choose from your own firm."})

        before_status = matter.status
        matter = serializer.save()
        if matter.status == Matter.Status.CLOSED and not matter.closed_on:
            matter.closed_on = timezone.localdate()
            matter.save(update_fields=["closed_on"])
        record(
            "matter.updated", actor=self.request.user, target=matter, matter=matter,
            fields=sorted(serializer.validated_data), status_change=[before_status, matter.status],
        )

    def destroy(self, request, *args, **kwargs):
        # Lawyers have a legal duty to keep files for years after closing.
        # Matters are closed, never deleted.
        raise PermissionDenied("Matters cannot be deleted. Close the matter instead.")

    @action(detail=True, methods=["get", "post"])
    def team(self, request, pk=None):
        matter = self.get_object()
        if request.method == "GET":
            return Response(MatterMemberSerializer(matter.memberships.select_related("user"), many=True).data)

        if not can_work_on_matter(request.user, matter):
            raise PermissionDenied()
        serializer = MatterMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["user"].firm_id != request.user.firm_id:
            raise ValidationError({"user_id": "Choose a colleague from your own firm."})
        member, _ = MatterMember.objects.update_or_create(
            matter=matter, user=serializer.validated_data["user"], defaults={"role": serializer.validated_data["role"]}
        )
        record("matter.member_added", actor=request.user, target=matter, matter=matter, user=str(member.user_id))
        return Response(MatterMemberSerializer(member).data, status=201)

    @action(detail=True, methods=["delete"], url_path=r"team/(?P<user_id>[0-9a-f-]+)")
    def remove_member(self, request, pk=None, user_id=None):
        matter = self.get_object()
        if not can_work_on_matter(request.user, matter):
            raise PermissionDenied()
        if as_uuid(user_id) is None:
            raise ValidationError({"user_id": "Not a valid person."})
        if str(matter.lead_lawyer_id) == user_id:
            raise ValidationError("Assign a new lead lawyer before removing this one.")
        matter.memberships.filter(user_id=user_id).delete()
        record("matter.member_removed", actor=request.user, target=matter, matter=matter, user=user_id)
        return Response(status=204)

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        """Everything that has happened on this file, newest first."""
        matter = self.get_object()
        if request.user.is_client:
            raise PermissionDenied()
        events = AuditEvent.objects.filter(matter_id=str(matter.pk)).exclude(action="matter.viewed")[:200]
        return Response(AuditEventSerializer(events, many=True).data)


class MatterScopedViewSet(viewsets.ModelViewSet):
    """
    Base for anything that belongs to a matter. Reads are limited to visible
    matters; writes additionally require being able to work on the matter.
    """

    model = None
    audit_name = ""
    filterset_fields = ["matter"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return self.model.objects.filter(matter__in=visible_matters(self.request.user)).select_related("matter")

    def _check_write(self, matter):
        if not can_work_on_matter(self.request.user, matter):
            raise PermissionDenied("You are not on the team for this matter.")

    def _check_firm(self, matter):
        if matter.firm_id != self.request.user.firm_id:
            raise PermissionDenied()

    def perform_create(self, serializer):
        self._check_firm(serializer.validated_data["matter"])
        self._check_write(serializer.validated_data["matter"])
        self._check_people(serializer.validated_data)
        obj = serializer.save(**self.extra_create_fields())
        record(f"{self.audit_name}.created", actor=self.request.user, target=obj, matter=obj.matter)

    def perform_update(self, serializer):
        self._check_firm(serializer.instance.matter)
        self._check_write(serializer.instance.matter)
        self._check_people(serializer.validated_data)
        if "matter" in serializer.validated_data and serializer.validated_data["matter"] != serializer.instance.matter:
            raise ValidationError({"matter": "Items cannot be moved between matters."})
        obj = serializer.save()
        record(f"{self.audit_name}.updated", actor=self.request.user, target=obj, matter=obj.matter,
               fields=sorted(serializer.validated_data))

    def perform_destroy(self, instance):
        self._check_firm(instance.matter)
        self._check_write(instance.matter)
        record(f"{self.audit_name}.deleted", actor=self.request.user, target=instance, matter=instance.matter)
        instance.delete()

    def extra_create_fields(self):
        return {}

    def _check_people(self, data):
        """Anyone named on a record (assignee, attendee) must work at the firm."""
        people = list(data.get("attendees") or [])
        if data.get("assigned_to"):
            people.append(data["assigned_to"])
        if any(p.firm_id != self.request.user.firm_id for p in people):
            raise ValidationError("Choose people from your own firm.")


class PartyViewSet(MatterScopedViewSet):
    model = Party
    audit_name = "party"
    serializer_class = PartySerializer
    search_fields = ["name"]


class TaskViewSet(MatterScopedViewSet):
    model = Task
    audit_name = "task"
    serializer_class = TaskSerializer
    filterset_fields = ["matter", "status", "priority", "assigned_to"]
    search_fields = ["title"]
    ordering_fields = ["due_on", "priority", "created_at"]

    def get_queryset(self):
        if self.request.user.is_client:
            return Task.objects.none()  # internal work list, not for clients
        qs = super().get_queryset().select_related("assigned_to")
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(assigned_to=self.request.user)
        return qs

    def extra_create_fields(self):
        return {"created_by": self.request.user}

    def perform_update(self, serializer):
        new_status = serializer.validated_data.get("status")
        if new_status == Task.Status.DONE and serializer.instance.status != Task.Status.DONE:
            serializer.validated_data["completed_at"] = timezone.now()
        elif new_status and new_status != Task.Status.DONE:
            serializer.validated_data["completed_at"] = None
        super().perform_update(serializer)


class NoteViewSet(MatterScopedViewSet):
    model = Note
    audit_name = "note"
    serializer_class = NoteSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("author", "court_event")
        user = self.request.user
        if user.is_client:
            return qs.filter(shared_with_client=True)
        # Privileged: only the matter team reads file notes, partners included.
        return qs.filter(Q(matter__lead_lawyer=user) | Q(matter__memberships__user=user)).distinct()

    def _check_write(self, matter):
        if not can_read_privileged(self.request.user, matter) or self.request.user.is_client:
            raise PermissionDenied("File notes are for the matter team.")

    def extra_create_fields(self):
        return {"author": self.request.user}

    def perform_update(self, serializer):
        # A file note is a record. Only its author may change it.
        if serializer.instance.author_id != self.request.user.id:
            raise PermissionDenied("Only the author can edit a file note.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id and self.request.user.role not in SEES_ALL_MATTERS:
            raise PermissionDenied("Only the author or a partner can delete a file note.")
        super().perform_destroy(instance)


class CourtDiaryViewSet(MatterScopedViewSet):
    """
    The firm's court diary. Filter by date range for a calendar view:
        /api/v1/diary/?from=2026-10-01&to=2026-10-31
    """

    model = CourtEvent
    audit_name = "diary"
    serializer_class = CourtEventSerializer
    filterset_fields = ["matter", "kind", "outcome"]
    search_fields = ["title", "location", "matter__reference", "matter__title"]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.RECEPTIONIST:
            # Reception keeps the firm's diary but should not browse case files.
            qs = CourtEvent.objects.filter(matter__firm_id=user.firm_id).select_related("matter")
        else:
            qs = super().get_queryset()

        start = parse_date(self.request.query_params.get("from", "") or "")
        end = parse_date(self.request.query_params.get("to", "") or "")
        if start:
            qs = qs.filter(starts_at__date__gte=start)
        if end:
            qs = qs.filter(starts_at__date__lte=end)
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(attendees=user)
        return qs.prefetch_related("attendees").order_by("starts_at")

    def _check_write(self, matter):
        if self.request.user.role == Role.RECEPTIONIST:
            return
        super()._check_write(matter)

    # Everyone involved hears about a date the moment it is set, moved or
    # vacated, on every channel they chose. Reminders are booked by signals.

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        if not serializer.validated_data.get("attendees") and user.role in FEE_EARNERS:
            # A lawyer diarising a hearing is, unless they say otherwise, going.
            serializer.validated_data["attendees"] = [user]
        super().perform_create(serializer)
        event = serializer.instance
        transaction.on_commit(lambda: reminders.announce_court_event(event, "created"))

    @transaction.atomic
    def perform_update(self, serializer):
        event = serializer.instance
        before = {
            "starts_at": event.starts_at, "ends_at": event.ends_at, "all_day": event.all_day,
            "location": event.location, "outcome": event.outcome, "kind": event.kind,
        }
        people_before = {p.pk for p in reminders.court_recipients(event)}
        super().perform_update(serializer)
        event.refresh_from_db()

        if before["outcome"] == "pending" and event.outcome in {"vacated", "adjourned"}:
            change = "cancelled"
        elif event.outcome != "pending":
            change = None  # held, or deadline met: nothing to tell anyone
        elif event.starts_at != before["starts_at"] or event.all_day != before["all_day"]:
            change = "moved"
        elif any(getattr(event, field) != before[field] for field in ("ends_at", "location", "kind")) or before["outcome"] != "pending":
            change = "updated"
        else:
            change = None

        newcomers = [p for p in reminders.court_recipients(event) if p.pk not in people_before]

        def tell():
            if change:
                reminders.announce_court_event(event, change, previous_start=before["starts_at"])
            elif newcomers and event.outcome == "pending":
                reminders.announce_court_event(event, "created", only_people=newcomers)

        transaction.on_commit(tell)

    def perform_destroy(self, instance):
        if instance.outcome == "pending" and instance.starts_at > timezone.now():
            reminders.announce_court_event(instance, "cancelled")
        super().perform_destroy(instance)

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        now = timezone.now()
        qs = self.get_queryset().filter(starts_at__gte=now, starts_at__lte=now + timedelta(days=14), outcome="pending")
        return Response(self.get_serializer(qs[:100], many=True).data)

    @action(detail=True, methods=["get"])
    def brief(self, request, pk=None):
        """
        The court brief: everything a lawyer needs at the bar table, on one
        screen, so nobody carries a paper file to court. Privileged notes are
        included only for the matter team.
        """
        from apps.documents.models import Document
        from apps.documents.serializers import DocumentSerializer

        event = self.get_object()
        matter = event.matter
        user = request.user
        if user.is_client or (user.role == Role.RECEPTIONIST and not visible_matters(user).filter(pk=matter.pk).exists()):
            raise PermissionDenied("The court brief is for the lawyers on the matter.")

        privileged = can_read_privileged(user, matter)
        history = matter.events.exclude(pk=event.pk).order_by("-starts_at")
        documents = (
            Document.objects.filter(matter=matter, court_bundle=True, is_archived=False)
            .select_related("matter", "uploaded_by").prefetch_related("versions")
        )
        record("diary.brief_opened", actor=user, target=event, matter=matter)

        data = {
            "event": CourtEventSerializer(event, context={"request": request}).data,
            "matter": {
                "id": str(matter.pk), "reference": matter.reference, "title": matter.title, "client_name": matter.client.name,
                "court": matter.court, "case_number": matter.case_number, "judge": matter.judge,
                "opposing_counsel": matter.opposing_counsel, "description": matter.description,
                "practice_area": matter.get_practice_area_display(), "is_restricted": matter.is_restricted,
                "lead_lawyer": matter.lead_lawyer.full_name if matter.lead_lawyer else "",
                "client_phone": matter.client.phone,
            },
            "parties": PartySerializer(matter.parties.all(), many=True).data,
            "history": [
                {
                    "id": str(e.pk), "kind": e.get_kind_display(), "title": e.title, "starts_at": e.starts_at,
                    "outcome": e.outcome, "outcome_display": e.get_outcome_display(), "outcome_notes": e.outcome_notes,
                }
                for e in history[:20]
            ],
            "documents": DocumentSerializer(documents, many=True, context={"request": request}).data,
            "tasks": TaskSerializer(matter.tasks.exclude(status="done").select_related("assigned_to")[:20], many=True).data,
            "privileged": privileged,
            "hearing_notes": [],
            "file_notes": [],
        }
        if privileged:
            notes = matter.notes.select_related("author", "court_event").order_by("-created_at")
            data["hearing_notes"] = NoteSerializer([n for n in notes if n.court_event_id == event.pk], many=True).data
            data["file_notes"] = NoteSerializer([n for n in notes if n.court_event_id != event.pk][:30], many=True).data
        return Response(data)

    @action(detail=True, methods=["post"], url_path="record-outcome")
    @transaction.atomic
    def record_outcome(self, request, pk=None):
        """
        After court, in one step: what happened, and when the matter is back.
        Adjourned to a new date? The new hearing is diarised, linked, and the
        team (and the client, if they were told about this one) is notified.
        """
        event = self.get_object()
        self._check_firm(event.matter)
        self._check_write(event.matter)
        outcome = request.data.get("outcome")
        if outcome not in {"held", "adjourned", "met", "vacated"}:
            raise ValidationError({"outcome": "Choose held, adjourned, met or vacated."})

        before = event.outcome
        event.outcome = outcome
        event.outcome_notes = (request.data.get("outcome_notes") or "")[:5000]

        next_data = request.data.get("next") or None
        new_event = None
        if next_data and next_data.get("starts_at"):
            serializer = CourtEventSerializer(data={
                "matter": str(event.matter_id),
                "kind": next_data.get("kind") or event.kind,
                "title": next_data.get("title") or event.title,
                "starts_at": next_data["starts_at"],
                "location": next_data.get("location", event.location),
                "attendees": [str(u.pk) for u in event.attendees.all()],
                "notify_client": event.notify_client,
            }, context={"request": request})
            serializer.is_valid(raise_exception=True)
            new_event = serializer.save()
            event.next_event = new_event
        event.save(update_fields=["outcome", "outcome_notes", "next_event", "updated_at"])
        record("diary.outcome_recorded", actor=request.user, target=event, matter=event.matter, outcome=outcome,
               next_event=str(new_event.pk) if new_event else "")

        def tell():
            if before == "pending" and outcome in {"vacated", "adjourned"}:
                reminders.announce_court_event(event, "cancelled")
            if new_event is not None:
                reminders.announce_court_event(new_event, "created")

        transaction.on_commit(tell)
        return Response({
            "event": CourtEventSerializer(event, context={"request": request}).data,
            "next_event": CourtEventSerializer(new_event, context={"request": request}).data if new_event else None,
        })
