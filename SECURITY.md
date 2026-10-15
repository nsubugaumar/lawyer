# LexDesk: Security Testing Report

| | |
|---|---|
| **System** | LexDesk, multi-firm practice management for law firms (web app, client portal, public firm websites, Android app) |
| **Version tested** | Repository `nsubugaumar/lawyer`, branch `main`, 15 October 2026 |
| **Environment** | Development build on Windows (Django 6.1 + DRF API, Next.js 15.5.28 web app, SQLite), with production settings checked separately |
| **Tested by** | The development team, assisted by AI (Claude), using industry tools and automated tests |
| **Status** | All tests that can run without a live server are complete. **Independent penetration test and server-side tests still to do** (section 8). |

> **What this report does and does not claim.** It records the security tests
> carried out, what they found, and what was fixed. It is evidence that the
> tests below passed on the date above. It is **not** an independent security
> certification. Before real client data goes in, an independent penetration
> tester should assess the deployed system (section 8).

---

## 1. Summary

| Area | Tool | Result |
|---|---|---|
| Known-vulnerable libraries | pip-audit, npm audit | **0** remaining (found and fixed 4, including 1 critical) |
| Static code analysis, Python | Bandit 1.9 | **0 high, 0 medium**; 10 low, all reviewed as false positives |
| Static code analysis, all code | Semgrep 1.181 (353 rules: Python, Django, OWASP Top 10, TypeScript, React, JavaScript, secrets) | **1 finding**, a reviewed false positive (the app's launcher screen must be exported); 207 files, 0 parse errors |
| Dynamic scan, website | OWASP ZAP 2.17 (crawl + active attack) | **0 high**; 1 medium accepted (inline styles); 2 informational |
| Dynamic scan, API, signed in | OWASP ZAP 2.17 (154 endpoints, 40-minute active attack) | 2 "high" alerts investigated: one false positive, one real crash bug, **now fixed** |
| Android app | Android Lint + manifest inspection | **No security errors**; release build https-only, not debuggable, no backups; 1 usability bug fixed |
| Automated security and integrity tests | Django test suite | **217 / 217** pass, including 58 dedicated attack and integrity tests |
| Live outside-in scan | `security/live_check.py` | **55 / 55** pass |
| Cross-firm access (7 roles × 20 record addresses × read/change/delete + 16 actions) | Automated tests | **All refused** |
| Secrets in the repository and its history | Pattern scan | **None found** |
| Production configuration | `manage.py check --deploy` | No errors; one intentional warning (https redirect handled by Caddy) |
| Threat model | `lexdesk/security/THREAT_MODEL.md` | 26 threats, each mapped to its controls and tests |

**Findings fixed during this assessment:** 1 critical, 5 high, 6 medium, 6 low.
**Open findings:** none critical or high. Accepted residual risks are in section 7.

---

## 2. Scope and method

**In scope:** the API (all endpoints), the web app and client portal, the public
firm websites and booking, firm self-registration, the platform console,
notifications (WhatsApp, SMS, email, calendar feed), payments, the document
vault, messaging, the Android app, and the deployment configuration (Docker
Compose, Caddy, backups).

**Out of scope for now:** the live production server and network (not yet
built), the third-party services themselves (Meta WhatsApp, Africa's Talking,
Flutterwave), physical security, and staff security practices.

**Standards:** OWASP Top 10 (2021) as the risk list; OWASP ASVS 4.0 for testable
requirements; NIST SSDF for building security into development (the tests run
on every change); STRIDE for the threat model. Uganda's Data Protection and
Privacy Act, 2019 informed the privacy checks.

**Tools:** Bandit, Semgrep, pip-audit, npm audit, OWASP ZAP, Android Lint and
`aapt`, Django's deployment checks, the project's own automated attack and
integrity tests (`apps/core/tests/test_security.py`, `test_integrity.py`,
`apps/firm/tests/test_isolation.py` and others), the live scanner
(`lexdesk/security/live_check.py`), and the load script
(`lexdesk/security/load_check.py`, plus `curl` for concurrency).

All evidence is in `lexdesk/security/reports/`.

---

## 3. Tests performed and results

### A. Can an attacker break in?

| # | Test | What was done | Result |
|---|---|---|---|
| 1 | Penetration-style testing (internal) | Automated attack tests act as an outsider, as another firm and as every role, against every record and action; OWASP ZAP attacked 154 API endpoints signed in. | **Pass** after fixes. An independent manual test is still required (section 8). |
| 2 | Vulnerability assessment | pip-audit and npm audit against every library. | **Fixed, then pass.** Next.js remote-code-execution flaw, pypdf, sharp/libvips, postcss: all upgraded or removed. **0 known vulnerabilities.** |
| 3 | Automated security scanning | Bandit, Semgrep (353 rules), OWASP ZAP (website and API), live scanner. | **Pass** after fixes (see sections 1 and 5). |
| 4 | Web application security | Headers, Content Security Policy, clickjacking, cookies, error leakage, open redirect, injection, third-party resources. | **Fixed, then pass.** Per-request nonce CSP (no inline scripts), fonts self-hosted, open redirect closed. |
| 5 | API security | Every endpoint without a session; forged, unsigned (`alg=none`) and expired tokens; cross-firm and cross-role requests; malformed IDs and bodies. | **Fixed, then pass.** Malformed IDs no longer crash anything (ZAP finding). |
| 6 | Infrastructure (configuration review) | Docker Compose and Caddy reviewed; Django `check --deploy` with production settings. | **Pass.** Only ports 80/443 exposed; database and Redis on a private network; non-root containers; secrets only in `.env`; HSTS; automatic TLS only for real firms' domains. Trivy and Nmap to run on the server. |

### B. Can people see what they should not?

| # | Test | Result |
|---|---|---|
| 7 | **Authentication**: lockout after 5 failures, rate limit, identical errors for unknown and wrong accounts, password policy, Argon2, token rotation and revocation, two-factor sign-in, deactivation, cookie flags. | **Pass** |
| 8 | **Authorisation by role**: client, receptionist, lawyer off the matter, accountant, partner behind an ethical wall. | **Pass.** Partners oversee everything **except** privileged notes and messages unless on the matter team. |
| 9 | **Privilege escalation**: making oneself admin or superuser, changing firm, adding staff, changing firm settings, reaching the platform console. | **Pass**: all refused or ignored. |
| 10 | **Data isolation between firms (BOLA/IDOR)**: 7 roles × 20 addresses × read/change/delete, 16 actions, lists and searches. | **Pass**: nothing crosses firms. |

### C. Can client information be exposed?

| # | Test | Result |
|---|---|---|
| 11 | **Data protection**: notes, messages, ID numbers, notifications, MFA secrets and provider keys checked directly in the database. | **Pass**: encrypted; secrets never returned; API responses not cached. |
| 12 | **Database security**: injection through every search, filter and ordering field; ZAP's SQL injection probes replayed on stable data. | **Pass**: answers identical; ORM with bound parameters throughout. |
| 13 | **Encryption**: files on disk, a tampered file, a backup read with the wrong keys. | **Pass**: AES-256-GCM; tampering detected and withheld; backups useless without keys. |
| 14 | **Privacy**: public pages; WhatsApp/SMS/email alert contents; third-party loading. | **Pass**: public pages show only what firms publish; alerts never carry note or message text; fonts no longer loaded from Google, so visitors aren't tracked. |
| 15 | **Audit logs**: actions recorded; direct database tampering; edits through the app and API. | **Pass**: tampering detected at the exact row; log read-only; content never logged; per firm. |

### D. Further tests specific to LexDesk

| Test | Result |
|---|---|
| **Database integrity** (14 tests): unique case numbers, logins, firm codes and domains; no duplicate client from repeat bookings; no double-booking; impossible appointments refused by the database; records cannot move between matters, clients or firms; issued invoices fixed; paid invoices cannot be voided; overpayment refused; billed time locked; document versions kept, delete only archives; notes editable only by their author; matters and clients never deleted. | **Pass** after fixing 3 gaps (appointment client and matter, next-hearing link) |
| **Android app**: Android Lint security checks; manifest of the built release app inspected; the bridge between web pages and the phone reviewed. | **Pass** after hardening: release https-only and not debuggable; no cloud or device-transfer backups; bridge answers only LexDesk's own pages and never saves installers or scripts; only the launcher screen is exported. |
| **File uploads**: disguised programs, HTML, SVG with script, `.exe`, empty and oversized files, malicious file names. | **Pass** |
| **Stored script (XSS)** in names, messages and emails. | **Pass** |
| **Webhooks**: forged WhatsApp, Flutterwave and Africa's Talking callbacks. | **Pass** |
| **Payments logic**: underpayment, wrong currency, replayed webhooks, races. | **Pass**: only a verified full payment is recorded, once. |
| **E-signatures**: signing for someone else; signing a changed document. | **Pass** |
| **Load** (development server): 20 simultaneous users, 200 requests. | Public pages median **52 ms**, signed in **85 ms**, **0 errors**. Sustained load needs the production stack (section 8). |
| **Backup and recovery**: database and vault restored from a copy; all documents decrypt; the same copy with the wrong keys. | **Pass**. Full drill on the server still to do. |
| **Secrets in the repository**: all files and history; raw scan reports with machine details kept out of git. | **Pass** |

---

## 4. Threat model

`lexdesk/security/THREAT_MODEL.md` lists what LexDesk protects (privileged
communications, documents, personal data, the diary, firm separation, money,
keys, the audit trail, availability), who might attack it (opposing parties,
competing firms, insiders, internet attackers, fraudsters, device thieves,
curious clients), the trust boundaries, and 26 threats under STRIDE. Each threat
is mapped to its mitigations and to the tests that prove them.

---

## 5. Findings and fixes

| ID | Severity | Finding | Found by | Fix |
|---|---|---|---|---|
| F-01 | **Critical** | Next.js 15.5.4: remote code execution and 20+ other advisories | npm audit | Upgraded to 15.5.28 |
| F-02 | High | pypdf 5.4.0 (reads uploaded PDFs): many known flaws | pip-audit | Upgraded to 6.20.1, minimum pinned |
| F-03 | High | sharp/libvips image libraries: known flaws | npm audit | Patched version pinned **and** unused image optimiser turned off |
| F-04 | High | Firm administrators could open the Django admin (all firms' data) | Review | Platform operators only |
| F-05 | High | Screens with their own permission rules skipped two-factor enforcement | Review | Checks restored on every screen |
| F-06 | High | Malformed IDs crashed several endpoints (HTTP 500); on the development server the crash page showed machine details | **OWASP ZAP** | Validated in 6 places, plus a global safety net (HTTP 400) |
| F-07 | Medium | Sign-in `?next=` accepted `/\evil.com` (open redirect) | Review | Strict in-app path check |
| F-08 | Medium | Web pages had no Content Security Policy | Live scan | Added |
| F-09 | Medium | CSP allowed inline scripts | **OWASP ZAP** | Fresh nonce per request with `strict-dynamic`; no inline scripts without it |
| F-10 | Medium | Google Fonts loaded without integrity check (and tracked visitors) | **OWASP ZAP** | Fonts self-hosted |
| F-11 | Medium | An appointment could be re-pointed to another client, or to another firm's matter; a hearing's next-date link to another matter | Integrity tests | Validated against firm and client |
| F-12 | Medium | Email already used at another firm could be linked to a client portal | Review | Logins never cross firms |
| F-13 | Low | Android test-build http settings applied to release builds | Android review | Release https-only (build-type configuration) |
| F-14 | Low | Android 12+ ignored the backup opt-out: session and saved briefs could go to cloud backup or a new phone | **Android Lint** | Data-extraction rules exclude everything |
| F-15 | Low | Android web-to-phone bridge answered any page and any file type | Android review | LexDesk pages only; never installers or scripts |
| F-16 | Low | Outdated `pip` in the server image | pip-audit | Upgraded at build |
| F-17 | Low | Scanned-PDF reader started `pdftoppm` by name | Bandit | Full path |
| F-18 | Low | WhatsApp "phone number ID" setting not validated | Review | Digits only |

**Not a security issue, but fixed because the scans found it:** on Android 13+,
the back gesture closed the app instead of going back a page (Android Lint).

**Investigated and dismissed:** 189 ZAP "SQL injection" alerts (live data
changing between compared requests; disproved by test); a ZAP CSRF alert on a
development-only page; Semgrep's exported-activity alert (the launcher must be
exported and accepts no input from other apps).

Earlier in the build, the same process also found and fixed: lawyers seeing
colleagues' appointments, and clients seeing court dates their lawyer had not
shared.

---

## 6. How security is built in (controls)

- **Isolation:** every query starts from the signed-in person's firm; each firm has its own website, provider keys, numbering and audit trail; suspension cuts access on the next request.
- **Privilege:** file notes and lawyer–client messages are readable only by the matter team and the client; partners oversee through counts and reports.
- **Encryption:** documents with AES-256-GCM; sensitive fields with Fernet; a keyed blind index for search; secrets never returned; TLS in production.
- **Accounts:** Argon2, 12-character minimum, lockout, rate limits, two-factor sign-in (required for staff), 10-minute tokens, rotating refresh tokens in HttpOnly cookies.
- **Browser:** strict per-request CSP, no third-party resources, framing refused, HSTS.
- **Accountability:** a tamper-evident, hash-chained audit trail.
- **Abuse limits:** rate limits on login, booking, registration, test messages and downloads; honeypots on public forms.
- **Repeatable:** attack and integrity tests on every change; scanners and scripts to rerun against any deployment.

---

## 7. Residual risks (accepted for now)

| Risk | Why accepted / what reduces it | Owner action |
|---|---|---|
| CSP allows inline **styles** | Needed by the layout; styles cannot run code; scripts are strictly nonce-only | Revisit if a style-based attack becomes practical |
| Redis has no password | Reachable only on the private Docker network | Add `requirepass` if the network layout changes |
| The search index reveals which documents share a word (never the word) | Inherent to searchable encryption; key kept outside the database | Keep `LEXDESK_SEARCH_KEY` secret and backed up offline |
| Offline court briefs live on lawyers' phones | Deleted at sign-out and two days after each hearing; excluded from backups | Firm policy: phones must have a screen lock |
| No protection from large DDoS attacks at the network edge | Rate limits and Caddy limits help with small abuse only | Put the domain behind Cloudflare at go-live |
| Client accounts are not forced to use two-factor sign-in | Optional for clients, required for staff | Revisit if firms ask |
| WebView runs JavaScript | Required for the app; bridge restricted, CSP strict, external links open outside the app | Keep the bridge minimal |

---

## 8. Still to do before going live

These need the real server, outside parties, or people.

1. **Independent penetration test** of the deployed test server by a qualified tester who did not build LexDesk (written scope, test window, report with severities, fixes retested).
2. **OWASP ZAP** again, on the server, signed in as each role, without a time cap.
3. **Trivy** scan of the built Docker images, and **Nmap** of the server, to confirm only ports 80/443 answer.
4. **Live scan** on the server: `python lexdesk/security/live_check.py https://<domain> --email <test account> --password <...>`.
5. **Load test** on the production stack: `python lexdesk/security/load_check.py https://<domain> --users 50 --seconds 60`.
6. **Restore drill** onto a spare server with the offline `.env` (DEPLOY.md, "Restore").
7. **TLS check**: SSL Labs (target A or A+).
8. **Data protection**: register with Uganda's Personal Data Protection Office; publish a privacy notice; sign data-processing agreements with each firm; review by a Ugandan data-protection lawyer.
9. **Monitoring and response**: uptime monitoring on `/api/v1/health/`; a written incident-response plan.
10. **Release signing** of the Android app with the firm's own key, kept offline.

**Release rule:** no go-live with an open critical or high finding; medium findings need a written decision.

---

## 9. How to re-run these tests

```bash
# Every change: all tests, including attack and integrity tests
cd lexdesk/backend
LEXDESK_DEBUG=1 python manage.py test

# Code and libraries
python -m bandit -r apps config -x "*/tests/*,*/migrations/*"
semgrep scan --config p/python --config p/django --config p/owasp-top-ten \
  --config p/typescript --config p/react --config p/javascript --config p/secrets lexdesk/
python -m pip_audit -l
cd ../web && npm audit --omit=dev

# Android
cd ../mobile-android && gradle lintDebug assembleRelease

# Against a running system (only systems you are authorised to test)
python lexdesk/security/live_check.py https://<domain> --email <test account> --password <password>
python lexdesk/security/load_check.py https://<domain> --email <test account> --password <password> --users 50 --seconds 60
zap.sh -cmd -quickurl https://<domain>/ -quickout zap-report.html
```

Re-run after every release, and at least monthly for the library audits:
new vulnerabilities are published all the time.
