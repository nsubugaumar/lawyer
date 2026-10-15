# OWASP ZAP 2.17.0: authenticated API scan, 15 October 2026

- **Target:** LexDesk API (development server, http://127.0.0.1:8000), signed in as a partner.
- **Coverage:** 154 API addresses imported from the API description (OpenAPI); passive scan, then active attack scan with 4 threads for 40 minutes (the time cap was reached).
- **Raw report:** not committed. It contains copies of development-only debug pages, which hold details of the test computer. It is available on request.

| Risk | Alert | Instances | Verdict | Action |
|---|---|---|---|---|
| High | SQL Injection (boolean-based) | 189 | **False positive.** ZAP compared answers to `…'1'='1` and `…'1'='2` on live lists (audit log, time sheet) that change with every request, including ZAP's own. All queries go through Django's ORM with bound parameters. On stable data, the same probes return byte-identical answers. | Regression test `MalformedInputTests.test_boolean_sql_injection_probes_get_identical_answers` |
| High | Server Side Include | 36 | **Real bug, different cause.** The `/messages/?matter=` parameter crashed (HTTP 500) on a malformed id. On the development server, the crash page displayed environment variables, which ZAP's rule matched. Production has crash pages switched off, but the crash itself was a defect. | Fixed in 6 places with `apps/core/ids.as_uuid` (messages, documents, notifications, team, activation, calendar invites), plus a global safety net for invalid values (HTTP 400). Regression test `MalformedInputTests.test_bad_ids_in_paths_queries_and_bodies_never_crash` |
| Medium | Absence of Anti-CSRF Tokens | 1 | **Not applicable.** It was flagged on a development HTML page; the API authenticates with bearer tokens, not cookies. The only cookie (refresh token) is SameSite=Strict and path-scoped. | None |
| Low | Application Error Disclosure | 2 | Same cause as the Server Side Include alert (development crash page). | Fixed, as above |
| Low | Server header reveals version | Systemic | Development server (`WSGIServer/CPython`). In production, Caddy strips the `Server` header. | None for production |
| Info | Modern Web Application | 1 | Informational. | None |

**Retest after the fixes:** the same malformed requests return 400/403/404; no 5xx. All 217 backend tests pass.
