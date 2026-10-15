from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("", views.AppointmentViewSet, basename="appointment")

urlpatterns = [
    # Public endpoints used by the booking page on the firm's website.
    path("public/lawyers/", views.PublicLawyersView.as_view(), name="public-lawyers"),
    path("public/availability/", views.PublicAvailabilityView.as_view(), name="public-availability"),
    path("public/book/", views.PublicBookingView.as_view(), name="public-book"),
    *router.urls,
]
