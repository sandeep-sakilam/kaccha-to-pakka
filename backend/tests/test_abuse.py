from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import AuthSession, Notification, User
from app.modules.abuse.limits import TooMany, count_distinct, hit
from tests.conftest import login, new_phone, setup_business


def test_otp_rate_limit_per_phone(client: TestClient) -> None:
    phone = new_phone()
    codes = [client.post("/auth/otp/request", json={"phone": phone}).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_confirmer_distinct_business_limit() -> None:
    for i in range(10):
        count_distinct("confirmer_month", "+919999", f"biz{i}")
    count_distinct("confirmer_month", "+919999", "biz3")  # same business again is fine
    try:
        count_distinct("confirmer_month", "+919999", "biz-eleven")
        raise AssertionError("expected limit")
    except TooMany as exc:
        assert exc.code == "rate_limited:confirmer_month"


def test_penny_drop_attempts_limited() -> None:
    for _ in range(3):
        hit("penny_drop_invite", "inv-1")
    try:
        hit("penny_drop_invite", "inv-1")
        raise AssertionError("expected limit")
    except TooMany:
        pass


def test_new_device_freezes_shares_and_notifies(client: TestClient, db: Session) -> None:
    phone = new_phone()
    h, biz = setup_business(client, phone=phone, device="device-first-01")
    client.post(f"/businesses/{biz}/passport", headers=h)
    share = client.post(
        f"/businesses/{biz}/shares", headers=h, json={"lender_org": "Coop Bank"}
    ).json()
    token = share["link"].rsplit("/l/", 1)[1]
    assert client.get(f"/l/{token}").status_code == 200
    h2 = login(client, phone, device="device-thief-01")  # takeover attempt on a new phone
    user = db.execute(select(User).where(User.phone == phone)).scalar_one()
    note = db.execute(
        select(Notification).where(
            Notification.user_id == user.id, Notification.kind == "new_device"
        )
    ).first()
    assert note is not None
    r = client.post(f"/businesses/{biz}/shares", headers=h2, json={"lender_org": "Elsewhere"})
    assert r.status_code == 423 and r.json()["code"] == "shares_frozen"
    assert client.get(f"/l/{token}").json()["code"] == "share_paused"
    # After 24 hours the freeze lifts.
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id)
        .values(created_at=utcnow() - timedelta(hours=25))
    )
    db.flush()
    assert client.get(f"/l/{token}").status_code == 200
