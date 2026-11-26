from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.db.base import utcnow
from app.db.models import Business, Consent, User
from app.modules.consent import service
from tests.conftest import login, new_phone


def _user_biz(db: Session) -> tuple[User, Business]:
    u = User(phone=new_phone())
    db.add(u)
    db.flush()
    b = Business(owner_user_id=u.id, name="B", category="kirana")
    db.add(b)
    db.flush()
    return u, b


def test_notice_in_both_languages(client: TestClient) -> None:
    hi = client.get("/consents/notice?language=hi").json()
    en = client.get("/consents/notice?language=en").json()
    assert len(hi["lines"]) == len(en["lines"]) == 5
    assert any("never sell" in line for line in en["lines"])
    assert {p["key"] for p in en["purposes"]} >= {"build_passport", "share_lender", "aa_fetch"}


def test_grant_check_expire_revoke(db: Session) -> None:
    u, b = _user_biz(db)
    with pytest.raises(Forbidden):
        service.require(db, u.id, "aa_fetch", b.id)
    c = service.grant(db, u, "aa_fetch", b.id, {"months": 12})
    service.require(db, u.id, "aa_fetch", b.id)
    assert c.expires_at is not None and c.expires_at > utcnow() + timedelta(days=364)
    c.expires_at = utcnow() - timedelta(seconds=1)
    assert not service.has(db, u.id, "aa_fetch", b.id)
    c2 = service.grant(db, u, "aa_fetch", b.id)
    service.revoke(db, u, c2.id)
    assert not service.has(db, u.id, "aa_fetch", b.id)


def test_purposes_are_separate(db: Session) -> None:
    u, b = _user_biz(db)
    service.grant(db, u, "build_passport")
    assert service.has(db, u.id, "build_passport", b.id)
    assert not service.has(db, u.id, "share_lender", b.id)


def test_api_grant_list_revoke_purpose(client: TestClient, db: Session) -> None:
    phone = new_phone()
    h = login(client, phone)
    user = db.execute(select(User).where(User.phone == phone)).scalar_one()
    biz = Business(owner_user_id=user.id, name="Kirana", category="kirana")
    db.add(biz)
    db.flush()
    r = client.post(
        "/consents", json={"purpose": "monthly_refresh", "business_id": biz.id}, headers=h
    )
    assert r.status_code == 200 and r.json()["active"]
    assert (
        client.post("/consents", json={"purpose": "aa_fetch"}, headers=h).json()["code"]
        == "business_required"
    )
    assert client.post(
        "/consents/revoke-purpose", json={"purpose": "monthly_refresh"}, headers=h
    ).json() == {"revoked": 1}
    assert not client.get("/consents", headers=h).json()[0]["active"]


def test_cannot_consent_for_someone_elses_business(client: TestClient, db: Session) -> None:
    _, other = _user_biz(db)
    h = login(client)
    r = client.post("/consents", json={"purpose": "aa_fetch", "business_id": other.id}, headers=h)
    assert r.status_code == 403


def test_cannot_revoke_someone_elses_consent(client: TestClient, db: Session) -> None:
    u, b = _user_biz(db)
    c = service.grant(db, u, "aa_fetch", b.id)
    h = login(client)
    assert client.post(f"/consents/{c.id}/revoke", headers=h).status_code == 404
    assert db.get(Consent, c.id).revoked_at is None  # type: ignore[union-attr]
