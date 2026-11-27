"""Adapter selection. Each provider setting is "mock", "real" or "auto" (default):
auto uses the real adapter when its keys are present in .env and the mock otherwise.
Tests force "mock". Whatever runs as a mock is reported as Sandbox to the UI."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.adapters.account_aggregator import (
    AccountAggregator,
    MockAccountAggregator,
    SetuAccountAggregator,
)
from app.adapters.ai import AIProvider, AnthropicAI, GeminiAI, MockAI, SarvamAI
from app.adapters.errors import NotConfiguredError
from app.adapters.gateway import AIGateway
from app.adapters.kyc import HttpKYC, KYCProvider, MockKYC
from app.adapters.messaging import SMS, MetaWhatsApp, MockSMS, MockWhatsApp, Msg91SMS, WhatsApp
from app.adapters.payments import CashfreeGateway, MockPaymentGateway, PaymentGateway
from app.adapters.storage import LocalStorage, MemoryStorage, S3Storage, Storage
from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)


def _pick(mode: str, real: Callable[[], Any], mock: Callable[[], Any], what: str) -> Any:
    if mode == "mock":
        return mock()
    try:
        return real()
    except NotConfiguredError as exc:
        if mode == "real":
            log.warning(
                "%s: real adapter requested but not configured (%s); using Sandbox", what, exc
            )
        return mock()


@dataclass
class Adapters:
    ai: AIGateway
    aa: AccountAggregator
    payments: PaymentGateway
    whatsapp: WhatsApp
    sms: SMS
    kyc: KYCProvider
    storage: Storage
    # Sandbox businesses (seeded demo data) always use the simulated gateway, even when real
    # payment keys are set, so a demo never moves real money.
    sandbox_payments: MockPaymentGateway | None = None

    def __post_init__(self) -> None:
        if self.sandbox_payments is None:
            self.sandbox_payments = (
                self.payments
                if isinstance(self.payments, MockPaymentGateway)
                else MockPaymentGateway()
            )

    def sandbox_status(self) -> dict[str, bool]:
        return {
            "ai": self.ai.sandbox,
            "account_aggregator": self.aa.sandbox,
            "payments": self.payments.sandbox,
            "whatsapp": self.whatsapp.sandbox,
            "sms": self.sms.sandbox,
            "kyc": self.kyc.sandbox,
            "storage": self.storage.sandbox,
        }


def _fallback(s: Settings) -> AIProvider:
    if s.fallback_ai_vendor == "anthropic":
        return AnthropicAI(s)
    return GeminiAI(s)


def build_adapters(s: Settings) -> Adapters:
    primary: AIProvider = _pick(s.ai_provider, lambda: SarvamAI(s), MockAI, "ai")
    fallback: AIProvider = _pick(
        s.fallback_ai_provider, lambda: _fallback(s), MockAI, "fallback_ai"
    )
    storage: Storage
    if s.storage_provider == "memory":
        storage = MemoryStorage()
    elif s.storage_provider == "s3":
        storage = _pick(
            "real", lambda: S3Storage(s), lambda: LocalStorage(s.local_storage_dir), "storage"
        )
    else:
        storage = LocalStorage(s.local_storage_dir)
    return Adapters(
        ai=AIGateway(primary=primary, fallback=fallback),
        aa=_pick(s.aa_provider, lambda: SetuAccountAggregator(s), MockAccountAggregator, "aa"),
        payments=_pick(
            s.payments_provider,
            lambda: CashfreeGateway(s),
            lambda: MockPaymentGateway(s.verification_vpa),
            "payments",
        ),
        whatsapp=_pick(s.whatsapp_provider, lambda: MetaWhatsApp(s), MockWhatsApp, "whatsapp"),
        sms=_pick(s.sms_provider, lambda: Msg91SMS(s), MockSMS, "sms"),
        kyc=_pick(s.kyc_provider, lambda: HttpKYC(s), MockKYC, "kyc"),
        storage=storage,
    )


@lru_cache
def get_adapters() -> Adapters:
    return build_adapters(get_settings())
