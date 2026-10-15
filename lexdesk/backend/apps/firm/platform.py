"""
The platform console: where LexDesk's own operators add law firms.

Operators manage firms, never their files. Their accounts belong to no firm,
so every firm-scoped query returns nothing for them, and nothing here reads a
client, matter, document or note.
"""

from django.db import transaction
from django.db.models import Count, Q
from django.utils.text import slugify
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import BasePermission

from apps.accounts.permissions import MFASatisfied

from apps.accounts.models import Role, User
from apps.audit.services import record

from .models import Firm


class IsPlatformOperator(BasePermission):
    message = "This area is for LexDesk's platform operators."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_platform_operator)


class PlatformFirmSerializer(serializers.ModelSerializer):
    staff_count = serializers.IntegerField(read_only=True, default=0)
    matter_count = serializers.IntegerField(read_only=True, default=0)
    # The firm's first managing partner, invited by email on creation.
    partner_email = serializers.EmailField(write_only=True, required=False)
    partner_first_name = serializers.CharField(write_only=True, required=False)
    partner_last_name = serializers.CharField(write_only=True, required=False)
    partner_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    slug = serializers.SlugField(max_length=60, required=False)

    class Meta:
        model = Firm
        fields = [
            "id", "name", "slug", "code", "domain", "is_active", "created_at", "staff_count", "matter_count",
            "phone", "email", "partner_email", "partner_first_name", "partner_last_name", "partner_phone",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_code(self, value):
        value = (value or "").strip().upper()
        if self.instance and value != self.instance.code:
            raise serializers.ValidationError("A firm's code cannot change: it is part of every case number.")
        return value

    def validate_slug(self, value):
        return slugify(value)

    def validate(self, attrs):
        if self.instance is None:
            missing = [f for f in ("partner_email", "partner_first_name", "partner_last_name") if not attrs.get(f)]
            if missing:
                raise serializers.ValidationError({f: "Needed to invite the firm's managing partner." for f in missing})
            if User.objects.filter(email__iexact=attrs["partner_email"]).exists():
                raise serializers.ValidationError({"partner_email": "Someone already uses this email on LexDesk."})
            attrs.setdefault("slug", slugify(attrs["name"])[:60])
            if Firm.objects.filter(slug=attrs["slug"]).exists():
                raise serializers.ValidationError({"slug": "Another firm already uses that web address name."})
        return attrs


class PlatformFirmViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = PlatformFirmSerializer
    permission_classes = [MFASatisfied, IsPlatformOperator]
    search_fields = ["name", "slug", "code", "domain"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return Firm.objects.annotate(
            staff_count=Count("people", filter=Q(people__is_active=True) & ~Q(people__role=Role.CLIENT), distinct=True),
            matter_count=Count("matters", distinct=True),
        ).order_by("name")

    @transaction.atomic
    def perform_create(self, serializer):
        from apps.accounts.provisioning import provision_user

        data = serializer.validated_data
        partner = {k: data.pop(k, "") for k in ("partner_email", "partner_first_name", "partner_last_name", "partner_phone")}
        firm = serializer.save()
        user, _ = provision_user(
            email=partner["partner_email"], first_name=partner["partner_first_name"], last_name=partner["partner_last_name"],
            phone=partner["partner_phone"], role=Role.PARTNER, title="Managing Partner", firm=firm, invited_by=self.request.user,
        )
        record("platform.firm_created", actor=self.request.user, target=firm, partner=str(user.pk))

    def perform_update(self, serializer):
        before = serializer.instance.is_active
        firm = serializer.save()
        record("platform.firm_updated", actor=self.request.user, target=firm, fields=sorted(serializer.validated_data))
        if before and not firm.is_active:
            # Suspension is immediate: end every session at the firm.
            from django.utils import timezone
            from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

            for token in OutstandingToken.objects.filter(user__firm=firm, expires_at__gt=timezone.now()):
                BlacklistedToken.objects.get_or_create(token=token)
