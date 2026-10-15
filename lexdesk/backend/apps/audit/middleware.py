import ipaddress

from django.conf import settings

from .context import request_ip, request_user_agent


def client_ip(request) -> str | None:
    if settings.LEXDESK_TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            # The left-most entry is the original client; our proxy appends.
            candidate = forwarded.split(",")[0].strip()
        else:
            candidate = request.META.get("REMOTE_ADDR", "")
    else:
        candidate = request.META.get("REMOTE_ADDR", "")

    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip_token = request_ip.set(client_ip(request))
        ua_token = request_user_agent.set(request.META.get("HTTP_USER_AGENT", "")[:256])
        try:
            return self.get_response(request)
        finally:
            request_ip.reset(ip_token)
            request_user_agent.reset(ua_token)
