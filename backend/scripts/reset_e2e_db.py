"""Recreate the e2e database schema from migrations. Refuses to touch any other database."""

from alembic.config import Config

from alembic import command
from app.core.config import get_settings
from app.db.base import get_engine


def main() -> None:
    url = get_settings().database_url
    if not url.endswith("/ktp_e2e"):
        raise SystemExit(f"refusing to reset non-e2e database: {url}")
    with get_engine().begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    command.upgrade(Config("alembic.ini"), "head")


if __name__ == "__main__":
    main()
