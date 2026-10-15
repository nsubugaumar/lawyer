"""
Secure messages between a client and their lawyers, one conversation per matter.

Who takes part: the client of the matter and the matter team. Everyone else
in the firm, partners included, is outside the conversation unless they are
on the team, because what client and lawyer say is privileged. Alerts by
WhatsApp, SMS and email never carry the message itself, only that there is
one, so nothing privileged sits in a phone's notification history.
"""

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.matters.models import Matter
from apps.notifications.models import Category
from apps.notifications.services import notify

from .models import Message, ReadMarker


def conversations_for(user):
    """Matters whose conversation this person takes part in."""
    if not user.firm_id:
        return Matter.objects.none()
    qs = Matter.objects.filter(firm_id=user.firm_id)
    if user.is_client:
        return qs.filter(client__portal_user=user)
    return qs.filter(Q(lead_lawyer=user) | Q(memberships__user=user)).distinct()


def _matter(user, matter_id):
    matter = conversations_for(user).filter(pk=matter_id).first() if matter_id else None
    if matter is None:
        raise PermissionDenied("Messages on this matter are between the client and the matter team.")
    return matter


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_is_client = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()
    document_title = serializers.CharField(source="document.title", read_only=True, default=None)

    class Meta:
        model = Message
        fields = ["id", "matter", "body", "sender_name", "sender_is_client", "mine", "document", "document_title", "created_at"]

    def get_sender_name(self, obj):
        return obj.sender.full_name if obj.sender else "Former colleague"

    def get_sender_is_client(self, obj):
        return bool(obj.sender and obj.sender.is_client)

    def get_mine(self, obj):
        return obj.sender_id == self.context["request"].user.id


class ThreadsView(APIView):
    """The inbox: one row per conversation, newest first, with unread counts."""

    def get(self, request):
        user = request.user
        matters = (
            conversations_for(user)
            .annotate(last_at=Max("messages__created_at"), total=Count("messages", distinct=True))
            .select_related("client", "lead_lawyer")
        )
        if not user.is_client:
            matters = matters.filter(total__gt=0) if request.query_params.get("all") != "1" else matters
        markers = {m.matter_id: m.read_at for m in ReadMarker.objects.filter(user=user)}
        rows = []
        for m in matters:
            last = m.messages.order_by("-created_at").select_related("sender").first()
            since = markers.get(m.pk)
            unread_qs = m.messages.exclude(sender=user)
            if since:
                unread_qs = unread_qs.filter(created_at__gt=since)
            rows.append({
                "matter": str(m.pk), "reference": m.reference, "title": m.title, "client_name": m.client.name,
                "lead_lawyer": m.lead_lawyer.full_name if m.lead_lawyer else "",
                "last_at": m.last_at, "last_sender": last.sender.full_name if last and last.sender else "",
                "last_preview": (last.body[:120] if last else ""), "unread": unread_qs.count(),
            })
        rows.sort(key=lambda r: (r["last_at"] is None, r["last_at"] and -r["last_at"].timestamp()))
        return Response({"threads": rows, "unread_total": sum(r["unread"] for r in rows)})


class MessagesView(APIView):
    def get(self, request):
        matter = _matter(request.user, request.query_params.get("matter"))
        messages = matter.messages.select_related("sender", "document")[:500]
        return Response(MessageSerializer(messages, many=True, context={"request": request}).data)

    @transaction.atomic
    def post(self, request):
        user = request.user
        matter = _matter(user, request.data.get("matter"))
        body = (request.data.get("body") or "").strip()
        if not body:
            raise ValidationError({"body": "Write a message first."})
        if len(body) > 10000:
            raise ValidationError({"body": "Please keep messages under 10,000 characters, or send a document."})
        document = None
        if request.data.get("document"):
            document = matter.documents.filter(pk=request.data["document"], is_archived=False).first()
            if document is None or (user.is_client and not document.shared_with_client):
                raise ValidationError({"document": "That document is not on this matter."})
            if not user.is_client and not document.shared_with_client:
                document.shared_with_client = True  # sending it to the client shares it
                document.save(update_fields=["shared_with_client", "updated_at"])

        message = Message.objects.create(matter=matter, sender=user, body=body, document=document)
        ReadMarker.objects.update_or_create(matter=matter, user=user, defaults={"read_at": message.created_at})
        record("message.sent", actor=user, target=message, matter=matter)
        transaction.on_commit(lambda: _alert(message, user, matter))
        return Response(MessageSerializer(message, context={"request": request}).data, status=status.HTTP_201_CREATED)


def _alert(message, sender, matter):
    """Tell the other side there is a message, without repeating what it says."""
    if sender.is_client:
        people = {u for u in [matter.lead_lawyer] if u} | {m.user for m in matter.memberships.select_related("user")}
        subject = f"New message from {sender.full_name} · {matter.reference}"
        body = f"{sender.full_name} sent a message on {matter.reference} ({matter.title}). Open LexDesk to read and reply."
        link = f"/messages?matter={matter.pk}"
    else:
        client_user = matter.client.portal_user
        people = {client_user} if client_user else set()
        subject = f"New message from {sender.full_name}"
        body = f"{sender.full_name} sent you a message about {matter.title}. Open your client portal to read it."
        link = f"/messages?matter={matter.pk}"
    for person in people:
        if person and person.is_active and person.pk != sender.pk:
            notify(person, subject=subject, body=body, sms=f"{subject}. Open LexDesk to read it.", link=link,
                   category=Category.MESSAGES, dedupe_key=f"msg:{message.pk}")


class MarkReadView(APIView):
    def post(self, request):
        matter = _matter(request.user, request.data.get("matter"))
        ReadMarker.objects.update_or_create(matter=matter, user=request.user, defaults={"read_at": timezone.now()})
        return Response(status=204)
