"""Run the evaluation harness against a scratch database (`ktp_eval`) and write eval/report.*.

Usage: make eval  (uses the scratch database ktp_eval)
"""

from app.core.config import get_settings
from app.db import models, triggers  # noqa: F401
from app.db.base import Base, _session_factory, get_engine
from app.evaluation.harness import run, write


def main() -> None:
    url = get_settings().database_url
    if not url.endswith("_eval"):
        raise SystemExit(f"refusing to use a non-eval database: {url}")
    get_settings().jobs_inline = True
    with get_engine().begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    Base.metadata.create_all(get_engine())
    db = _session_factory()()
    try:
        report = run(db)
        db.rollback()
    finally:
        db.close()
    j, m = write(report)
    print(f"wrote {j} and {m}; red-team catch rate {report['red_team']['catch_rate']:.0%}")


if __name__ == "__main__":
    main()
