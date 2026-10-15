class SecurityHeadersMiddleware:
    """
    Headers Django does not set by default but every serious API should.

    The API never serves HTML to browsers (the web app does that), so the
    Content-Security-Policy can be as strict as it gets. The admin is the one
    exception and needs its own scripts and styles.
    """

    API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ADMIN_CSP = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        is_api = request.path.startswith("/api/")

        response.setdefault("Content-Security-Policy", self.API_CSP if is_api else self.ADMIN_CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        response.setdefault("Cross-Origin-Resource-Policy", "same-site")

        # Legal data must never sit in a shared proxy or a browser cache.
        if is_api:
            response.setdefault("Cache-Control", "no-store")
            response.setdefault("Pragma", "no-cache")
        return response
