from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("team", views.TeamViewSet, basename="team")

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("mfa/verify/", views.MFAVerifyView.as_view(), name="mfa-verify"),
    path("refresh/", views.RefreshView.as_view(), name="token-refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password-change"),
    path("password/forgot/", views.ForgotPasswordView.as_view(), name="password-forgot"),
    path("activate/", views.ActivateView.as_view(), name="activate"),
    path("mfa/setup/", views.MFASetupView.as_view(), name="mfa-setup"),
    path("mfa/confirm/", views.MFAConfirmView.as_view(), name="mfa-confirm"),
    path("mfa/disable/", views.MFADisableView.as_view(), name="mfa-disable"),
    *router.urls,
]
