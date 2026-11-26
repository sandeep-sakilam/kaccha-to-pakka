# Decision log

One line per decision: date | question | choice | reason.

2026-11-26 | Arq or Celery for jobs? | Arq | Async-native, small, uses the Redis we already run; enough for a solo builder.
2026-11-26 | Sync or async SQLAlchemy? | Sync SQLAlchemy with FastAPI sync endpoints | Simpler to debug and test; throughput is not a bottleneck for the prototype.
2026-11-26 | Field-level encryption for amounts too? | Encrypt names, party text, narration and account refs; keep amounts and VPAs plain | Amounts and VPAs are needed for SQL joins and graph queries; names are the most identifying fields. Revisit with KMS in production.
2026-11-26 | Extra columns beyond the spec table list? | Add a few (status, meta, roles, women_owned, is_sandbox, idempotency_key) | Needed by later flows; spec fields are all present.
2026-11-26 | How are real vs mock adapters chosen? | Provider setting auto/mock/real, default auto (real only when keys present) | Spec: real turns on when keys are in .env; tests force mock.
2026-11-26 | Real adapter endpoints can't be verified without keys | Implement against public API docs with model names and URLs in .env; covered by MockTransport tests only | External services never block the build; verify once Sandeep adds keys.
