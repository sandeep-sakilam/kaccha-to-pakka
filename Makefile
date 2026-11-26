# Local quality gate and dev helpers. `make check` must pass before every PR.
signing-key:  ## print a new Ed25519 passport signing key for .env
	$(BACKEND) uv run python -c "from app.core.signing import new_key_b64; print(new_key_b64())"

eval:  ## run the evaluation harness (scratch DB ktp_eval) and write backend/eval/report.md
	-sudo -u postgres psql -q -c "CREATE DATABASE ktp_eval OWNER ktp;"
	$(BACKEND) DATABASE_URL=postgresql+psycopg://ktp:ktp@localhost:5432/ktp_eval JOBS_INLINE=true uv run python -m scripts.run_eval

seed:  ## reset the local database and load the Sandbox demo businesses
	$(BACKEND) uv run python -m scripts.seed_demo

migrate:  ## apply database migrations
	$(BACKEND) uv run alembic upgrade head

.PHONY: migrate help services install check check-backend check-web e2e dev-api dev-web dev-worker up down

export UV_SYSTEM_CERTS := 1
unexport UV_NATIVE_TLS

BACKEND := cd backend &&
WEB := cd web &&

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1

services:  ## start local Postgres and Redis (cloud session)
	-service postgresql start
	-service redis-server start

db-setup:  ## create local role and databases (dev, test, e2e)
	-sudo -u postgres psql -q -c "CREATE USER ktp WITH PASSWORD 'ktp' CREATEDB;"
	-for d in ktp ktp_test ktp_e2e; do sudo -u postgres psql -q -c "CREATE DATABASE $$d OWNER ktp;"; done

install:
	$(BACKEND) uv sync
	$(WEB) npm ci --no-audit --no-fund

fix:  ## auto-fix lint and formatting
	$(BACKEND) uv run ruff check --fix -q . ; uv run ruff format -q .
	$(WEB) npx eslint --fix . || true

check: check-backend check-web

check-backend:
	$(BACKEND) uv run ruff check .
	$(BACKEND) uv run ruff format --check .
	$(BACKEND) uv run mypy app tests
	$(BACKEND) uv run pytest

check-web:
	$(WEB) npx eslint .
	$(WEB) npx tsc -b --noEmit
	$(WEB) npx vitest run

e2e:
	$(WEB) npx playwright test --trace off

dev-api:
	$(BACKEND) uv run uvicorn app.main:app --reload --port 8000

dev-worker:
	$(BACKEND) uv run arq app.worker.WorkerSettings

dev-web:
	$(WEB) npm run dev

up:
	docker compose up -d --build

down:
	docker compose down
