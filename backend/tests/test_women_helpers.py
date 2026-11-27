"""A woman-owned business can only be helped by women helpers, unless the owner changes it."""

from fastapi.testclient import TestClient

from tests.conftest import login, new_phone
from tests.test_sahayak import sahayak


def _woman_owner(client: TestClient) -> tuple[dict[str, str], str]:
    h = login(client, new_phone())
    client.post("/consents", json={"purpose": "build_passport"}, headers=h)
    r = client.post(
        "/businesses",
        json={"name": "Meena Namkeen", "category": "namkeen", "women_owned": True},
        headers=h,
    ).json()
    return h, str(r["id"])


def test_women_owned_business_accepts_only_women_helpers(client: TestClient) -> None:
    h, biz = _woman_owner(client)
    assert client.get(f"/businesses/{biz}", headers=h).json()["women_helpers_only"] is True
    _, man = sahayak(client, "Ramesh BC", "male")
    unknown = new_phone()
    uh = login(client, unknown, device="device-helper-unknown")
    client.post("/sahayak/register", json={"name": "Someone"}, headers=uh)  # gender not given
    _, woman = sahayak(client, "Sunita SHG", "female")
    for phone in (man, unknown):
        r = client.post(f"/businesses/{biz}/sahayaks", headers=h, json={"phone": phone})
        assert r.status_code == 403 and r.json()["code"] == "women_helpers_only"
    r = client.post(f"/businesses/{biz}/sahayaks", headers=h, json={"phone": woman})
    assert r.status_code == 200, r.text


def test_owner_can_turn_it_off(client: TestClient) -> None:
    h, biz = _woman_owner(client)
    client.patch(f"/businesses/{biz}", json={"women_helpers_only": False}, headers=h)
    _, man = sahayak(client, "Ramesh BC", "male")
    r = client.post(f"/businesses/{biz}/sahayaks", headers=h, json={"phone": man})
    assert r.status_code == 200, r.text


def test_other_businesses_are_not_restricted_by_default(client: TestClient) -> None:
    from tests.conftest import setup_business

    h, biz = setup_business(client)
    assert client.get(f"/businesses/{biz}", headers=h).json()["women_helpers_only"] is False
    _, man = sahayak(client, "Ramesh BC", "male")
    assert (
        client.post(f"/businesses/{biz}/sahayaks", headers=h, json={"phone": man}).status_code
        == 200
    )


def test_a_helper_cannot_change_the_setting(client: TestClient) -> None:
    h, biz = _woman_owner(client)
    helper_h, woman = sahayak(client, "Sunita SHG", "female")
    client.post(f"/businesses/{biz}/sahayaks", headers=h, json={"phone": woman})
    r = client.patch(f"/businesses/{biz}", json={"women_helpers_only": False}, headers=helper_h)
    assert r.status_code == 403
