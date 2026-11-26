#!/bin/sh
# Daily encrypted database backup (AES-256, passphrase from BACKUP_PASSPHRASE), 14 days kept.
# Never writes an unencrypted dump. Restore drill: see docs/deploy.md.
set -eu
command -v openssl >/dev/null || (apt-get update -qq && apt-get install -y -qq openssl >/dev/null)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="/backups/ktp-$stamp.dump.enc"
pg_dump -h db -U "${POSTGRES_USER:-ktp}" -d "${POSTGRES_DB:-ktp}" -Fc \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "$out"
find /backups -name 'ktp-*.dump.enc' -mtime +14 -delete
echo "backup ok $out"
