from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Notification, Share, User
from app.modules.passport.service import issue
from app.modules.trust.features import gather  # noqa: F401
from tests.conftest import login, new_phone, setup_business


def owner_with_passport(client: TestClient) -> tuple[dict[str, str], str]:
    h, biz = setup_business(client, phone=new_phone())
    client.post(f"/businesses/{biz}/passport", headers=h)
    return h, biz


def test_share_view_notify_revoke(client: TestClient, db: Session) -> None:
    h, biz = owner_with_passport(client)
    s = client.post(
        f"/businesses/{biz}/shares",
        headers=h,
        json={"lender_org": "SBI Rajwada branch", "scope": "summary"},
    ).json()
    assert s["state"] == "active" and "/l/" in s["link"]
    token = s["link"].rsplit("/l/", 1)[1]
    view = client.get(f"/l/{token}").json()
    assert view["lender_org"] == "SBI Rajwada branch" and "evidence" not in view
    assert view["passport"]["vc"]["credentialSubject"]["band"] == "U"
    logs = client.get(f"/businesses/{biz}/access-logs", headers=h).json()
    assert logs[0]["viewer"] == "SBI Rajwada branch"
    note = (
        db.execute(
            select(Notification)
            .where(Notification.kind == "share_viewed")
            .order_by(Notification.created_at.desc())
        )
        .scalars()
        .first()
    )
    assert note is not None and "SBI Rajwada branch" in note.text
    assert client.get(f"/businesses/{biz}/shares", headers=h).json()[0]["views"] == 1
    client.post(f"/shares/{s['id']}/revoke", headers=h)
    r = client.get(f"/l/{token}")
    assert r.status_code == 410 and r.json()["code"] == "share_revoked"
    active = [
        c
        for c in client.get("/consents", headers=h).json()
        if c["purpose"] == "share_lender" and c["active"]
    ]
    assert active == []


def test_evidence_scope_hides_partner_identity(client: TestClient, db: Session) -> None:
    from tests.test_trust_engine import strong_business

    biz = strong_business(db)
    issue(db, biz, "t")
    owner = db.get(User, biz.owner_user_id)
    assert owner is not None
    h = login(client, owner.phone, device="device-share-1")
    s = client.post(
        f"/businesses/{biz.id}/shares",
        headers=h,
        json={"lender_org": "Bank of Indore", "scope": "evidence", "days": 7},
    ).json()
    view = client.get(f"/l/{s['link'].rsplit('/l/', 1)[1]}").json()
    ev = view["evidence"]
    assert ev["money_source"] == "aa" and ev["monthly_totals_paise"]
    text = str(view)
    assert "CUSTOMER" not in text and "@oksbi" not in text and owner.phone not in text


def test_expiry_and_rules(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client, phone=new_phone())
    r = client.post(f"/businesses/{biz}/shares", headers=h, json={"lender_org": "X Bank"})
    assert r.json()["code"] == "no_passport"
    client.post(f"/businesses/{biz}/passport", headers=h)
    assert (
        client.post(
            f"/businesses/{biz}/shares", headers=h, json={"lender_org": "X Bank", "days": 365}
        ).json()["code"]
        == "bad_days"
    )
    s = client.post(f"/businesses/{biz}/shares", headers=h, json={"lender_org": "X Bank"}).json()
    row = db.get(Share, s["id"])
    assert row is not None
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.flush()
    assert client.get(f"/l/{s['link'].rsplit('/l/', 1)[1]}").json()["code"] == "share_expired"
