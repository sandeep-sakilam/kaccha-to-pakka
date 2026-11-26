# Local quality gate and dev helpers. `make check` must pass before every PR.
migrate:  ## apply database migrations
	$(BACKEND) uv run alembic upgrade head

.PHONY: migrate help services install check check-backend check-web e2e dev-api dev-web dev-worker up down

BACKEND := cd backend &&
WEB := cd web &&

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1

services:  ## start local Postgres and Redis (cloud session)
	-service postgresql start
	-service redis-server start

install:
	$(BACKEND) uv sync
	$(WEB) npm ci --no-audit --no-fund

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
