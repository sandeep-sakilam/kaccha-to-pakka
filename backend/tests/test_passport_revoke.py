from fastapi.testclient import TestClient

from tests.conftest import login, new_phone, setup_business


def test_owner_revokes_passport(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    p = client.post(f"/businesses/{biz}/passport", headers=h).json()
    share = client.post(
        f"/businesses/{biz}/shares", headers=h, json={"lender_org": "Coop Bank"}
    ).json()
    r = client.post(f"/businesses/{biz}/passport/revoke", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    assert client.get(f"/passports/{p['id']}/status").json()["status"] == "revoked"
    verify = client.post("/passports/verify", json={"qr_token": p["qr_token"]}).json()
    assert verify["signature_valid"] is True and verify["status"] == "revoked"
    lender = client.get(f"/l/{share['link'].rsplit('/l/', 1)[1]}").json()
    assert lender["passport"]["status"] == "revoked"
    # A new passport can be made afterwards.
    assert client.post(f"/businesses/{biz}/passport", headers=h).json()["status"] == "valid"


def test_only_owner_can_revoke(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    client.post(f"/businesses/{biz}/passport", headers=h)
    other = login(client, device="device-other-77")
    assert client.post(f"/businesses/{biz}/passport/revoke", headers=other).status_code == 403


def test_revoke_without_passport(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    assert (
        client.post(f"/businesses/{biz}/passport/revoke", headers=h).json()["code"] == "no_passport"
    )
