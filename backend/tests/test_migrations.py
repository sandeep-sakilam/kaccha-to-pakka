"""The Alembic migrations must build exactly the schema the models describe."""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from alembic import command
from app.db.base import Base

URL = os.environ["TEST_DATABASE_URL"].replace("/ktp_test", "/ktp_migrations")


@pytest.fixture
def migrated_url() -> str:
    admin = create_engine(os.environ["TEST_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.exec_driver_sql("DROP DATABASE IF EXISTS ktp_migrations")
        c.exec_driver_sql("CREATE DATABASE ktp_migrations")
    admin.dispose()
    return URL


def test_upgrade_matches_models(migrated_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", migrated_url)
    get_settings.cache_clear()
    try:
        cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
        cfg.set_main_option(
            "script_location", os.path.join(os.path.dirname(__file__), "..", "alembic")
        )
        command.upgrade(cfg, "head")
        engine = create_engine(migrated_url)
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        engine.dispose()
        assert diff == []
        command.downgrade(cfg, "base")
    finally:
        get_settings.cache_clear()
