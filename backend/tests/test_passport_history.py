"""The band over time: every passport issued, oldest first, for the owner and the lender."""

from fastapi.testclient import TestClient

from tests.conftest import login, setup_business


def _link_bank(client: TestClient, h: dict[str, str], biz: str) -> None:
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    client.post(
        f"/sandbox/aa/{start['redirect_url'].rsplit('/', 1)[1]}/decide",
        json={"approve": True},
        headers=h,
    )
    client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h)


def test_history_shows_the_band_improving(client: TestClient) -> None:
    h, biz = setup_business(client)
    client.post(f"/businesses/{biz}/passport", headers=h)  # nothing proven yet
    _link_bank(client, h, biz)
    client.post(f"/businesses/{biz}/passport", headers=h)  # 12 months of bank data
    hist = client.get(f"/businesses/{biz}/passport/history", headers=h).json()
    assert len(hist) == 2
    assert hist[0]["band"] == "U" and hist[1]["band"] in {"C", "D", "E"}
    assert hist[0]["issued_at"] <= hist[1]["issued_at"]
    assert all(x["rules_version"] for x in hist)


def test_lender_sees_the_trend_with_any_scope(client: TestClient) -> None:
    h, biz = setup_business(client)
    client.post(f"/businesses/{biz}/passport", headers=h)
    _link_bank(client, h, biz)
    client.post(f"/businesses/{biz}/passport", headers=h)
    s = client.post(
        f"/businesses/{biz}/shares", headers=h, json={"lender_org": "Coop Bank", "scope": "summary"}
    ).json()
    view = client.get(f"/l/{s['link'].rsplit('/l/', 1)[1]}").json()
    assert view["history"][0]["band"] == "U" and len(view["history"]) == 2
    assert set(view["history"][0]) == {"issued_at", "band", "status"}  # nothing more


def test_history_is_private(client: TestClient) -> None:
    h, biz = setup_business(client)
    client.post(f"/businesses/{biz}/passport", headers=h)
    other = login(client)
    assert client.get(f"/businesses/{biz}/passport/history", headers=other).status_code == 403
