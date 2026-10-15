from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import FlutterwaveWebhookView, InvoiceViewSet, OnlinePaymentView, TimeEntryViewSet

router = DefaultRouter()
router.register("time", TimeEntryViewSet, basename="time-entry")
router.register("invoices", InvoiceViewSet, basename="invoice")

urlpatterns = [
    path("online-payments/<str:tx_ref>/", OnlinePaymentView.as_view(), name="online-payment"),
    path("flutterwave/webhook/<slug:slug>/", FlutterwaveWebhookView.as_view(), name="flutterwave-webhook"),
    *router.urls,
]
