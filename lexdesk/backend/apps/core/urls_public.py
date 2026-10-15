from django.conf import settings


def public_url(request, path: str) -> str:
    """
    The address people and services outside should use for `path`.

    The web app serves /api/ on the firm's own domain, so links we hand out
    (calendar feeds, webhook addresses) use that domain when it is known,
    not whichever internal host the request arrived on.
    """
    base = (getattr(settings, "LEXDESK_WEB_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else request.build_absolute_uri(path)
