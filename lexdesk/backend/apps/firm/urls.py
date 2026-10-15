from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .platform import PlatformFirmViewSet
from .signup import FirmSignupView

platform = DefaultRouter()
platform.register("firms", PlatformFirmViewSet, basename="platform-firm")

urlpatterns = [
    path("settings/", views.FirmSettingsView.as_view(), name="firm-settings"),
    path("logo/", views.FirmLogoView.as_view(), name="firm-logo"),
    path("public/", views.PublicFirmView.as_view(), name="firm-public"),
    path("register/", FirmSignupView.as_view(), name="firm-register"),
    path("tls-ask/", views.TlsAskView.as_view(), name="firm-tls-ask"),
]
