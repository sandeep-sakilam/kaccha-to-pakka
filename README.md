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
`consent.service.require()` guards every step that needs permission; `/consents/revoke-purpose` withdraws in one call. In the app, "My permissions" (`/consents`) lists every consent with why, dates and status; each is withdrawn with one tap or by saying "consent wapas lo" / "withdraw consent" (with what it is for, or its number). Withdrawing stops what it allowed at once: the lender link, the helper's access, or the bank link and its monthly refresh. `/consents/notice` returns the consent screen text (what we collect, why, who sees it, how to delete) in Hindi or English for read-aloud.

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

## Account Aggregator

"Link bank" records our `aa_fetch` consent (12 months) and, by default, `monthly_refresh`, then asks the AA for consent. In Sandbox the AA app is replaced by an in-app approve/reject page (`/sandbox/aa/approve/:handle`, labelled Sandbox; the API route exists only while the AA adapter is the mock). Approved data is stored once per transaction, so re-fetches never double-count. The worker runs a daily cron that refreshes links older than 30 days; revoking stops both the AA consent and the refresh. If the AA is down the owner is pointed to the PDF fallback.

## Reconciliation

`reconciliation/engine.py` matches counted ledger entries (high-confidence or owner-confirmed) to money data (excluding statements on hold): same direction, exact amount, dates within ±3 days, and names that agree across scripts (`names.py` transliterates Devanagari, drops honorifics like "ji" and words like "traders", and uses rapidfuzz token-set similarity). A nameless entry matches only when it is the single candidate both ways (weaker rule). Unclear names become owner questions ("Is Pappu the same as PRADEEP KUMAR?"), remembered as aliases. A party's entries on nearby days can add up to one payment (many-to-one). The match rate by value feeds the Records pillar.

## Counterparty invites

`GET /businesses/{id}/counterparties/top` lists the top 5 counterparties by value over the last 6 months of money data (statements on hold excluded), with masked UPI ID, bank payee name and supplier/customer role. The owner cannot add or swap names; they only give a phone number per partner (`POST /businesses/{id}/invites`). The invite goes out on WhatsApp (SMS fallback) in the confirmer's language with a `/confirm/{token}` link. The owner's own number is refused, and one number routed for several partners is flagged. The public invite view shows only the claim being confirmed.

## Reverse penny drop

The confirmer opens `/confirm/{token}` (no login) and pays ₹1 from their UPI app to our verification UPI ID (`POST /invites/{token}/penny-drop` gives the UPI link). `POST /invites/{token}/penny-drop/check` compares the payer UPI ID (exact) and bank-registered name (≥ 80 similarity) with the counterparty in the owner's payments: a match proves control; anything else rejects the confirmation, opens a reviewer dispute and red-flags the business. The ₹1 is always refunded. In Sandbox a simulated gateway stands in, and the page lets you choose which UPI ID "pays".

## Attestations

After the ₹1 proof the confirmer answers four bucketed questions (supplier/customer, years trading, typical monthly value, payment behaviour) and may add a GSTIN or Udyam (format and checksum checked, business name compared with the bank-registered name). `attestations/claims.py` compares the claimed relationship and monthly-value bucket with the actual flows between the two accounts over 12 months: a match is a full confirmation (weight 1.0 with an ID, 0.7 without); a mismatch is a discrepancy (weight 0.2) that lowers the Network pillar. The attestation is saved against the confirmer's own profile, signed with Ed25519 (`core/signing.py`, `make signing-key`) and expires after 6 months. A Sahayak or field officer can confirm a cash-only partner in person (separate evidence type, weight 0.5).

## Presence checks

The first shop-front photo with good GPS sets the shop's home location. With `presence_location` consent, `POST /businesses/{id}/presence/start` schedules 4 checks on random days and hours over the next 28 days; their dates stay hidden from the owner. The worker sends each request when due (WhatsApp/SMS) and marks it missed after 24 hours. A presence photo passes when it arrives in the window with GPS accuracy ≤ 100 m, within 150 m of the shop, and is not a re-sent photo. `POST /sandbox/presence/{id}/now` brings the next check forward for demos (not in production).

## Trust engine

`trust/features.py` gathers a feature snapshot; `trust/rules.py` (`RULES_VERSION = 2026.11-r2`) turns it into a band A–E (or **U**: unverified / insufficient evidence), a confidence level and reasons. No AI is involved.

| Pillar | Built from |
| --- | --- |
| Money (40%) | AA or PDF transactions, last 12 months: active months, weekly regularity, volume, seasonality (same month last year when there are 13+ months), freshness; round-trips are netted out |
| Records (20%) | match rate by value of independent ledgers against money; a ledger that mirrors the bank statement counts once (as money) |
| Network (25%) | confirmed attestations by weight (3 full = 100); discrepancies subtract |
| Presence (15%) | business age, shop-front photo, random presence checks passed, in-person visit |

Caps: band A needs all four pillars ≥ 50, B needs three; no AA data → best C; nothing verified → U; under 3 months → Low confidence. Red flags (tamper signal, round-tripping, failed confirmation, holder-name mismatch) put the assessment **on hold** without changing the band. Money data older than 120 days makes it **stale**. Assessments are immutable (Postgres trigger), store their rules version, model versions, feature snapshot and inputs hash, and `GET /assessments/{id}/verify` recomputes them.

## Explanations

`trust/explain.py` turns an assessment's structured reasons into the owner's language: a headline ("Your passport is strong because 82% of your ledger matches your bank payments and 3 trading partners confirmed you."), top positives, gaps and what would raise it. The LLM (Sarvam-105B) may rephrase each reason, but its output must have exactly one line per reason with exactly the same numbers; otherwise, or when it is down, fixed Hindi/English templates are used. `GET /businesses/{id}/explanation?language=hi`.

## Passport

`POST /businesses/{id}/passport` assesses afresh and issues a W3C Verifiable Credential (`BusinessTrustPassport`) signed with Ed25519 (`DataIntegrityProof`, `eddsa-jcs-2022`), valid for up to 60 days (less if the money data is ageing). It contains the band, confidence, pillar scores, reason codes and rules version, never phone numbers or partner names. The QR code encodes `/v/{id}#{token}`: a compact signed summary a lender can verify offline with the public key from `/.well-known/ktp-keys.json`; live status comes from `GET /passports/{id}/status` (valid, on_hold, expired, revoked, superseded). The owner can withdraw the passport (`POST /businesses/{id}/passport/revoke`, "Withdraw my passport" with a spoken confirmation); QR checks and lender links then show "revoked". `GET /businesses/{id}/passport.pdf?language=hi|en` renders the passport with WeasyPrint and bundled Noto Sans Devanagari (OFL).

## Owner passport screen

`/passport/:businessId` shows the band as a large coloured tile, its label, confidence, status (Active / On hold / Expired) and valid-until date in IST, the headline, reasons and gaps, and coaching tips each with a "Do it now" button to the right screen (link bank, ask partners, add ledger, shop photo). It shows the verification QR, PDF downloads in Hindi and English, the Sandbox badge when relevant, and "not a loan: the lender decides". The Listen button reads the headline, gaps and tips aloud.

## Demo data

`make seed` resets the **local** database (refused in production; the script itself needs `--reset-database`) and loads three fictional Indore businesses (Sharma Kirana → B, Meena Namkeen → B, Ansari Tailors with a PDF only → C) and the scripted fraud attempt: a friend posing as a supplier is rejected and Raju General Store's passport is issued on hold. See `docs/demo-script.md` for logins and the scene-by-scene demo.

## Deploy

`docker-compose.prod.yml` runs Caddy (automatic HTTPS, security headers), the API (migrates on start), the worker, Postgres 16, Redis 7 and a daily encrypted backup job on one Indian-region VPS. Step-by-step guide: `docs/deploy.md`.

## Sharing with lenders

`POST /businesses/{id}/shares` (owner only) creates a link for one named lender with a scope (`summary`, or `evidence` for summary plus evidence) and an expiry (default 30 days, max 90), backed by a `share_lender` consent. The lender opens `/l/{token}`; every view is logged and the owner is notified ("SBI Rajwada branch viewed your passport"). Partner names, UPI IDs and phone numbers are never in the lender view: partners appear as "verified supplier, trading 5+ years". Revoking stops the link (HTTP 410) and the consent at once.

## Lender portal

- `/lender`: scan a passport QR (BarcodeDetector camera) or paste a link.
- `/v/{id}#{token}`: verifies the QR signature in the browser with the Ed25519 public key (`tweetnacl`, key cached for offline use), then fetches live status. A changed QR shows "Signature NOT valid".
- `/l/{token}`: the shared scope only, with a diagonal watermark "Shared with {lender} · {date} · do not forward"; evidence scope adds monthly money totals, ledger match rate, partner confirmations as labels, presence checks, evidence hashes and flags. `GET /l/{token}/passport.pdf` gives a watermarked PDF. Every view is logged and shown to the owner.

## WhatsApp bot

`POST /whatsapp/webhook` (Meta Cloud API, signature checked when real; `GET` handles the verify challenge). Conversation state is kept per phone in `wa_conversations`; repeated webhook deliveries are handled once. Flow: "Hi" → language buttons → 4-digit PIN (WhatsApp already proves the number) → consent text with Yes/No → name, what you sell, since when, where (text or voice note, each read back for Yes/No) → profile. Then: send a ledger photo (extracted, then low-confidence entries read back with Yes/No buttons), "check" for pending entries, "passport" for the band, headline, tips and verify link. SMS is used when WhatsApp is down.

## Sahayak (helper) mode

A helper registers (`/sahayak/register`, optional women's directory). The owner adds them by phone with chosen permissions (capture, voice entry, read-back, CSV, statements, invites, passport) backed by a `sahayak_help` consent, and can remove them at once. Sahayaks see only owners who added them and only while allowed; sharing, consents and bank linking stay owner-only. Every Sahayak action is tagged: evidence carries `sahayak_user_id` and audit entries use `sahayak:{id}`. Screens: `/sahayak` (helper dashboard) and `/helpers/:businessId` (owner).

## Fraud graph

`fraud/graph.py` (NetworkX, nightly worker job and on demand): **payment cycles** between known businesses (A → B → C → A within 10 days per hop, amounts within 5%) and **collusion rings** (3+ businesses confirming each other, all joined in the last year, with little trade outside the cluster) become `graph_flags` that put every member's passport on hold. **Confirmer standing** (0.3–1.2) scales each confirmation's weight in the Network pillar: it grows with the confirmer's age and number of independent partners and drops to 30% once any of their confirmations is shown false.

## Review queue and Sahayak monitoring

Disputes come from the system (tamper holds, page totals, failed confirmations, fraud-graph flags, Sahayak anomalies, random audits) and from people: an owner can contest a ledger line, a confirmation or the result (`POST /businesses/{id}/disputes`), a confirmer can contest through their invite link (`POST /invites/{token}/dispute`, followed with `GET /invites/{token}/disputes`). In the app: "Disagree with something?" on Home (`/disputes/:businessId`: pick the result, a ledger entry or a confirmation, type or say the reason, follow the status) and "Something wrong? Tell us" on the confirm page. Reviewers (role `reviewer`) work `/review`: every queue view, case view and decision is written to the audit log. Clearing a held statement makes it count again; upholding a false confirmation marks it `disproved` (the confirmer's standing drops everywhere); upholding a Sahayak anomaly suspends that Sahayak. Nightly monitoring flags Sahayaks for high volume, high failure rate, one device used for many businesses, or shop photos of different businesses clustered within 25 m, and opens random audits of 5% of Sahayak-created evidence.

## Abuse limits and takeover freeze

`abuse/limits.py` keeps fixed-window counters in Redis (in-process if Redis is down): OTP per phone (5/hour) and per network (30/hour), photos per device (200/day), Sahayak actions (300/day), invites per business (10/day), ₹1 attempts per invite (3/day), a confirmer may confirm at most 10 different businesses a month, lender views per link (60/hour). Over the limit → HTTP 429 with a spoken-friendly message. A login from a new device freezes sharing for 24 hours (no new shares, existing lender links answer 423 "paused") and the owner is told at once.

## Evaluation

`make eval` runs `app/evaluation/harness.py` on a scratch database and writes `backend/eval/report.md` and `report.json`: field-level extraction accuracy and exact-amount match per provider (golden set in `backend/eval/golden/`, synthetic until real pages are added), reconciliation precision/recall on synthetic businesses with known ground truth, the red-team suite (one case per fraud-table row plus stale passport; currently 13/13 caught), speech-to-text WER (when transcripts are added), AI cost per passport, and band distribution by business type, season and owner gender. With Sandbox models the numbers show the harness works, not real model accuracy.

## Accessibility and performance

WCAG 2.2 AA checks (axe-core) and a slow-3G / 4× CPU Moto G4 run are part of `make e2e`; the first-load budget (300 KB gzipped, currently ~120 KB) is part of `make check`. Details in `docs/accessibility.md`.

## Identity

Onboarding asks for the owner's full name "as on the bank account" and, optionally, the PAN. `POST /auth/identity` calls the KYC adapter (Sandbox mock by default): a matching PAN stores the **registered** name (`kyc_status = verified`); a PAN of another name stores the registered name and holds the passport (`kyc_name_mismatch`); without a PAN the name is `self_declared`. The trust engine compares the Account Aggregator account-holder name with this name; a mismatch (`holder_name_mismatch`) puts the passport on hold, so nobody can build a passport on someone else's bank account.
