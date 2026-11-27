# Evaluation report

Generated 2026-11-27T20:32:57+00:00 · **Sandbox models**: numbers show the harness works, not real accuracy.

## Ledger extraction

Golden set: 10 pages (synthetic sandbox)

| Provider | Date | Party | Amount (exact) | Direction | Failures |
| --- | --- | --- | --- | --- | --- |
| mock | 1.0 | 1.0 | 1.0 | 1.0 | 0 |
| mock | 1.0 | 1.0 | 1.0 | 1.0 | 0 |

## Reconciliation

Precision 1.0, recall 0.812 over 10 synthetic businesses (tp 195, fp 0, fn 45); 10 unclear names sent to the owner as questions.

## Credit books (udhaar)

Repayments found in the bank: precision 0.976, recall 1.0 over 60 synthetic customers (tp 82, fp 2, fn 0). Patterns: cash 18, on_time 16, partial 8, two_together 13, unpaid 5.

## Red-team

Catch rate **13/13** (100%)

| Attack | Defence | Caught |
| --- | --- | --- |
| Edited bank statement PDF | producer metadata + balance continuity | yes |
| AI-generated or staged ledger photos | ledger only counts when it reconciles with real money | yes |
| Friend poses as supplier | system-selected partner + reverse penny drop | yes |
| Round-tripping | cycle detection + net-flow netting | yes |
| Collusion ring of new accounts | graph clusters + confirmer weighting | yes |
| Photo of someone else's shop | random-day presence checks with GPS | yes |
| Identity theft | KYC + account-holder name match | yes |
| Sahayak creating fake businesses | per-Sahayak anomaly monitoring | yes |
| Account takeover | new-device 24-hour share freeze | yes |
| Prompt injection inside an image | strict schema; scoring is code | yes |
| Forged passport shown to a lender | Ed25519 signature + live status | yes |
| Lender leaking or misusing data | scoped expiring shares, no PII | yes |
| Stale passport of an abandoned business | freshness decay + expiry | yes |

## Speech to text

{'status': 'not run: add eval/golden/transcripts.json with audio files'}

## AI cost per passport

₹10.7 (per-call prices are estimates in AI_COST_RUPEES; replace with invoice data)

## Band distribution (same evidence strength)

- category:kirana: {'D': 4}
- category:namkeen: {'D': 2}
- category:tailor: {'D': 4}
- category:vegetables: {'D': 2}
- gender:female: {'D': 6}
- gender:male: {'D': 6}
- seasonal:False: {'D': 6}
- seasonal:True: {'D': 6}

Not measured by the harness: time from first message to first passport (needs field sessions); unaided completion with 5 shopkeepers
