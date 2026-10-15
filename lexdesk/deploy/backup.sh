#!/bin/sh
# Nightly backup of the database and the document vault.
#
#   crontab -e
#   30 2 * * * /opt/lexdesk/deploy/backup.sh >> /var/log/lexdesk-backup.log 2>&1
#
# Documents are already encrypted in the vault, and the database's sensitive
# columns are encrypted too, so these files are safe to copy off the server
# (to another region, or an external drive). They are useless without the
# keys in .env, which must be backed up separately and kept offline.

set -eu
cd "$(dirname "$0")"
. ./.env

STAMP=$(date +%Y-%m-%d_%H%M)
DEST=${LEXDESK_BACKUP_DIR:-/var/backups/lexdesk}
KEEP_DAYS=${LEXDESK_BACKUP_DAYS:-30}
mkdir -p "$DEST"

docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "$DEST/db_$STAMP.dump"
docker compose run --rm --no-deps -v "$DEST":/backup --entrypoint "" api \
  tar -czf "/backup/vault_$STAMP.tar.gz" -C /vault .

# Prove the dump is readable before trusting it.
docker compose exec -T db pg_restore --list < "$DEST/db_$STAMP.dump" > /dev/null

find "$DEST" -name 'db_*.dump' -mtime +"$KEEP_DAYS" -delete
find "$DEST" -name 'vault_*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date) backup ok: $DEST/db_$STAMP.dump, vault_$STAMP.tar.gz"
