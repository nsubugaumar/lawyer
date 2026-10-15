# LexDesk

Paperless practice management for law firms: many firms on one platform,
each in its own sealed space.

| Folder | What it is |
|---|---|
| `lexdesk/backend` | The API: Django + Django REST Framework, PostgreSQL, Celery |
| `lexdesk/web` | The public website, staff app and client portal (Next.js); installable on phones |
| `lexdesk/mobile-android` | The Android app, with offline court mode |
| `lexdesk/deploy` | Docker Compose, Caddy (automatic https), backups, and **DEPLOY.md** |

## What it does

- **Firms**: self-registration, a platform console, per-firm website, branding, domain and case numbering; firms never see each other's data.
- **Court diary**: hearings and deadlines, WhatsApp/SMS/email/in-app notices and reminders, court briefs, outcomes and next dates, offline court mode.
- **Matters**: parties, tasks, privileged file notes (matter team only, partners included only when on the team), team.
- **Clients**: register, conflict check, retainer or one-off, secure client portal.
- **Appointments**: online booking, seen only by the chosen lawyer (and front desk and partners).
- **Documents**: encrypted vault, versions, search inside documents (blind index), templates to Word, e-signatures with certificates.
- **Messages**: encrypted lawyer–client conversations.
- **Billing**: time, invoices, Mobile Money and card payments (Flutterwave).
- **Reports**: lawyer workload, retainers vs one-off clients, billed vs collected, debt ageing.
- **Security**: two-factor sign-in, Argon2 passwords, field and file encryption, a tamper-evident audit trail.

## Run it on a developer machine

```bash
# API
cd lexdesk/backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
LEXDESK_DEBUG=1 .venv/Scripts/python manage.py migrate
LEXDESK_DEBUG=1 .venv/Scripts/python manage.py seed_demo
LEXDESK_DEBUG=1 .venv/Scripts/python manage.py runserver 127.0.0.1:8000

# Website and app
cd lexdesk/web
npm install && npm run build && npm start      # http://localhost:3000
```

Tests: `LEXDESK_DEBUG=1 python manage.py test` in `lexdesk/backend`.

Going live: see [`lexdesk/deploy/DEPLOY.md`](lexdesk/deploy/DEPLOY.md).
