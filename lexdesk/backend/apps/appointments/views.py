import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import FEE_EARNERS, User
from apps.audit.services import record
from apps.clients.models import Client
from apps.firm.tenancy import firm_for, public_firm

from .models import Appointment
from .serializers import AppointmentSerializer, CancelSerializer, ClientAppointmentSerializer, PublicBookingSerializer
from apps.notifications import reminders

from .services import assert_lawyer_free, available_slots, public_booking


class AppointmentViewSet(viewsets.ModelViewSet):
    filterset_fields = ["status", "lawyer", "client", "mode", "matter"]
    ordering_fields = ["starts_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = Appointment.objects.filter(firm_id=user.firm_id).select_related("client", "lawyer") if user.firm_id else Appointment.objects.none()
        if user.is_client:
            qs = qs.filter(client__portal_user=user)
        elif user.role in ("lawyer", "paralegal"):
            # A booking with a lawyer is that lawyer's business: colleagues
            # do not see it. Reception, the practice manager and partners
            # keep the firm-wide diary because they book and oversee.
            qs = qs.filter(lawyer=user)
        elif user.role == "accountant":
            qs = qs.none()
        elif self.request.query_params.get("mine") == "1":
            qs = qs.filter(lawyer=user)

        start = parse_date(self.request.query_params.get("from", "") or "")
        end = parse_date(self.request.query_params.get("to", "") or "")
        if start:
            qs = qs.filter(starts_at__date__gte=start)
        if end:
            qs = qs.filter(starts_at__date__lte=end)
        return qs

    def get_serializer_class(self):
        return ClientAppointmentSerializer if getattr(self.request.user, "is_client", False) else AppointmentSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        data = serializer.validated_data
        extra = {"booked_by": user}

        if user.is_client:
            client = Client.objects.filter(portal_user=user).first()
            if client is None:
                raise PermissionDenied("Your portal account is not linked to a client record yet.")
            extra["client"] = client
        elif user.role == "accountant":
            raise PermissionDenied()

        client = extra.get("client") or data.get("client")
        if client is None or client.firm_id != user.firm_id or data["lawyer"].firm_id != user.firm_id:
            raise ValidationError("Choose a client and lawyer from your own firm.")
        self._check_matter(data.get("matter"), client)
        extra["firm_id"] = user.firm_id
        assert_lawyer_free(data["lawyer"], data["starts_at"], data["ends_at"])
        # Staff bookings are confirmed straight away; client requests wait for the firm.
        extra["status"] = Appointment.Status.REQUESTED if user.is_client else Appointment.Status.CONFIRMED
        appointment = serializer.save(**extra)
        record("appointment.created", actor=user, target=appointment, matter=appointment.matter)
        change = "confirmed" if appointment.status == Appointment.Status.CONFIRMED else "requested"
        transaction.on_commit(lambda: reminders.announce_appointment(appointment, change))

    @transaction.atomic
    def perform_update(self, serializer):
        user = self.request.user
        appointment = serializer.instance
        if user.is_client:
            raise PermissionDenied("To change an appointment, please cancel it and book a new time.")
        if appointment.status not in Appointment.ACTIVE:
            raise ValidationError("Only upcoming appointments can be changed.")

        data = serializer.validated_data
        if "lawyer" in data and data["lawyer"].firm_id != user.firm_id:
            raise ValidationError({"lawyer": "Choose a lawyer from your own firm."})
        if "client" in data and data["client"] != appointment.client:
            # An appointment belongs to the client it was booked for.
            raise ValidationError({"client": "To see a different client, book a new appointment."})
        if "matter" in data:
            self._check_matter(data["matter"], appointment.client)
        previous_start, previous_lawyer = appointment.starts_at, appointment.lawyer
        moved = any(k in data for k in ("lawyer", "starts_at", "ends_at"))
        if moved:
            assert_lawyer_free(
                data.get("lawyer", appointment.lawyer), data.get("starts_at", appointment.starts_at),
                data.get("ends_at", appointment.ends_at), exclude=appointment,
            )
        appointment = serializer.save()
        record("appointment.updated", actor=user, target=appointment, fields=sorted(data))
        if moved:
            def tell():
                if appointment.lawyer != previous_lawyer:
                    # The new lawyer is told as if newly booked; the old one is released.
                    reminders.announce_appointment(appointment, "moved", previous_start=previous_start, include_lawyer=False)
                    reminders.announce_appointment(appointment, "confirmed", include_client=False)
                    reminders.announce_reassigned(appointment, previous_lawyer)
                elif appointment.starts_at != previous_start:
                    reminders.announce_appointment(appointment, "moved", previous_start=previous_start)
            transaction.on_commit(tell)

    def _check_matter(self, matter, client):
        if matter is not None and (matter.firm_id != self.request.user.firm_id or matter.client_id != client.pk):
            raise ValidationError({"matter": "Choose one of this client's matters."})

    def _transition(self, request, to_status, allowed_from, *, client_may=False):
        appointment = self.get_object()
        if request.user.is_client and not client_may:
            raise PermissionDenied()
        if appointment.status not in allowed_from:
            raise ValidationError(f"An appointment that is {appointment.get_status_display().lower()} cannot be changed that way.")
        appointment.status = to_status
        return appointment

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        appointment = self._transition(request, Appointment.Status.CONFIRMED, [Appointment.Status.REQUESTED])
        appointment.save(update_fields=["status", "updated_at"])
        record("appointment.confirmed", actor=request.user, target=appointment)
        reminders.announce_appointment(appointment, "confirmed")
        return Response(self.get_serializer(appointment).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        data = CancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        appointment = self._transition(request, Appointment.Status.CANCELLED, Appointment.ACTIVE, client_may=True)
        if request.user.is_client and appointment.starts_at - timezone.now() < timedelta(hours=2):
            raise ValidationError("Please call the office to cancel within two hours of your appointment.")
        appointment.cancellation_reason = data.validated_data.get("reason", "")
        appointment.save(update_fields=["status", "cancellation_reason", "updated_at"])
        record("appointment.cancelled", actor=request.user, target=appointment)
        # Whoever cancelled knows already; everyone else is told.
        reminders.announce_appointment(
            appointment, "cancelled", include_client=not request.user.is_client,
            include_lawyer=request.user.is_client or request.user != appointment.lawyer,
        )
        return Response(self.get_serializer(appointment).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        appointment = self._transition(request, Appointment.Status.COMPLETED, Appointment.ACTIVE)
        appointment.save(update_fields=["status", "updated_at"])
        record("appointment.completed", actor=request.user, target=appointment)
        return Response(self.get_serializer(appointment).data)

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        appointment = self._transition(request, Appointment.Status.NO_SHOW, Appointment.ACTIVE)
        appointment.save(update_fields=["status", "updated_at"])
        record("appointment.no_show", actor=request.user, target=appointment)
        return Response(self.get_serializer(appointment).data)


# --------------------------------------------------------------------------
# Public website booking (no login)
# --------------------------------------------------------------------------


class PublicLawyersView(APIView):
    """The lawyers a member of the public can book. Names and titles only."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        firm = firm_for(request)
        lawyers = User.objects.filter(firm=firm, is_active=True, role__in=FEE_EARNERS).exclude(role="paralegal")
        return Response([{"id": str(u.id), "name": u.full_name, "title": u.title} for u in lawyers])


class PublicAvailabilityView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        day = parse_date(request.query_params.get("date", "") or "")
        lawyer_id = _as_uuid(request.query_params.get("lawyer"))
        firm = public_firm(request)
        lawyer = User.objects.filter(firm=firm, pk=lawyer_id, is_active=True, role__in=FEE_EARNERS).first() if lawyer_id else None
        if not day or not lawyer:
            raise ValidationError("Please give a lawyer and a date (YYYY-MM-DD).")
        days_ahead = firm.booking_days_ahead
        if (day - timezone.localdate()).days > days_ahead:
            raise ValidationError(f"Bookings open up to {days_ahead} days ahead.")
        return Response({"date": day, "slots": available_slots(lawyer, day)})


class PublicBookingView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_booking"

    def post(self, request):
        data = PublicBookingSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v.get("website"):
            # Honeypot tripped. Pretend it worked so the bot learns nothing.
            return Response({"detail": "Thank you. We will be in touch."}, status=201)

        appointment = public_booking(
            firm=public_firm(request),
            name=v["name"], email=v["email"], phone=v["phone"], lawyer_id=v["lawyer"], starts_at=v["starts_at"],
            mode=v["mode"], purpose=v["purpose"], practice_area=v.get("practice_area", ""),
            whatsapp_opt_in=v["whatsapp_opt_in"],
        )
        return Response(
            {
                "detail": "Thank you. Your request has been received and the firm will confirm shortly. "
                "We have emailed you a link to your secure client portal.",
                "reference": str(appointment.id)[:8].upper(),
            },
            status=201,
        )


def _as_uuid(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None
