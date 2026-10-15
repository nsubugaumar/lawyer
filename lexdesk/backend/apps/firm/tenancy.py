"""
Which firm a request belongs to.

Signed-in people always act inside their own firm; nothing a browser sends
can change that. Public pages (a firm's website, its booking page) have no
signed-in person, so the firm is worked out from the address the visitor
used, in this order:

  1. `?firm=<slug>` or the `X-LexDesk-Firm` header (links shared by a firm)
  2. the firm's own domain, e.g. www.nsc-advocates.co.ug
  3. a sub-domain, e.g. nsc.lexdesk.app or nsc.localhost
  4. LEXDESK_DEFAULT_FIRM, or the only firm if there is just one (or, on a
     developer's machine, the first firm)

Public pages only ever show what a firm publishes, so a visitor choosing a
different firm here simply sees that firm's website.
"""

from django.conf import settings
from django.http import Http404

from .models import Firm


def _host(request) -> str:
    # The web app forwards the address bar's host; the API itself sits behind it.
    host = request.headers.get("X-LexDesk-Host") or request.get_host()
    return host.split(":")[0].lower().strip()


def public_firm(request) -> Firm:
    active = Firm.objects.filter(is_active=True)

    slug = request.query_params.get("firm") if hasattr(request, "query_params") else request.GET.get("firm")
    slug = slug or request.headers.get("X-LexDesk-Firm")
    if slug:
        # A named firm is that firm or nothing; never quietly another firm.
        firm = active.filter(slug=slug.strip().lower()).first()
        if firm is None:
            raise Http404("No law firm at this address.")
        return firm

    host = _host(request)
    if host:
        firm = active.filter(domain__iexact=host).first() or active.filter(domain__iexact=host.removeprefix("www.")).first()
        if firm:
            return firm
        label = host.split(".")[0]
        if "." in host and label not in {"www", "app", "api"}:
            firm = active.filter(slug=label).first()
            if firm:
                return firm

    default = getattr(settings, "LEXDESK_DEFAULT_FIRM", "")
    if default:
        firm = active.filter(slug=default).first()
        if firm:
            return firm
    if active.count() == 1 or (settings.DEBUG and active.exists()):
        # One firm, or a developer's machine: show the first firm's website.
        return active.order_by("pk").first()
    raise Http404("No law firm at this address.")


def firm_for(request) -> Firm:
    """The signed-in person's firm, or the public firm for visitors."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and getattr(user, "firm_id", None):
        return user.firm
    return public_firm(request)
