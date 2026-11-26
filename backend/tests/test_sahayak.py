from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, EvidenceItem
from tests.conftest import login, new_phone, photo, setup_business


def sahayak(
    client: TestClient, name: str = "Kavita (CSC)", gender: str = "female"
) -> tuple[dict[str, str], str]:
    phone = new_phone()
    h = login(client, phone, device=f"device-sahayak-{phone[-4:]}")
    client.post("/sahayak/register", json={"name": name, "gender": gender}, headers=h)
    return h, phone


def upload(client: TestClient, h: dict[str, str], biz: str, key: str) -> int:
    r = client.post(
        f"/businesses/{biz}/captures",
        headers={**h, "Idempotency-Key": key},
        files={"file": ("p.png", photo(variant=key), "image/png")},
        data={
            "kind": "ledger_page",
            "captured_at": datetime.now(UTC).isoformat(),
            "device_id": "device-sahayak",
        },
    )
    return int(r.status_code)


def test_sahayak_flow_permissions_and_tagging(client: TestClient, db: Session) -> None:
    owner_h, biz = setup_business(client, phone=new_phone())
    sh, sphone = sahayak(client)
    assert upload(client, sh, biz, "sah-key-0001") == 403  # not added yet
    r = client.post(
        f"/businesses/{biz}/sahayaks",
        headers=owner_h,
        json={"phone": sphone, "permissions": ["capture"]},
    )
    assert r.status_code == 200 and r.json()["permissions"] == ["capture"]
    assert [b["id"] for b in client.get("/sahayak/businesses", headers=sh).json()] == [biz]
    assert upload(client, sh, biz, "sah-key-0002") == 200
    ev = db.execute(
        select(EvidenceItem).where(EvidenceItem.idempotency_key == "sah-key-0002")
    ).scalar_one()
    assert ev.sahayak_user_id is not None and ev.sahayak_user_id == ev.actor_user_id
    tagged = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.action == "evidence.capture")
            .order_by(AuditLog.seq.desc())
        )
        .scalars()
        .first()
    )
    assert tagged is not None and tagged.actor.startswith("sahayak:")
    # Not allowed: statements, shares, consents for the business
    r = client.post(
        f"/businesses/{biz}/statements",
        headers={**sh, "Idempotency-Key": "x" * 9},
        files={"file": ("s.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.json()["code"] == "sahayak_not_allowed"
    assert (
        client.post(
            f"/businesses/{biz}/shares", headers=sh, json={"lender_org": "Bank"}
        ).status_code
        == 403
    )
    # Owner removes the Sahayak: access ends at once
    link = client.get(f"/businesses/{biz}/sahayaks", headers=owner_h).json()[0]
    client.post(f"/businesses/{biz}/sahayaks/{link['id']}/revoke", headers=owner_h)
    assert upload(client, sh, biz, "sah-key-0003") == 403
    assert client.get("/sahayak/businesses", headers=sh).json() == []


def test_only_registered_sahayaks_and_women_directory(client: TestClient) -> None:
    owner_h, biz = setup_business(client, phone=new_phone())
    stranger = new_phone()
    login(client, stranger, device="device-stranger-1")
    r = client.post(f"/businesses/{biz}/sahayaks", headers=owner_h, json={"phone": stranger})
    assert r.json()["code"] == "not_sahayak"
    sahayak(client, "Ramesh BC", "male")
    _, woman = sahayak(client, "Sunita SHG", "female")
    women = client.get("/sahayak/directory?women_only=true", headers=owner_h).json()
    assert any(w["phone_last4"] == woman[-4:] for w in women)
    assert all(w["gender"] == "female" for w in women)
