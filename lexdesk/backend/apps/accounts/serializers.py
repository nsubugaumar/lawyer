from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import Role, User


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    is_platform_operator = serializers.BooleanField(read_only=True)
    firm = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name", "phone", "role", "role_display",
            "title", "mfa_enabled", "date_joined", "is_platform_operator", "firm",
        ]
        read_only_fields = ["id", "email", "role", "mfa_enabled", "date_joined"]

    def get_firm(self, obj):
        f = obj.firm
        return {"id": f.pk, "name": f.name, "slug": f.slug, "code": f.code} if f else None


class TeamMemberSerializer(serializers.ModelSerializer):
    """Used by administrators to manage staff. Creating one sends an invitation."""

    full_name = serializers.CharField(read_only=True)
    is_locked = serializers.BooleanField(read_only=True)
    has_activated = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name", "phone", "role", "title",
            "hourly_rate", "is_active", "mfa_enabled", "is_locked", "has_activated", "last_login", "date_joined",
        ]
        read_only_fields = ["id", "mfa_enabled", "last_login", "date_joined"]

    def get_has_activated(self, obj):
        return obj.has_usable_password()

    def validate_role(self, value):
        if value == Role.CLIENT:
            raise serializers.ValidationError("Client accounts are created automatically from the client register.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Someone already uses this email address.")
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})


class MFAVerifySerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    code = serializers.CharField(max_length=16, help_text="Six-digit code, or a recovery code like ABCDE-12345")


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=16)


class PasswordConfirmSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False)
    code = serializers.CharField(max_length=16)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "That is not your current password."})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class ActivateSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
