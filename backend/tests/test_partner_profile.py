"""One person, one business: a confirmer who later joins as an owner, and an owner who confirms."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Attestation, Business, User
from tests.conftest import login, setup_business
from tests.test_attestations import CLAIM, prove
from tests.test_penny_drop import invite_token


def _confirm(client: TestClient, db: Session, phone: str) -> Attestation:
    _, _, token = invite_token(client, db, phone)
    prove(client, token)
    body = dict(CLAIM, monthly_value="10k-25k", business_name="Sethi Sev Traders")
    a = db.get(Attestation, client.post(f"/invites/{token}/claim", json=body).json()["id"])
    assert a is not None and a.confirmer_business_id
    return a


def test_confirmer_who_joins_gets_their_own_business_not_the_partner_profile(
    client: TestClient, db: Session
) -> None:
    a = _confirm(client, db, "9844400001")
    h = login(client, "9844400001")
    client.post("/consents", json={"purpose": "build_passport"}, headers=h)
    r = client.post(
        "/businesses",
        json={"name": "Verma Provision Store", "category": "kirana", "started_year": 2015},
        headers=h,
    )
    assert r.status_code == 200, r.text
    mine = client.get("/businesses", headers=h).json()
    assert [(b["name"], b["category"]) for b in mine] == [("Verma Provision Store", "kirana")]
    # The partner profile became this business, so the confirmation stays linked to it.
    assert mine[0]["id"] == a.confirmer_business_id == r.json()["id"]


def test_owner_who_confirms_a_partner_confirms_as_their_own_business(
    client: TestClient, db: Session
) -> None:
    h, own = setup_business(client, name="Gupta Traders", phone="9844400002")
    a = _confirm(client, db, "9844400002")
    assert a.confirmer_business_id == own
    assert [b["id"] for b in client.get("/businesses", headers=h).json()] == [own]


def test_own_business_listed_before_an_older_partner_profile(
    client: TestClient, db: Session
) -> None:
    h, own = setup_business(client, phone="9844400003")
    biz = db.get(Business, own)
    assert biz is not None
    user = db.get(User, biz.owner_user_id)
    assert user is not None
    db.add(
        Business(
            owner_user_id=user.id,
            name="Old partner profile",
            category="trading_partner",
            created_at=utcnow() - timedelta(days=30),
        )
    )
    db.commit()
    assert client.get("/businesses", headers=h).json()[0]["id"] == own
