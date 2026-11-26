"""KYC through a licensed provider (PAN verification / DigiLocker)."""

import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.adapters.errors import AdapterError, NotConfiguredError
from app.core.config import Settings

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


@dataclass(frozen=True)
class KYCResult:
    verified: bool
    registered_name: str | None
    reason: str


class KYCProvider(Protocol):
    name: str
    sandbox: bool

    def verify_pan(self, pan: str, name: str) -> KYCResult: ...


class MockKYC:
    """Sandbox KYC: any well-formed PAN verifies and returns the given name in upper case,
    except PANs ending in 'X' (used by tests and the identity-theft red-team case)."""

    name = "mock-kyc"
    sandbox = True

    def verify_pan(self, pan: str, name: str) -> KYCResult:
        pan = pan.strip().upper()
        if not PAN_RE.match(pan):
            return KYCResult(False, None, "PAN format invalid")
        if pan.endswith("X"):
            return KYCResult(True, "SOMEONE ELSE", "PAN belongs to another person")
        return KYCResult(True, name.upper(), "verified (sandbox)")


class HttpKYC:
    """Real adapter for a licensed PAN-verification API (Setu / Surepass style)."""

    name = "kyc-http"
    sandbox = False

    def __init__(self, settings: Settings) -> None:
        if not (settings.kyc_api_key and settings.kyc_base_url):
            raise NotConfiguredError("KYC_API_KEY / KYC_BASE_URL missing")
        self.client = httpx.Client(
            base_url=settings.kyc_base_url,
            timeout=20,
            headers={"Authorization": f"Bearer {settings.kyc_api_key}"},
        )

    def verify_pan(self, pan: str, name: str) -> KYCResult:
        try:
            res = self.client.post("/api/v1/pan/verify", json={"pan": pan, "name": name})
            res.raise_for_status()
            data: dict[str, Any] = res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterError(f"kyc: {exc}") from exc
        return KYCResult(
            bool(data.get("valid")), data.get("registered_name"), str(data.get("message", ""))
        )
