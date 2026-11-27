"""Udyam / GSTIN numbers checked against the government register (Sandbox register here)."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.kyc import SANDBOX_REGISTER, MockKYC, RegistrationResult
from app.adapters.registry import get_adapters
from app.core.identifiers import make_gstin
from app.modules.business import registration
from app.modules.trust import service as trust
from app.modules.trust.rules import PresenceFeatures, presence_pillar
from tests import factories as f
from tests.conftest import setup_business

UDYAM = "UDYAM-MP-23-0012345"


def test_owner_adds_udyam_and_it_is_verified(client: TestClient) -> None:
    h, biz = setup_business(client, name="Verma Provision Store")
    r = client.patch(f"/businesses/{biz}", json={"udyam": UDYAM.lower()}, headers=h).json()
    assert r["registration_status"] == "verified" and r["registration_source"] == "udyam"
    assert r["registration_name"] == "VERMA PROVISION STORE"


def test_register_entry_in_the_proprietors_own_name_also_agrees(db: Session) -> None:
    SANDBOX_REGISTER["UDYAM-MP-23-0055501"] = RegistrationResult(
        True, "active", "RAMESH KUMAR SHARMA", None, date(2021, 3, 2), date(2009, 6, 1)
    )
    biz = f.business(db, "Sharma Kirana Store", owner_name="Ramesh Kumar Sharma")
    biz.udyam = "UDYAM-MP-23-0055501"
    c = registration.check(db, biz, "test")
    assert (c.status, c.registered_on, c.started_on) == (
        "verified",
        date(2021, 3, 2),
        date(2009, 6, 1),
    )


def test_someone_elses_gstin_puts_the_passport_on_hold(db: Session) -> None:
    biz = f.business(db, "Borrowed Number Store", owner_name="Mohan Lal")
    biz.gstin = make_gstin("23", "ABCDE1234X")  # sandbox: a PAN ending in X is someone else's
    assert registration.check(db, biz, "test").status == "name_mismatch"
    a = trust.assess(db, biz)
    assert a.status == "on_hold"
    assert any(fl["code"] == "registration_name_mismatch" for fl in a.flags)


def test_unknown_and_cancelled_numbers(db: Session) -> None:
    biz = f.business(db, "Ghost Store")
    biz.udyam = "UDYAM-MP-23-0010000"
    assert registration.check(db, biz, "test").status == "not_found"
    SANDBOX_REGISTER["UDYAM-MP-23-0077701"] = RegistrationResult(
        True, "cancelled", None, "GHOST STORE", date(2021, 1, 1)
    )
    biz.udyam = "UDYAM-MP-23-0077701"
    assert registration.check(db, biz, "test").status == "cancelled"
    a = trust.assess(db, biz)
    assert any(fl["code"] == "registration_cancelled" for fl in a.flags)
    assert a.status != "on_hold"  # cancelled is a warning, not a hold


def test_provider_down_keeps_the_previous_answer(db: Session, monkeypatch: object) -> None:
    biz = f.business(db, "Verma Provision Store")
    biz.udyam = UDYAM
    assert registration.check(db, biz, "test").status == "verified"

    def down(self: MockKYC, number: str, hint: str) -> RegistrationResult:
        raise AdapterError("provider down")

    import pytest

    mp = pytest.MonkeyPatch()
    mp.setattr(MockKYC, "verify_udyam", down)
    try:
        assert registration.check(db, biz, "test").status == "failed"
        assert biz.registration_status == "verified"  # not downgraded by an outage
    finally:
        mp.undo()


def test_verified_registration_adds_presence_points_and_a_reason(client: TestClient) -> None:
    base = PresenceFeatures(business_age_years=6, has_shop_front=True)
    reg = PresenceFeatures(business_age_years=6, has_shop_front=True, registration="verified")
    assert presence_pillar(reg) == presence_pillar(base) + 10
    h, biz = setup_business(client, name="Verma Provision Store")
    client.patch(f"/businesses/{biz}", json={"udyam": UDYAM}, headers=h)
    client.post(f"/businesses/{biz}/passport", headers=h)
    ex = client.get(f"/businesses/{biz}/explanation?language=en", headers=h).json()
    assert any("Udyam registration is confirmed" in line for line in ex["positives"])


def test_recheck_endpoint(client: TestClient) -> None:
    h, biz = setup_business(client, name="Verma Provision Store")
    client.patch(f"/businesses/{biz}", json={"gstin": make_gstin("23", "ABCDE1234F")}, headers=h)
    r = client.post(f"/businesses/{biz}/registration/check", headers=h).json()
    assert r["registration_status"] == "verified" and r["registration_source"] == "gstin"
    assert get_adapters().kyc.sandbox
