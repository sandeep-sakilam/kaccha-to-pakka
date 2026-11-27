"""Identity theft defence through the real API flow: onboarding with full name and PAN (KYC),
bank link through Account Aggregator, assessment."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.adapters.account_aggregator import AAAccount, AATransaction, MockAccountAggregator
from app.adapters.registry import get_adapters
from tests.conftest import new_phone, setup_business


def bank_with_holder(phone: str, holder: str) -> None:
    aa = get_adapters().aa
    assert isinstance(aa, MockAccountAggregator)
    today = date.today()
    aa.register(
        phone,
        [
            AAAccount(
                "XXXX9999",
                holder,
                "Sandbox Bank",
                [
                    AATransaction(
                        today - timedelta(days=d),
                        250_000,
                        "in",
                        f"c{d % 9}@okaxis",
                        "C",
                        f"7{d:011d}",
                        None,
                        "UPI",
                    )
                    for d in range(3, 200, 3)
                ],
            )
        ],
    )


def link_bank_and_assess(client: TestClient, h: dict[str, str], biz: str) -> dict[str, object]:
    start = client.post(f"/businesses/{biz}/aa/consent", json={}, headers=h).json()
    client.post(
        f"/sandbox/aa/{start['redirect_url'].rsplit('/', 1)[1]}/decide",
        json={"approve": True},
        headers=h,
    )
    client.post(f"/businesses/{biz}/aa/{start['consent_id']}/fetch", headers=h)
    a: dict[str, object] = client.post(f"/businesses/{biz}/assess", headers=h).json()
    return a


def test_someone_elses_bank_account_puts_the_passport_on_hold(client: TestClient) -> None:
    phone = new_phone()
    h, biz = setup_business(client, phone=phone)
    r = client.post(
        "/auth/identity", headers=h, json={"full_name": "Ramesh Kumar Sharma", "pan": "ABCDE1234F"}
    ).json()
    assert r["kyc_status"] == "verified" and r["name"] == "RAMESH KUMAR SHARMA"
    bank_with_holder(phone, "SURESH PATEL")  # the account belongs to someone else
    a = link_bank_and_assess(client, h, biz)
    assert a["status"] == "on_hold"
    assert any(f["code"] == "holder_name_mismatch" for f in a["flags"])  # type: ignore[attr-defined]
    p = client.post(f"/businesses/{biz}/passport", headers=h).json()
    assert p["status"] == "on_hold"


def test_own_bank_account_passes(client: TestClient) -> None:
    phone = new_phone()
    h, biz = setup_business(client, phone=phone)
    client.post(
        "/auth/identity", headers=h, json={"full_name": "Ramesh Kumar Sharma", "pan": "ABCDE1234F"}
    )
    bank_with_holder(phone, "RAMESH K SHARMA")
    a = link_bank_and_assess(client, h, biz)
    assert not any(f["code"] == "holder_name_mismatch" for f in a["flags"])  # type: ignore[attr-defined]


def test_pan_of_another_person_holds(client: TestClient) -> None:
    h, biz = setup_business(client, phone=new_phone())
    r = client.post(
        "/auth/identity", headers=h, json={"full_name": "Ramesh Sharma", "pan": "ABCDE1234X"}
    ).json()
    assert r["kyc_status"] == "name_mismatch"
    a = client.post(f"/businesses/{biz}/assess", headers=h).json()
    assert any(f["code"] == "kyc_name_mismatch" for f in a["flags"])


def test_name_without_pan_is_self_declared(client: TestClient) -> None:
    h, _ = setup_business(client, phone=new_phone())
    r = client.post("/auth/identity", headers=h, json={"full_name": "Meena Devi"}).json()
    assert r["kyc_status"] == "self_declared"
    assert client.get("/auth/me", headers=h).json()["name"] == "Meena Devi"


def test_full_name_interview_rule(client: TestClient) -> None:
    from tests.conftest import login

    h = login(client)
    r = client.post(
        "/onboarding/interpret",
        headers=h,
        json={
            "question": "full_name",
            "transcript": "mera naam Ramesh Kumar Sharma hai",
            "language": "en",
        },
    ).json()
    assert r["value"] == "Ramesh Kumar Sharma" and r["understood"]
