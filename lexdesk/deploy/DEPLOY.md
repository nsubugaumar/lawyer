# LexDesk: deploying, testing, going live

This guide takes LexDesk from this folder to a live service that law firms
use every day. It has three stages:

1. **Deploy** to a server (about an hour).
2. **Test** with one or two friendly firms (two to four weeks).
3. **Go live** for everyone.

---

## What you need first

| What | Why | Where |
|---|---|---|
| A server | Runs LexDesk | Any Ubuntu 24.04 VPS with **4 GB RAM, 2 CPUs, 80 GB disk**, e.g. Hetzner, DigitalOcean, AWS Lightsail, or a Ugandan data centre (Raxio, Africa Data Centres) if clients' data must stay in Uganda |
| A domain | Your address, e.g. `lexdesk.co.ug` | Any registrar; `.ug` domains via a Uganda registrar |
| An email account that can send | Activation links, reminders | Google Workspace, Microsoft 365, Zoho, Brevo, Mailgun |
| WhatsApp Business (per firm, or one for the platform) | WhatsApp reminders | business.facebook.com → WhatsApp Manager |
| Africa's Talking account | SMS | account.africastalking.com |
| Flutterwave account (per firm) | Mobile Money and card payments | dashboard.flutterwave.com |

Each firm can connect its **own** WhatsApp, SMS sender and Flutterwave account
in *Settings › Firm settings*, so money goes straight to the firm and messages
carry the firm's name. The platform-wide values in `.env` are only defaults.

---

## Stage 1: Deploy

### 1. Point your domain at the server

In your domain's DNS, create:

| Type | Name | Value |
|---|---|---|
| A | `@` | your server's IP |
| A | `www` | your server's IP |
| A | `*` | your server's IP (so every firm gets `name.lexdesk.co.ug`) |

A firm that wants its own domain (e.g. `www.nsc-advocates.co.ug`) points an
A record at the same IP and enters the domain in *Firm settings › Firm
profile*. The https certificate is then issued automatically.

### 2. Prepare the server

```bash
ssh root@your-server
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

### 3. Copy LexDesk and configure it

Copy the `lexdesk` folder to `/opt/lexdesk` (with `scp -r`, or from a private
Git repository). Then:

```bash
cd /opt/lexdesk/deploy
cp .env.example .env
nano .env                       # domain, email account, firm-signup choice
python3 generate_keys.py >> .env
```

**Back up `.env` now**, offline: a password manager and a USB stick in a safe.
The keys in it cannot be recovered. Without them, encrypted documents and
notes in any backup are unreadable. That is the point of encryption.

### 4. Start it

```bash
docker compose up -d --build
docker compose ps               # all services "running" / "healthy"
docker compose logs -f api      # migrations, then "Listening at: http://0.0.0.0:8000"
```

Open `https://lexdesk.co.ug`. The first visit takes a few seconds while the
certificate is issued.

### 5. Create your platform owner account

```bash
docker compose exec api python manage.py createsuperuser
```

Sign in with it at `https://lexdesk.co.ug/login`. You will be asked to set up
two-factor sign-in. You land on **Law firms**, the platform console.

### 6. Nightly backups

```bash
chmod +x /opt/lexdesk/deploy/backup.sh
crontab -e
# add:
30 2 * * * /opt/lexdesk/deploy/backup.sh >> /var/log/lexdesk-backup.log 2>&1
```

Copy `/var/backups/lexdesk` off the server regularly (rclone to another
provider, or an external drive). Test a restore once a month (below).

### 7. WhatsApp webhook and template (once per WhatsApp number)

In WhatsApp Manager:

1. **Message template** → create `lexdesk_notice`, category *Utility*,
   language *English*, body:

   ```
   {{1}}

   {{2}}

   {{3}}
   ```

2. **Configuration → Webhook**: the callback URL and verify token are shown in
   *Firm settings › WhatsApp connection* (or, for the platform-wide number,
   `https://lexdesk.co.ug/api/v1/notifications/whatsapp/webhook/` with
   `WHATSAPP_WEBHOOK_VERIFY_TOKEN` from `.env`). Subscribe to **messages**.

---

## Stage 2: Test (user acceptance)

Invite one or two firms you know. Ask the managing partner to register at
`https://lexdesk.co.ug/register`. Go through this list with them; tick each
item only when it worked for a real person on a real phone.

### Firm and team
- [ ] Partner registers the firm, receives the activation email, sets a password.
- [ ] Partner sets up two-factor sign-in with an authenticator app.
- [ ] Partner adds a lawyer, a paralegal and a receptionist; each activates.
- [ ] Partner uploads the logo, chooses colours, sets office hours and social media links; the website shows them.
- [ ] A second firm cannot see anything of the first (try opening a link copied from the first firm).

### Clients and matters
- [ ] Receptionist registers a client; the client receives the portal activation email.
- [ ] Mark one client "On retainer" with a monthly fee and one "One-off".
- [ ] Lawyer opens a matter, adds a colleague to the team.
- [ ] Partner sees the matter but **not** its file notes or messages (unless added to the team).

### Court diary and reminders
- [ ] Lawyer adds a hearing: WhatsApp, email and in-app notice arrive within a minute.
- [ ] Move the hearing: everyone is told the new and old date.
- [ ] Reminders arrive at 7 days, 1 day and 2 hours (set a hearing a little over 2 hours ahead to test the last one).
- [ ] Morning agenda arrives at 06:30 on a working day.
- [ ] Open the court brief, write a note, record "Adjourned" with a next date.
- [ ] Save a week's briefs for court, turn on airplane mode, open them from *Saved for court*.
- [ ] Subscribe to the calendar link in Google or Apple Calendar.

### Documents
- [ ] Upload a PDF and a Word file; search for a word inside each.
- [ ] Draft an engagement letter from a template; open it in Word.
- [ ] Ask the client to sign; client signs on a phone; the certificate appears.

### Clients' side
- [ ] Book a consultation on the website; the chosen lawyer, and only that lawyer, is notified.
- [ ] Client messages the lawyer from the portal; the lawyer replies.
- [ ] Issue an invoice; client pays in **test mode**, then (once connected) a small live Mobile Money payment.

### Phone app
- [ ] Install the Android app; sign in; WhatsApp, phone and social links open their apps.
- [ ] Open a document; upload a photo from the phone.

Write down everything that confuses people, not only what breaks.

---

## Stage 3: Go live

- [ ] Every Stage 2 box ticked, with at least one firm using it daily for two weeks.
- [ ] Email sending from your own domain, with SPF and DKIM set (ask your email provider), so activation emails do not land in spam.
- [ ] WhatsApp template approved; at least one live WhatsApp reminder received.
- [ ] Africa's Talking sender ID approved, and the account topped up.
- [ ] Flutterwave account verified (KYC) and switched to live keys.
- [ ] `.env` backed up offline in two places.
- [ ] A restore tested (below).
- [ ] Uptime monitoring on `https://lexdesk.co.ug/api/v1/health/` (UptimeRobot, BetterStack: free).
- [ ] Terms of use and privacy notice published. Register with the **Personal Data Protection Office** under Uganda's Data Protection and Privacy Act, 2019.
- [ ] Android app rebuilt with the live address and released (see `mobile-android/README.md`).

---

## Everyday operations

| Task | Command (in `/opt/lexdesk/deploy`) |
|---|---|
| See status | `docker compose ps` |
| Follow logs | `docker compose logs -f api worker beat` |
| Update to a new version | copy the new code, then `docker compose up -d --build` |
| Restart | `docker compose restart` |
| Make old documents searchable | `docker compose exec api python manage.py rebuild_search_index` |
| Verify the audit trail is intact | `docker compose exec api python manage.py verify_audit_chain` |
| Backup now | `./backup.sh` |

### Restore (practise this)

```bash
docker compose stop api worker beat
docker compose exec -T db pg_restore -U lexdesk -d lexdesk --clean --if-exists < /var/backups/lexdesk/db_YYYY-MM-DD_HHMM.dump
docker compose run --rm --no-deps -v /var/backups/lexdesk:/backup --entrypoint "" api \
  sh -c "rm -rf /vault/* && tar -xzf /backup/vault_YYYY-MM-DD_HHMM.tar.gz -C /vault"
docker compose start api worker beat
```

The `.env` from the original server is needed. Its keys decrypt the data.
