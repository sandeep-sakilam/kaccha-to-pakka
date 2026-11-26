"""Test fixtures. Tests run against a separate Postgres database and always use mock adapters."""

import os

os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://ktp:ktp@localhost:5432/ktp_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["APP_ENV"] = "test"
for _var in (
    "AI_PROVIDER",
    "FALLBACK_AI_PROVIDER",
    "AA_PROVIDER",
    "PAYMENTS_PROVIDER",
    "WHATSAPP_PROVIDER",
    "KYC_PROVIDER",
    "SMS_PROVIDER",
):
    os.environ[_var] = "mock"
os.environ["STORAGE_PROVIDER"] = "memory"

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import Connection  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import models  # noqa: E402, F401
from app.db.base import Base, get_engine  # noqa: E402


@pytest.fixture(scope="session")
def _schema() -> Iterator[None]:
    engine = get_engine()
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def connection(_schema: None) -> Iterator[Connection]:
    conn = get_engine().connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    """A session whose commits are savepoints inside a rolled-back outer transaction."""
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
