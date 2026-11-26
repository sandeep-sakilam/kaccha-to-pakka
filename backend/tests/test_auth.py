from fastapi.testclient import TestClient

from tests.conftest import login, new_phone


def _otp(client: TestClient, phone: str, device: str = "device-aaaa-1") -> dict[str, object]:
    sent = client.post("/auth/otp/request", json={"phone": phone}).json()
    assert sent["sandbox_code"] and len(sent["sandbox_code"]) == 6
    res = client.post(
        "/auth/otp/verify", json={"phone": phone, "code": sent["sandbox_code"], "device_id": device}
    )
    assert res.status_code == 200, res.text
    body: dict[str, object] = res.json()
    return body


def test_bad_phone_rejected(client: TestClient) -> None:
    res = client.post("/auth/otp/request", json={"phone": "12345"})
    assert res.status_code == 401 and res.json()["code"] == "bad_phone"


def test_signup_otp_then_pin(client: TestClient) -> None:
    phone = new_phone()
    res = _otp(client, phone)
    assert res["stage"] == "otp" and res["has_pin"] is False and res["new_device"] is False
    h = {"Authorization": f"Bearer {res['token']}"}
    assert client.get("/auth/me", headers=h).json()["code"] == "pin_required"
    assert (
        client.post("/auth/pin/set", json={"pin": "1234"}, headers=h).json()["code"] == "weak_pin"
    )
    assert client.post("/auth/pin/set", json={"pin": "4826"}, headers=h).status_code == 200
    me = client.get("/auth/me", headers=h).json()
    assert me["phone"] == phone and me["roles"] == ["owner"]


def test_wrong_otp_counts_attempts(client: TestClient) -> None:
    phone = new_phone()
    client.post("/auth/otp/request", json={"phone": phone})
    for _ in range(5):
        r = client.post(
            "/auth/otp/verify",
            json={"phone": phone, "code": "000000", "device_id": "device-aaaa-1"},
        )
        assert r.json()["code"] in {"otp_wrong", "otp_locked"}
    r = client.post(
        "/auth/otp/verify", json={"phone": phone, "code": "000000", "device_id": "device-aaaa-1"}
    )
    assert r.json()["code"] == "otp_locked"


def test_otp_alone_does_not_open_existing_profile(client: TestClient) -> None:
    """Shared phone: a son who receives the OTP still needs his mother's PIN."""
    phone = new_phone()
    login(client, phone, device="device-mom-1", pin="4826")
    res = _otp(client, phone, device="device-mom-1")
    assert res["has_pin"] is True
    h = {"Authorization": f"Bearer {res['token']}"}
    assert client.get("/auth/me", headers=h).status_code == 401
    assert (
        client.post("/auth/pin/set", json={"pin": "9137"}, headers=h).json()["code"] == "pin_exists"
    )
    assert (
        client.post("/auth/pin/verify", json={"pin": "1111"}, headers=h).json()["code"]
        == "pin_wrong"
    )
    assert client.post("/auth/pin/verify", json={"pin": "4826"}, headers=h).status_code == 200


def test_pin_login_needs_bound_device(client: TestClient) -> None:
    phone = new_phone()
    login(client, phone, device="device-bound-1")
    ok = client.post(
        "/auth/login", json={"phone": phone, "pin": "4826", "device_id": "device-bound-1"}
    )
    assert ok.status_code == 200 and ok.json()["stage"] == "full"
    other = client.post(
        "/auth/login", json={"phone": phone, "pin": "4826", "device_id": "device-other-1"}
    )
    assert other.json()["code"] == "otp_required"


def test_new_device_is_flagged(client: TestClient) -> None:
    phone = new_phone()
    login(client, phone, device="device-first-1")
    res = _otp(client, phone, device="device-second-1")
    assert res["new_device"] is True


def test_pin_lockout(client: TestClient) -> None:
    phone = new_phone()
    login(client, phone, device="device-lock-1")
    for _ in range(5):
        client.post(
            "/auth/login", json={"phone": phone, "pin": "0001", "device_id": "device-lock-1"}
        )
    r = client.post(
        "/auth/login", json={"phone": phone, "pin": "4826", "device_id": "device-lock-1"}
    )
    assert r.json()["code"] == "pin_locked"


def test_logout(client: TestClient) -> None:
    h = login(client)
    assert client.post("/auth/logout", headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).json()["code"] == "session_expired"
