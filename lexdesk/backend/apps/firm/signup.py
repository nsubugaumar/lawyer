"""
A law firm registers itself on LexDesk.

The managing partner fills in the firm's name and their own details on the
website. LexDesk creates the firm (its own sealed space, website and case
numbering) and the partner's account, and emails an activation link. Until
the partner opens that link and chooses a password, nobody can sign in, so
an address that is not really theirs gets nowhere. Once in, the partner adds
everyone else at the firm from Team; each gets their own activation email.

The platform owners are told about every new firm and can suspend one at
any time from the Law firms console.
"""

import re

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.audit.services import record
from apps.notifications.channels import normalise_phone
from apps.notifications.models import Category
from apps.notifications.services import notify

from .models import Firm

STOP_WORDS = {"and", "of", "the", "co", "company", "advocates", "associates", "chambers", "law", "legal", "partners", "llp", "ltd"}


def unique_slug(name: str) -> str:
    base = slugify(name)[:50] or "firm"
    slug, n = base, 2
    while Firm.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def unique_code(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in STOP_WORDS] or re.findall(r"[A-Za-z]+", name) or ["FIRM"]
    base = "".join(w[0] for w in words).upper()[:4]
    if len(base) < 2:
        base = (words[0][:3] if words else "FRM").upper()
    code, n = base, 2
    while Firm.objects.filter(code=code).exists() or code == "INV":
        suffix = re.sub(r"[^A-Z]", "", chr(64 + n) if n <= 26 else "Z")
        code, n = (base[:5] + suffix)[:6], n + 1
    return code


class FirmSignupSerializer(serializers.Serializer):
    firm_name = serializers.CharField(max_length=150)
    firm_phone = serializers.CharField(max_length=32)
    firm_email = serializers.EmailField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=80, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32)
    title = serializers.CharField(max_length=80, required=False, allow_blank=True)
    agree = serializers.BooleanField()
    # Honeypot: invisible to people.
    website = serializers.CharField(required=False, allow_blank=True)

    def validate_firm_name(self, value):
        value = " ".join(value.split())
        if len(value) < 3:
            raise serializers.ValidationError("Enter the firm's full name.")
        if Firm.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("A firm with this name is already on LexDesk. If it is yours, ask your managing partner to add you.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email already has a LexDesk account. Sign in instead, or use another email.")
        return value

    def validate_phone(self, value):
        if not normalise_phone(value):
            raise serializers.ValidationError("Enter a mobile number, e.g. 0772 123 456.")
        return normalise_phone(value)

    def validate_firm_phone(self, value):
        if not normalise_phone(value):
            raise serializers.ValidationError("Enter the office phone number.")
        return normalise_phone(value)

    def validate_agree(self, value):
        if value is not True:
            raise serializers.ValidationError("Please accept the terms to continue.")
        return value


class FirmSignupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "firm_signup"

    @transaction.atomic
    def post(self, request):
        if not settings.LEXDESK_ALLOW_FIRM_SIGNUP:
            return Response({"error": {"code": "signup_closed", "message": "New firms join by invitation. Please contact LexDesk."}}, status=403)
        data = FirmSignupSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v.get("website"):
            return Response({"detail": "Thank you. Check your email to activate your account."}, status=201)

        from apps.accounts.provisioning import provision_user

        firm = Firm.objects.create(
            name=v["firm_name"], slug=unique_slug(v["firm_name"]), code=unique_code(v["firm_name"]),
            phone=v["firm_phone"], email=v.get("firm_email", ""), address=v.get("city", ""),
            whatsapp_number=v["firm_phone"] if v["firm_phone"].startswith("+2567") else "",
        )
        partner, _ = provision_user(
            email=v["email"], first_name=v["first_name"], last_name=v["last_name"], role=Role.PARTNER,
            firm=firm, phone=v["phone"], title=v.get("title") or "Managing Partner",
        )
        record("firm.self_registered", actor=None, target=firm, partner=str(partner.pk))

        def tell_owners():
            for owner in User.objects.filter(is_superuser=True, firm__isnull=True, is_active=True):
                notify(owner, subject=f"New firm registered: {firm.name}",
                       body=f"{partner.full_name} ({partner.email}) registered {firm.name} ({firm.code}). "
                            "You can review or suspend it in the Law firms console.",
                       link="/platform", category=Category.GENERAL)

        transaction.on_commit(tell_owners)
        return Response({
            "detail": f"Welcome to LexDesk. We have emailed {partner.email} a link to activate your account.",
            "firm": {"name": firm.name, "slug": firm.slug, "code": firm.code},
        }, status=status.HTTP_201_CREATED)
