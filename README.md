# Kaccha to Pakka: Business Trust Passport

A signed, merchant-owned proof that a small business is real and what it earns, built from independent sources that must agree.
We are an evidence and verification layer, not a lender and not a credit bureau. See `SPEC.md` for the full design.

Status of each functionality is in `PROGRESS.md`; working rules are in `CLAUDE.md`; decisions in `DECISIONS.md`.

## What Sandeep must provide

- [ ] API keys (put them in `.env`, see `.env.example` for where to get each):
  - Sarvam AI
  - Fallback AI (Gemini or Anthropic)
  - WhatsApp (Meta Cloud API or Twilio)
  - Account Aggregator sandbox (Setu or Finvu)
  - Payment gateway sandbox with reverse penny drop (Cashfree or Razorpay)
  - KYC provider (DigiLocker / PAN)
- [ ] Hosting: a VPS in an Indian region, plus a domain and DNS.
- [ ] GitHub settings: allow direct pushes to `main`, turn off the email-privacy push block, verify the email on the account.
- [ ] 50+ real ledger photos with owners' consent, for the golden test set.
- [ ] Recording the demo video, and the Hack2skill submission itself.

## Layout

- `backend/`: Python 3.12 FastAPI modular monolith (`app/modules/*`), Arq worker (`app/worker.py`), adapters for outside services (`app/adapters/*`).
- `web/`: React + Vite + TypeScript installable web app (owner, Sahayak and lender views).
- `docker-compose.yml`: API, worker, Postgres 16, Redis 7, web.
- `Makefile`: `make check` is the local quality gate (ruff, mypy, pytest, eslint, tsc, vitest); `make e2e` runs Playwright.

## Run locally

```bash
make services      # or: docker compose up -d db redis
make install
make dev-api       # http://localhost:8000/health
make dev-web       # http://localhost:5173
```

Or everything in containers: `cp .env.example .env && docker compose up --build` (web on http://localhost:8080).
