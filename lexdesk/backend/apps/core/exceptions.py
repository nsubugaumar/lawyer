import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("lexdesk.security")


def exception_handler(exc, context):
    """
    Give every API error the same shape so the web and mobile apps can handle
    them in one place:

        {"error": {"code": "permission_denied", "message": "...", "fields": {...}}}

    Unexpected exceptions are left to Django, which returns a bare 500 with no
    stack trace in production. We never echo internals back to the caller.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.response import Response

        if isinstance(exc, DjangoValidationError):
            # Malformed input that reached the database layer (a bad id, say):
            # a clean refusal, never a crash with a stack trace.
            return Response({"error": {"code": "invalid", "message": "That request contains an invalid value."}}, status=400)
        return None

    data = response.data
    code = getattr(exc, "default_code", "error")
    detail = getattr(exc, "detail", None)

    if isinstance(detail, dict) and "code" in detail and "detail" in detail:
        # Our own errors raised with an explicit code, e.g. mfa_setup_required.
        code = str(detail["code"])
        message, fields = str(detail["detail"]), None
    elif isinstance(data, dict) and "detail" in data:
        message, fields = str(data["detail"]), None
        code = getattr(data["detail"], "code", code)
    elif isinstance(data, dict):
        message, fields = "Please correct the highlighted fields.", data
    else:
        message, fields = "Please correct the errors below.", {"non_field_errors": data}

    if response.status_code in (401, 403):
        request = context.get("request")
        logger.info(
            "access refused status=%s code=%s path=%s user=%s",
            response.status_code,
            code,
            getattr(request, "path", "?"),
            getattr(getattr(request, "user", None), "pk", None),
        )

    response.data = {"error": {"code": str(code), "message": message, **({"fields": fields} if fields else {})}}
    return response
