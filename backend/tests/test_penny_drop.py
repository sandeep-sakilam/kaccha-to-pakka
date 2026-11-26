from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.messaging import MockWhatsApp
from app.adapters.payments import MockPaymentGateway
from app.adapters.registry import get_adapters
from app.db.models import Dispute
from tests.conftest import new_phone, setup_business
from tests.test_invites import seed_money


def invite_token(
    client: TestClient, db: Session, phone: str = "9822200001"
) -> tuple[dict[str, str], str, str]:
    h, biz = setup_business(client, phone=new_phone())
    seed_money(db, biz)
    top = client.get(f"/businesses/{biz}/counterparties/top", headers=h).json()
    client.post(
        f"/businesses/{biz}/invites",
        headers=h,
        json={"counterparty_id": top[0]["counterparty_id"], "phone": phone},
    )
    wa = get_adapters().whatsapp
    assert isinstance(wa, MockWhatsApp)
    msg = wa.last_to("+91" + phone)
    assert msg is not None
    return h, biz, msg.text.rsplit("/confirm/", 1)[1]


def test_real_supplier_proves_control(client: TestClient, db: Session) -> None:
    _, _, token = invite_token(client, db)
    pd = client.post(f"/invites/{token}/penny-drop").json()
    assert pd["amount_paise"] == 100 and pd["sandbox"] and pd["upi_link"].startswith("upi://")
    assert client.post(f"/invites/{token}/penny-drop/check").json()["status"] == "pending"
    client.post(
        f"/sandbox/payments/{pd['ref']}/pay",
        json={"payer_vpa": "Partner0@OKSBI", "payer_name": "PARTNER 0"},
    )
    assert client.post(f"/invites/{token}/penny-drop/check").json() == {
        "status": "proven",
        "reason": None,
    }
    gw = get_adapters().payments
    assert isinstance(gw, MockPaymentGateway) and gw.get_result(pd["ref"]).refunded


def test_friend_paying_from_own_account_is_rejected(client: TestClient, db: Session) -> None:
    _, biz, token = invite_token(client, db, "9822200002")
    pd = client.post(f"/invites/{token}/penny-drop").json()
    client.post(
        f"/sandbox/payments/{pd['ref']}/pay",
        json={"payer_vpa": "my.friend@okaxis", "payer_name": "PARTNER 0"},
    )
    res = client.post(f"/invites/{token}/penny-drop/check").json()
    assert res == {"status": "rejected", "reason": "account_mismatch"}
    assert db.execute(
        select(Dispute).where(Dispute.business_id == biz, Dispute.target_type == "invite")
    ).first()
    again = client.post(f"/invites/{token}/penny-drop")
    assert again.status_code == 409


def test_right_account_wrong_name(client: TestClient, db: Session) -> None:
    _, _, token = invite_token(client, db, "9822200003")
    pd = client.post(f"/invites/{token}/penny-drop").json()
    client.post(
        f"/sandbox/payments/{pd['ref']}/pay",
        json={"payer_vpa": "partner0@oksbi", "payer_name": "SOMEONE ELSE"},
    )
    assert client.post(f"/invites/{token}/penny-drop/check").json()["reason"] == "name_mismatch"
