# Testing LexDesk on Render (free)

For trying LexDesk out, not for real client work. The free database is
deleted after 30 days, uploaded documents disappear when a service sleeps,
and timed reminders do not run. For real use, follow DEPLOY.md.

## 1. Make the keys (on your computer)

    python lexdesk/deploy/generate_keys.py

Keep the output open. You need five of its lines in step 3. Ignore
POSTGRES_PASSWORD and WHATSAPP_WEBHOOK_VERIFY_TOKEN; Render handles the
database password itself.

## 2. Create the Blueprint

Render dashboard > **New** > **Blueprint** > connect the GitHub repository
`lawyer`. Render reads `render.yaml` and plans three things: `lexdesk-db`,
`lexdesk-api` and `lexdesk-web`.

## 3. Fill in the values Render asks for

| Setting | Value |
|---|---|
| `LEXDESK_SECRET_KEY`, `LEXDESK_JWT_SIGNING_KEY`, `LEXDESK_VAULT_KEYS`, `LEXDESK_FIELD_KEYS`, `LEXDESK_SEARCH_KEY` | from step 1, everything after the `=` |
| `LEXDESK_WEB_URL` and `LEXDESK_CORS_ORIGINS` | `https://lexdesk-web.onrender.com` |
| `LEXDESK_API_ORIGIN` | `https://lexdesk-api.onrender.com` |

If Render had to give a service a different name (it adds letters when a
name is taken), use the real addresses shown on each service's page, then
**Manual Deploy** the web service so it is rebuilt with the right API address.

## 4. Sign up

1. Open the web address and register a firm.
2. The activation email is not sent: open **lexdesk-api > Logs** and copy the
   activation link printed there.
3. Staff must set up two-factor sign-in, so have an authenticator app ready
   (Google Authenticator, Microsoft Authenticator, Authy).

Use one firm. The `onrender.com` addresses cannot give each firm its own
sub-domain, so LexDesk shows the only firm there is.

## Things to expect

- After 15 idle minutes each service sleeps. The first visit can take one to
  two minutes while the web app and then the API wake up.
- Uploaded documents are kept on the service's own disk and are lost when it
  sleeps or redeploys.
- Free services get 750 hours a month between them. Two services kept busy
  all month would run out; light testing will not.
