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
make db-setup      # role ktp and databases ktp, ktp_test, ktp_e2e
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

## Consent

One consent row per purpose (`build_passport`, `aa_fetch`, `monthly_refresh`, `share_lender`, `keep_originals`, `presence_location`, optional `model_training`), each with a scope and expiry.
`consent.service.require()` guards every step that needs permission; `/consents/revoke-purpose` withdraws in one call. `/consents/notice` returns the consent screen text (what we collect, why, who sees it, how to delete) in Hindi or English for read-aloud.

## Web app

Installable web app (manifest + service worker via `vite-plugin-pwa`), Hindi and English with `i18next` (`web/src/i18n/*.json`), Hindi by default.
Every screen uses `<Screen title spoken={[...]}>`, which adds a Listen button: server voice (Sarvam Bulbul via `POST /voice/tts`) when real, the phone's own speech engine in Sandbox or offline. Amounts are read in words (`rupeesInWords`).
A yellow "Sandbox" badge shows whenever any outside service is a mock. First-load JS is about 73 KB gzipped (budget: 300 KB).

## Onboarding

Login (phone keypad, OTP, PIN) → consent screen read aloud → voice interview (name, what you sell, since when, where; each answer is read back for a yes or no, with icon choices and typing as fallbacks) → optional Udyam/GSTIN (format and checksum checked) → profile.
`POST /onboarding/interpret` turns a transcript or audio into a field with deterministic rules (`business/interview.py`), never an AI guess. `make e2e` runs the full flow against a real API on the `ktp_e2e` database.

## Capture

Live camera only (no gallery picker). The phone checks blur (Laplacian variance), darkness, over-exposure and glare before saving (`web/src/lib/quality.ts`), compresses to JPEG, stamps time and GPS, and queues the photo in IndexedDB (`web/src/lib/queue.ts`). The queue syncs when the network returns, every upload carrying an `Idempotency-Key`.
The API (`POST /businesses/{id}/captures`) repeats the cheap checks, refuses photos older than 7 days or with old camera EXIF dates, flags the same photo sent twice, stores the file and a SHA-256 hash, and logs it.

## Ledger extraction and jobs

A ledger or bill capture queues `extract_ledger` (Arq worker; in-process when `JOBS_INLINE=true` or in tests). The AI gateway returns a schema-checked page; each entry keeps per-field confidence, and entries below 0.8 are marked `needs_readback`. Trader scripts or unreadable pages are marked `needs_voice`.
The raw photo is deleted after extraction unless the owner gave `keep_originals` consent. If every AI provider is down the job is retried with backoff, then lands in `job_failures` (dead letter); the owner is told on WhatsApp (SMS if WhatsApp is down) and again when a retry succeeds.

## Page checksum and read-back

After extraction, the entries on a page must add up to the page total (by direction: received, paid or net). A mismatch puts the page on review (a `disputes` row) and its entries stop counting.
`GET /businesses/{id}/readback` lists entries the owner must hear ("Sharma ji, चार हज़ार रुपये, 12 अक्टूबर को मिले: सही?") because a field was below 0.8 confidence or the page did not add up. The owner says yes, corrects the amount with the keypad (read back in words), or rejects the entry. Once a page adds up again its review closes automatically.

## Voice entry

For pages in Mahajani or Sarrafi script, or handwriting the AI can't read, the owner reads entries aloud (`/voice-entry/:businessId`). Speech-to-text gives a transcript; `extraction/voice_parse.py` pulls out party, amount (digits or words like "chaar hazaar", "dedh lakh"), received/paid and date by rules; the entry is read back in words for a yes or no. After two misses the screen switches to large-button entry (keypad + received/paid). Saved entries are stored as confirmed by the owner, linked to the unreadable photo.

## Ledger-app CSV import

`POST /businesses/{id}/imports/csv` reads Khatabook ("You Gave / You Got"), OkCredit ("Type, Amount") and Vyapar ("Type, Received/Paid") exports, detected from the header row (title rows above it are skipped). Unknown layouts are refused with a reason; the same file twice is refused; entries are stored with confidence 1.0 and need no read-back.

## Statement PDFs

`POST /businesses/{id}/statements` reads bank and UPI statement PDFs with pdfplumber. Known layouts are parsed by fixed rules; an unknown layout is read by the LLM only if its running balance then adds up row by row, else it is rejected with the reason. Scanned PDFs are refused. Transactions are stored once (by UTR, or by date/amount/balance), so overlapping statements never double-count; every UPI ID becomes a counterparty node. `app/sandbox/statements.py` generates sandbox statements.

## PDF tamper checks

Every statement PDF runs `statements/tamper.py`: editing-tool producers (iLovePDF, Word, Sejda, Canva…), changes appended after the first save, a few characters in a different font, malformed or repeated UTRs, running-balance breaks and closing-balance mismatch put it **on hold** (status `on_hold` plus a reviewer dispute); unknown producers, later modification dates and out-of-order dates are recorded as warnings. A hold pauses the passport; it is never offset by good evidence elsewhere.
