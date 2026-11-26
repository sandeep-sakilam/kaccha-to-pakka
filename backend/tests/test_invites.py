from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.messaging import MockWhatsApp
from app.adapters.registry import get_adapters
from app.db.models import Business, User
from app.modules.attestations.selection import mask_vpa, top_counterparties
from app.modules.statements.money import MoneyTxn, store_transactions
from tests import factories as f
from tests.conftest import new_phone, setup_business


def seed_money(db: Session, biz_id: str, today: date | None = None) -> None:
    today = today or date.today()
    biz = db.get(Business, biz_id)
    assert biz is not None
    ev = f.evidence(db, biz, "aa_fetch", "aa:mock")
    rows = []
    for i in range(7):  # 7 partners with decreasing value
        vpa = f"partner{i}@oksbi"
        for m in range(3):
            rows.append(
                MoneyTxn(
                    today - timedelta(days=30 * m + i),
                    (10 - i) * 100_000,
                    "out" if i < 2 else "in",
                    vpa,
                    f"PARTNER {i}",
                    None,
                    None,
                    None,
                    None,
                )
            )
    rows.append(
        MoneyTxn(
            today - timedelta(days=300), 99_999_999, "in", "old@ok", "OLD", None, None, None, None
        )
    )
    store_transactions(db, biz.id, ev, rows)


def test_top_five_by_value_in_six_months(db: Session) -> None:
    biz = f.business(db)
    seed_money(db, biz.id)
    top = top_counterparties(db, biz.id)
    assert [t.vpa_or_account for t in top] == [f"partner{i}@oksbi" for i in range(5)]
    assert top[0].relationship == "supplier" and top[3].relationship == "customer"
    assert top[0].months_active == 3
    assert mask_vpa("partner0@oksbi") == "par•••••@oksbi"


def test_invite_flow(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client, phone=new_phone())
    seed_money(db, biz)
    top = client.get(f"/businesses/{biz}/counterparties/top", headers=h).json()
    assert len(top) == 5 and top[0]["masked_id"].startswith("par") and "@" in top[0]["masked_id"]
    cp = top[0]["counterparty_id"]
    friend = "9811100001"
    r = client.post(
        f"/businesses/{biz}/invites",
        headers=h,
        json={"counterparty_id": cp, "phone": friend, "language": "hi"},
    )
    assert r.status_code == 200 and r.json()["status"] == "sent"
    wa = get_adapters().whatsapp
    assert isinstance(wa, MockWhatsApp)
    msg = wa.last_to("+91" + friend)
    assert msg is not None and "/confirm/" in msg.text
    token = msg.text.rsplit("/confirm/", 1)[1]
    pub = client.get(f"/invites/{token}").json()
    assert pub["relationship"] == "supplier" and pub["status"] == "opened"
    assert "phone" not in pub and pub["masked_id"].startswith("par")
    again = client.post(
        f"/businesses/{biz}/invites", headers=h, json={"counterparty_id": cp, "phone": friend}
    )
    assert again.json()["code"] == "invite_open"
    second = client.post(
        f"/businesses/{biz}/invites",
        headers=h,
        json={"counterparty_id": top[1]["counterparty_id"], "phone": friend},
    ).json()
    assert second["flags"] == ["same_phone_multiple_partners"]


def test_owner_cannot_pick_partners_or_use_own_phone(client: TestClient, db: Session) -> None:
    phone = new_phone()
    h, biz = setup_business(client, phone=phone)
    seed_money(db, biz)
    other = f.business(db)
    seed_money(db, other.id)
    from app.db.models import Counterparty

    stranger = Counterparty(vpa_or_account="friend@okaxis", registered_name="MY FRIEND")
    db.add(stranger)
    db.flush()
    r = client.post(
        f"/businesses/{biz}/invites",
        headers=h,
        json={"counterparty_id": stranger.id, "phone": "9811100002"},
    )
    assert r.json()["code"] == "not_selected"
    top = client.get(f"/businesses/{biz}/counterparties/top", headers=h).json()
    r = client.post(
        f"/businesses/{biz}/invites",
        headers=h,
        json={"counterparty_id": top[0]["counterparty_id"], "phone": phone},
    )
    assert r.json()["code"] == "own_phone"
    assert db.execute(select(User).where(User.phone == phone)).scalar_one()
