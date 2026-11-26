from datetime import date
from typing import Any

import pytest

from app.adapters.account_aggregator import AAAccount, AATransaction, MockAccountAggregator
from app.adapters.errors import AdapterError
from app.adapters.kyc import MockKYC
from app.adapters.messaging import MockWhatsApp
from app.adapters.payments import MockPaymentGateway
from app.adapters.registry import build_adapters
from app.adapters.storage import LocalStorage, MemoryStorage
from app.core.config import Settings
from app.core.money import format_inr, to_paise

AUTO: dict[str, Any] = {
    k: "auto"
    for k in (
        "ai_provider",
        "fallback_ai_provider",
        "aa_provider",
        "payments_provider",
        "whatsapp_provider",
        "sms_provider",
        "kyc_provider",
    )
}


def test_registry_auto_uses_mocks_without_keys() -> None:
    a = build_adapters(Settings(**AUTO, storage_provider="memory"))
    assert all(a.sandbox_status().values())


def test_registry_auto_uses_real_with_keys() -> None:
    a = build_adapters(Settings(**AUTO, sarvam_api_key="k", storage_provider="memory"))
    assert a.ai.primary.name == "sarvam" and not a.ai.sandbox


def test_registry_mock_mode_overrides_keys() -> None:
    a = build_adapters(Settings(ai_provider="mock", sarvam_api_key="k", storage_provider="memory"))
    assert a.ai.primary.name == "mock"


def test_aa_mock_requires_active_consent() -> None:
    aa = MockAccountAggregator()
    c = aa.create_consent("+919800000001", 12, "build passport")
    with pytest.raises(AdapterError):
        aa.fetch(c.handle, 12)
    aa.approve(c.handle)
    accounts = aa.fetch(c.handle, 12)
    assert accounts[0].transactions
    assert accounts == aa.fetch(c.handle, 12) or accounts[0].masked_account.endswith("0001")


def test_aa_mock_registered_profile() -> None:
    aa = MockAccountAggregator()
    acct = AAAccount(
        "XXXX1",
        "RAKESH",
        "SBI",
        [AATransaction(date(2026, 1, 1), 100, "in", "a@ok", "A", "1", 100, "n")],
    )
    aa.register("+91", [acct])
    c = aa.create_consent("+91", 12, "p")
    aa.approve(c.handle)
    assert aa.fetch(c.handle, 12) == [acct]
    aa.revoke(c.handle)
    assert aa.consent_status(c.handle).status == "REVOKED"


def test_penny_drop_simulation() -> None:
    gw = MockPaymentGateway()
    req = gw.create_reverse_penny_drop("att-1")
    assert req.amount_paise == 100 and req.upi_link.startswith("upi://pay")
    assert gw.get_result(req.ref).status == "PENDING"
    gw.simulate_payment(req.ref, "Supplier@OKSBI", "GUPTA TRADERS")
    res = gw.get_result(req.ref)
    assert res.status == "PAID" and res.payer_vpa == "supplier@oksbi"
    gw.refund(req.ref)
    assert gw.get_result(req.ref).refunded


def test_whatsapp_mock_records_and_can_go_down() -> None:
    wa = MockWhatsApp()
    wa.send("+91", "hi", ["Haan", "Nahi"])
    assert wa.last_to("+91").buttons == ("Haan", "Nahi")  # type: ignore[union-attr]
    wa.down = True
    with pytest.raises(AdapterError):
        wa.send("+91", "x")


def test_kyc_mock() -> None:
    k = MockKYC()
    assert k.verify_pan("ABCDE1234F", "Ramesh").registered_name == "RAMESH"
    assert not k.verify_pan("BAD", "x").verified
    assert k.verify_pan("ABCDE1234X", "x").registered_name == "SOMEONE ELSE"


def test_storage(tmp_path: object) -> None:
    for st in (MemoryStorage(), LocalStorage(str(tmp_path))):
        st.put("a/b.bin", b"123")
        assert st.get("a/b.bin") == b"123" and st.exists("a/b.bin")
        st.delete("a/b.bin")
        assert not st.exists("a/b.bin")
    with pytest.raises(AdapterError):
        LocalStorage(str(tmp_path)).put("../escape", b"x")


def test_money() -> None:
    assert to_paise("1,23,456.50") == 12345650
    assert to_paise("₹ 40,000") == 4000000
    assert to_paise(5) == 500
    assert format_inr(12345650) == "₹1,23,456.50"
    assert format_inr(4000000) == "₹40,000"
    with pytest.raises(ValueError):
        to_paise("abc")
