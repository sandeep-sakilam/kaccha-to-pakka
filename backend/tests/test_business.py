from datetime import date

from fastapi.testclient import TestClient

from app.core.identifiers import make_gstin, valid_gstin, valid_udyam
from app.modules.business import interview
from tests.conftest import login


def test_gstin_checksum() -> None:
    g = make_gstin("23", "ABCDE1234F")
    assert valid_gstin(g)
    bad = g[:-1] + ("A" if g[-1] != "A" else "B")
    assert not valid_gstin(bad)
    assert valid_gstin("27AAPFU0939F1ZV")  # public example GSTIN
    assert not valid_gstin("27AAPFU0939F1ZX")


def test_udyam_format() -> None:
    assert valid_udyam("UDYAM-MP-23-0012345")
    assert not valid_udyam("UDYAM-MP-23-12")


def test_interview_rules() -> None:
    assert interview.interpret_category("hum namkeen aur sev banate hain").value == "namkeen"
    assert interview.interpret_category("किराना की दुकान").value == "kirana"
    today = date(2026, 11, 26)
    assert interview.interpret_since("2012 se chal rahi hai", today).value == 2012
    assert interview.interpret_since("das saal se", today).value == 2016
    assert interview.interpret_since("15 years", today).value == 2011
    assert interview.interpret_since("पता नहीं", today).understood is False
    assert interview.interpret_place("Rajwada ke paas").value == "Rajwada"
    assert (
        interview.interpret_name("meri dukaan ka naam Sharma Kirana hai").value == "Sharma Kirana"
    )


def test_profile_needs_consent_then_creates(client: TestClient) -> None:
    h = login(client)
    body = {
        "name": "Sharma Kirana",
        "category": "kirana",
        "started_year": 2012,
        "address": "Rajwada",
        "gstin": make_gstin("23", "ABCDE1234F"),
    }
    r = client.post("/businesses", json=body, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "consent_required:build_passport"
    client.post("/consents", json={"purpose": "build_passport"}, headers=h)
    r = client.post("/businesses", json=body, headers=h)
    assert r.status_code == 200, r.text
    biz = r.json()
    assert biz["started_on"] == "2012-01-01"
    assert [b["id"] for b in client.get("/businesses", headers=h).json()] == [biz["id"]]
    r = client.patch(f"/businesses/{biz['id']}", json={"gstin": "BAD"}, headers=h)
    assert r.json()["code"] == "bad_gstin"
    r = client.patch(f"/businesses/{biz['id']}", json={"udyam": "udyam-mp-23-0012345"}, headers=h)
    assert r.json()["udyam"] == "UDYAM-MP-23-0012345"


def test_business_without_ids_is_welcome(client: TestClient) -> None:
    h = login(client)
    client.post("/consents", json={"purpose": "build_passport"}, headers=h)
    r = client.post("/businesses", json={"name": "Thela", "category": "food_stall"}, headers=h)
    assert r.status_code == 200


def test_other_owner_cannot_read(client: TestClient) -> None:
    h1 = login(client)
    client.post("/consents", json={"purpose": "build_passport"}, headers=h1)
    biz = client.post("/businesses", json={"name": "A", "category": "kirana"}, headers=h1).json()
    h2 = login(client, device="device-other-2")
    assert client.get(f"/businesses/{biz['id']}", headers=h2).status_code == 403


def test_interpret_endpoint_with_mock_audio(client: TestClient) -> None:
    import base64

    h = login(client)
    audio = base64.b64encode(b"MOCK:hum kapde silai karte hain").decode()
    r = client.post(
        "/onboarding/interpret",
        json={"question": "category", "audio_b64": audio, "language": "hi"},
        headers=h,
    )
    body = r.json()
    assert body["value"] == "tailor" and body["sandbox"] is True and "सही" in body["confirm"]
