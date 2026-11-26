# Progress

Current: none; next is `feat/f08-onboarding`

Submission cut: F01 to F27 by 30 Nov 2026, 6:00 PM IST.

## Functionality backlog

- [x] F01 Monorepo layout, Docker Compose (API, worker, Postgres, Redis, web), Makefile with the quality gate (`feat/f01-foundation`)
- [x] F02 Database models and migrations for all tables in the Data model, money in paise (`feat/f02-data-model`)
- [x] F03 AI gateway and adapter interfaces with mocks for every outside service (`feat/f03-adapters`)
- [x] F04 Hash-chained audit log (`feat/f04-audit-log`)
- [x] F05 Phone OTP, PIN, sessions, device binding (`feat/f05-auth`)
- [x] F06 Consent records: grant, scope, expiry, revoke (`feat/f06-consent`)
- [x] F07 Web app shell: installable, i18n (Hindi, English), voice playback of each screen (`feat/f07-web-shell`)
- [ ] F08 Voice onboarding and business profile (`feat/f08-onboarding`)
- [ ] F09 Live-camera capture with on-phone quality check, offline queue and sync (`feat/f09-capture`)
- [ ] F10 Ledger extraction through Sarvam Vision with schema and confidence; fallback model (`feat/f10-ledger-extraction`)
- [ ] F11 Page-total checksum and owner read-back confirmation (`feat/f11-readback`)
- [ ] F12 Voice entry for unreadable ledgers (`feat/f12-voice-entry`)
- [ ] F13 Ledger-app CSV import (Khatabook, OkCredit, Vyapar) (`feat/f13-csv-import`)
- [ ] F14 UPI and bank statement PDF parsers (`feat/f14-statement-parsers`)
- [ ] F15 PDF tamper checks (`feat/f15-tamper-checks`)
- [ ] F16 Account Aggregator sandbox adapter and consent flow (`feat/f16-account-aggregator`)
- [ ] F17 Reconciliation engine with transliterated name matching and owner disambiguation (`feat/f17-reconciliation`)
- [ ] F18 Counterparty selection from money data and invite flow (`feat/f18-counterparty-invites`)
- [ ] F19 Reverse penny drop verification (sandbox or simulated gateway) (`feat/f19-penny-drop`)
- [ ] F20 Bucketed claims, GSTIN/Udyam check, money match, signed attestation (`feat/f20-attestations`)
- [ ] F21 Presence checks: geotagged photos on random days (`feat/f21-presence`)
- [ ] F22 Trust engine pillars, caps, red-flag holds, seasonality, freshness, versioning (`feat/f22-trust-engine`)
- [ ] F23 Explanations in the owner's language, with template fallback (`feat/f23-explanations`)
- [ ] F24 Passport issuance: signed credential, QR, Hindi and English PDF (`feat/f24-passport`)
- [ ] F25 Owner passport screen with coaching tips (`feat/f25-passport-ui`)
- [ ] F26 Seed data and the scripted fraud-attempt scenario (`feat/f26-demo-seed`)
- [ ] F27 Deployment files and deploy guide (submission cut, 30 Nov 2026) (`feat/f27-deploy`)
- [ ] F28 Scoped shares, expiry, revoke, owner view notifications (`feat/f28-shares`)
- [ ] F29 Lender portal: QR verify, live status, evidence view, watermark (`feat/f29-lender-portal`)
- [ ] F30 WhatsApp bot: onboarding, capture, confirmations (`feat/f30-whatsapp`)
- [ ] F31 Sahayak mode with action tagging and permissions (`feat/f31-sahayak`)
- [ ] F32 Fraud graph: cycles, collusion clusters, confirmer weighting (`feat/f32-fraud-graph`)
- [ ] F33 Sahayak anomaly monitoring and reviewer dispute queue (`feat/f33-review-queue`)
- [ ] F34 Rate and abuse limits, account-takeover freeze (`feat/f34-abuse-limits`)
- [ ] F35 Evaluation harness: golden set, red-team suite, metrics report (`feat/f35-evaluation`)
- [ ] F36 Accessibility audit fixes (WCAG 2.2 AA) and low-end phone performance budget (`feat/f36-accessibility`)
