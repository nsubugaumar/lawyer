from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import FEE_EARNERS, MANAGES_BILLING


class HealthView(APIView):
    """For the load balancer. Says nothing about the system beyond 'alive'."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})


class DashboardView(APIView):
    """
    The first screen after sign-in. Every number is computed from what this
    person is allowed to see, so a lawyer's dashboard and a partner's
    dashboard can differ, and a client sees their own case at a glance.
    """

    allow_without_mfa = False

    def get(self, request):
        from apps.appointments.models import Appointment
        from apps.billing.models import Invoice, TimeEntry
        from apps.matters.access import visible_matters
        from apps.matters.models import CourtEvent, Task

        user = request.user
        now = timezone.now()
        today = timezone.localdate()
        matters = visible_matters(user)

        upcoming = CourtEvent.objects.filter(
            matter__in=matters, starts_at__gte=now, starts_at__lte=now + timedelta(days=7), outcome="pending"
        ).select_related("matter").order_by("starts_at")
        if user.is_client:
            # Clients see the dates their lawyer chose to share with them.
            upcoming = upcoming.filter(notify_client=True)
        upcoming = upcoming[:10]

        appointments = Appointment.objects.filter(
            firm_id=user.firm_id, starts_at__date=today, status__in=Appointment.ACTIVE
        ).select_related("client", "lawyer")
        if user.is_client:
            appointments = Appointment.objects.filter(
                client__portal_user=user, starts_at__gte=now, status__in=Appointment.ACTIVE
            ).select_related("client", "lawyer")
        elif user.role in FEE_EARNERS:
            appointments = appointments.filter(lawyer=user)

        data = {
            "greeting_name": user.first_name,
            "today": today,
            "matters": dict(matters.values_list("status").annotate(n=Count("id", distinct=True)).order_by()),
            "upcoming_court": [
                {
                    "id": str(e.id),
                    "kind": e.get_kind_display(),
                    "title": e.title,
                    "starts_at": e.starts_at,
                    "location": e.location,
                    "matter_id": str(e.matter_id),
                    "matter_reference": e.matter.reference,
                    "is_deadline": e.is_deadline,
                }
                for e in upcoming
            ],
            "appointments": [
                {
                    "id": str(a.id),
                    "starts_at": a.starts_at,
                    "client": a.client.name,
                    "lawyer": a.lawyer.full_name,
                    "mode": a.get_mode_display(),
                    "status": a.status,
                }
                for a in appointments[:10]
            ],
        }

        if not user.is_client:
            my_tasks = Task.objects.filter(assigned_to=user, matter__in=matters).exclude(status="done")
            data["tasks"] = {
                "open": my_tasks.count(),
                "overdue": my_tasks.filter(due_on__lt=today).count(),
                "due_today": my_tasks.filter(due_on=today).count(),
            }

        if user.role in FEE_EARNERS:
            week_start = today - timedelta(days=today.weekday())
            minutes = TimeEntry.objects.filter(user=user, date__gte=week_start).aggregate(m=Sum("minutes"))["m"] or 0
            data["hours_this_week"] = round(minutes / 60, 1)

        if user.role in MANAGES_BILLING:
            outstanding = [
                inv.balance
                for inv in Invoice.objects.filter(
                    matter__in=matters, status__in=[Invoice.Status.ISSUED, Invoice.Status.PART_PAID]
                ).prefetch_related("lines", "payments")
            ]
            data["billing"] = {
                "outstanding_total": sum(outstanding, Decimal("0")),
                "outstanding_count": len(outstanding),
                "overdue_count": Invoice.objects.filter(
                    matter__in=matters, status__in=[Invoice.Status.ISSUED, Invoice.Status.PART_PAID], due_date__lt=today
                ).count(),
            }

        return Response(data)
