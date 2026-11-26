# Deploy guide (single VPS, India region)

Target: one Linux VPS in an Indian region (data stays in India), Docker Compose, Caddy for HTTPS.
Good options: AWS Lightsail/EC2 `ap-south-1` (Mumbai), DigitalOcean `blr1` (Bangalore), E2E Networks (Delhi/Mumbai). 2 vCPU / 4 GB RAM / 40 GB disk is enough for the prototype.

## 1. Server

```bash
# Ubuntu 24.04
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER   # log out and in again
git clone https://github.com/sandeep-sakilam/kaccha-to-pakka.git && cd kaccha-to-pakka
```

## 2. DNS

Create an `A` record for your domain (e.g. `pakka.example.in`) pointing at the VPS IP. Open ports 80 and 443.

## 3. Configuration

```bash
cp .env.example .env
```

Fill in at least: `DOMAIN`, `ACME_EMAIL`, `POSTGRES_PASSWORD`, `BACKUP_PASSPHRASE`, `SECRET_KEY`, `FIELD_ENCRYPTION_KEY` (`python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`) and `PASSPORT_SIGNING_KEY` (`make signing-key`). Keep a copy of the signing key and backup passphrase somewhere safe: losing the signing key means old passports can't be re-verified with a new key.

Outside services stay **Sandbox** until their keys are added (each `*_PROVIDER=auto`). The app shows the Sandbox badge while any service is a mock.

## 4. Start

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
docker compose -f docker-compose.prod.yml ps
curl -fsS https://$DOMAIN/api/health && curl -fsS https://$DOMAIN/api/ready
```

The API container runs `alembic upgrade head` before starting. The worker runs extraction jobs, the daily AA refresh and the presence-check scheduler.

### Demo data (Sandbox only)

The demo seed resets the database, so it refuses to run with `APP_ENV=production`. For a demo server, run it once with the development setting:

```bash
docker compose -f docker-compose.prod.yml run --rm -e APP_ENV=development -e JOBS_INLINE=true api python -m scripts.seed_demo
```

## 5. Backups and restore drill

The `backup` service writes an AES-256 encrypted `pg_dump` every 24 hours to the `backups` volume and keeps 14 days. Copy them off the server (e.g. to S3 in `ap-south-1`) with your provider's tools.

Monthly restore drill:

```bash
f=$(docker compose -f docker-compose.prod.yml exec backup sh -c 'ls -t /backups/*.enc | head -1')
docker compose -f docker-compose.prod.yml exec backup sh -c \
  "openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in $f > /tmp/r.dump && \
   createdb -h db -U ktp ktp_restore && pg_restore -h db -U ktp -d ktp_restore /tmp/r.dump && \
   psql -h db -U ktp -d ktp_restore -c 'select count(*) from audit_log'"
```

## 6. Updating

```bash
git pull && docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

## 7. Monitoring

- `GET /api/health` (liveness) and `GET /api/ready` (database + Redis).
- Set `SENTRY_DSN` for error tracking. `docker compose logs -f api worker` for logs.
- The `job_failures` table is the dead-letter queue; check it daily.
