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
from typing import TYPE_CHECKING  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import Connection  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import models, triggers  # noqa: E402, F401
from app.db.base import Base, get_engine  # noqa: E402

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


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


@pytest.fixture
def client(db: Session) -> Iterator["TestClient"]:
    from fastapi.testclient import TestClient

    from app.db.base import get_db
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c


_phone_counter = iter(range(10_000_000))


def new_phone() -> str:
    return f"+9198{next(_phone_counter):08d}"


def login(
    client: "TestClient", phone: str | None = None, device: str = "device-test-1", pin: str = "4826"
) -> dict[str, str]:
    """OTP + PIN login through the API. Returns auth headers."""
    phone = phone or new_phone()
    sent = client.post("/auth/otp/request", json={"phone": phone}).json()
    res = client.post(
        "/auth/otp/verify", json={"phone": phone, "code": sent["sandbox_code"], "device_id": device}
    ).json()
    headers = {"Authorization": f"Bearer {res['token']}"}
    if res["has_pin"]:
        r = client.post("/auth/pin/verify", json={"pin": pin}, headers=headers)
    else:
        r = client.post("/auth/pin/set", json={"pin": pin}, headers=headers)
    assert r.status_code == 200, r.text
    return headers


def setup_business(
    client: "TestClient",
    name: str = "Sharma Kirana",
    category: str = "kirana",
    phone: str | None = None,
    device: str = "device-test-1",
) -> tuple[dict[str, str], str]:
    """Logged-in owner with build_passport consent and one business."""
    h = login(client, phone, device=device)
    client.post("/consents", json={"purpose": "build_passport"}, headers=h)
    r = client.post(
        "/businesses", json={"name": name, "category": category, "started_year": 2012}, headers=h
    )
    assert r.status_code == 200, r.text
    return h, r.json()["id"]


def photo(kind: str = "sharp", size: tuple[int, int] = (800, 1000), variant: str = "") -> bytes:
    """Test images: 'sharp' (a sandbox ledger page), 'blurry', 'dark'."""
    import io

    from PIL import Image, ImageFilter

    from app.adapters.sandbox_images import ledger_png

    if kind == "sharp":
        return ledger_png(
            {
                "entries": [
                    {
                        "entry_date": "2026-10-12",
                        "party_text": "Sharma ji",
                        "amount_paise": 400000,
                        "direction": "in",
                        "confidence": {"date": 0.9, "party": 0.9, "amount": 0.9, "direction": 0.9},
                    }
                ],
                "page_total_paise": 400000,
                "page_confidence": 0.9,
            },
            noise="x" * 80 + variant,
        )
    img = Image.new("RGB", size, (128, 128, 128) if kind == "blurry" else (5, 5, 5))
    if kind == "blurry":
        img = img.filter(ImageFilter.GaussianBlur(8))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
