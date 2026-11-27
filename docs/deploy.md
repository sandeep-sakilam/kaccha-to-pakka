# Deploy guide: fresh Ubuntu 24.04 VPS (India region)

One server runs everything with Docker Compose: Caddy (HTTPS), the web app, the API, the background worker, PostgreSQL 16, Redis 7 and a daily encrypted backup. Follow the steps in order; each ends with a check.

## 0. What you need

- A VPS in an Indian region with Ubuntu 24.04, 2 vCPU, 4 GB RAM, 40 GB disk. Good options: AWS Lightsail/EC2 `ap-south-1` (Mumbai), DigitalOcean `blr1` (Bangalore), E2E Networks.
- A domain you control, e.g. `pakka.example.in`.
- About 30 minutes.

## 1. Point the domain at the server

At your DNS provider, create an `A` record: `pakka.example.in → <server IP>`. Wait until it resolves:

```bash
dig +short pakka.example.in
```

Check: it prints the server IP.

## 2. Log in and prepare the server

```bash
ssh root@<server IP>
```

```bash
apt-get update && apt-get -y upgrade
```

```bash
apt-get install -y docker.io docker-compose-v2 git ufw python3
```

```bash
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

Check: `docker compose version` prints a version (v2).

## 3. Get the code

```bash
git clone https://github.com/sandeep-sakilam/kaccha-to-pakka.git /opt/ktp && cd /opt/ktp
```

## 4. Create `.env` and generate the keys

```bash
cp .env.example .env
```

Generate the secrets (each command prints one value):

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
```

```bash
python3 -c "import os, base64; print('FIELD_ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
```

```bash
python3 -c "import os, base64; print('PASSPORT_SIGNING_KEY=' + base64.b64encode(os.urandom(32)).decode())"
```

```bash
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24)); print('BACKUP_PASSPHRASE=' + secrets.token_urlsafe(24))"
```

Open `.env` (`nano .env`) and set:

| Setting | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DOMAIN` | `pakka.example.in` |
| `ACME_EMAIL` | your email (for the HTTPS certificate) |
| `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `PASSPORT_SIGNING_KEY`, `POSTGRES_PASSWORD`, `BACKUP_PASSPHRASE` | the values printed above |
| Provider keys (`SARVAM_API_KEY`, …) | only those you have; every other service stays Sandbox |


The API and the worker refuse to start in production if `SECRET_KEY`, `FIELD_ENCRYPTION_KEY` or `PASSPORT_SIGNING_KEY` is missing, malformed or a development default.

**Copy the signing key, the field-encryption key and the backup passphrase to a password manager now.** Without the field key, encrypted names can't be read; without the signing key, you can't keep issuing passports under the same public key; without the passphrase, backups can't be restored.

## 5. Build the images on the server

```bash
docker compose -f docker-compose.prod.yml --env-file .env build
```

Check: it ends without errors (first build takes 5–10 minutes).

## 6. Start

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

```bash
docker compose -f docker-compose.prod.yml ps
```

Check: `db`, `redis`, `api`, `worker`, `caddy`, `backup` are `running` (`api` shows `healthy`); `web` shows `exited (0)`: it only copies the web app into place and stops, which is expected. The API runs database migrations on start. Caddy gets the HTTPS certificate on the first request (needs ports 80/443 open and DNS from step 1).

## 7. Smoke test

```bash
bash deploy/smoke.sh https://pakka.example.in
```

Check: `8 passed, 0 failed`. If HTTPS fails, read `docker compose -f docker-compose.prod.yml logs caddy`.

## 8. Demo data (Sandbox), only for a demo server

The demo seed **erases the database** and loads the three fictional Indore businesses and the fraud scene. It never calls real AI, never sends messages, and seeded businesses always use the simulated payment gateway even when real payment keys are set. Do not run it on a server with real users.

```bash
docker compose -f docker-compose.prod.yml --env-file .env run --rm -e APP_ENV=development api python -m scripts.seed_demo --reset-database
```

Check: it prints the three businesses with their bands (Kirana B, Namkeen B, Tailor C) and the fraud link. Logins and scenes are in `docs/demo-script.md`.

## 9. Backups and the monthly restore drill

The `backup` service writes an AES-256 encrypted `pg_dump` every 24 hours to the `backups` volume and keeps 14 days. Copy them off the server (e.g. to S3 in `ap-south-1`).

```bash
docker compose -f docker-compose.prod.yml exec backup sh -c 'ls -lh /backups'
```

Restore drill (into a separate database, never over the live one):

```bash
docker compose -f docker-compose.prod.yml exec backup sh -c 'f=$(ls -t /backups/*.enc | head -1); openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$f" > /tmp/r.dump && createdb -h db -U "$POSTGRES_USER" ktp_restore && pg_restore -h db -U "$POSTGRES_USER" -d ktp_restore /tmp/r.dump && psql -h db -U "$POSTGRES_USER" -d ktp_restore -c "select count(*) from audit_log"'
```

## 10. Updating

```bash
cd /opt/ktp && git pull && docker compose -f docker-compose.prod.yml --env-file .env up -d --build && bash deploy/smoke.sh https://pakka.example.in
```

## 11. Monitoring

- `GET /api/health` (liveness) and `GET /api/ready` (database and Redis).
- Logs: `docker compose -f docker-compose.prod.yml logs -f api worker`.
- The `job_failures` table is the dead-letter queue; check it daily.
