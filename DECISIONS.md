# Decision log

One line per decision: date | question | choice | reason.

2026-11-26 | Arq or Celery for jobs? | Arq | Async-native, small, uses the Redis we already run; enough for a solo builder.
2026-11-26 | Sync or async SQLAlchemy? | Sync SQLAlchemy with FastAPI sync endpoints | Simpler to debug and test; throughput is not a bottleneck for the prototype.
