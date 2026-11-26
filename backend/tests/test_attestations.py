from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import signing
from app.core.identifiers import make_gstin
from app.db.models import Attestation, Business
from app.modules.attestations.claims import attestation_payload, bucket_for
from tests import factories as f
from tests.test_penny_drop import invite_token

CLAIM = {
    "relationship": "supplier",
    "years_trading": "3-5",
    "monthly_value": "1L-5L",
    "payment_behaviour": "on_time",
}


def prove(
    client: TestClient, token: str, vpa: str = "partner0@oksbi", name: str = "PARTNER 0"
) -> None:
    pd = client.post(f"/invites/{token}/penny-drop").json()
    client.post(f"/sandbox/payments/{pd['ref']}/pay", json={"payer_vpa": vpa, "payer_name": name})
    assert client.post(f"/invites/{token}/penny-drop/check").json()["status"] == "proven"


def test_buckets() -> None:
    assert bucket_for(9_999_00) == "0-10k" and bucket_for(10_000_00) == "10k-25k"
    assert bucket_for(1_000_000_00) == "5L+"


def test_signing_roundtrip() -> None:
    sig = signing.sign({"a": 1})
    assert signing.verify({"a": 1}, sig) and not signing.verify({"a": 2}, sig)
    assert signing.verify({"a": 1}, sig, signing.public_key_b64())


def test_claim_must_follow_proof(client: TestClient, db: Session) -> None:
    _, _, token = invite_token(client, db, "9833300001")
    r = client.post(f"/invites/{token}/claim", json=CLAIM)
    assert r.json()["code"] == "not_proven"


def test_matching_claim_with_gstin_full_weight(client: TestClient, db: Session) -> None:
    h, biz, token = invite_token(client, db, "9833300002")
    prove(client, token)
    # partner0 is paid 10 lakh paise (₹10,000) x ... per month in seed_money -> check bucket
    body = dict(
        CLAIM,
        monthly_value="10k-25k",
        gstin=make_gstin("23", "ABCDE1234F"),
        business_name="Partner 0",
    )
    a = client.post(f"/invites/{token}/claim", json=body).json()
    assert a["money_match"] is True and a["weight"] == 1.0 and a["signature_valid"]
    assert a["claim"]["id_status"] == "gstin_valid"
    listed = client.get(f"/businesses/{biz}/attestations", headers=h).json()
    assert len(listed) == 1
    att = db.get(Attestation, a["id"])
    assert att is not None and att.confirmer_business_id is not None
    assert db.get(Business, att.confirmer_business_id).category == "trading_partner"  # type: ignore[union-attr]
    assert (att.expires_at - att.created_at) > timedelta(days=180)  # type: ignore[operator]
    # tampering with a stored claim breaks the signature
    att.claim = {**att.claim, "monthly_value": "5L+"}
    assert not signing.verify(attestation_payload(att), att.signature or "")


def test_no_id_lower_weight_and_mismatch_is_discrepancy(client: TestClient, db: Session) -> None:
    _, _, token = invite_token(client, db, "9833300003")
    prove(client, token)
    a = client.post(f"/invites/{token}/claim", json=dict(CLAIM, monthly_value="10k-25k")).json()
    assert a["weight"] == 0.7 and a["status"] == "confirmed"
    _, _, token2 = invite_token(client, db, "9833300004")
    prove(client, token2)
    b = client.post(
        f"/invites/{token2}/claim", json=dict(CLAIM, relationship="customer", monthly_value="5L+")
    ).json()
    assert b["status"] == "discrepancy" and b["weight"] == 0.2
    assert set(b["claim"]["discrepancies"]) == {"relationship_mismatch", "value_mismatch"}


def test_invalid_gstin_refused(client: TestClient, db: Session) -> None:
    _, _, token = invite_token(client, db, "9833300005")
    prove(client, token)
    r = client.post(f"/invites/{token}/claim", json=dict(CLAIM, gstin="23ABCDE1234F1Z0"))
    assert r.json()["code"] == "bad_id"


def test_in_person_needs_role(client: TestClient, db: Session) -> None:
    from sqlalchemy import select

    from app.db.models import User
    from tests.conftest import login, new_phone

    subject = f.business(db)
    phone = new_phone()
    h = login(client, phone, device="device-officer-1")
    body = {"relationship": "visited", "note": "Shop open, stock seen"}
    assert (
        client.post(
            f"/businesses/{subject.id}/attestations/in-person", json=body, headers=h
        ).status_code
        == 403
    )
    officer = db.execute(select(User).where(User.phone == phone)).scalar_one()
    officer.roles = ["owner", "field_officer"]
    db.flush()
    r = client.post(f"/businesses/{subject.id}/attestations/in-person", json=body, headers=h)
    assert r.json()["evidence_type"] == "in_person" and r.json()["weight"] == 0.5
    assert date.today()
