import logging

from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.services import record
from apps.core.crypto import DecryptionError
from apps.core.ids import as_uuid
from apps.matters.access import can_see_matter, can_work_on_matter, visible_matters

from .models import Document, DocumentTemplate, DocumentVersion, SignatureRequest
from .search import matching
from .serializers import (
    ClientDocumentSerializer,
    DocumentSerializer,
    DocumentTemplateSerializer,
    NewVersionSerializer,
    SignatureRequestSerializer,
    VersionSerializer,
)
from .services import add_version, read_version
from .validation import INLINE_TYPES

logger = logging.getLogger("lexdesk.security")


class DocumentViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["matter", "category", "shared_with_client", "court_bundle", "is_archived"]
    search_fields = ["title", "description", "tags", "versions__original_filename", "matter__reference"]
    ordering_fields = ["created_at", "updated_at", "title"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    throttle_scope = None  # the download action sets its own, stricter scope

    def get_queryset(self):
        user = self.request.user
        qs = (
            Document.objects.filter(matter__in=visible_matters(user))
            .select_related("matter", "uploaded_by")
            .prefetch_related(
                Prefetch("versions", queryset=DocumentVersion.objects.select_related("uploaded_by")),
                Prefetch("signature_requests", queryset=SignatureRequest.objects.order_by("-created_at")),
            )
        )
        if user.is_client:
            qs = qs.filter(shared_with_client=True, is_archived=False)
        elif "is_archived" not in self.request.query_params:
            qs = qs.filter(is_archived=False)
        query = self.request.query_params.get("q", "").strip()
        if query:
            # Words inside the documents themselves, via the blind index.
            qs = matching(qs, query)
        return qs.distinct()

    def get_serializer_class(self):
        return ClientDocumentSerializer if getattr(self.request.user, "is_client", False) else DocumentSerializer

    def _check_write(self, matter):
        user = self.request.user
        if user.is_client:
            if not can_see_matter(user, matter):
                raise PermissionDenied()
            return
        if not can_work_on_matter(user, matter):
            raise PermissionDenied("You are not on the team for this matter.")

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        matter = serializer.validated_data["matter"]
        self._check_write(matter)
        upload = serializer.validated_data.pop("file")

        extra = {"uploaded_by": user}
        if user.is_client:
            # What a client sends us is visible to them, and goes in a tray
            # for the lawyer to review and file properly.
            extra.update(category=Document.Category.CLIENT_UPLOAD, shared_with_client=True, court_bundle=False)

        document = serializer.save(**extra)
        add_version(document, upload, user=user)

    def perform_update(self, serializer):
        if self.request.user.is_client:
            raise PermissionDenied()
        self._check_write(serializer.instance.matter)
        serializer.validated_data.pop("file", None)
        document = serializer.save()
        record("document.updated", actor=self.request.user, target=document, matter=document.matter,
               fields=sorted(serializer.validated_data))

    def perform_destroy(self, document):
        # Archive rather than delete: firms must retain files, and an
        # accidental click should be reversible.
        if self.request.user.is_client:
            raise PermissionDenied()
        self._check_write(document.matter)
        document.is_archived = True
        document.save(update_fields=["is_archived", "updated_at"])
        record("document.archived", actor=self.request.user, target=document, matter=document.matter)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        document = self.get_object()
        if request.user.is_client:
            raise PermissionDenied()
        self._check_write(document.matter)
        document.is_archived = False
        document.save(update_fields=["is_archived", "updated_at"])
        record("document.restored", actor=request.user, target=document, matter=document.matter)
        return Response(self.get_serializer(document).data)

    @action(detail=True, methods=["get", "post"])
    def versions(self, request, pk=None):
        document = self.get_object()
        if request.method == "GET":
            return Response(VersionSerializer(document.versions.all(), many=True).data)

        if request.user.is_client and document.uploaded_by_id != request.user.id:
            raise PermissionDenied("You can only add versions to documents you uploaded.")
        self._check_write(document.matter)
        data = NewVersionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        version = add_version(document, data.validated_data["file"], user=request.user, comment=data.validated_data.get("comment", ""))
        return Response(VersionSerializer(version).data, status=201)

    @action(detail=True, methods=["get"], throttle_scope="download")
    def download(self, request, pk=None):
        """
        Stream the decrypted file. Add ?version=N for an older version and
        ?inline=1 to view a PDF or image in the app instead of saving it.
        """
        document = self.get_object()
        number = request.query_params.get("version") or document.current_version
        try:
            version = document.versions.get(number=int(number))
        except (DocumentVersion.DoesNotExist, ValueError):
            raise ValidationError({"version": "No such version."}) from None

        try:
            content = read_version(version)
        except DecryptionError:
            logger.critical("INTEGRITY FAILURE document=%s version=%s", document.pk, version.number)
            record("document.integrity_failure", actor=request.user, target=document, matter=document.matter, version=version.number)
            return Response(
                {"error": {"code": "integrity_failure", "message": "This file failed its integrity check and has been "
                           "withheld. The firm's administrator has been alerted."}},
                status=500,
            )

        inline = request.query_params.get("inline") == "1" and version.content_type in INLINE_TYPES
        record(
            "document.viewed" if inline else "document.downloaded",
            actor=request.user, target=document, matter=document.matter, version=version.number,
        )

        response = HttpResponse(content, content_type=version.content_type)
        response["Content-Disposition"] = content_disposition_header(not inline, version.original_filename)
        response["Content-Length"] = str(len(content))
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
        response["Cache-Control"] = "private, no-store"
        response["X-Document-SHA256"] = version.sha256
        return response

    @action(detail=False, methods=["get"], url_path="court-bundle")
    def court_bundle(self, request):
        """
        Everything a lawyer needs in court, for the mobile app to cache
        offline. Includes each file's SHA-256 so the device can prove its
        cached copy is genuine before showing it.
        """
        if request.user.is_client:
            raise PermissionDenied()
        qs = self.get_queryset().filter(court_bundle=True)
        matter = request.query_params.get("matter")
        if matter:
            qs = qs.filter(matter_id=matter)
        record("document.court_bundle_synced", actor=request.user, matter_filter=matter or "all", count=qs.count())
        return Response(DocumentSerializer(qs[:500], many=True, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="request-signature")
    def request_signature(self, request, pk=None):
        from .signing import request_signature

        document = self.get_object()
        if request.user.is_client:
            raise PermissionDenied()
        self._check_write(document.matter)
        req = request_signature(document, requested_by=request.user, message=str(request.data.get("message", "")))
        return Response(SignatureRequestSerializer(req).data, status=201)


class DocumentTemplateViewSet(viewsets.ModelViewSet):
    """The firm's letters and pleadings, ready to draft from."""

    serializer_class = DocumentTemplateSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    search_fields = ["name", "description"]

    def get_queryset(self):
        user = self.request.user
        if user.is_client or not user.firm_id:
            return DocumentTemplate.objects.none()
        return DocumentTemplate.objects.filter(firm_id=user.firm_id)

    def _require_lawyer(self):
        if self.request.user.role not in ("admin", "partner", "lawyer", "paralegal"):
            raise PermissionDenied("Only lawyers and the practice manager edit templates.")

    def perform_create(self, serializer):
        self._require_lawyer()
        template = serializer.save(firm_id=self.request.user.firm_id, created_by=self.request.user)
        record("template.created", actor=self.request.user, target=template)

    def perform_update(self, serializer):
        self._require_lawyer()
        record("template.updated", actor=self.request.user, target=serializer.save())

    def perform_destroy(self, instance):
        self._require_lawyer()
        record("template.deleted", actor=self.request.user, target=instance)
        instance.delete()

    @action(detail=False, methods=["get"])
    def placeholders(self, request):
        from .drafting import PLACEHOLDERS

        return Response([{"key": k, "label": v} for k, v in PLACEHOLDERS.items()])

    @action(detail=False, methods=["post"])
    def starter(self, request):
        from .drafting import add_starter_templates

        self._require_lawyer()
        created = add_starter_templates(request.user.firm, request.user)
        return Response(DocumentTemplateSerializer(created, many=True).data, status=201)

    @action(detail=True, methods=["post"])
    def draft(self, request, pk=None):
        """Fill the template from a matter and file the Word draft on it."""
        from apps.matters.models import Matter

        from .drafting import draft_from_template

        template = self.get_object()
        matter_id = as_uuid(request.data.get("matter"))
        matter = visible_matters(request.user).filter(pk=matter_id).first() if matter_id else None
        if matter is None:
            raise ValidationError({"matter": "Choose one of your matters."})
        if not can_work_on_matter(request.user, matter):
            raise PermissionDenied("You are not on the team for this matter.")
        matter = Matter.objects.select_related("client", "lead_lawyer", "firm").get(pk=matter.pk)
        document = draft_from_template(template, matter, user=request.user, title=str(request.data.get("title", "")))
        return Response(DocumentSerializer(document, context={"request": request}).data, status=201)


class SignatureRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Clients see what is waiting for their signature; lawyers see the requests
    on matters they can see.
    """

    serializer_class = SignatureRequestSerializer
    filterset_fields = ["status", "document"]

    def get_queryset(self):
        user = self.request.user
        qs = SignatureRequest.objects.select_related("document", "document__matter", "signer", "requested_by")
        if user.is_client:
            return qs.filter(signer=user)
        return qs.filter(document__matter__in=visible_matters(user))

    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        from .signing import sign

        req = sign(
            self.get_object(), user=request.user, full_name=str(request.data.get("full_name", "")),
            signature_data_url=str(request.data.get("signature", "")), agreed=request.data.get("agreed") is True,
        )
        return Response(SignatureRequestSerializer(req).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        from .signing import decline

        req = decline(self.get_object(), user=request.user, reason=str(request.data.get("reason", "")))
        return Response(SignatureRequestSerializer(req).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        req = self.get_object()
        if request.user.is_client:
            raise PermissionDenied()
        if req.status != SignatureRequest.Status.PENDING:
            raise ValidationError("Only a pending request can be cancelled.")
        req.status = SignatureRequest.Status.CANCELLED
        req.save(update_fields=["status", "updated_at"])
        record("signature.cancelled", actor=request.user, target=req.document, matter=req.document.matter)
        return Response(SignatureRequestSerializer(req).data)

