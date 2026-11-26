from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.account_aggregator import MockAccountAggregator
from app.adapters.registry import get_adapters
from app.db.base import utcnow
from app.db.models import Consent, User
from app.jobs import run_now
from app.modules.aa.service import due_for_refresh
from tests.conftest import new_phone, setup_business


def test_link_approve_fetch_revoke(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client, phone=new_phone())
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    assert start["sandbox"] is True and start["redirect_url"].startswith("/sandbox/aa/approve/")
    handle = start["redirect_url"].rsplit("/", 1)[-1]
    early = client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h)
    assert early.status_code == 409 and early.json()["code"] == "aa_pending"
    assert client.post(
        f"/sandbox/aa/{handle}/decide", json={"approve": True}, headers=h
    ).json() == {"status": "ACTIVE"}
    res = client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h).json()
    assert res["accounts"][0]["txns"] > 50 and res["accounts"][0]["sandbox"] is True
    again = client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h).json()
    assert again["accounts"][0]["txns"] == 0  # same data never stored twice
    purposes = {c["purpose"] for c in client.get("/consents", headers=h).json() if c["active"]}
    assert {"aa_fetch", "monthly_refresh"} <= purposes
    client.post(f"/businesses/{biz}/aa/{start['consent_id']}/revoke", headers=h)
    purposes = {c["purpose"] for c in client.get("/consents", headers=h).json() if c["active"]}
    assert not purposes & {"aa_fetch", "monthly_refresh"}
    r = client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h)
    assert r.json()["code"] == "consent_inactive"


def test_rejected_in_aa_app(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    handle = start["redirect_url"].rsplit("/", 1)[-1]
    client.post(f"/sandbox/aa/{handle}/decide", json={"approve": False}, headers=h)
    r = client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h)
    assert r.json()["code"] == "aa_rejected"


def test_someone_else_cannot_approve(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    handle = start["redirect_url"].rsplit("/", 1)[-1]
    h2, _ = setup_business(client, phone=new_phone(), device="device-test-9")
    assert (
        client.post(f"/sandbox/aa/{handle}/decide", json={"approve": True}, headers=h2).status_code
        == 403
    )


def test_monthly_refresh_due(client: TestClient, db: Session) -> None:
    phone = new_phone()
    h, biz = setup_business(client, phone=phone)
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    aa = get_adapters().aa
    assert isinstance(aa, MockAccountAggregator)
    aa.approve(start["redirect_url"].rsplit("/", 1)[-1])
    assert (biz, start["consent_id"]) in due_for_refresh(db)
    run_now(db, "aa_refresh", biz, start["consent_id"])
    assert (biz, start["consent_id"]) not in due_for_refresh(db)
    c = db.get(Consent, start["consent_id"])
    assert c is not None
    c.scope = {**c.scope, "last_fetch_at": (utcnow() - timedelta(days=31)).isoformat()}
    db.flush()
    assert (biz, start["consent_id"]) in due_for_refresh(db)
    user = db.execute(select(User).where(User.phone == phone)).scalar_one()
    assert user is not None
