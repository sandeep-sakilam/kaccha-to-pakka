from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapters
from app.db.models import AuditLog, BankTransaction, Business, EvidenceItem, Passport, User
from app.modules.audit.service import verify_chain
from tests.conftest import login, new_phone, photo, setup_business


def test_erase_account_end_to_end(client: TestClient, db: Session) -> None:
    phone = new_phone()
    h, biz = setup_business(client, phone=phone)
    client.post("/consents", json={"purpose": "keep_originals", "business_id": biz}, headers=h)
    ev = client.post(
        f"/businesses/{biz}/captures",
        headers={**h, "Idempotency-Key": "erase-key-1"},
        files={"file": ("p.png", photo(variant="erase"), "image/png")},
        data={
            "kind": "ledger_page",
            "captured_at": datetime.now(UTC).isoformat(),
            "device_id": "device-test-1",
        },
    ).json()
    key = db.get(EvidenceItem, ev["id"]).storage_key  # type: ignore[union-attr]
    assert key and get_adapters().storage.exists(key)
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    client.post(
        f"/sandbox/aa/{start['redirect_url'].rsplit('/', 1)[1]}/decide",
        json={"approve": True},
        headers=h,
    )
    client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h)
    p = client.post(f"/businesses/{biz}/passport", headers=h).json()
    share = client.post(
        f"/businesses/{biz}/shares", headers=h, json={"lender_org": "Coop Bank"}
    ).json()

    assert (
        client.post("/auth/erase", headers=h, json={"pin": "4826", "confirm": "no"}).json()["code"]
        == "confirm_required"
    )
    assert (
        client.post("/auth/erase", headers=h, json={"pin": "0000", "confirm": "DELETE"}).json()[
            "code"
        ]
        == "pin_wrong"
    )
    r = client.post("/auth/erase", headers=h, json={"pin": "4826", "confirm": "DELETE"}).json()
    assert r["erased"] and r["shares_revoked"] == 1 and r["files_deleted"] == 1

    assert not get_adapters().storage.exists(key)
    assert client.get(f"/l/{share['link'].rsplit('/l/', 1)[1]}").status_code == 410
    assert client.get(f"/passports/{p['id']}/status").json()["status"] == "revoked"
    assert db.execute(select(EvidenceItem).where(EvidenceItem.business_id == biz)).first() is None
    assert db.execute(select(BankTransaction)).first() is None or all(
        t.evidence_id != ev["id"] for t in db.execute(select(BankTransaction)).scalars()
    )
    b = db.get(Business, biz)
    assert b is not None and b.name == "Erased business" and b.deleted_at is not None
    assert db.execute(select(Passport).where(Passport.business_id == biz)).scalar_one().vc_json == {
        "erased": True
    }
    u = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    assert u is None  # the phone number is no longer stored
    assert client.get("/auth/me", headers=h).status_code == 401  # sessions gone
    # The anonymised audit trail stays and still verifies
    assert verify_chain(db).ok
    assert db.execute(select(AuditLog).where(AuditLog.action == "account.erased")).first()
    # The same phone can sign up again as a new person
    h2 = login(client, phone, device="device-new-life")
    assert client.get("/businesses", headers=h2).json() == []
