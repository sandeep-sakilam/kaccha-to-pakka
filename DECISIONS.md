# Decision log

One line per decision: date | question | choice | reason.

2026-11-26 | Arq or Celery for jobs? | Arq | Async-native, small, uses the Redis we already run; enough for a solo builder.
2026-11-26 | Sync or async SQLAlchemy? | Sync SQLAlchemy with FastAPI sync endpoints | Simpler to debug and test; throughput is not a bottleneck for the prototype.
2026-11-26 | Field-level encryption for amounts too? | Encrypt names, party text, narration and account refs; keep amounts and VPAs plain | Amounts and VPAs are needed for SQL joins and graph queries; names are the most identifying fields. Revisit with KMS in production.
2026-11-26 | Extra columns beyond the spec table list? | Add a few (status, meta, roles, women_owned, is_sandbox, idempotency_key) | Needed by later flows; spec fields are all present.
2026-11-26 | How are real vs mock adapters chosen? | Provider setting auto/mock/real, default auto (real only when keys present) | Spec: real turns on when keys are in .env; tests force mock.
2026-11-26 | Real adapter endpoints can't be verified without keys | Implement against public API docs with model names and URLs in .env; covered by MockTransport tests only | External services never block the build; verify once Sandeep adds keys.
2026-11-26 | Play Integrity on a web app? | Record device_attestation as web_unattested with device id; real attestation comes with an Android wrapper or WhatsApp capture | Web browsers can't call Play Integrity; ledgers only score when they reconcile with money, so the risk stays bounded.
2026-11-26 | How long may an offline capture wait? | Up to 7 days between capture and upload | Weak networks need slack; older captures are refused as not live.
2026-11-26 | OkCredit 'Credit' rows move no cash | Import them as 'out' entries like the app shows them; reconciliation only credits entries that match real money | Keeps the owner's record intact; independence rules stop it adding unbacked strength.
2026-11-26 | Which statement layouts to support first? | Two sandbox layouts (SBI-style bank, PhonePe-style UPI) with fixed rules, plus LLM for unknown layouts gated by balance continuity | Real bank PDFs vary; new layouts get a parser once Sandeep collects samples. Password-protected PDFs are refused for now.
