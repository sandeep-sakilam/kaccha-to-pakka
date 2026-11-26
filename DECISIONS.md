# Decision log

One line per decision: date | question | choice | reason.

2026-11-26 | Arq or Celery for jobs? | Arq | Async-native, small, uses the Redis we already run; enough for a solo builder.
2026-11-26 | Sync or async SQLAlchemy? | Sync SQLAlchemy with FastAPI sync endpoints | Simpler to debug and test; throughput is not a bottleneck for the prototype.
2026-11-26 | Field-level encryption for amounts too? | Encrypt names, party text, narration and account refs; keep amounts and VPAs plain | Amounts and VPAs are needed for SQL joins and graph queries; names are the most identifying fields. Revisit with KMS in production.
2026-11-26 | Extra columns beyond the spec table list? | Add a few (status, meta, roles, women_owned, is_sandbox, idempotency_key) | Needed by later flows; spec fields are all present.
