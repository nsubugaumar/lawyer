from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("", views.NotificationViewSet, basename="notification")

urlpatterns = [
    path("preferences/", views.PreferenceView.as_view(), name="notification-preferences"),
    path("test/", views.TestMessageView.as_view(), name="notification-test"),
    path("calendar-feed/", views.CalendarFeedView.as_view(), name="calendar-feed"),
    path("calendar/<str:token>.ics", views.CalendarFeedPublicView.as_view(), name="calendar-feed-public"),
    path("whatsapp/webhook/", views.WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
    path("sms/delivery/<slug:slug>/", views.SmsDeliveryReportView.as_view(), name="sms-delivery"),
    path("whatsapp/webhook/<slug:slug>/", views.WhatsAppWebhookView.as_view(), name="whatsapp-webhook-firm"),
    *router.urls,
]
