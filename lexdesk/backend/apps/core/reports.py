"""
Reports for the partners who run the firm.

Numbers, not files: how many matters each lawyer carries, how many of the
firm's clients are on retainer and how many came for a single service, what
was billed and collected, and what is overdue. Nothing here opens a matter's
contents, so oversight never touches privilege.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import FEE_EARNERS, Role, User
from apps.accounts.permissions import FirmActive, HasRole, MFASatisfied


def _months(n=12):
    today = timezone.localdate().replace(day=1)
    months = []
    for _ in range(n):
        months.append(today)
        today = (today - timedelta(days=1)).replace(day=1)
    return list(reversed(months))


def _key(d: date) -> str:
    return d.strftime("%Y-%m")


class ReportsView(APIView):
    permission_classes = [MFASatisfied, FirmActive, HasRole.of(Role.ADMIN, Role.PARTNER)]

    def get(self, request):
        from apps.appointments.models import Appointment
        from apps.billing.models import Invoice, Payment, TimeEntry
        from apps.clients.models import Client
        from apps.matters.models import CourtEvent, Matter, Task

        firm_id = request.user.firm_id
        today = timezone.localdate()
        month_start = today.replace(day=1)
        months = _months()
        since = months[0]

        matters = Matter.objects.filter(firm_id=firm_id)
        clients = Client.objects.filter(firm_id=firm_id)
        open_matters = matters.filter(status__in=["intake", "open", "on_hold"])

        # ------------------------------------------------ lawyer workload
        lawyers = User.objects.filter(firm_id=firm_id, is_active=True, role__in=FEE_EARNERS).order_by("last_name")
        lead_counts = dict(open_matters.values_list("lead_lawyer").annotate(n=Count("id")).order_by())
        member_counts = dict(
            open_matters.exclude(lead_lawyer=None).values_list("memberships__user").annotate(n=Count("id", distinct=True)).order_by()
        )
        engagement = defaultdict(Counter)
        for lawyer_id, kind in clients.filter(status="active").values_list("responsible_lawyer", "engagement"):
            engagement[lawyer_id][kind] += 1
        hours = {
            row["user"]: row
            for row in TimeEntry.objects.filter(matter__firm_id=firm_id, date__gte=month_start)
            .values("user").annotate(total_minutes=Sum("minutes"), billable_minutes=Sum("minutes", filter=Q(billable=True))).order_by()
        }
        overdue = dict(
            Task.objects.filter(matter__firm_id=firm_id, due_on__lt=today).exclude(status="done")
            .values_list("assigned_to").annotate(n=Count("id")).order_by()
        )
        court_soon = dict(
            CourtEvent.objects.filter(matter__firm_id=firm_id, outcome="pending", starts_at__date__gte=today,
                                      starts_at__date__lte=today + timedelta(days=30))
            .values_list("attendees").annotate(n=Count("id", distinct=True)).order_by()
        )
        workload = []
        for lawyer in lawyers:
            h = hours.get(lawyer.pk, {})
            workload.append({
                "id": str(lawyer.pk),
                "name": lawyer.full_name,
                "title": lawyer.title or lawyer.get_role_display(),
                "leading": lead_counts.get(lawyer.pk, 0),
                "on_team": member_counts.get(lawyer.pk, 0),
                "retainer_clients": engagement[lawyer.pk]["retainer"],
                "one_off_clients": engagement[lawyer.pk]["one_off"],
                "hours_this_month": round((h.get("total_minutes") or 0) / 60, 1),
                "billable_hours_this_month": round((h.get("billable_minutes") or 0) / 60, 1),
                "overdue_tasks": overdue.get(lawyer.pk, 0),
                "court_dates_next_30_days": court_soon.get(lawyer.pk, 0),
            })

        # -------------------------------------------------------- clients
        active_clients = clients.filter(status="active")
        retainers = active_clients.filter(engagement="retainer")
        retainer_income = retainers.filter(Q(retainer_end__isnull=True) | Q(retainer_end__gte=today)).aggregate(s=Sum("retainer_fee"))["s"] or Decimal("0")
        new_clients = Counter(_key(d) for d in clients.filter(created_at__date__gte=since).values_list("created_at__date", flat=True))
        by_source = dict(clients.filter(created_at__date__gte=since).values_list("source").annotate(n=Count("id")).order_by())

        # -------------------------------------------------------- matters
        opened = Counter(_key(d) for d in matters.filter(opened_on__gte=since).values_list("opened_on", flat=True))
        closed = Counter(_key(d) for d in matters.filter(closed_on__gte=since).values_list("closed_on", flat=True))
        by_area = dict(open_matters.values_list("practice_area").annotate(n=Count("id")).order_by())
        by_status = dict(matters.values_list("status").annotate(n=Count("id")).order_by())

        # ---------------------------------------------------------- money
        invoices = Invoice.objects.filter(matter__firm_id=firm_id).prefetch_related("lines", "payments")
        billed = defaultdict(Decimal)
        aging = {"current": Decimal("0"), "1_30": Decimal("0"), "31_60": Decimal("0"), "61_90": Decimal("0"), "over_90": Decimal("0")}
        outstanding = Decimal("0")
        for inv in invoices:
            if inv.status in ("draft", "void"):
                continue
            if inv.issue_date and inv.issue_date >= since:
                billed[_key(inv.issue_date)] += inv.total
            balance = inv.balance
            if inv.status in ("issued", "part_paid") and balance > 0:
                outstanding += balance
                late = (today - inv.due_date).days if inv.due_date else 0
                bucket = "current" if late <= 0 else "1_30" if late <= 30 else "31_60" if late <= 60 else "61_90" if late <= 90 else "over_90"
                aging[bucket] += balance
        collected = defaultdict(Decimal)
        for received_on, amount in Payment.objects.filter(invoice__matter__firm_id=firm_id, received_on__gte=since).values_list("received_on", "amount"):
            collected[_key(received_on)] += amount

        appointments = Counter(_key(d) for d in Appointment.objects.filter(firm_id=firm_id, starts_at__date__gte=since)
                               .exclude(status="cancelled").values_list("starts_at__date", flat=True))

        return Response({
            "generated_at": timezone.now(),
            "summary": {
                "open_matters": open_matters.count(),
                "active_clients": active_clients.count(),
                "retainer_clients": retainers.count(),
                "one_off_clients": active_clients.filter(engagement="one_off").count(),
                "monthly_retainer_income": retainer_income,
                "outstanding": outstanding,
                "billed_this_month": billed.get(_key(month_start), Decimal("0")),
                "collected_this_month": collected.get(_key(month_start), Decimal("0")),
                "court_dates_next_30_days": CourtEvent.objects.filter(
                    matter__firm_id=firm_id, outcome="pending", starts_at__date__gte=today, starts_at__date__lte=today + timedelta(days=30)
                ).count(),
            },
            "workload": workload,
            "months": [
                {
                    "month": _key(m), "label": m.strftime("%b %Y"),
                    "opened": opened.get(_key(m), 0), "closed": closed.get(_key(m), 0),
                    "billed": billed.get(_key(m), Decimal("0")), "collected": collected.get(_key(m), Decimal("0")),
                    "new_clients": new_clients.get(_key(m), 0), "appointments": appointments.get(_key(m), 0),
                }
                for m in months
            ],
            "matters_by_area": by_area,
            "matters_by_status": by_status,
            "clients_by_source": by_source,
            "aging": aging,
        })
