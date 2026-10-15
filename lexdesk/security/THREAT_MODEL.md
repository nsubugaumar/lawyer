# LexDesk threat model

What is valuable in LexDesk, who might come after it, how, and what stops
them. Method: list the assets and the attackers, draw the trust boundaries,
then walk each boundary with STRIDE (Spoofing, Tampering, Repudiation,
Information disclosure, Denial of service, Elevation of privilege).

Reviewed: 15 October 2026. Review again after any major feature and at
least once a year.

---

## 1. What we protect (assets)

| Asset | Why it matters | Worst case |
|---|---|---|
| **Privileged communications**: file notes, lawyer–client messages, strategy | Protected by legal professional privilege; disclosure can lose a case and breach the Advocates Act | Opponent or media reads a firm's strategy |
| **Client documents**: pleadings, evidence, contracts, IDs | Confidential; often sensitive personal data | Identity theft, leaked evidence, blackmail |
| **Client personal data**: names, phones, emails, ID numbers, addresses | Data Protection and Privacy Act, 2019 | Regulatory penalty, loss of trust |
| **Court diary** | A missed date is the commonest cause of negligence claims | Hearing missed, case struck out |
| **Firm separation** | Each firm trusts LexDesk to keep it apart from its competitors | One firm sees another's clients and cases |
| **Money**: invoices, payments, payment provider keys | Direct financial loss | Payments diverted, fraudulent receipts |
| **Accounts and keys**: passwords, MFA secrets, vault/field/search keys, provider tokens | Keys to everything above | Full compromise |
| **Audit trail** | Proof of who did what, for regulators and courts | Wrongdoing hidden |
| **Availability** | Lawyers rely on it on the morning of a hearing | Unable to reach the brief in court |

## 2. Who might attack (threat actors)

| Actor | Motive | Capability |
|---|---|---|
| **Opposing party or their agent** | See the other side's strategy and evidence | Moderate; may hire help; phishing |
| **A competing firm on LexDesk** | Poach clients, see cases | Has a genuine account; knows the system |
| **A curious or disgruntled insider** (staff, ex-staff) | Look at matters they are not on; take files when leaving | Valid credentials; knows record IDs |
| **Opportunistic internet attackers** | Data to sell, ransom, crypto-mining | Automated scanners, credential stuffing, known exploits |
| **Fraudsters** | Divert or fake payments; impersonate the firm on WhatsApp/SMS | Social engineering, forged webhooks |
| **Device thief** | Whatever is on a lawyer's phone | Physical access to an unlocked or stolen phone |
| **A client trying to see more** | Their own file's internal notes, other clients | Valid portal account |

## 3. Trust boundaries and entry points

```
 Internet ──► Caddy (TLS, certificates) ──► Web app (Next.js) ──► API (Django) ──► PostgreSQL
    │                                          │                        │──► Vault (encrypted files)
    │                                          │                        └──► Redis ◄── Worker / Beat
    │                                          │                                         │
    ├── Browsers: staff, clients, public       └── Android app (WebView)                 ├──► WhatsApp (Meta)
    ├── Webhooks: Meta, Flutterwave, Africa's Talking  ──────────────────────► API      ├──► SMS (Africa's Talking)
    └── Calendar apps (private feed URL)  ───────────────────────────────────► API      ├──► Email (SMTP)
                                                                                         └──► Flutterwave
```

Entry points: the public website and booking; firm registration; sign-in, MFA,
activation and password reset; the authenticated API; webhooks; the calendar
feed; file uploads; the Android bridge; the Django admin (platform operators
only); the server itself (SSH, Docker).

## 4. Threats and mitigations (STRIDE)

| # | Threat | Category | Mitigations in LexDesk | Tested by |
|---|---|---|---|---|
| T1 | Guessing or stuffing passwords | Spoofing | Argon2, 12+ chars, common-password list, lockout after 5 failures, rate limit 10/min, MFA required for staff | `test_auth`, `test_security.AuthenticationTests`, live scan |
| T2 | Stolen session token reused | Spoofing | 10-minute access tokens; refresh in HttpOnly SameSite=Strict cookie; rotation and blacklisting; password change revokes all | `test_auth`, `AuthenticationTests` |
| T3 | Forged JWT (`alg=none`, tampered) | Spoofing | Signature required (HS256 with separate key) | `AuthenticationTests`, live scan |
| T4 | Phishing link bouncing to a fake site after sign-in | Spoofing | Strict in-app `?next=` check | live scan |
| T5 | Forged webhook "payment succeeded" / "message delivered" | Spoofing, Tampering | Signatures (Meta HMAC), secret hash (Flutterwave), and every payment verified directly with Flutterwave for amount and currency | `test_modules.OnlinePaymentTests`, `test_notifications` |
| T6 | Firm B reads Firm A's records by changing an ID (BOLA/IDOR) | Information disclosure | Every query scoped to the person's firm; random UUIDs; per-firm reference numbers | `test_isolation`, `test_security.CrossFirmAccessTests` (7 roles × all records) |
| T7 | Partner or colleague reads privileged notes/messages | Information disclosure | Notes and messages only for the matter team and client; ethical walls; partners oversee via counts | `PartnerOversightTests`, `MessagingTests`, `RoleAccessTests` |
| T8 | Client sees internal notes, other clients, unshared court dates | Information disclosure | Client queries filtered to own record and shared items | `RoleAccessTests`, `test_notifications` |
| T9 | Database or backup stolen | Information disclosure | Documents AES-256-GCM; notes, messages, IDs, secrets encrypted; blind search index; keys kept outside the database and backed up offline | `DataProtectionTests`, `BackupAndKeyTests` |
| T10 | Privileged content leaks via WhatsApp/SMS/email history | Information disclosure | Alerts carry only "you have a message/date"; never note or message text | `MessagingTests` |
| T11 | SQL injection | Tampering, Disclosure | ORM only, parameterised; input treated as data | `InjectionTests`, ZAP |
| T12 | Stored script (XSS) in names, notes, messages | Tampering | React escaping; per-request nonce CSP with `strict-dynamic`; email autoescaping | `InjectionTests`, ZAP |
| T13 | Malicious upload (program disguised as PDF, SVG with script) | Tampering, Elevation | Extension allow-list plus magic-byte check; SVG refused; size limits; files never served from a public path; downloads sandboxed by CSP | `UploadTests` |
| T14 | Path or header injection through file names | Tampering | Names sanitised; RFC-compliant Content-Disposition | `InjectionTests` |
| T15 | Changing history (backdated notes, edited invoices, deleted files) | Tampering, Repudiation | Notes editable by author only; issued invoices fixed; versions immutable; delete archives; matters/clients never deleted | `test_integrity` |
| T16 | Covering tracks by editing the audit log | Repudiation | Append-only, hash-chained audit; tamper detected at the exact row; ORM refuses edits/deletes | `AuditTrailTests` |
| T17 | Lawyer escalates to partner/admin, or to another firm | Elevation | Role and firm not writable by the user; team management for partners/manager only; platform console for operators only; Django admin for operators only | `PrivilegeEscalationTests` |
| T18 | Moving a record into another firm's matter/client | Tampering | Every foreign key checked against the firm; items cannot move between matters | `test_integrity`, `test_isolation` |
| T19 | Brute-forcing booking, sign-up, test messages (spam, SMS cost) | Denial of service | Rate limits (booking 5/h, sign-up 5/h, tests 10/h, anon 60/min); honeypots | `test_modules`, live scan |
| T20 | Flooding the server | Denial of service | Gunicorn workers, request size limits, Caddy; **edge DDoS protection recommended** (Cloudflare) | load test (partial) |
| T21 | Known vulnerable library exploited | Elevation | pip-audit, npm audit, Bandit, Semgrep, ZAP; patched Next.js, pypdf, sharp | reports in `security/reports` |
| T22 | Stolen phone with saved court briefs | Information disclosure | Saved briefs deleted at sign-out and 2 days after the hearing; app relies on the phone's screen lock | manual review |
| T23 | Malicious page abusing the Android app's bridge | Elevation | Bridge answers only LexDesk's own pages; only our API paths; never saves installers or scripts; no file access; external links open outside the app | Android lint, manual review |
| T24 | Certificates obtained for a domain we don't control | Spoofing | Caddy on-demand TLS asks LexDesk; only active firms' domains approved | `firm/views.TlsAskView` |
| T25 | Server compromise via exposed services | Elevation | Only 80/443 published; DB and Redis on private network; non-root containers; secrets only in `.env` | config review; Trivy/Nmap to do on server |
| T26 | Secrets leaked in the code repository | Disclosure | `.gitignore`; no secrets in git history (scanned) | secret scan |

## 5. Residual risks (owned)

Listed in `SECURITY.md` §6: inline styles allowed by CSP; Redis without a
password on the private network; blind-index word co-occurrence; data on
lawyers' phones; edge DDoS; optional MFA for clients.

## 6. What would change this model

A native mobile app with its own storage; letting firms share matters with
each other; an AI feature reading documents; storing documents with a cloud
provider outside Uganda; new payment providers. Revisit before building any.
