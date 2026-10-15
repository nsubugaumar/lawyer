"""
Small, dependency-free writers for the two formats lawyers live in:
a Word document (.docx) for drafts they will edit, and a plain PDF for
records that must not change (signature certificates).
"""

import io
import zipfile
from xml.sax.saxutils import escape

# ---------------------------------------------------------------- Word (.docx)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Cambria" w:hAnsi="Cambria" w:cs="Cambria"/><w:sz w:val="23"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
</w:styles>"""


def _run(text, bold=False, size=None, color=None):
    props = ""
    if bold:
        props += "<w:b/>"
    if size:
        props += f'<w:sz w:val="{size}"/>'
    if color:
        props += f'<w:color w:val="{color}"/>'
    rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _para(runs, align=None, after=None, border=False):
    ppr = ""
    if align:
        ppr += f'<w:jc w:val="{align}"/>'
    if after is not None:
        ppr += f'<w:spacing w:after="{after}"/>'
    if border:
        ppr += '<w:pBdr><w:bottom w:val="single" w:sz="8" w:space="4" w:color="A8823F"/></w:pBdr>'
    props = f"<w:pPr>{ppr}</w:pPr>" if ppr else ""
    return f"<w:p>{props}{''.join(runs)}</w:p>"


def make_docx(body: str, *, letterhead: list[str] | None = None, title: str = "") -> bytes:
    """
    `body` is plain text; blank lines separate paragraphs, and a line written
    in **double stars** is set in bold (headings like **WITHOUT PREJUDICE**).
    """
    parts = []
    if letterhead:
        parts.append(_para([_run(letterhead[0], bold=True, size=30, color="12294F")], align="center", after=40))
        for line in letterhead[1:]:
            parts.append(_para([_run(line, size=18, color="555555")], align="center", after=0))
        parts.append(_para([], border=True, after=240))
    if title:
        parts.append(_para([_run(title, bold=True, size=26)], align="center", after=240))
    for block in body.replace("\r\n", "\n").split("\n\n"):
        lines = block.split("\n")
        runs = []
        for i, line in enumerate(lines):
            bold = line.startswith("**") and line.endswith("**") and len(line) > 4
            runs.append(_run(line[2:-2] if bold else line, bold=bold))
            if i < len(lines) - 1:
                runs.append("<w:r><w:br/></w:r>")
        parts.append(_para(runs))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(parts)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1300" w:bottom="1440" w:left="1300" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/document.xml", document)
    return buffer.getvalue()


# ----------------------------------------------------------------------- PDF


def _pdf_escape(text: str) -> bytes:
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")


def _wrap(text: str, width: int) -> list[str]:
    out = []
    for raw in text.split("\n"):
        line = ""
        for word in raw.split(" "):
            if len(line) + len(word) + 1 > width and line:
                out.append(line)
                line = word
            else:
                line = f"{line} {word}" if line else word
        out.append(line)
    return out


def make_pdf(title: str, lines: list[str]) -> bytes:
    """A simple, valid, multi-page A4 PDF of text. Helvetica, no images."""
    body = []
    for line in lines:
        body.extend(_wrap(line, 92) if line else [""])
    per_page = 48
    pages = [body[i:i + per_page] for i in range(0, max(len(body), 1), per_page)] or [[]]

    page_objects = []
    for index, page in enumerate(pages):
        ops = []
        y = 800
        if index == 0:
            ops.append(b"BT /F1 15 Tf 56 800 Td (" + _pdf_escape(title) + b") Tj ET")
            y = 770
        for line in page:
            ops.append(b"BT /F1 10 Tf 56 %d Td (" % y + _pdf_escape(line) + b") Tj ET")
            y -= 15
        page_objects.append(b"\n".join(ops))

    # 1 catalog, 2 pages, 3 font, then (page, content) pairs.
    objects: list[bytes] = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for stream in page_objects:
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {page_id + 1} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()

    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)
