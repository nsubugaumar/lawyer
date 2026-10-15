from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("last_name", "first_name")
    list_display = ("email", "full_name", "role", "is_active", "mfa_enabled", "last_login")
    list_filter = ("role", "is_active", "mfa_enabled")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("last_login", "date_joined", "password_changed_at", "mfa_enabled", "failed_login_count", "locked_until")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Person", {"fields": ("first_name", "last_name", "phone", "title", "role", "hourly_rate")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Security", {"fields": ("mfa_enabled", "failed_login_count", "locked_until", "password_changed_at")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "role")}),)

    def save_model(self, request, obj, form, change):
        # Accounts added through the admin follow the same rule as the API:
        # no password set by someone else, an activation link instead.
        if not change:
            from .provisioning import provision_user

            user, _ = provision_user(
                email=obj.email, first_name=obj.first_name, last_name=obj.last_name,
                role=obj.role, invited_by=request.user,
            )
            obj.pk = user.pk
            return
        super().save_model(request, obj, form, change)
