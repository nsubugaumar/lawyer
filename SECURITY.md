# LexDesk: Security Testing Report

| | |
|---|---|
| **System** | LexDesk, multi-firm practice management for law firms (web app, client portal, public firm websites, Android app) |
| **Version tested** | Repository `nsubugaumar/lawyer`, branch `main`, 15 October 2026 |
| **Environment** | Development build on Windows (Django 6.1 + DRF API, Next.js 15.5.28 web app, SQLite), with production settings checked separately |
| **Tested by** | The development team, assisted by AI (Claude), using automated tools and automated tests |
| **Status** | Internal security testing complete; **independent penetration test not yet done** (see section 7) |

> **What this report does and does not claim.** It records the security tests
> carried out, what they found, and what was fixed. It is evidence that the
> tests below passed on the date above. It is **not** an independent security
> certification. Before real client data goes in, an independent penetration
> tester should assess the deployed system (section 7).

---

## 1. Summary

| Area | Result |
|---|---|
| Known-vulnerable libraries (Python and JavaScript) | **0** remaining (4 found and fixed, including 1 critical) |
| Static code analysis (Bandit) | **0 high, 0 medium**; 10 low, all reviewed as false positives |
| Automated security tests | **201 / 201** backend tests pass, including 42 dedicated attack tests |
| Live outside-in scan of the running system | **55 / 55** checks pass |
| Cross-firm access attempts (7 roles × 20 record addresses × read/change/delete + 16 actions) | **All refused** |
| Secrets in the code repository or its history | **None found** |
| Production configuration (`manage.py check --deploy`) | No errors; one intentional warning (https redirect handled by Caddy) |

**Findings fixed during this assessment:** 1 critical, 4 high, 3 medium, 3 low.
**Open findings:** none critical or high. Accepted residual risks are listed in section 6.

---

## 2. Scope and method

**In scope:** the API (all endpoints), the web app and client portal, the public
firm websites and booking, firm self-registration, the platform console,
notifications (WhatsApp, SMS, email, calendar feed), payments, document vault,
messaging, and the Android app's handling of documents and offline data. Also
the deployment configuration (Docker Compose, Caddy, backups).

**Out of scope for now:** the live production server and network (not yet built),
the third-party services themselves (Meta WhatsApp, Africa's Talking,
Flutterwave), physical security, and staff security practices.

**Standards used:** OWASP Top 10 (2021) as the risk list; OWASP ASVS 4.0 for
testable requirements; NIST SSDF practices for building security into
development (tests run on every change). Uganda's Data Protection and Privacy
Act, 2019 informed the privacy checks.

**Tools:** Bandit 1.9 (Python static analysis), pip-audit 2.10 (Python
dependencies), npm audit (JavaScript dependencies), Django's deployment checks,
the project's own automated attack tests (`apps/core/tests/test_security.py`,
`apps/firm/tests/test_isolation.py` and others), a live scanner
(`lexdesk/security/live_check.py`), and a load script
(`lexdesk/security/load_check.py`, plus `curl` for concurrency).

Evidence files are in `lexdesk/security/reports/`.

---

## 3. Tests performed and results

### A. Can an attacker break in?

| # | Test | What was done | Result |
|---|---|---|---|
| 1 | Penetration-style testing (internal) | Automated attack tests act as an outsider, as another firm, and as every role, against every record and action. | **Pass.** An independent manual test is still recommended (section 7). |
| 2 | Vulnerability assessment | pip-audit and npm audit against every library in use. | **Fixed, then pass.** Found: Next.js critical remote-code-execution flaw (CVE in React flight protocol) and others; pypdf (many flaws in PDF parsing); sharp/libvips; postcss. All upgraded or removed. Now **0 known vulnerabilities**. |
| 3 | Automated security scanning | Bandit over all Python code; live scanner over the running site. | **Pass.** Bandit: 0 high/medium after review. Live: 55/55. |
| 4 | Web application security | Security headers, Content Security Policy, clickjacking, cookies, error leakage, open redirect, injection probes. | **Fixed, then pass.** Added a Content Security Policy to all web pages; fixed a sign-in open-redirect (`/\evil.com`). |
| 5 | API security | Every endpoint without a session; forged, unsigned (`alg=none`) and expired tokens; cross-firm and cross-role requests. | **Pass.** All return 401/403/404 as expected. |
| 6 | Infrastructure (configuration review) | Docker Compose and Caddy reviewed; Django `check --deploy` with production settings. | **Pass.** Only ports 80/443 exposed; database and Redis on the private network; containers run as non-root; secrets only in `.env` (never in images or git); HSTS, automatic TLS, certificates only for real firms' domains. Scanning the built images (Trivy) is to be done on the server. |

### B. Can people see what they should not?

| # | Test | What was done | Result |
|---|---|---|---|
| 7 | Authentication | Login, lockout after 5 failures, rate limit (429), identical errors for unknown/wrong accounts, password policy (12+ chars, common-password check), Argon2 hashing, token rotation and revocation, password change kills old sessions, two-factor sign-in and recovery codes, MFA required for staff, deactivation ends sessions at once, refresh cookie HttpOnly + SameSite=Strict + path-scoped. | **Pass.** |
| 8 | Authorisation (roles) | Client, receptionist, lawyer off the matter, accountant, partner behind an ethical wall: each tried what they should not. | **Pass.** Clients see only their own shared items; reception keeps the diary but not files; lawyers see only their matters; partners oversee everything **except** privileged notes and messages unless on the matter team. |
| 9 | Privilege escalation | Users tried to make themselves admin/superuser, change firm, add staff, change firm settings, reach the platform console, move colleagues to another firm, create client logins via the staff form. | **Pass.** All refused or ignored. |
| 10 | Data isolation between firms (BOLA / IDOR) | 7 intruder roles from Firm B against 20 addresses naming Firm A's records (read, change, delete), 16 state-changing actions, and searches/lists. | **Pass.** Every attempt refused; nothing of Firm A appears in Firm B's lists or searches. |

### C. Can client information be exposed?

| # | Test | What was done | Result |
|---|---|---|---|
| 11 | Data protection | Checked database columns directly: file notes, messages, ID numbers, notification bodies, MFA secrets and provider keys. | **Pass.** Stored encrypted; API never returns secrets; API responses `Cache-Control: no-store`. |
| 12 | Database security | Injection payloads (`' OR '1'='1`, `UNION SELECT`, `DROP TABLE`) through every search, filter and ordering field. | **Pass.** Treated as plain text; no errors, no data leaked. All database access goes through the ORM (parameterised). |
| 13 | Encryption | Documents on disk checked for plaintext; a tampered file; a backup copy read with the wrong keys. | **Pass.** Files are AES-256-GCM ciphertext; a tampered file is withheld and alerted; a backup is unreadable without the keys. TLS is automatic in production (Caddy, HSTS). |
| 14 | Privacy | Public pages and endpoints checked for anything beyond what a firm publishes. | **Pass.** Public lawyer list shows only name and title; public firm page shows no secrets or internals; WhatsApp/SMS/email alerts never contain message or note content. |
| 15 | Audit logs | Sensitive actions recorded; a row edited directly in the database; attempts to edit/delete through the app and API. | **Pass.** Tampering detected at the exact row (hash chain); the log cannot be changed through the app; it records actions, never content; each firm sees only its own log. |

### D. Additional tests specific to LexDesk

| Test | Result |
|---|---|
| **File uploads**: a Windows program renamed `.pdf`, HTML, SVG with script, `.exe`, empty and oversized files, file names with `../` and header-injection characters. | **Pass.** All refused or neutralised. |
| **Stored script (XSS)**: `<script>` saved in client names and messages, then emailed. | **Pass.** Escaped in emails; React escapes it on screen; the page CSP blocks external scripts. |
| **Webhooks**: forged WhatsApp, Flutterwave and Africa's Talking callbacks. | **Pass.** Signatures and secret hashes checked; forged requests refused. |
| **Payments logic**: underpayment, wrong currency, a replayed webhook, the return page racing the webhook. | **Pass.** Only a verified, full payment is recorded, exactly once. |
| **E-signatures**: signing for someone else; signing after the document changed. | **Pass.** Refused; a signature binds to the exact document fingerprint. |
| **Load (development server)**: 20 people at once, 200 requests. | Public pages median **52 ms**, signed-in median **85 ms**, **0 errors**. Sustained load needs the production setup (gunicorn + PostgreSQL); see 7. |
| **Backup and recovery**: vault copy restored; same copy with wrong keys. | **Pass** for the data and keys. A full restore drill on the server is pending (7). |
| **Secrets in the repository**: all files and full git history scanned. | **Pass.** No keys, passwords or databases committed. |

---

## 4. Findings and fixes

| ID | Severity | Finding | Fix | Verified by |
|---|---|---|---|---|
| F-01 | **Critical** | Next.js 15.5.4 had a remote-code-execution flaw and 20+ other advisories. | Upgraded to Next.js 15.5.28. | npm audit: 0 vulnerabilities |
| F-02 | High | pypdf 5.4.0 (reads uploaded PDFs for search) had many known flaws. | Upgraded to 6.20.1; minimum version pinned. | pip-audit: 0 vulnerabilities |
| F-03 | High | sharp/libvips image libraries had known flaws. | Pinned patched sharp 0.35.5 **and** turned the unused image optimiser off. | npm audit |
| F-04 | High | Firm administrators could open Django's built-in admin, which shows every firm's data. | Admin restricted to platform operators only. | Isolation tests |
| F-05 | High | Screens with their own permission rules skipped the two-factor requirement. | The checks were restored on every such screen. | Security tests |
| F-06 | Medium | Sign-in `?next=` accepted `/\evil.com` (open redirect). | Strict in-app path check. | Live scan |
| F-07 | Medium | Web pages had no Content Security Policy. | CSP added to every page. | Live scan |
| F-08 | Medium | An email already used at another firm could be linked to this firm's client portal. | Refused; logins never cross firms. | Isolation tests |
| F-09 | Low | `pip` in the server image was outdated. | Upgraded during the image build. | Dockerfile |
| F-10 | Low | The scan reader started `pdftoppm` by name, not its full path. | Full path used. | Bandit |
| F-11 | Low | The WhatsApp "phone number ID" setting was not validated. | Digits only. | Code review |

Earlier in the build, the same process also found and fixed: lawyers seeing
colleagues' appointments, and clients seeing court dates the lawyer had not
shared with them.

---

## 5. How security is built in (controls)

- **Isolation:** every query starts from the signed-in person's firm; each firm has its own website, keys for WhatsApp/SMS/payments, numbering and audit trail; suspension cuts access on the next request.
- **Privilege:** file notes and lawyer–client messages are readable only by the matter team and the client; partners oversee by numbers (reports), not by reading privileged content.
- **Encryption:** documents with AES-256-GCM (per-file keys wrapped by a master key); sensitive fields with Fernet; search via a keyed blind index; secrets never returned; TLS everywhere in production.
- **Accounts:** Argon2 passwords, 12-character minimum, lockout, rate limits, two-factor sign-in (required for staff), short-lived tokens, rotating refresh tokens in HttpOnly cookies.
- **Accountability:** tamper-evident, hash-chained audit trail of every sensitive action.
- **Abuse limits:** rate limits on login, booking, firm registration, test messages, downloads; honeypots on public forms.
- **Repeatable:** the attack tests run on every change; the live scanner and load script run against any deployment.

---

## 6. Residual risks (accepted for now)

| Risk | Why accepted / what reduces it | Owner action |
|---|---|---|
| CSP allows inline scripts (`'unsafe-inline'`). | Needed by Next.js hydration; external scripts are still blocked, and React escapes all data. | Move to CSP nonces in a later version. |
| Redis has no password. | It is reachable only on the private Docker network, not the internet. | Add `requirepass` if the network layout changes. |
| The search index reveals which documents share a word (never the word itself). | Inherent to searchable encryption; the key is outside the database. | Keep `LEXDESK_SEARCH_KEY` offline-backed up and secret. |
| Offline court briefs are stored on lawyers' phones. | Deleted at sign-out and two days after each hearing. | Firm policy: phones must have a screen lock. |
| No protection from large DDoS attacks at the network edge. | Rate limits and Caddy limits help with small abuse only. | Put the domain behind Cloudflare (free tier) at go-live. |
| Client accounts are not forced to use two-factor sign-in. | Optional for clients, required for staff. | Revisit if firms ask. |

---

## 7. Still to do before going live

These need the real server, outside parties, or people. They are part of
*Stage 2 and 3* in `lexdesk/deploy/DEPLOY.md`.

1. **Independent penetration test** of the deployed test server by a qualified tester who did not build LexDesk (written scope, test window, report with severities, fixes retested).
2. **OWASP ZAP full scan** (active) against the test server, authenticated as each role.
3. **Trivy scan** of the built Docker images and the server: `trivy image lexdesk-api:latest`, `trivy image lexdesk-web:latest`.
4. **Live scan** on the server: `python lexdesk/security/live_check.py https://<domain> --email <test account> --password <...>`.
5. **Load test** on the production stack: `python lexdesk/security/load_check.py https://<domain> --users 50 --seconds 60`.
6. **Restore drill**: restore last night's backup onto a spare server with the offline `.env`, and confirm documents open (DEPLOY.md, "Restore").
7. **TLS check**: SSL Labs test on the domain (target grade A or A+).
8. **Data protection**: register with Uganda's Personal Data Protection Office; publish a privacy notice; sign data-processing agreements with each firm; have a Ugandan data-protection lawyer review.
9. **Monitoring and response**: uptime monitoring on `/api/v1/health/`; a written incident-response plan (who is called, how firms are told, the 72-hour regulator notice).

**Release rule:** no go-live with an open critical or high finding; medium findings need a written decision.

---

## 8. How to re-run these tests

```bash
# Every change: all tests, including the attack tests
cd lexdesk/backend
LEXDESK_DEBUG=1 python manage.py test

# Code and libraries
python -m bandit -r apps config -x "*/tests/*,*/migrations/*"
python -m pip_audit -l
cd ../web && npm audit --omit=dev

# Against a running system (only systems you are authorised to test)
python lexdesk/security/live_check.py https://<domain> --email <test account> --password <password>
python lexdesk/security/load_check.py https://<domain> --email <test account> --password <password> --users 50 --seconds 60
```

Re-run after every release, and at least monthly for the library audits:
new vulnerabilities are published all the time.
