from rest_framework import serializers

from apps.accounts.models import FEE_EARNERS, User

from .models import CourtEvent, Matter, MatterMember, Note, Party, Task


class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "full_name", "title", "role"]


class MatterMemberSerializer(serializers.ModelSerializer):
    user = PersonSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        source="user", queryset=User.objects.filter(is_active=True).exclude(role="client"), write_only=True
    )

    class Meta:
        model = MatterMember
        fields = ["user", "user_id", "role", "added_at"]


class MatterSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    lead_lawyer_detail = PersonSerializer(source="lead_lawyer", read_only=True)
    team = MatterMemberSerializer(source="memberships", many=True, read_only=True)
    practice_area_display = serializers.CharField(source="get_practice_area_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    next_event = serializers.SerializerMethodField()
    on_team = serializers.SerializerMethodField()

    class Meta:
        model = Matter
        fields = [
            "id", "reference", "title", "client", "client_name", "practice_area", "practice_area_display",
            "status", "status_display", "description", "court", "case_number", "judge", "opposing_counsel",
            "lead_lawyer", "lead_lawyer_detail", "team", "is_restricted", "opened_on", "closed_on",
            "hourly_rate", "next_event", "on_team", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reference", "created_at", "updated_at"]

    def validate_lead_lawyer(self, value):
        if value and value.role not in FEE_EARNERS:
            raise serializers.ValidationError("The lead lawyer must be a partner, lawyer or paralegal.")
        return value

    def get_on_team(self, obj):
        """Whether this person may read the privileged file notes."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user) and (obj.lead_lawyer_id == user.id or any(m.user_id == user.id for m in obj.memberships.all()))

    def get_next_event(self, obj):
        from django.utils import timezone

        event = obj.events.filter(starts_at__gte=timezone.now(), outcome="pending").order_by("starts_at").first()
        return CourtEventBriefSerializer(event).data if event else None


class ClientMatterSerializer(serializers.ModelSerializer):
    """The client's view of their own case: progress, not internal workings."""

    lead_lawyer = PersonSerializer(read_only=True)
    practice_area_display = serializers.CharField(source="get_practice_area_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Matter
        fields = [
            "id", "reference", "title", "practice_area_display", "status", "status_display",
            "court", "case_number", "lead_lawyer", "opened_on", "closed_on",
        ]
        read_only_fields = fields


class PartySerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = Party
        fields = ["id", "matter", "name", "role", "role_display", "represented_by", "contact", "created_at"]
        read_only_fields = ["id", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    assigned_to_detail = PersonSerializer(source="assigned_to", read_only=True)
    matter_reference = serializers.CharField(source="matter.reference", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id", "matter", "matter_reference", "title", "details", "assigned_to", "assigned_to_detail",
            "due_on", "status", "priority", "completed_at", "created_at",
        ]
        read_only_fields = ["id", "completed_at", "created_at"]


class NoteSerializer(serializers.ModelSerializer):
    author = PersonSerializer(read_only=True)
    court_event_label = serializers.SerializerMethodField()

    class Meta:
        model = Note
        fields = ["id", "matter", "author", "body", "shared_with_client", "court_event", "court_event_label", "created_at", "updated_at"]
        read_only_fields = ["id", "author", "created_at", "updated_at"]

    def get_court_event_label(self, obj):
        e = obj.court_event
        if e is None:
            return ""
        from django.utils import timezone

        return f"{e.get_kind_display()}, {timezone.localtime(e.starts_at):%d %b %Y}"

    def validate(self, attrs):
        event = attrs.get("court_event")
        matter = attrs.get("matter") or getattr(self.instance, "matter", None)
        if event is not None and matter is not None and event.matter_id != matter.pk:
            raise serializers.ValidationError({"court_event": "That hearing belongs to another matter."})
        return attrs


class CourtEventBriefSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = CourtEvent
        fields = ["id", "kind", "kind_display", "title", "starts_at", "location"]


class CourtEventSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    matter_reference = serializers.CharField(source="matter.reference", read_only=True)
    matter_title = serializers.CharField(source="matter.title", read_only=True)
    is_deadline = serializers.BooleanField(read_only=True)

    class Meta:
        model = CourtEvent
        fields = [
            "id", "matter", "matter_reference", "matter_title", "kind", "kind_display", "is_deadline", "title",
            "starts_at", "ends_at", "all_day", "location", "attendees", "notes", "outcome", "outcome_notes",
            "next_event", "notify_client", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_attendees(self, value):
        request = self.context.get("request")
        firm_id = getattr(getattr(request, "user", None), "firm_id", None)
        if request is not None and any(u.firm_id != firm_id for u in value):
            raise serializers.ValidationError("Attendees must work at your firm.")
        if any(not u.is_active or u.is_client for u in value):
            raise serializers.ValidationError("Attendees must be active members of the firm. Use notify_client to tell the client.")
        return value

    def validate(self, attrs):
        starts, ends = attrs.get("starts_at"), attrs.get("ends_at")
        if starts and ends and ends < starts:
            raise serializers.ValidationError({"ends_at": "The end must be after the start."})
        return attrs
