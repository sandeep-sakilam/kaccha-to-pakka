"""Mother and son share one phone number: each has a profile and a PIN; neither can open the
other's passport."""

from fastapi.testclient import TestClient

from tests.conftest import login, new_phone


def otp(client: TestClient, phone: str, device: str) -> dict[str, object]:
    code = client.post("/auth/otp/request", json={"phone": phone}).json()["sandbox_code"]
    body: dict[str, object] = client.post(
        "/auth/otp/verify", json={"phone": phone, "code": code, "device_id": device}
    ).json()
    return body


def test_two_profiles_on_one_phone(client: TestClient) -> None:
    phone = new_phone()
    mom = login(client, phone, device="device-shared-1", pin="4826")
    client.post("/consents", json={"purpose": "build_passport"}, headers=mom)
    biz = client.post(
        "/businesses", headers=mom, json={"name": "Meena Namkeen", "category": "namkeen"}
    ).json()["id"]
    # The son gets the OTP on the same phone and makes his own profile.
    r = otp(client, phone, "device-shared-1")
    assert r["profiles"] == 1 and r["has_pin"] is True
    son = {"Authorization": f"Bearer {r['token']}"}
    assert (
        client.post("/auth/profile/new", headers=son, json={"name": "Raju", "pin": "4826"}).json()[
            "code"
        ]
        == "pin_in_use"
    )
    made = client.post("/auth/profile/new", headers=son, json={"name": "Raju", "pin": "7391"})
    assert made.json() == {"stage": "full", "profile_name": "Raju"}
    me = client.get("/auth/me", headers=son).json()
    assert me["profile_name"] == "Raju" and me["phone"] == phone
    assert client.get(f"/businesses/{biz}", headers=son).status_code == 403
    assert client.get("/businesses", headers=son).json() == []

    # Next login: the PIN decides whose profile opens.
    r2 = otp(client, phone, "device-shared-1")
    assert r2["profiles"] == 2
    h = {"Authorization": f"Bearer {r2['token']}"}
    client.post("/auth/pin/verify", headers=h, json={"pin": "7391"})
    assert client.get("/auth/me", headers=h).json()["profile_name"] == "Raju"
    r3 = otp(client, phone, "device-shared-1")
    h3 = {"Authorization": f"Bearer {r3['token']}"}
    client.post("/auth/pin/verify", headers=h3, json={"pin": "4826"})
    assert client.get("/auth/me", headers=h3).json()["profile_name"] == "main"
    assert [b["id"] for b in client.get("/businesses", headers=h3).json()] == [biz]
    # A wrong PIN opens nobody.
    r4 = otp(client, phone, "device-shared-1")
    h4 = {"Authorization": f"Bearer {r4['token']}"}
    assert (
        client.post("/auth/pin/verify", headers=h4, json={"pin": "1357"}).json()["code"]
        == "pin_wrong"
    )
    # PIN-only login on the bound device also picks the right profile.
    pin_login = client.post(
        "/auth/login", json={"phone": phone, "pin": "7391", "device_id": "device-shared-1"}
    ).json()
    h5 = {"Authorization": f"Bearer {pin_login['token']}"}
    assert client.get("/auth/me", headers=h5).json()["profile_name"] == "Raju"


def test_profile_name_must_be_new(client: TestClient) -> None:
    phone = new_phone()
    login(client, phone, device="device-shared-2")
    r = otp(client, phone, "device-shared-2")
    h = {"Authorization": f"Bearer {r['token']}"}
    assert (
        client.post("/auth/profile/new", headers=h, json={"name": "main", "pin": "7391"}).json()[
            "code"
        ]
        == "profile_exists"
    )
