from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.account_aggregator import AAAccount, AATransaction, MockAccountAggregator
from app.adapters.registry import get_adapters
from app.db.models import Business
from app.modules.trust import service as trust
from tests import factories as f
from tests.conftest import new_phone, photo, setup_business

SHOP = {"lat": 22.7186, "lng": 75.8553}


def link_bank_with_merchant(
    client: TestClient, h: dict[str, str], biz: str, phone: str, merchant: dict[str, float] | None
) -> None:
    aa = get_adapters().aa
    assert isinstance(aa, MockAccountAggregator)
    today = date.today()
    aa.register(
        phone,
        [
            AAAccount(
                "XXXX1",
                "SANDBOX HOLDER",
                "Sandbox Bank",
                [
                    AATransaction(
                        today - timedelta(days=d),
                        100_000,
                        "in",
                        f"c{d}@ok",
                        "C",
                        f"8{d:011d}",
                        None,
                        "UPI",
                    )
                    for d in range(3, 60, 3)
                ],
                merchant_geo=merchant,
            )
        ],
    )
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    client.post(
        f"/sandbox/aa/{start['redirect_url'].rsplit('/', 1)[1]}/decide",
        json={"approve": True},
        headers=h,
    )
    client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h)


def capture(
    client: TestClient, h: dict[str, str], biz: str, kind: str, key: str, lat: float, lng: float
) -> dict[str, object]:
    r = client.post(
        f"/businesses/{biz}/captures",
        headers={**h, "Idempotency-Key": key},
        files={"file": ("p.png", photo(variant=key), "image/png")},
        data={
            "kind": kind,
            "captured_at": datetime.now(UTC).isoformat(),
            "device_id": "device-test-1",
            "lat": str(lat),
            "lng": str(lng),
            "accuracy_m": "10",
        },
    )
    body: dict[str, object] = r.json()
    return body


def test_merchant_location_is_stored_and_checked(client: TestClient, db: Session) -> None:
    phone = new_phone()
    h, biz = setup_business(client, phone=phone)
    link_bank_with_merchant(client, h, biz, phone, SHOP)
    b = db.get(Business, biz)
    assert b is not None and b.merchant_geo and b.merchant_geo["source"] == "aa"
    capture(client, h, biz, "shop_front", "merchant-shop-1", SHOP["lat"], SHOP["lng"])
    # A presence photo far from the merchant location fails that check
    client.post("/consents", json={"purpose": "presence_location", "business_id": biz}, headers=h)
    client.post(f"/businesses/{biz}/presence/start", headers=h)
    client.post(f"/sandbox/presence/{biz}/now", headers=h)
    far = capture(client, h, biz, "presence", "merchant-far-1", 22.76, 75.91)
    assert "far_from_merchant_location" in far["meta"]["presence"]["reasons"]  # type: ignore[index]


def test_someone_elses_shop_far_from_merchant_holds(db: Session) -> None:
    biz = f.business(db)
    biz.geo_home = {"lat": 22.76, "lng": 75.91}  # photos taken at another shop, 7 km away
    biz.merchant_geo = SHOP
    db.flush()
    a = trust.assess(db, biz)
    assert a.status == "on_hold"
    assert any(fl["code"] == "shop_far_from_merchant_location" for fl in a.flags)


def test_nearby_is_only_a_warning_and_missing_is_fine(db: Session) -> None:
    biz = f.business(db)
    biz.geo_home = {"lat": SHOP["lat"] + 0.008, "lng": SHOP["lng"]}  # ~900 m
    biz.merchant_geo = SHOP
    db.flush()
    a = trust.assess(db, biz)
    assert a.status != "on_hold"
    assert any(fl["code"] == "shop_near_but_not_at_merchant_location" for fl in a.flags)
    other = f.business(db)
    other.geo_home = SHOP
    db.flush()
    assert not any("merchant" in fl["code"] for fl in trust.assess(db, other).flags)
