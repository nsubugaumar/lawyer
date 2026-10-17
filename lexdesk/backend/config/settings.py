"""
LexDesk settings.

One settings file, driven entirely by environment variables. The guiding rule:
development should be easy, production should be impossible to misconfigure
quietly. Anything security-sensitive refuses to start in production if it is
missing, rather than falling back to a weak default.
"""

from datetime import timedelta
from pathlib import Path
import os
import sys
import warnings

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None, *, required_in_prod=False):
    value = os.environ.get(name, default)
    if required_in_prod and not DEBUG and not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

DEBUG = env_bool("LEXDESK_DEBUG", False)

SECRET_KEY = env("LEXDESK_SECRET_KEY", required_in_prod=True)
if not SECRET_KEY:
    # Only reachable in DEBUG. Never use this outside a laptop.
    SECRET_KEY = "dev-only-insecure-key-change-me-0123456789abcdefghijklmnopqrstuvwxyz"

ALLOWED_HOSTS = env_list("LEXDESK_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
# Render tells each service its own public address (e.g. lexdesk-api.onrender.com).
if env("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(env("RENDER_EXTERNAL_HOSTNAME"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # LexDesk
    "apps.core",
    "apps.firm",
    "apps.accounts",
    "apps.audit",
    "apps.notifications",
    "apps.clients",
    "apps.matters",
    "apps.appointments",
    "apps.documents",
    "apps.billing",
    "apps.messaging",
    "apps.library",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.audit.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
# PostgreSQL in every real deployment. SQLite exists only so a developer can
# clone the repo and be productive in two minutes.

if env("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER", "lexdesk"),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"sslmode": env("POSTGRES_SSLMODE", "prefer")},
        }
    }
else:
    if not DEBUG:
        raise ImproperlyConfigured("PostgreSQL (POSTGRES_DB) is required in production.")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------

# Argon2id first: memory-hard, the current OWASP recommendation. The others are
# kept so older hashes still verify and get upgraded transparently on login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------

LANGUAGE_CODE = "en-gb"
TIME_ZONE = env("LEXDESK_TIME_ZONE", "Africa/Kampala")
USE_I18N = True
USE_TZ = True  # everything stored in UTC, shown in the firm's local time

# --------------------------------------------------------------------------
# Static & media
# --------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# The document vault only ever holds ciphertext, but we still keep it out of
# any publicly served directory. Files are only reachable through the API.
MEDIA_ROOT = Path(env("LEXDESK_VAULT_DIR", str(BASE_DIR / "vault")))

if env("LEXDESK_S3_BUCKET"):
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("LEXDESK_S3_BUCKET"),
                "region_name": env("LEXDESK_S3_REGION"),
                "endpoint_url": env("LEXDESK_S3_ENDPOINT_URL"),
                "default_acl": "private",
                "querystring_auth": True,
                "file_overwrite": False,
                # Server-side encryption on top of our own client-side
                # encryption. Belt and braces.
                "object_parameters": {"ServerSideEncryption": "AES256"},
            },
        },
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

# --------------------------------------------------------------------------
# Encryption keys
# --------------------------------------------------------------------------
# Two separate key sets, so a leak of one does not expose the other:
#
#   LEXDESK_VAULT_KEYS  - master keys that wrap the per-document data keys.
#                         Format: "keyid:base64key,keyid:base64key". First is
#                         the active key; the rest are kept for decryption only.
#   LEXDESK_FIELD_KEYS  - Fernet keys for sensitive database columns (national
#                         IDs, private notes, MFA secrets). Same rotation rule.
#
# In production these belong in a KMS / secrets manager, injected at boot.

LEXDESK_VAULT_KEYS = env("LEXDESK_VAULT_KEYS", required_in_prod=True)
LEXDESK_FIELD_KEYS = env("LEXDESK_FIELD_KEYS", required_in_prod=True)
# Keys the blind index that lets lawyers search inside encrypted documents.
LEXDESK_SEARCH_KEY = env("LEXDESK_SEARCH_KEY", required_in_prod=True)

if DEBUG and not (LEXDESK_VAULT_KEYS and LEXDESK_FIELD_KEYS):
    warnings.warn(
        "LexDesk is deriving encryption keys from SECRET_KEY. Fine for development, "
        "never acceptable in production.",
        stacklevel=1,
    )

# --------------------------------------------------------------------------
# REST API
# --------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "apps.accounts.permissions.MFASatisfied",
        "apps.accounts.permissions.FirmActive",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.Pagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "600/minute",
        "login": "10/minute",
        "mfa": "10/minute",
        "download": "120/minute",
        "public_booking": "5/hour",
        "firm_signup": "5/hour",
        "notification_test": "10/hour",
        "calendar_feed": "120/hour",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
}

SIMPLE_JWT = {
    # Short-lived access tokens limit the damage of a stolen token. Refresh
    # tokens rotate on every use and the old one is blacklisted, so a replayed
    # refresh token is detectable and useless.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("LEXDESK_JWT_SIGNING_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Changing your password instantly kills every token issued before it.
    "CHECK_REVOKE_TOKEN": True,
    "REVOKE_TOKEN_CLAIM": "hash_password",
}

# Where the web app's refresh token cookie lives. HttpOnly so JavaScript (and
# therefore any XSS) can never read it.
LEXDESK_REFRESH_COOKIE = "lexdesk_refresh"
LEXDESK_REFRESH_COOKIE_PATH = "/api/v1/auth/"

SPECTACULAR_SETTINGS = {
    "TITLE": "LexDesk API",
    "DESCRIPTION": "Paperless practice management for law firms.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"] if not DEBUG else [],
}

# Rate limits are counted in the cache. Redis in production so every server
# shares one count; local memory in development; a no-op cache under test so
# limits from one test cannot leak into the next. (Account lockout lives in
# the database and is still fully exercised by the tests.)
if "test" in sys.argv:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
elif env("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env("REDIS_URL")}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --------------------------------------------------------------------------
# CORS / CSRF
# --------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list(
    "LEXDESK_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000" if DEBUG else ""
)
CORS_ALLOW_CREDENTIALS = True  # needed for the refresh cookie
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-lexdesk-client",
    "x-lexdesk-firm",
    "x-lexdesk-host",
    "x-requested-with",
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# --------------------------------------------------------------------------
# Transport & browser hardening
# --------------------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_AGE = 60 * 60 * 8  # admin sessions end with the working day
CSRF_COOKIE_SAMESITE = "Strict"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("LEXDESK_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Only trust X-Forwarded-For when we know a proxy we control sets it.
# Otherwise a client could forge its IP in the audit trail.
LEXDESK_TRUST_X_FORWARDED_FOR = env_bool("LEXDESK_TRUST_X_FORWARDED_FOR", False)

# --------------------------------------------------------------------------
# LexDesk behaviour
# --------------------------------------------------------------------------

LEXDESK_FIRM_NAME = env("LEXDESK_FIRM_NAME", "LexDesk Advocates")
# Which firm's website to show on an address that names no firm (e.g. the
# office IP during testing). Leave blank in a multi-firm deployment.
LEXDESK_DEFAULT_FIRM = env("LEXDESK_DEFAULT_FIRM", "")
# The platform's own domain, e.g. lexdesk.co.ug. Firms get <slug>.lexdesk.co.ug.
LEXDESK_BASE_DOMAIN = env("LEXDESK_BASE_DOMAIN", "localhost")
# Law firms can register themselves from the website. Turn off to onboard
# firms only from the platform console.
LEXDESK_ALLOW_FIRM_SIGNUP = env_bool("LEXDESK_ALLOW_FIRM_SIGNUP", True)
# Where activation and password links point (the web app).
LEXDESK_WEB_URL = env("LEXDESK_WEB_URL", "http://localhost:3000" if DEBUG else None, required_in_prod=True)

# Activation and reset links expire after three days.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 3
LEXDESK_CURRENCY = env("LEXDESK_CURRENCY", "UGX")

# Every staff member must use two-factor authentication in production.
LEXDESK_REQUIRE_MFA_FOR_STAFF = env_bool("LEXDESK_REQUIRE_MFA_FOR_STAFF", not DEBUG)

# Brute-force protection on top of rate limiting.
LEXDESK_MAX_FAILED_LOGINS = int(env("LEXDESK_MAX_FAILED_LOGINS", "5"))
LEXDESK_LOCKOUT_MINUTES = int(env("LEXDESK_LOCKOUT_MINUTES", "15"))

# Document vault limits.
LEXDESK_MAX_UPLOAD_MB = int(env("LEXDESK_MAX_UPLOAD_MB", "50"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Office hours used to offer appointment slots (local time).
LEXDESK_OFFICE_OPENS = env("LEXDESK_OFFICE_OPENS", "08:30")
LEXDESK_OFFICE_CLOSES = env("LEXDESK_OFFICE_CLOSES", "17:30")
LEXDESK_SLOT_MINUTES = int(env("LEXDESK_SLOT_MINUTES", "30"))

# --------------------------------------------------------------------------
# Background jobs & notifications
# --------------------------------------------------------------------------

CELERY_BROKER_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", DEBUG)
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    # Every minute, so a "2 hours before" reminder is on time, not up to an hour late.
    "reminders": {"task": "apps.notifications.tasks.send_due_reminders", "schedule": 60},
    "delivery-retries": {"task": "apps.notifications.tasks.retry_deliveries", "schedule": 60},
    "daily-agendas": {"task": "apps.notifications.tasks.send_daily_agendas", "schedule": 5 * 60},
}

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "LexDesk <no-reply@lexdesk.local>")
# Used for Message-IDs and calendar UIDs. Your mail domain in production.
LEXDESK_EMAIL_DOMAIN = env("LEXDESK_EMAIL_DOMAIN", "lexdesk.local")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True

# SMS: "console" in development, "africastalking" in production.
LEXDESK_SMS_BACKEND = env("LEXDESK_SMS_BACKEND", "console")
AFRICASTALKING_USERNAME = env("AFRICASTALKING_USERNAME", "")
AFRICASTALKING_API_KEY = env("AFRICASTALKING_API_KEY", "")
AFRICASTALKING_SENDER_ID = env("AFRICASTALKING_SENDER_ID", "")

# Local numbers ("0772 123456") are read as this country. 256 = Uganda.
LEXDESK_DEFAULT_COUNTRY_CODE = env("LEXDESK_DEFAULT_COUNTRY_CODE", "256")

# WhatsApp: "console" in development, "meta" (WhatsApp Business Cloud API)
# in production, "off" to disable. See apps/notifications/channels.py for
# the one message template to create in WhatsApp Manager.
LEXDESK_WHATSAPP_BACKEND = env("LEXDESK_WHATSAPP_BACKEND", "console")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", "v21.0")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET", "")  # verifies webhook signatures
WHATSAPP_WEBHOOK_VERIFY_TOKEN = env("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
LEXDESK_WHATSAPP_TEMPLATE = env("LEXDESK_WHATSAPP_TEMPLATE", "lexdesk_notice")
LEXDESK_WHATSAPP_TEMPLATE_LANGUAGE = env("LEXDESK_WHATSAPP_TEMPLATE_LANGUAGE", "en")
LEXDESK_WHATSAPP_TEMPLATE_HAS_BUTTON = env_bool("LEXDESK_WHATSAPP_TEMPLATE_HAS_BUTTON", False)
# Staff consent to WhatsApp reminders is taken once, in their contract.
# Clients always opt in themselves.
LEXDESK_WHATSAPP_STAFF_OPTED_IN = env_bool("LEXDESK_WHATSAPP_STAFF_OPTED_IN", True)
LEXDESK_AGENDA_ON_WEEKENDS = env_bool("LEXDESK_AGENDA_ON_WEEKENDS", False)

if not DEBUG and LEXDESK_WHATSAPP_BACKEND == "meta":
    for _name in ("WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_APP_SECRET", "WHATSAPP_WEBHOOK_VERIFY_TOKEN"):
        if not globals()[_name]:
            raise ImproperlyConfigured(f"{_name} must be set when LEXDESK_WHATSAPP_BACKEND=meta.")

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
# Structured, and deliberately never logs request bodies: they contain client
# confidences, passwords and documents.

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "lexdesk.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

if "test" in sys.argv:
    # Tests deliberately trigger hundreds of refusals. Keep the output readable.
    LOGGING["loggers"]["lexdesk.security"]["level"] = "ERROR"
    LOGGING["loggers"]["django.request"] = {"handlers": ["console"], "level": "ERROR", "propagate": False}
    MEDIA_ROOT = BASE_DIR / ".test-vault"
    CELERY_TASK_ALWAYS_EAGER = True  # deliver notifications inline, no broker
    LEXDESK_WHATSAPP_BACKEND = "console"
    LEXDESK_SMS_BACKEND = "console"
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher", *PASSWORD_HASHERS]  # fast tests only
