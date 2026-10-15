from rest_framework import serializers

from apps.matters.serializers import PersonSerializer

from .models import Document, DocumentTemplate, DocumentVersion, SignatureRequest


class VersionSerializer(serializers.ModelSerializer):
    uploaded_by = PersonSerializer(read_only=True)

    class Meta:
        model = DocumentVersion
        fields = ["number", "original_filename", "content_type", "size", "sha256", "uploaded_by", "comment", "created_at"]
        read_only_fields = fields


class DocumentSerializer(serializers.ModelSerializer):
    matter_reference = serializers.CharField(source="matter.reference", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    uploaded_by = PersonSerializer(read_only=True)
    latest = serializers.SerializerMethodField()
    signature = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True, required=False, help_text="Required when creating a document")

    class Meta:
        model = Document
        fields = [
            "id", "matter", "matter_reference", "title", "category", "category_display", "description", "tags",
            "shared_with_client", "court_bundle", "current_version", "latest", "uploaded_by", "is_archived",
            "signature", "file", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "current_version", "is_archived", "created_at", "updated_at"]

    def get_signature(self, obj):
        req = next(iter(obj.signature_requests.all()), None)
        if req is None or req.status == SignatureRequest.Status.CANCELLED:
            return None
        return {"id": str(req.id), "status": req.status, "signed_at": req.signed_at, "signer_name": req.signer_name}

    def get_latest(self, obj):
        version = next((v for v in obj.versions.all() if v.number == obj.current_version), None)
        return VersionSerializer(version).data if version else None

    def validate(self, attrs):
        if self.instance is None and not attrs.get("file"):
            raise serializers.ValidationError({"file": "Please attach the file."})
        if self.instance is not None and "matter" in attrs and attrs["matter"] != self.instance.matter:
            raise serializers.ValidationError({"matter": "Documents cannot be moved between matters."})
        return attrs


class ClientDocumentSerializer(DocumentSerializer):
    class Meta(DocumentSerializer.Meta):
        fields = [
            "id", "matter", "matter_reference", "title", "category", "category_display", "description",
            "current_version", "latest", "signature", "file", "created_at",
        ]
        read_only_fields = ["id", "category", "current_version", "created_at"]


class NewVersionSerializer(serializers.Serializer):
    file = serializers.FileField()
    comment = serializers.CharField(max_length=250, required=False, allow_blank=True)


class DocumentTemplateSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = DocumentTemplate
        fields = ["id", "name", "category", "category_display", "description", "body", "letterhead", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class SignatureRequestSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title", read_only=True)
    matter_reference = serializers.CharField(source="document.matter.reference", read_only=True)
    signer_name_on_file = serializers.CharField(source="signer.full_name", read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.full_name", read_only=True, default="")
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SignatureRequest
        fields = [
            "id", "document", "document_title", "matter_reference", "version_number", "document_sha256", "status",
            "status_display", "message", "signer_name_on_file", "requested_by_name", "signed_at", "signer_name",
            "decline_reason", "certificate", "created_at",
        ]
        read_only_fields = fields
