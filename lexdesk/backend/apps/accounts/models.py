import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.fields import EncryptedTextField


class Role(models.TextChoices):
    ADMIN = "admin", "Administrator"
    PARTNER = "partner", "Partner"
    LAWYER = "lawyer", "Lawyer"
    PARALEGAL = "paralegal", "Paralegal"
    RECEPTIONIST = "receptionist", "Receptionist"
    ACCOUNTANT = "accountant", "Accountant"
    CLIENT = "client", "Client"


# Who can do what, in one place. Views ask these questions rather than
# checking role names directly, so changing a policy is a one-line edit.
FEE_EARNERS = {Role.PARTNER, Role.LAWYER, Role.PARALEGAL}
SEES_ALL_MATTERS = {Role.ADMIN, Role.PARTNER}
MANAGES_CLIENTS = {Role.ADMIN, Role.PARTNER, Role.LAWYER, Role.PARALEGAL, Role.RECEPTIONIST}
MANAGES_BILLING = {Role.ADMIN, Role.PARTNER, Role.ACCOUNTANT}


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        extra.setdefault("role", Role.ADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The firm this person works at (or is a client of). Empty only for the
    # platform's own operators, who manage firms but see no firm's files.
    firm = models.ForeignKey("firm.Firm", null=True, blank=True, on_delete=models.PROTECT, related_name="people")
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENT)
    title = models.CharField(max_length=80, blank=True, help_text="e.g. Senior Associate")
    hourly_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can sign in to the office admin site.")
    date_joined = models.DateTimeField(default=timezone.now)

    # Two-factor authentication
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = EncryptedTextField(blank=True)
    mfa_pending_secret = EncryptedTextField(blank=True)
    mfa_last_used_step = models.BigIntegerField(null=True, blank=True)

    # Brute-force protection
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name or self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_client(self):
        return self.role == Role.CLIENT

    @property
    def is_firm_staff(self):
        return self.role != Role.CLIENT

    @property
    def is_platform_operator(self):
        return self.is_superuser and self.firm_id is None

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.password_changed_at = timezone.now()

    # ---- lockout ---------------------------------------------------------

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failed_login(self):
        self.failed_login_count += 1
        if self.failed_login_count >= settings.LEXDESK_MAX_FAILED_LOGINS:
            self.locked_until = timezone.now() + timedelta(minutes=settings.LEXDESK_LOCKOUT_MINUTES)
            self.failed_login_count = 0
        self.save(update_fields=["failed_login_count", "locked_until"])

    def clear_failed_logins(self):
        if self.failed_login_count or self.locked_until:
            self.failed_login_count = 0
            self.locked_until = None
            self.save(update_fields=["failed_login_count", "locked_until"])


class RecoveryCode(models.Model):
    """
    One-time backup codes for when a lawyer loses their phone the morning of
    a hearing. Stored as SHA-256 hashes: the codes are long and random, so a
    slow hash adds nothing, and the plaintext is shown to the user only once.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def hash(code: str) -> str:
        return hashlib.sha256(code.replace("-", "").upper().encode()).hexdigest()

    @classmethod
    def issue_for(cls, user, count=10) -> list[str]:
        cls.objects.filter(user=user).delete()
        codes = []
        for _ in range(count):
            raw = secrets.token_hex(5).upper()  # 40 bits each, 10 hex chars
            codes.append(f"{raw[:5]}-{raw[5:]}")
            cls.objects.create(user=user, code_hash=cls.hash(raw))
        return codes

    @classmethod
    def redeem(cls, user, code: str) -> bool:
        updated = cls.objects.filter(user=user, code_hash=cls.hash(code), used_at__isnull=True).update(
            used_at=timezone.now()
        )
        return updated == 1
