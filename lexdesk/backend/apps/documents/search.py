"""
Search inside encrypted documents, without keeping their text.

Every document in the vault is encrypted, so the database can never hold a
readable copy of what it says. Instead, when a file is uploaded we read its
words once, in memory, and store only a keyed fingerprint (HMAC) of each
distinct word: a "blind index". To search, we fingerprint the words typed
and look for documents holding all of them.

Someone who steals the database sees only fingerprints. Without the search
key (kept with the other keys, outside the database) they cannot tell which
word a fingerprint stands for. What they can learn is which documents share
a word, which is the known, accepted cost of this design.

Scanned images have no text layer; when Tesseract OCR is installed on the
server, it reads them too.
"""

import hashlib
import hmac
import io
import logging
import re
import shutil
import subprocess
import tempfile
import zipfile

from apps.core.crypto import search_key

logger = logging.getLogger(__name__)

MAX_PAGES = 400
MAX_TOKENS = 25000
WORD = re.compile(r"[^\W_]{2,40}", re.UNICODE)
# Too common to narrow anything down.
STOP = {"the", "and", "for", "of", "to", "in", "a", "an", "is", "on", "at", "by", "or", "be", "as", "it", "this", "that", "with"}


def extract_text(content: bytes, content_type: str) -> str:
    try:
        if content_type == "application/pdf":
            return _pdf_text(content)
        if content_type.startswith("application/vnd.openxmlformats-officedocument") or content_type == "application/vnd.oasis.opendocument.text":
            return _office_text(content)
        if content_type.startswith("text/") or content_type == "message/rfc822":
            return content.decode("utf-8", "ignore")
        if content_type in ("image/png", "image/jpeg", "image/tiff"):
            return _ocr(content)
    except Exception:  # noqa: BLE001 - a file we cannot read is still stored; it just is not searchable
        logger.warning("Could not extract text for indexing (%s)", content_type)
    return ""


def _pdf_text(content: bytes) -> str:
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(content))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES])
    if len(text.strip()) < 20:
        # Probably a scan with no text layer.
        text += _ocr(content, pdf=True)
    return text


def _office_text(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        parts = [n for n in z.namelist() if n in ("word/document.xml", "content.xml") or n.startswith(("ppt/slides/slide", "xl/sharedStrings"))]
        xml = " ".join(z.read(n).decode("utf-8", "ignore") for n in parts)
    return re.sub(r"<[^>]+>", " ", xml)


def _ocr(content: bytes, pdf: bool = False) -> str:
    tesseract = shutil.which("tesseract")
    # PDFs need rasterising first (pdftoppm); images go straight in.
    if not tesseract or (pdf and not shutil.which("pdftoppm")):
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        source = f"{tmp}/in"
        with open(source, "wb") as fh:
            fh.write(content)
        images = [source]
        if pdf:
            subprocess.run(["pdftoppm", "-r", "200", "-png", "-l", "30", source, f"{tmp}/page"], check=True, timeout=300)
            import glob

            images = sorted(glob.glob(f"{tmp}/page*.png"))
        text = []
        for image in images:
            result = subprocess.run([tesseract, image, "-", "-l", "eng"], capture_output=True, timeout=120)
            text.append(result.stdout.decode("utf-8", "ignore"))
        # The temporary directory, with the decrypted copy, is deleted here.
        return "\n".join(text)


def words(text: str) -> set[str]:
    found = set()
    for match in WORD.finditer(text.lower()):
        word = match.group()
        if word not in STOP:
            found.add(word)
            if len(found) >= MAX_TOKENS:
                break
    return found


def blind(word: str) -> str:
    return hmac.new(search_key(), word.encode(), hashlib.sha256).hexdigest()[:32]


def index_document(document, content: bytes, content_type: str):
    """Replace the document's index with the words of this version and its title."""
    from .models import DocumentSearchToken

    tokens = words(extract_text(content, content_type)) | words(f"{document.title} {document.description} {document.tags}")
    DocumentSearchToken.objects.filter(document=document).delete()
    DocumentSearchToken.objects.bulk_create([DocumentSearchToken(document=document, token=blind(w)) for w in tokens], batch_size=2000)
    return len(tokens)


def matching(queryset, query: str):
    """Documents in `queryset` that contain every word of `query`."""
    from django.db.models import Count

    from .models import DocumentSearchToken

    tokens = [blind(w) for w in words(query)]
    if not tokens:
        return queryset
    hits = (
        DocumentSearchToken.objects.filter(token__in=tokens)
        .values("document_id")
        .annotate(n=Count("token", distinct=True))
        .filter(n=len(set(tokens)))
        .values("document_id")
    )
    return queryset.filter(pk__in=hits)
