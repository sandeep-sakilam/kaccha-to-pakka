"""Reset the local database and load the Sandbox demo (3 Indore businesses + fraud script).

Usage: uv run python -m scripts.seed_demo --reset-database   (refuses APP_ENV=production)
       (the friend's first ₹1 attempt is played and Raju's passport issued: on hold)
"""

import json
import sys

from alembic.config import Config

from alembic import command
from app.core.config import get_settings
from app.db.base import _session_factory, get_engine
from app.sandbox import demo


def main() -> None:
    s = get_settings()
    s.jobs_inline = True  # extraction runs in-process so the seed is complete and deterministic
    # The demo is Sandbox data: never call real AI, never message the fictional phone numbers,
    # even on a server where real keys are set. Seeded businesses use the simulated gateway.
    s.ai_provider = s.fallback_ai_provider = "mock"
    s.whatsapp_provider = s.sms_provider = s.kyc_provider = s.aa_provider = "mock"
    if s.app_env == "production":
        raise SystemExit("refusing to reset a production database")
    if "--reset-database" not in sys.argv:
        raise SystemExit("this ERASES the database; run again with --reset-database to confirm")
    with get_engine().begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    command.upgrade(Config("alembic.ini"), "head")
    db = _session_factory()()
    try:
        out = demo.seed_all(db)
        db.commit()
    finally:
        db.close()
    base = s.public_base_url.rstrip("/")
    fraud = out["fraud"]
    assert isinstance(fraud, dict)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(
        f"\nLog in with any phone above, PIN {demo.DEMO_PIN} (OTP is shown on screen in Sandbox)."
    )
    print(
        f"Fraud scene: open {base}/confirm/{fraud['replay_invite_token']} and pay from "
        f"{demo.FRIEND_VPA} / {demo.FRIEND_NAME}."
    )


if __name__ == "__main__":
    main()
