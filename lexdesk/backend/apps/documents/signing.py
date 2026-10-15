"""
Electronic signatures.

A lawyer asks the client to sign one exact version of a document. The client
reads it in their portal, types their full name, draws their signature and
confirms. LexDesk then records who signed, when, from where, and the SHA-256
fingerprint of the exact bytes signed, and files a signature certificate on
the matter. Under Uganda's Electronic Signatures Act, 2011 this is evidence
of the signature and of the document's integrity.
"""

import base64
import hashlib
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.context import request_ip, request_user_agent
from apps.audit.services import record
from apps.core.filemakers import make_pdf
from apps.notifications.models import Category
from apps.notifications.services import notify

from .models import Document, SignatureRequest
from .services import add_version

DATA_URL = re.compile(r"^data:image/png;base64,([A-Za-z0-9+/=]+)$")
MAX_SIGNATURE_BYTES = 200 * 1024


@transaction.atomic
def request_signature(document: Document, *, requested_by, message: str = "") -> SignatureRequest:
    signer = document.matter.client.portal_user
    if signer is None or not signer.is_active:
        raise ValidationError("This client has no portal account yet. Give them portal access first.")
    version = document.latest
    if version is None:
        raise ValidationError("Upload the document before asking for a signature.")
    if document.signature_requests.filter(status=SignatureRequest.Status.PENDING).exists():
        raise ValidationError("A signature is already pending on this document.")

    if not document.shared_with_client:
        document.shared_with_client = True  # they must be able to read what they sign
        document.save(update_fields=["shared_with_client", "updated_at"])

    req = SignatureRequest.objects.create(
        document=document, version_number=version.number, document_sha256=version.sha256,
        signer=signer, requested_by=requested_by, message=message[:500],
    )
    record("signature.requested", actor=requested_by, target=document, matter=document.matter, version=version.number)
    transaction.on_commit(lambda: notify(
        signer,
        subject=f"Please sign: {document.title}",
        body=f"{requested_by.full_name} has asked you to sign “{document.title}”.\n\n"
        + (f"{message}\n\n" if message else "")
        + "Open your client portal to read it and sign. It takes a minute.",
        sms=f"Please sign “{document.title[:60]}” in your LexDesk portal.",
        link="/portal", category=Category.GENERAL,
    ))
    return req


@transaction.atomic
def sign(req: SignatureRequest, *, user, full_name: str, signature_data_url: str, agreed: bool) -> SignatureRequest:
    req = SignatureRequest.objects.select_for_update().select_related("document__matter").get(pk=req.pk)
    if req.signer_id != user.id:
        raise PermissionDenied("This signature request is for someone else.")
    if req.status != SignatureRequest.Status.PENDING:
        raise ValidationError("This request is no longer waiting for a signature.")
    document = req.document
    if document.current_version != req.version_number:
        raise ValidationError("The document has changed since you were asked to sign. Your lawyer will send the new version.")
    if not agreed:
        raise ValidationError({"agreed": "Please confirm that you have read the document and agree to sign it."})
    full_name = " ".join(full_name.split())
    if len(full_name) < 3:
        raise ValidationError({"full_name": "Type your full name."})
    match = DATA_URL.match(signature_data_url or "")
    if not match:
        raise ValidationError({"signature": "Please draw your signature."})
    image = base64.b64decode(match.group(1))
    if len(image) > MAX_SIGNATURE_BYTES or not image.startswith(b"\x89PNG"):
        raise ValidationError({"signature": "That signature could not be read. Please draw it again."})

    now = timezone.now()
    req.status = SignatureRequest.Status.SIGNED
    req.signed_at = now
    req.signer_name = full_name[:200]
    req.signature_image = signature_data_url
    req.signature_sha256 = hashlib.sha256(image).hexdigest()
    req.ip_address = request_ip.get()
    req.user_agent = (request_user_agent.get() or "")[:256]

    local = timezone.localtime(now)
    lines = [
        f"Document: {document.title}",
        f"Matter: {document.matter.reference} {document.matter.title}",
        f"Version signed: {req.version_number}",
        f"Document SHA-256: {req.document_sha256}",
        "",
        f"Signed by: {req.signer_name}",
        f"Account: {user.email}",
        f"Signed at: {local:%d %B %Y, %H:%M:%S %Z}",
        f"IP address: {req.ip_address or 'unknown'}",
        f"Device: {req.user_agent or 'unknown'}",
        f"Signature image SHA-256: {req.signature_sha256}",
        "",
        "The signer confirmed: \"I have read this document and I agree to sign it electronically.\"",
        "",
        "Any change to the document after signing changes its SHA-256 fingerprint, so this",
        "certificate proves exactly which bytes were signed. Issued by LexDesk under the",
        "Electronic Signatures Act, 2011 (Uganda).",
    ]
    certificate = Document.objects.create(
        matter=document.matter, title=f"Signature certificate – {document.title}"[:250], category=Document.Category.CONTRACT,
        shared_with_client=True, uploaded_by=user, description="Evidence of electronic signature",
    )
    add_version(certificate, SimpleUploadedFile("signature-certificate.pdf", make_pdf("Electronic signature certificate", lines)), user=user)
    req.certificate = certificate
    req.save()

    record("signature.signed", actor=user, target=document, matter=document.matter, version=req.version_number,
           document_sha256=req.document_sha256, signature_sha256=req.signature_sha256)
    if req.requested_by:
        requester = req.requested_by
        transaction.on_commit(lambda: notify(
            requester,
            subject=f"Signed: {document.title}",
            body=f"{req.signer_name} signed “{document.title}” on {local:%d %B %Y at %H:%M}. The signature certificate is on the matter.",
            sms=f"{req.signer_name} signed “{document.title[:60]}”.",
            link=f"/matters/{document.matter_id}", category=Category.GENERAL,
        ))
    return req


def decline(req: SignatureRequest, *, user, reason: str = ""):
    if req.signer_id != user.id:
        raise PermissionDenied()
    if req.status != SignatureRequest.Status.PENDING:
        raise ValidationError("This request is no longer waiting for a signature.")
    req.status = SignatureRequest.Status.DECLINED
    req.decline_reason = reason[:500]
    req.save(update_fields=["status", "decline_reason", "updated_at"])
    record("signature.declined", actor=user, target=req.document, matter=req.document.matter)
    if req.requested_by:
        notify(req.requested_by, subject=f"Signature declined: {req.document.title}",
               body=f"{user.full_name} declined to sign. {('Reason: ' + reason) if reason else ''}",
               link=f"/matters/{req.document.matter_id}", category=Category.GENERAL)
    return req
