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
make migrate       # create tables (Alembic)
make dev-api       # http://localhost:8000/health
make dev-web       # http://localhost:5173
```

Or everything in containers: `cp .env.example .env && docker compose up --build` (web on http://localhost:8080).

## Data model

All tables from SPEC are in `backend/app/db/models.py`, with Alembic migrations in `backend/alembic/versions`.
Money is integer paise (`*_paise` columns, never floats). Timestamps are stored in UTC and shown in IST.
Counterparty names, ledger party text, narrations and account references are encrypted at the field level (AES-256-GCM, key from `FIELD_ENCRYPTION_KEY`).

## Outside services (adapters)

Every outside service sits behind an interface in `backend/app/adapters/` with a mock and a real adapter.
Each `*_PROVIDER` setting is `auto` (real when its keys are in `.env`, otherwise mock), `mock` or `real`.
`GET /meta/sandbox` reports which services are mocks so the UI shows a "Sandbox" label. Tests always force mocks.

| Service | Interface | Real adapter | Mock |
| --- | --- | --- | --- |
| Document vision, STT, TTS, LLM | `AIProvider` via `AIGateway` (fallback, model versions) | Sarvam; fallback Gemini or Anthropic | `MockAI` reads sandbox ledger PNGs that carry ground truth |
| Bank data | `AccountAggregator` | Setu AA | `MockAccountAggregator` (seeded or synthetic accounts) |
| Reverse penny drop | `PaymentGateway` | Cashfree | `MockPaymentGateway` (simulated ₹1 payment) |
| WhatsApp / SMS | `WhatsApp`, `SMS` | Meta Cloud API, MSG91 | outbox recorders, never message real people |
| KYC | `KYCProvider` | licensed PAN API | `MockKYC` |
| Files | `Storage` | S3-compatible (India region) | local disk or memory |

## Audit log

Every read, share, score and reviewer action is written with `app.modules.audit.service.record()` in the same transaction as the change.
Entries are hash-chained (`sha256(prev_hash || canonical record)`), a Postgres trigger refuses UPDATE and DELETE, and `verify_chain()` finds the first altered entry.

## Login

Phone OTP (`/auth/otp/request`, `/auth/otp/verify`) proves the phone and binds the device; a 4-digit PIN per profile (`/auth/pin/set`, `/auth/pin/verify`) opens it, because family members often share a phone.
On a bound device the PIN alone logs in (`/auth/login`). Weak PINs are refused, 5 wrong PINs lock the profile for 30 minutes, and a login from a new device is flagged for the takeover freeze.
When SMS is Sandbox the OTP is returned as `sandbox_code` so the demo can run without real messages.
