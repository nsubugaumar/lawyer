"""
The wire: one function per channel that sends one message and returns the
provider's message id.

Each raises `TemporaryFailure` when trying again later may work (network
down, rate limited, provider 5xx) and `PermanentFailure` when it will not
(number not on WhatsApp, bad address). The dispatcher decides what to do.
"""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from email.utils import make_msgid

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from apps.firm.models import Firm

logger = logging.getLogger(__name__)


class TemporaryFailure(Exception):
    pass


class PermanentFailure(Exception):
    pass


# --------------------------------------------------------------------------
# Phone numbers
# --------------------------------------------------------------------------


def normalise_phone(raw: str) -> str:
    """
    "0772 123 456", "256772123456", "+256 (772) 123-456" -> "+256772123456".
    Local numbers get the firm's country code. Returns "" for nonsense.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("00"):
        digits = digits[2:]
    elif raw.strip().startswith("0") or (len(digits) <= 10 and not raw.strip().startswith("+")):
        digits = settings.LEXDESK_DEFAULT_COUNTRY_CODE + digits.lstrip("0")
    if not 8 <= len(digits) <= 15:
        return ""
    return f"+{digits}"


def mask(address: str) -> str:
    """Enough to recognise in a log, not enough to be useful to anyone else."""
    if "@" in address:
        name, _, domain = address.partition("@")
        return f"{name[:1]}***@{domain}"
    return f"***{address[-3:]}" if address else ""


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------


def send_email(*, to: str, subject: str, body: str, firm: Firm, link: str = "", ics: bytes | None = None, ics_method="PUBLISH") -> str:
    message_id = make_msgid(domain=settings.LEXDESK_EMAIL_DOMAIN)
    context = {
        "firm": firm.name,
        "subject": subject,
        "paragraphs": [p for p in body.split("\n\n") if p.strip()],
        "action_url": f"{settings.LEXDESK_WEB_URL}{link}" if link and settings.LEXDESK_WEB_URL else "",
        "has_invite": bool(ics),
    }
    text = body
    if context["action_url"]:
        text += f"\n\nOpen in LexDesk: {context['action_url']}"

    email = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to], headers={"Message-ID": message_id})
    email.attach_alternative(render_to_string("notifications/email.html", context), "text/html")
    if ics:
        # Mail apps (Gmail, Outlook, Apple Mail) offer "Add to calendar" for this.
        email.attach("invite.ics", ics, f"text/calendar; charset=utf-8; method={ics_method}")
    try:
        email.send(fail_silently=False)
    except (ConnectionError, TimeoutError, OSError) as exc:
        raise TemporaryFailure(f"Mail server unreachable: {exc.__class__.__name__}") from exc
    except Exception as exc:  # noqa: BLE001 - smtplib raises many types
        if exc.__class__.__name__ in {"SMTPRecipientsRefused"}:
            raise PermanentFailure("The mail server refused this address") from exc
        raise TemporaryFailure(f"Email failed: {exc.__class__.__name__}") from exc
    return message_id.strip("<>")


# --------------------------------------------------------------------------
# WhatsApp (Meta WhatsApp Business Cloud API)
# --------------------------------------------------------------------------
#
# WhatsApp only lets a business start a conversation with a pre-approved
# template. LexDesk needs exactly one, created once in WhatsApp Manager
# (category: Utility, language: English):
#
#   name:  lexdesk_notice
#   body:  {{1}}
#
#          {{2}}
#
#          {{3}}
#   button (optional, URL): Open LexDesk -> https://your-lexdesk-domain/{{1}}
#
# {{1}} is the headline, {{2}} the details, {{3}} the firm name. With the
# button, set LEXDESK_WHATSAPP_TEMPLATE_HAS_BUTTON=1.

# Meta error codes that will never succeed on retry.
_WHATSAPP_PERMANENT = {
    131026,  # recipient cannot receive this message (not on WhatsApp)
    131030,  # number not in allowed list (test mode)
    131047,  # outside the 24h window (template required)
    131051,  # unsupported message type
    132000, 132001, 132005, 132007, 132012, 132015, 132016,  # template problems
    100,  # invalid parameter
    470,  # re-engagement message
}


def _template_text(value: str, limit: int) -> str:
    # Template parameters may not contain newlines, tabs or 4+ spaces.
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[: limit - 1] + "…" if len(value) > limit else value or "-"


def send_whatsapp(*, to: str, headline: str, details: str, firm: Firm, link: str = "") -> str:
    """Sent from the firm's own WhatsApp Business number."""
    backend = firm.whatsapp_backend
    if backend == "console":
        logger.info("WhatsApp to %s: %s | %s", mask(to), headline, details)
        return f"console-{make_msgid().strip('<>')}"
    if backend != "meta":
        raise PermanentFailure(f"Unknown WhatsApp backend {backend!r}")

    components = [{
        "type": "body",
        "parameters": [
            {"type": "text", "text": _template_text(headline, 200)},
            {"type": "text", "text": _template_text(details, 700)},
            {"type": "text", "text": _template_text(firm.name, 100)},
        ],
    }]
    if link and firm.whatsapp_has_button:
        components.append({"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": link.lstrip("/")}]})

    payload = {
        "messaging_product": "whatsapp",
        "to": to.lstrip("+"),
        "type": "template",
        "template": {
            "name": firm.whatsapp("template"),
            "language": {"code": firm.whatsapp("template_language")},
            "components": components,
        },
    }
    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{firm.whatsapp('phone_number_id')}/messages"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {firm.whatsapp('access_token')}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310  # nosec B310 - fixed https URL, reviewed
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read()).get("error", {})
        except ValueError:
            error = {}
        code = error.get("code")
        detail = f"WhatsApp error {code}: {error.get('message', exc.reason)}"[:480]
        if code in _WHATSAPP_PERMANENT or (400 <= exc.code < 500 and exc.code not in (408, 429)):
            raise PermanentFailure(detail) from exc
        raise TemporaryFailure(detail) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TemporaryFailure(f"WhatsApp unreachable: {exc.__class__.__name__}") from exc

    try:
        return data["messages"][0]["id"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TemporaryFailure("WhatsApp gave no message id") from exc


# --------------------------------------------------------------------------
# SMS (Africa's Talking HTTP API)
# --------------------------------------------------------------------------


def send_sms(*, to: str, text: str, firm: Firm) -> str:
    """Sent from the firm's own Africa's Talking account and sender ID."""
    backend = firm.sms_backend
    if backend == "console":
        # Development and test mode: recorded, never sent. Masked even here,
        # because logs end up pasted into bug reports.
        logger.info("SMS to %s: %s", mask(to), text)
        return f"console-{make_msgid().strip('<>')}"
    if backend == "off":
        raise PermanentFailure("SMS is switched off for this firm")
    if backend != "africastalking":
        raise PermanentFailure(f"Unknown SMS backend {backend!r}")

    username = firm.sms("username")
    host = "api.sandbox.africastalking.com" if username == "sandbox" else "api.africastalking.com"
    form = {"username": username, "to": to, "message": text[:459]}
    if firm.sms("sender_id"):
        form["from"] = firm.sms("sender_id")
    request = urllib.request.Request(
        f"https://{host}/version1/messaging",
        data=urllib.parse.urlencode(form).encode(),
        headers={"apiKey": firm.sms("api_key"), "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310  # nosec B310 - fixed https URL, reviewed
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = f"SMS gateway HTTP {exc.code}"
        if exc.code in (401, 403):
            raise PermanentFailure(f"{detail}: check the Africa's Talking username and API key") from exc
        raise TemporaryFailure(detail) from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise TemporaryFailure(f"SMS gateway unreachable: {exc.__class__.__name__}") from exc

    recipients = (data or {}).get("SMSMessageData", {}).get("Recipients", [])
    if not recipients:
        raise TemporaryFailure(f"SMS not accepted: {(data or {}).get('SMSMessageData', {}).get('Message', 'no recipients')}"[:480])
    first = recipients[0]
    if first.get("statusCode") in (100, 101, 102) or first.get("status") in {"Success", "Sent", "Submitted", "Buffered"}:
        return first.get("messageId", "")
    status = first.get("status", "")
    if status in {"InvalidPhoneNumber", "UserInBlacklist", "UserInBlackList", "InvalidSenderId", "UnsupportedNumberType"}:
        raise PermanentFailure(f"SMS refused: {status}")
    raise TemporaryFailure(f"SMS not sent: {status or first}"[:480])
