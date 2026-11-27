from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.account_aggregator import MockAccountAggregator
from app.adapters.registry import get_adapters
from app.db.models import SahayakLink
from tests.conftest import new_phone, setup_business
from tests.test_sahayak import sahayak


def consent_id(client: TestClient, h: dict[str, str], purpose: str) -> str:
    rows = client.get("/consents?language=hi", headers=h).json()
    row = next(c for c in rows if c["purpose"] == purpose and c["active"])
    assert row["why"]  # every consent says why, in the owner's language
    return str(row["id"])


def test_withdrawing_share_consent_stops_the_lender_link(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    client.post(f"/businesses/{biz}/passport", headers=h)
    share = client.post(
        f"/businesses/{biz}/shares", headers=h, json={"lender_org": "Coop Bank"}
    ).json()
    token = share["link"].rsplit("/l/", 1)[1]
    client.post(f"/consents/{consent_id(client, h, 'share_lender')}/revoke", headers=h)
    assert client.get(f"/l/{token}").json()["code"] == "share_revoked"


def test_withdrawing_helper_consent_removes_the_helper(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client, phone=new_phone())
    _, sphone = sahayak(client)
    client.post(f"/businesses/{biz}/sahayaks", headers=h, json={"phone": sphone})
    client.post(f"/consents/{consent_id(client, h, 'sahayak_help')}/revoke", headers=h)
    links = db.execute(select(SahayakLink).where(SahayakLink.business_id == biz)).scalars()
    assert all(link.revoked_at is not None for link in links)


def test_withdrawing_bank_consent_stops_refresh_and_aa(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    handle = start["redirect_url"].rsplit("/", 1)[1]
    client.post(f"/consents/{start['consent_id']}/revoke", headers=h)
    active = {c["purpose"] for c in client.get("/consents", headers=h).json() if c["active"]}
    assert not active & {"aa_fetch", "monthly_refresh"}
    aa = get_adapters().aa
    assert isinstance(aa, MockAccountAggregator)
    assert aa.consent_status(handle).status == "REVOKED"
