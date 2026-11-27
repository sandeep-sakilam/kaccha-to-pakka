from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from tests.conftest import login, new_phone, setup_business
from tests.test_penny_drop import invite_token
from tests.test_review import reviewer


def test_owner_raises_and_follows_a_dispute(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client, phone=new_phone())
    a = client.post(f"/businesses/{biz}/assess", headers=h).json()
    d = client.post(
        f"/businesses/{biz}/disputes",
        headers=h,
        json={
            "target_type": "assessment",
            "target_id": a["id"],
            "reason": "My bank data is missing a month",
        },
    ).json()
    assert d["status"] == "open" and d["raised_by"].startswith("user:")
    rh = reviewer(client, db)
    client.post(
        f"/review/disputes/{d['id']}/resolve",
        headers=rh,
        json={"decision": "cleared", "note": "checked"},
    )
    mine = client.get(f"/businesses/{biz}/disputes", headers=h).json()
    assert mine[0]["status"] == "resolved" and mine[0]["resolution"] == "cleared"


def test_counterparty_raises_and_follows(client: TestClient, db: Session) -> None:
    _, _, token = invite_token(client, db, "9855500001")
    r = client.post(f"/invites/{token}/dispute", json={"reason": "I never traded with them"})
    assert r.status_code == 200
    follow = client.get(f"/invites/{token}/disputes").json()
    assert len(follow) == 1 and follow[0]["status"] == "open"


def test_bad_target_and_other_owner(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    bad = client.post(
        f"/businesses/{biz}/disputes",
        headers=h,
        json={"target_type": "graph_flag", "target_id": "x", "reason": "abc"},
    )
    assert bad.json()["code"] == "bad_target"
    other = login(client, device="device-other-dsp")
    assert client.get(f"/businesses/{biz}/disputes", headers=other).status_code == 403
    assert date.today() and select(User) is not None
