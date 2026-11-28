# Kaccha to Pakka: Business Trust Passport

A signed, merchant-owned proof that a small business is real and what it earns, built from independent sources that must agree.
We are an evidence and verification layer, not a lender and not a credit bureau. See `SPEC.md` for the full design.

Status of each functionality is in `PROGRESS.md`; working rules are in `CLAUDE.md`; decisions in `DECISIONS.md`.

## What Sandeep must provide

- [ ] API keys (put them in `.env`, see `.env.example` for where to get each):
  - Sarvam AI
  - Fallback AI (Gemini or Anthropic)
  - WhatsApp (Meta Cloud API)
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
- `Makefile`: `make check` is the local quality gate (ruff, mypy, pytest, eslint, tsc, vitest with at least 60% line coverage, first-load size budget); `make e2e` runs Playwright.

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
On a bound device the PIN alone logs in (`/auth/login`). Weak PINs are refused, 5 wrong PINs lock the profile for 30 minutes, and a login from a new device is flagged for the takeover freeze. Several people can share one phone number: after the OTP, "Someone else on this phone? Make your own profile" creates a separate profile with its own PIN (`POST /auth/profile/new`); PINs on one number must differ, and at each login the PIN decides whose profile opens.
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

A ledger or bill capture queues `extract_ledger` (Arq worker; in-process when `JOBS_INLINE=true` or in tests). The AI gateway returns a schema-checked page; each entry keeps per-field confidence, and entries below 0.8 are marked `needs_readback`. Trader scripts or unreadable pages are marked `needs_voice`. Each entry also says whether money moved (`kind`: money, or credit_given for goods on credit) and, when written, how it was paid (`paid_by`); the read-back says it in words ("Sharma ji को पाँच सौ रुपये का सामान उधार दिया: सही?"), and the owner can change both when correcting an entry. Spoken entries understand "udhaar diya" and "ke naam likhe" as credit, "nakad" as cash and "PhonePe/GPay/UPI" as UPI; "udhaar ke 500 wapas mile" is a repayment.
The raw photo is deleted after extraction unless the owner gave `keep_originals` consent. If every AI provider is down the job is retried with backoff, then lands in `job_failures` (dead letter); the owner is told on WhatsApp (SMS if WhatsApp is down) and again when a retry succeeds.

## Page checksum and read-back

After extraction, the entries on a page must add up to the page total (by direction: received, paid or net). A mismatch puts the page on review (a `disputes` row) and its entries stop counting.
`GET /businesses/{id}/readback` lists entries the owner must hear ("Sharma ji, चार हज़ार रुपये, 12 अक्टूबर को मिले: सही?") because a field was below 0.8 confidence or the page did not add up. The owner says yes, corrects the amount with the keypad (read back in words), or rejects the entry. Once a page adds up again its review closes automatically.

## Voice entry

For pages in Mahajani or Sarrafi script, or handwriting the AI can't read, the owner reads entries aloud (`/voice-entry/:businessId`). Speech-to-text gives a transcript; `extraction/voice_parse.py` pulls out party, amount (digits or words like "chaar hazaar", "dedh lakh"), received/paid and date by rules; the entry is read back in words for a yes or no. After two misses the screen switches to large-button entry (keypad + received/paid). Saved entries are stored as confirmed by the owner, linked to the unreadable photo.

## Ledger-app CSV import

`POST /businesses/{id}/imports/csv` reads Khatabook ("You Gave / You Got"), OkCredit ("Type, Amount") and Vyapar ("Type, Received/Paid") exports, detected from the header row (title rows above it are skipped). Unknown layouts are refused with a reason; the same file twice is refused; entries are stored with confidence 1.0 and need no read-back. Khatabook and OkCredit are credit books: in a customer statement "You Gave" (OkCredit "Credit") is credit given and "You Got" is money received; in a Khatabook supplier statement (title or "Supplier Name" column) "You Gave" is money paid and "You Got" (goods bought on credit, no money moved) is left out.

## Statement PDFs

`POST /businesses/{id}/statements` reads bank and UPI statement PDFs with pdfplumber. Known layouts are parsed by fixed rules; an unknown layout is read by the LLM only if its running balance then adds up row by row, else it is rejected with the reason. Scanned PDFs are refused. Transactions are stored once (by UTR, or by date/amount/balance), so overlapping statements never double-count; every UPI ID becomes a counterparty node. `app/sandbox/statements.py` generates sandbox statements.

## PDF tamper checks

Every statement PDF runs `statements/tamper.py`: editing-tool producers (iLovePDF, Word, Sejda, Canva…), changes appended after the first save, a few characters in a different font, malformed or repeated UTRs, running-balance breaks and closing-balance mismatch put it **on hold** (status `on_hold` plus a reviewer dispute); unknown producers, later modification dates and out-of-order dates are recorded as warnings. A hold pauses the passport; it is never offset by good evidence elsewhere.

## Account Aggregator

"Link bank" records our `aa_fetch` consent (12 months) and, by default, `monthly_refresh`, then asks the AA for consent. In Sandbox the AA app is replaced by an in-app approve/reject page (`/sandbox/aa/approve/:handle`, labelled Sandbox; the API route exists only while the AA adapter is the mock). Approved data is stored once per transaction, so re-fetches never double-count. The worker runs a daily cron that refreshes links older than 30 days; revoking stops both the AA consent and the refresh. If the AA is down the owner is pointed to the PDF fallback.

## Reconciliation

`reconciliation/engine.py` matches counted ledger entries (high-confidence or owner-confirmed) to money data (excluding statements on hold): same direction, exact amount, dates within ±3 days, and names that agree across scripts (`names.py` transliterates Devanagari, drops honorifics like "ji" and words like "traders", and uses rapidfuzz token-set similarity). A nameless entry matches only when it is the single candidate both ways (weaker rule). Unclear names become owner questions ("Is Pappu the same as PRADEEP KUMAR?"), remembered as aliases. A party's entries on nearby days can add up to one payment (many-to-one). The match rate by value feeds the Records pillar. Since F49 it also strips Marwari honorifics ("Jain sa") and words like "cloth house", learns aliases from the owner's own history (the same ledger name meeting the same payer on 3+ unique exact-amount matches, never against the owner's answer), and matches one ledger entry paid in two instalments by the same payer. On the synthetic evaluation set recall went from 0.613 to 0.812 with precision 1.0.

Credit books (F58). Many shops record only udhaar: goods given on credit, and the customer's later repayments. A ledger entry has a `kind`: `money` (cash actually received or paid) or `credit_given` (goods on credit; no money moved, so it is never looked for in the bank). Money entries may say how they were paid (`paid_by`: cash, UPI or bank); entries written as cash are not looked for in the bank either. Credit is matched per customer as a running balance: a bank or UPI payment from that customer (sure name or learned alias only), or a repayment written in the ledger, clears the oldest dues first, up to 90 days after each due. Payments that clear whole dues exactly ("September and October together") are applied first and are strong matches; part payments are applied after them and count half; a payment larger than everything owed is a spot purchase, not a repayment. When a written repayment and a bank payment from the same customer have the same amount within 3 days, they are counted once. On the synthetic credit-book set (60 customers paying on time, late with two months together, in part, in cash or not at all, with spot-purchase and unrelated-payer decoys) repayments are found with precision 0.976 and recall 1.0; the two false positives are small UPI purchases by customers who still owed money, which no rule can tell from a part payment.

Payer identity (F59). Customers often pay from a relative's phone. The name check gives one of six verdicts: *owner* (the owner said this payer is this party), *no* (the owner said it is not), *sure* (names agree, e.g. "Sharma ji" and AMIT SHARMA), *maybe* (they share a word but differ, e.g. "Rakesh Sharma" and AMIT SHARMA: the owner is asked), *differs* (no word in common: asked once, only when it is the single candidate both ways, never matched on its own) and *unknown* (no name on one side, e.g. a number-only UPI ID such as 98••••2345@ybl, which is matched only when it is the single candidate both ways and otherwise asked about with the number masked). Names that only rhyme ("Sharma ji" and PRIYA VERMA) now score at most 40. An owner's answer is remembered by name and by the payment's UPI ID, so the son's phone is known next month even if its name changes. Matches that rest on the owner's answer get their own rule (`owner_confirmed`); when they carry more than half of the matched value, the records score is capped at 60 and the lender is shown the share.

Cash sales (F60). Spot sales paid by UPI need no ledger: they already feed the money pillar. Cash sales cannot be checked directly, so the passport never pretends to: cash deposited at the bank counts as sales at half weight (and is shown to the lender as its own line), and the owner may tell the day's total sales by voice or typing (`/businesses/{id}/daily-sales`, one total per day, up to 31 days back, read back in words). A month is checked only when the owner told at least 8 of its days: their average day is compared with the bank's average day that month (UPI and bank payments in plus cash deposited). It agrees when it is between 0.8 and 3 times the bank's (cash comes on top, but a shop cannot be mostly invisible). Only when two or more months agree and none fail does it add a small, capped 5 points to the records pillar; months below or far above the bank are shown as gaps. Daily totals are erased with the account.

Registration check (F61). A Udyam or GST number the owner gives is a claim; the government register's answer is evidence. The KYC provider (the same licensed provider and keys as the PAN check) looks the number up: Udyam first (it carries the commencement date declared to the government), else the GSTIN. The register's legal or trade name must match the business or the owner (proprietors are registered in their own name). Verified adds 10 points to presence and a reason; a number registered to a different business puts the passport on hold (red-team case "Borrowed Udyam / GSTIN"); cancelled is a warning; not found is shown as a gap. If the provider is down, the previous answer is kept. `POST /businesses/{id}/registration/check` asks again. The real adapter expects the provider's `/api/v1/gstin/verify` and `/api/v1/udyam/verify` (legal_name, trade_name, status, registration_date, commencement_date); confirm the paths with the chosen provider.

Verified business age (F62). The age the owner says ("since 2009") used to give up to 30 presence points on its own. Now age counts fully only as far as it is proven: by the government register's registration date, by the commencement date on a Udyam registration made at least 6 months earlier (a date on record before this passport, not made up for it), or by the first payment in bank data that came straight from the bank (Account Aggregator; PDFs do not count). Claimed age beyond that counts at half. When the claim is more than a year beyond the proof, the passport says so ("You said 17 years in business; papers and bank data show 1"), and the lender sees both numbers and the source.

Address proof (F63). The owner can photograph, with the live camera only, a recent electricity, water, gas or phone bill, or a shop licence (Shop and Establishment, FSSAI, trade licence). The AI gateway reads it into a strict schema (`DocumentExtraction`: type, holder name, address, issue date, valid until, number, confidence; Sarvam, Gemini and Anthropic adapters plus the mock), with the same fallback as ledger pages. Rules decide whether it counts (`extraction/documents.py`): the name must be the business's, the owner's or the registered name; the address must be the shop's area (or its city when no address is known); a bill must be at most 90 days old and a licence unexpired. A bill in the landlord's name is common, so a different name is not counted but is not a fraud signal; the owner is told why on WhatsApp. An accepted document adds 10 presence points, and an accepted licence's issue date can prove business age (F62). The photo is deleted after reading unless the owner chose to keep originals. Lenders see which documents matched, never their numbers.

Supplier credit (F64). Goods bought on credit from a supplier are entries of kind `credit_taken` (read by the AI, said aloud as "Gupta Traders se 12000 ka maal udhaar liya", chosen as "Bought on credit" when correcting, or a Khatabook supplier statement's "You Got"). The credit matcher runs a second time for suppliers: payments out to that supplier (bank, or written in the ledger) clear the oldest purchases first within 90 days, exact clearings before part payments. "Udhaar ke 12000 chukaye" is a payment, not new credit. The share paid through the bank joins the records pillar (weighted by entries), with a reason in Hindi and English, and lenders see goods bought on credit, the share paid by bank and in cash, the usual days to pay suppliers, and what is still owed.

Women helpers only (F65). The Sahayak directory could already be filtered to women helpers (F31), but nothing stopped another helper being added to a woman-owned business. A business now has `women_helpers_only`, on by default for women-owned businesses (and switched on for existing ones by migration 0017). While it is on, only helpers registered as women can be added (others are refused with `women_helpers_only`), and the directory shows women helpers. Only the owner can change it; a helper cannot.

Passport history (F66). Assessments are immutable, so every passport issued can be shown exactly as it was. `GET /businesses/{id}/passport/history` lists up to the last 12, oldest first (issued at, band, confidence, status, rules version). The owner's passport screen and the lender's view show the band over time ("12 Sep D → 14 Oct C → 27 Nov B") once there are two or more; the lender gets only dates, bands and status, whatever the share's scope.

Demo seed (F67). `make seed` now also shows F58-F66: Sharma Kirana has a verified Udyam registration (17 years proven by its commencement date), an accepted electricity bill, weekly cash deposits, supplier credit paid by UPI and a passport history C → B; Meena Namkeen has an udhaar khata with three credit customers (on time, two months together, part paid), 75 days of spoken daily sales that agree with the bank, and "only women helpers" on. Bands stay B, B, C and Raju's fraud scene is unchanged. `docs/demo-script.md` lists optional scenes for them.

UI refresh (F68). A small design system in `tailwind.config.js` and `src/index.css`: a brand green scale, a soft canvas background, white cards (`.card`), one input style (`.field`), pills, section titles, and one colour per band (`lib/bands.ts`, all passing WCAG AA with white text). Shared parts carry it to every page: a compact sticky header, screen titles with the Listen pill, buttons with list-row ("tile") and "do this now" ("alert") variants, and a refined keypad. Home is a business hero card with the passport button, then actions grouped by kind; the passport, lender and QR-verify pages show a coloured band tile, status pills and reasons with icons. System fonts only, so nothing extra downloads (first load stays about 126 KB gzipped of the 300 KB budget); all labels are unchanged.

## Counterparty invites

`GET /businesses/{id}/counterparties/top` lists the top 5 counterparties by value over the last 6 months of money data (statements on hold excluded), with masked UPI ID, bank payee name and supplier/customer role. The owner cannot add or swap names; they only give a phone number per partner (`POST /businesses/{id}/invites`). The invite goes out on WhatsApp (SMS fallback) in the confirmer's language with a `/confirm/{token}` link. The owner's own number is refused, and one number routed for several partners is flagged. The public invite view shows only the claim being confirmed.

## Reverse penny drop

The confirmer opens `/confirm/{token}` (no login) and pays ₹1 from their UPI app to our verification UPI ID (`POST /invites/{token}/penny-drop` gives the UPI link). `POST /invites/{token}/penny-drop/check` compares the payer UPI ID (exact) and bank-registered name (≥ 80 similarity) with the counterparty in the owner's payments: a match proves control; anything else rejects the confirmation, opens a reviewer dispute and red-flags the business. The ₹1 is always refunded. In Sandbox a simulated gateway stands in, and the page lets you choose which UPI ID "pays".

## Attestations

After the ₹1 proof the confirmer answers four bucketed questions (supplier/customer, years trading, typical monthly value, payment behaviour) and may add a GSTIN or Udyam (format and checksum checked, business name compared with the bank-registered name). `attestations/claims.py` compares the claimed relationship and monthly-value bucket with the actual flows between the two accounts over 12 months: a match is a full confirmation (weight 1.0 with an ID, 0.7 without); a mismatch is a discrepancy (weight 0.2) that lowers the Network pillar. The attestation is saved against the confirmer's own profile, signed with Ed25519 (`core/signing.py`, `make signing-key`) and expires after 6 months. A Sahayak or field officer can confirm a cash-only partner in person (separate evidence type, weight 0.5).

## Presence checks

The first shop-front photo with good GPS sets the shop's home location. With `presence_location` consent, `POST /businesses/{id}/presence/start` schedules 4 checks on random days and hours over the next 28 days; their dates stay hidden from the owner. The worker sends each request when due (WhatsApp/SMS) and marks it missed after 24 hours. A presence photo passes when it arrives in the window with GPS accuracy ≤ 100 m, within 150 m of the shop, and is not a re-sent photo. `POST /sandbox/presence/{id}/now` brings the next check forward for demos (not in production). Where the bank data includes the UPI merchant location (`AAAccount.merchant_geo`), it is stored on the business: a presence photo more than 500 m from it fails that check, shop photos 0.5–5 km away are a warning, and more than 5 km away puts the passport on hold (`shop_far_from_merchant_location`).

## Trust engine

`trust/features.py` gathers a feature snapshot; `trust/rules.py` (`RULES_VERSION = 2026.11-r2`) turns it into a band A–E (or **U**: unverified / insufficient evidence), a confidence level and reasons. No AI is involved.

| Pillar | Built from |
| --- | --- |
| Money (40%) | AA or PDF transactions, last 12 months: active months, weekly regularity, volume, seasonality (same month last year when there are 13+ months), freshness; round-trips are netted out; cash deposited at the bank (narration such as BY CASH / CASH DEP / CDM, or the Account Aggregator's CASH mode) counts at half weight, since the source of the cash is not known |
| Records (20%) | match rate by value of independent ledgers against money (credit given and cash entries left out); share of credit given that came back through the bank (part payments count half); the two are weighted by their number of entries. A ledger that mirrors the bank statement counts once (as money); a ledger with more cash entries than checkable ones is capped at 40; one where more than half the matched value rests on the owner's own answers about names is capped at 60 |
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

## Real AI smoke test

`make real-ai-smoke` (`scripts/real_ai_smoke.py`) calls the real Sarvam adapters (Vision on ledger pages, Bulbul TTS, Saaras STT, Sarvam-105B) and the fallback model once, and writes every result or exact error to `backend/eval/real_ai_smoke.md`. Keys can be placeholders (`SARVAM_API_KEY=proxy`) when a network proxy injects the real key. Latest run (27 Nov 2026, cloud session): 0/8 calls succeeded, because `api.sarvam.ai` is not allowed by the session's network policy and no network secret was configured for Gemini; see the report.

## Right to erase

"Delete my account" (My permissions screen; `POST /auth/erase` with the PIN and the word `DELETE`) revokes every share, passport, consent, helper link and the Account Aggregator link; deletes stored photos and files, ledger entries, bank transactions, matches and presence records; removes sessions, devices, notifications and WhatsApp state; and anonymises what must stay (the business row, immutable assessments, invites with third parties' phones, disputes, the user row whose phone becomes a non-identifying tag). The hash-chained audit log stays, with ids only, and still verifies. The same phone number can sign up again as a new person.
