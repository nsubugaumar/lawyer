"""
Live security checks against a running LexDesk: the outside-in view.

    python live_check.py http://localhost:3000                  # local
    python live_check.py https://lexdesk.co.ug --email you@firm --password ...

Only run this against a LexDesk you are authorised to test. It sends a few
dozen requests, including deliberate login failures (so use a test account:
it may be locked for 15 minutes afterwards).

Checks: security headers and cookies, TLS redirect (https targets), exposed
files, unauthenticated API access, CORS, HTTP methods, open redirects,
injection probes, error leakage, request size limits, and login rate limits.
"""

import json
import ssl
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000").rstrip("/")
EMAIL = sys.argv[sys.argv.index("--email") + 1] if "--email" in sys.argv else ""
PASSWORD = sys.argv[sys.argv.index("--password") + 1] if "--password" in sys.argv else ""
CTX = ssl.create_default_context()
results = []


# No system proxy lookups: on Windows they add seconds to every request.
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect, urllib.request.HTTPSHandler(context=CTX))


def req(path, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    h = {"Content-Type": "application/json"} if isinstance(body, (dict, list)) else {}
    h.update(headers or {})
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with OPENER.open(request, timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:  # noqa: BLE001
        return 0, {}, str(e).encode()


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))


def lower(h):
    return {k.lower(): v for k, v in h.items()}


print(f"LexDesk live security check: {BASE}\n")

# ---------------------------------------------------------------- headers
for path in ("/", "/login", "/api/v1/health/"):
    status, h, _ = req(path)
    h = lower(h)
    check(f"{path} answers", status == 200, str(status))
    check(f"{path} X-Content-Type-Options nosniff", h.get("x-content-type-options") == "nosniff")
    check(f"{path} refuses framing (clickjacking)", h.get("x-frame-options") == "DENY" or "frame-ancestors 'none'" in h.get("content-security-policy", ""))
    check(f"{path} has a Content-Security-Policy", bool(h.get("content-security-policy")))
    check(f"{path} Referrer-Policy set", bool(h.get("referrer-policy")))
    check(f"{path} does not advertise its server software", "x-powered-by" not in h)
    if BASE.startswith("https://"):
        check(f"{path} HSTS", "max-age=" in h.get("strict-transport-security", ""))

status, h, _ = req("/api/v1/health/")
check("API responses are not cached", "no-store" in lower(h).get("cache-control", ""))

if BASE.startswith("https://"):
    plain = "http://" + BASE[len("https://"):]
    try:
        r = urllib.request.Request(plain + "/login")
        OPENER.open(r, timeout=20)
        check("http redirects to https", False, "served over plain http")
    except urllib.error.HTTPError as e:
        check("http redirects to https", e.code in (301, 302, 307, 308) and e.headers.get("Location", "").startswith("https://"))
    except Exception as e:  # noqa: BLE001
        check("http redirects to https", False, str(e))

# ---------------------------------------------------------- exposed files
for path in ("/.env", "/.git/config", "/db.sqlite3", "/backend/.env", "/vault/", "/static/../config/settings.py",
             "/api/v1/../../config/settings.py", "/package.json", "/next.config.ts", "/.next/server/app/page.js"):
    status, _, body = req(path)
    leaked = status == 200 and any(s in body for s in (b"SECRET_KEY", b"[core]", b"SQLite format", b"\"dependencies\"", b"LEXDESK_"))
    check(f"{path} not exposed", not leaked, str(status))

# --------------------------------------------------- unauthenticated API
for path in ("/api/v1/matters/", "/api/v1/clients/", "/api/v1/documents/", "/api/v1/diary/", "/api/v1/messages/threads/",
             "/api/v1/billing/invoices/", "/api/v1/auth/team/", "/api/v1/reports/", "/api/v1/audit/events/", "/api/v1/platform/firms/"):
    status, _, _ = req(path)
    check(f"{path} needs a session", status == 401, str(status))

status, _, _ = req("/api/v1/matters/", headers={"Authorization": "Bearer eyJhbGciOiJub25lIn0.eyJ1c2VyX2lkIjoiMSJ9."})
check("unsigned (alg=none) token refused", status == 401, str(status))

# ------------------------------------------------------------------- CORS
status, h, _ = req("/api/v1/auth/me/", headers={"Origin": "https://evil.example"})
allow = lower(h).get("access-control-allow-origin", "")
check("CORS does not trust other websites", allow not in ("*", "https://evil.example"), allow)

# ----------------------------------------------------------- HTTP methods
for method in ("TRACE", "TRACK"):
    status, _, body = req("/api/v1/health/", method=method)
    check(f"{method} not allowed", status in (400, 403, 404, 405, 501), str(status))

# ------------------------------------------------------- open redirects
for path in ("/login?next=//evil.example", "/login?next=https://evil.example"):
    status, h, _ = req(path)
    location = lower(h).get("location", "")
    check(f"no server redirect off-site: {path}", "evil.example" not in location, location)

# ------------------------------------------------- injection & leakage
for payload in ("' OR '1'='1", "\"; DROP TABLE x; --", "<script>alert(1)</script>", "../../../../etc/passwd"):
    status, _, body = req("/api/v1/firm/public/?firm=" + urllib.request.quote(payload))
    check(f"injection probe handled ({payload[:12]})", status in (200, 400, 404) and b"Traceback" not in body and b"SQL" not in body, str(status))
status, _, body = req("/api/v1/appointments/public/availability/?lawyer=" + urllib.request.quote("' OR 1=1--") + "&date=2030-01-01")
check("bad input gives a clean error", status in (400, 404) and b"Traceback" not in body, str(status))

# --------------------------------------------------------- size limits
status, _, _ = req("/api/v1/auth/login/", "POST", b"{" + b"\"a\":\"" + b"x" * (6 * 1024 * 1024) + b"\"}", {"Content-Type": "application/json"})
check("oversized request refused", status in (400, 413, 431, 0), str(status))

# ------------------------------------------------ session cookie (before abuse tests lock the account)
if EMAIL and PASSWORD:
    status, h, _ = req("/api/v1/auth/login/", "POST", {"email": EMAIL, "password": PASSWORD})
    cookie = lower(h).get("set-cookie", "")
    check("refresh cookie HttpOnly", "httponly" in cookie.lower(), cookie[:60])
    check("refresh cookie SameSite=Strict", "samesite=strict" in cookie.lower())
    if BASE.startswith("https://"):
        check("refresh cookie Secure", "secure" in cookie.lower())


# ------------------------------------------------- login abuse controls
statuses = [req("/api/v1/auth/login/", "POST", {"email": EMAIL or "nobody@example.invalid", "password": "definitely-wrong"})[0] for _ in range(12)]
check("login is rate limited", 429 in statuses, ",".join(map(str, statuses)))
_, _, a = req("/api/v1/auth/login/", "POST", {"email": "nobody@example.invalid", "password": "x"})
check("unknown and wrong-password logins look the same", b"invalid_credentials" in a or b"throttled" in a)

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
