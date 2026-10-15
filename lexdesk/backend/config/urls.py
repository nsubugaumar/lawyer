from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import DashboardView, HealthView

# The admin lives at an unguessable-ish path in production. It is not real
# security, but it keeps automated scanners from hammering the login form.
ADMIN_PATH = "admin/" if settings.DEBUG else "lexdesk-office-admin/"

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("clients/", include("apps.clients.urls")),
    path("", include("apps.matters.urls")),
    path("appointments/", include("apps.appointments.urls")),
    path("documents/", include("apps.documents.urls")),
    path("messages/", include("apps.messaging.urls")),
    path("library/", include("apps.library.urls")),
    path("reports/", include("apps.core.urls_reports")),
    path("billing/", include("apps.billing.urls")),
    path("audit/", include("apps.audit.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("firm/", include("apps.firm.urls")),
    path("platform/", include(("apps.firm.urls_platform", "platform"))),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("health/", HealthView.as_view(), name="health"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

urlpatterns = [
    path(ADMIN_PATH, admin.site.urls),
    path("api/v1/", include(api_v1)),
]

admin.site.site_header = "LexDesk platform"
# The Django admin sees every firm's tables, so it is for LexDesk's platform
# operators only (superusers who belong to no firm), never for a firm's staff.
admin.site.has_permission = lambda request: bool(
    request.user.is_active and request.user.is_authenticated and getattr(request.user, "is_platform_operator", False)
)
admin.site.site_title = "LexDesk"
admin.site.index_title = "Office administration"
