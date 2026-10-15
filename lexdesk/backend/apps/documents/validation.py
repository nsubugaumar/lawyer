"""
What may go into the vault.

We never trust the file name or the Content-Type the browser sends; both are
trivially faked. Instead we read the first bytes of the file (its "magic
number") and check they match the claimed type. A program renamed to
"evidence.pdf" is rejected at the door.
"""

import os

from django.conf import settings
from rest_framework.exceptions import ValidationError

OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy Office (.doc, .xls, Outlook .msg)
ZIP = b"PK\x03\x04"  # modern Office and OpenDocument are zip containers


def _is_text(head: bytes) -> bool:
    return b"\x00" not in head


def _is_mp4_family(head: bytes) -> bool:
    return head[4:8] == b"ftyp"


# extension -> (stored content type, signature check)
ALLOWED = {
    ".pdf": ("application/pdf", lambda h: h.startswith(b"%PDF-")),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", lambda h: h.startswith(ZIP)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", lambda h: h.startswith(ZIP)),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", lambda h: h.startswith(ZIP)),
    ".odt": ("application/vnd.oasis.opendocument.text", lambda h: h.startswith(ZIP)),
    ".doc": ("application/msword", lambda h: h.startswith(OLE)),
    ".xls": ("application/vnd.ms-excel", lambda h: h.startswith(OLE)),
    ".msg": ("application/vnd.ms-outlook", lambda h: h.startswith(OLE)),
    ".rtf": ("application/rtf", lambda h: h.startswith(b"{\\rtf")),
    ".txt": ("text/plain", _is_text),
    ".csv": ("text/csv", _is_text),
    ".eml": ("message/rfc822", _is_text),
    ".png": ("image/png", lambda h: h.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda h: h.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda h: h.startswith(b"\xff\xd8\xff")),
    ".tif": ("image/tiff", lambda h: h[:4] in (b"II*\x00", b"MM\x00*")),
    ".tiff": ("image/tiff", lambda h: h[:4] in (b"II*\x00", b"MM\x00*")),
    ".heic": ("image/heic", _is_mp4_family),
    ".mp3": ("audio/mpeg", lambda h: h.startswith(b"ID3") or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")),
    ".m4a": ("audio/mp4", _is_mp4_family),
    ".mp4": ("video/mp4", _is_mp4_family),
}

# Safe to show inside the app's viewer rather than forcing a download.
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg"}


def inspect_upload(uploaded) -> tuple[bytes, str, str]:
    """
    Validate an upload and read it. Returns (content, safe_filename, content_type).
    """
    limit = settings.LEXDESK_MAX_UPLOAD_MB * 1024 * 1024
    if uploaded.size > limit:
        raise ValidationError({"file": f"Files can be at most {settings.LEXDESK_MAX_UPLOAD_MB} MB."})
    if uploaded.size == 0:
        raise ValidationError({"file": "This file is empty."})

    name = os.path.basename(uploaded.name or "document").strip()[:200] or "document"
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED:
        allowed = ", ".join(sorted(e.lstrip(".") for e in ALLOWED))
        raise ValidationError({"file": f"That file type is not accepted. Allowed: {allowed}."})

    content = uploaded.read()
    content_type, looks_right = ALLOWED[ext]
    if not looks_right(content[:8192]):
        raise ValidationError({"file": "The file's contents do not match its extension, so it was rejected for safety."})

    return content, name, content_type
