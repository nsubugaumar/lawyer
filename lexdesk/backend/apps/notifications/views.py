import hashlib
import hmac
import json
import logging
from datetime import timedelta

from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.ids import as_uuid
from apps.core.urls_public import public_url
from apps.firm.models import Firm

from . import ics, reminders
from .models import CalendarFeed, Category, Channel, Delivery, Notification
from .serializers import NotificationSerializer, PreferenceSerializer, TestMessageSerializer
from .services import notify, opt_out_whatsapp, preferences_for, record_receipt, whatsapp_number_for

logger = logging.getLogger(__name__)


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The bell. `?read_at__isnull=true` for unread, `?category=diary` to filter."""

    serializer_class = NotificationSerializer
    filterset_fields = {"read_at": ["isnull"], "category": ["exact"]}

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user, in_app=True).prefetch_related(
            Prefetch("deliveries", queryset=Delivery.objects.order_by("created_at"))
        )

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """Cheap enough to poll every 30 seconds."""
        return Response({"unread": self.get_queryset().filter(read_at__isnull=True).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        if as_uuid(pk):
            self.get_queryset().filter(pk=pk, read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=204)


class PreferenceView(APIView):
    def get(self, request):
        return Response(PreferenceSerializer(preferences_for(request.user)).data)

    def patch(self, request):
        prefs = preferences_for(request.user)
        before = (list(prefs.court_offsets), list(prefs.appointment_offsets))
        serializer = PreferenceSerializer(prefs, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        prefs = serializer.save()
        record("notifications.preferences_changed", actor=request.user, target=request.user, fields=sorted(request.data))
        if before != (prefs.court_offsets, prefs.appointment_offsets):
            _resync_reminders_for(request.user)
        return Response(PreferenceSerializer(prefs).data)


def _resync_reminders_for(user):
    from apps.appointments.models import Appointment
    from apps.matters.models import CourtEvent

    now = timezone.now()
    events = CourtEvent.objects.filter(outcome="pending", starts_at__gt=now).filter(
        Q(attendees=user) | Q(matter__lead_lawyer=user) | Q(matter__client__portal_user=user, notify_client=True)
    ).distinct()
    for event in events:
        reminders.sync_court_event(event)
    for appointment in Appointment.objects.filter(status="confirmed", starts_at__gt=now).filter(Q(lawyer=user) | Q(client__portal_user=user)):
        reminders.sync_appointment(appointment)


class TestMessageView(APIView):
    """'Send me a test': proves the phone number and WhatsApp really work."""

    throttle_scope = "notification_test"

    def post(self, request):
        data = TestMessageSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        channel = data.validated_data["channel"]
        user = request.user
        prefs = preferences_for(user)
        if channel in (Channel.WHATSAPP, Channel.SMS) and not whatsapp_number_for(user, prefs):
            raise ValidationError({"channel": "Add your mobile number first."})
        if channel == Channel.WHATSAPP and not prefs.whatsapp_active:
            raise ValidationError({"channel": "Turn on WhatsApp notifications first."})

        notification = notify(
            user,
            subject="LexDesk test message",
            body="This is a test. If you can read this, LexDesk can reach you here for court dates and appointments.",
            sms="LexDesk test: you will receive court date and appointment reminders here.",
            link="/settings/notifications",
            category=Category.GENERAL,
            urgent=True,
            only={channel},
        )
        return Response(NotificationSerializer(notification).data, status=201)


# --------------------------------------------------------------------------
# Calendar subscription
# --------------------------------------------------------------------------


class CalendarFeedView(APIView):
    """Manage your private calendar link. The link itself is shown only once."""

    def get(self, request):
        feed = CalendarFeed.objects.filter(user=request.user).first()
        return Response({"active": bool(feed), "created_at": feed and feed.created_at, "last_used_at": feed and feed.last_used_at})

    def post(self, request):
        token = CalendarFeed.issue_for(request.user)
        record("notifications.calendar_feed_issued", actor=request.user, target=request.user)
        url = public_url(request, f"/api/v1/notifications/calendar/{token}.ics")
        return Response({"url": url, "webcal_url": url.replace("https://", "webcal://").replace("http://", "webcal://")}, status=201)

    def delete(self, request):
        CalendarFeed.objects.filter(user=request.user).delete()
        record("notifications.calendar_feed_revoked", actor=request.user, target=request.user)
        return Response(status=204)


class CalendarFeedPublicView(APIView):
    """Polled by Google / Apple / Outlook. The token is the only credential."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "calendar_feed"

    def get(self, request, token):
        feed = CalendarFeed.objects.select_related("user").filter(token_hash=CalendarFeed.hash(token)).first()
        if feed is None or not feed.user.is_active:
            raise Http404
        now = timezone.now()
        if not feed.last_used_at or now - feed.last_used_at > timedelta(hours=1):
            CalendarFeed.objects.filter(pk=feed.pk).update(last_used_at=now)
        response = HttpResponse(ics.feed(feed.user), content_type="text/calendar; charset=utf-8")
        response["Cache-Control"] = "private, max-age=300"
        response["Content-Disposition"] = 'inline; filename="lexdesk.ics"'
        return response


# --------------------------------------------------------------------------
# WhatsApp webhook (delivery receipts, STOP replies)
# --------------------------------------------------------------------------

STOP_WORDS = {"stop", "unsubscribe", "stop all", "opt out", "optout"}


class WhatsAppWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []  # Meta sends bursts; the signature is the gate

    @staticmethod
    def _firm(slug):
        # Each firm's WhatsApp account posts to its own address; the bare
        # address uses the server's own (environment) credentials.
        if not slug:
            return Firm.platform_default()
        firm = Firm.objects.filter(slug=slug, is_active=True).first()
        if firm is None:
            raise Http404
        return firm

    def get(self, request, slug=None):
        """Meta's one-time subscription handshake."""
        params = request.query_params
        expected = self._firm(slug).whatsapp("verify_token")
        if expected and params.get("hub.mode") == "subscribe" and hmac.compare_digest(params.get("hub.verify_token", ""), expected):
            return HttpResponse(params.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse(status=403)

    def post(self, request, slug=None):
        firm = self._firm(slug)
        secret = firm.whatsapp("app_secret")
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest() if secret else ""
        if not secret or not hmac.compare_digest(signature, expected):
            logger.warning("WhatsApp webhook with a bad signature was refused")
            return HttpResponse(status=403)

        try:
            payload = json.loads(request.body)
        except ValueError:
            return HttpResponse(status=400)

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    errors = status.get("errors") or [{}]
                    record_receipt(status.get("id", ""), status.get("status", ""), errors[0].get("title", ""))
                for message in value.get("messages", []):
                    text = (message.get("text", {}).get("body") or message.get("button", {}).get("text") or "").strip().lower()
                    if text in STOP_WORDS:
                        opt_out_whatsapp(message.get("from", ""), firm=firm if firm.pk else None)
        # Always 200 once authenticated, or Meta retries for days.
        return HttpResponse(status=200)


class SmsDeliveryReportView(APIView):
    """
    Africa's Talking posts delivery reports here. It does not sign them, so a
    report can only ever move a delivery forward, and only one we sent (its
    message id is long and unguessable).
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request, slug):
        status_map = {"Success": "delivered", "Failed": "failed", "Rejected": "failed", "Sent": "sent", "Submitted": "sent", "Buffered": "sent"}
        message_id = request.data.get("id", "")
        mapped = status_map.get(request.data.get("status", ""))
        if message_id and mapped:
            record_receipt(message_id, mapped, request.data.get("failureReason", ""))
        return HttpResponse(status=200)

