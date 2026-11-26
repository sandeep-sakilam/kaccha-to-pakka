import random
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Business, PresenceRequest
from app.modules.presence.service import haversine_m, schedule_cycle, send_due
from tests import factories as f
from tests.conftest import photo, setup_business

SHOP = (22.7186, 75.8553)


def capture(
    client: TestClient,
    h: dict[str, str],
    biz: str,
    kind: str,
    key: str,
    lat: float,
    lng: float,
    acc: float = 15,
    data: bytes | None = None,
) -> dict[str, object]:
    r = client.post(
        f"/businesses/{biz}/captures",
        headers={**h, "Idempotency-Key": key},
        files={"file": ("p.png", data or photo(), "image/png")},
        data={
            "kind": kind,
            "captured_at": datetime.now(UTC).isoformat(),
            "device_id": "device-test-1",
            "lat": str(lat),
            "lng": str(lng),
            "accuracy_m": str(acc),
        },
    )
    body: dict[str, object] = r.json()
    return body


def test_haversine() -> None:
    assert (
        100 < haversine_m({"lat": 22.7186, "lng": 75.8553}, {"lat": 22.7196, "lng": 75.8553}) < 120
    )


def test_schedule_is_random_days_in_cycle(db: Session) -> None:
    biz = f.business(db)
    start = datetime(2026, 11, 1, tzinfo=UTC)
    reqs = schedule_cycle(db, biz, start, random.Random(1))
    assert len(reqs) == 4 and len({r.requested_at.date() for r in reqs}) == 4
    assert all(start < r.requested_at < start + timedelta(days=28) for r in reqs)
    other = schedule_cycle(db, biz, start, random.Random(2))
    assert [r.requested_at for r in reqs] != [r.requested_at for r in other]


def test_missed_check(db: Session) -> None:
    biz = f.business(db)
    reqs = schedule_cycle(db, biz, datetime(2026, 1, 1, tzinfo=UTC), random.Random(3))
    send_due(db, datetime(2026, 3, 1, tzinfo=UTC))
    assert {r.status for r in reqs} == {"missed"}


def test_presence_flow(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client)
    capture(client, h, biz, "shop_front", "pres-shop-01", *SHOP)
    b = db.get(Business, biz)
    assert b is not None and b.geo_home and abs(b.geo_home["lat"] - SHOP[0]) < 1e-6
    assert (
        client.post(f"/businesses/{biz}/presence/start", headers=h).json()["code"]
        == "consent_required:presence_location"
    )
    client.post("/consents", json={"purpose": "presence_location", "business_id": biz}, headers=h)
    listed = client.post(f"/businesses/{biz}/presence/start", headers=h).json()
    assert len(listed) == 4 and all(r["requested_at"] is None for r in listed)  # dates hidden
    client.post(f"/sandbox/presence/{biz}/now", headers=h)
    ok = capture(
        client,
        h,
        biz,
        "presence",
        "pres-near-01",
        SHOP[0] + 0.0005,
        SHOP[1],
        data=photo(variant="near"),
    )
    assert ok["meta"]["presence"]["passed"] is True  # type: ignore[index]
    client.post(f"/sandbox/presence/{biz}/now", headers=h)
    from app.adapters.sandbox_images import ledger_png

    far = capture(
        client,
        h,
        biz,
        "presence",
        "pres-far-001",
        22.75,
        75.90,
        data=ledger_png({"entries": [], "page_confidence": 0.9}, noise="y" * 90),
    )
    assert far["meta"]["presence"]["reasons"] == ["far_from_shop"]  # type: ignore[index]
    statuses = sorted(
        r["status"] for r in client.get(f"/businesses/{biz}/presence", headers=h).json()
    )
    assert statuses == ["done", "failed", "scheduled", "scheduled"]
    assert db.query(PresenceRequest).filter_by(business_id=biz, status="done").count() == 1
