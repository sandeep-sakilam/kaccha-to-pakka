"""KYC through a licensed provider (PAN verification / DigiLocker), and the same provider's
business registration lookups (GSTIN, Udyam)."""

import re
from dataclasses import dataclass
from datetime import date
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


@dataclass(frozen=True)
class RegistrationResult:
    """What the government register says about a GSTIN or Udyam number."""

    found: bool
    status: str  # active | cancelled | not_found
    legal_name: str | None = None  # the proprietor or company
    trade_name: str | None = None  # the shop name, when registered
    registered_on: date | None = None  # GST effective date / Udyam registration date
    started_on: date | None = None  # Udyam: commencement date declared to the government
    reason: str = ""


class KYCProvider(Protocol):
    name: str
    sandbox: bool

    def verify_pan(self, pan: str, name: str) -> KYCResult: ...
    def verify_gstin(self, gstin: str, name_hint: str) -> RegistrationResult: ...
    def verify_udyam(self, udyam: str, name_hint: str) -> RegistrationResult: ...


# Sandbox register: numbers used by the demo seed and tests. Any other well-formed number is
# found under the name it was given (Sandbox), registered on 1 April 2021.
SANDBOX_REGISTER: dict[str, RegistrationResult] = {}


def _sandbox_lookup(number: str, name_hint: str) -> RegistrationResult:
    number = number.strip().upper()
    if number in SANDBOX_REGISTER:
        return SANDBOX_REGISTER[number]
    if number.endswith("0000"):
        return RegistrationResult(False, "not_found", reason="not in the register (sandbox)")
    if number.endswith("9999") or (len(number) == 15 and number[11] == "X"):
        return RegistrationResult(
            True, "active", "SOMEONE ELSE", "OTHER TRADERS", date(2021, 4, 1), None, "sandbox"
        )
    return RegistrationResult(
        True, "active", None, name_hint.upper(), date(2021, 4, 1), None, "found (sandbox)"
    )


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

    def verify_gstin(self, gstin: str, name_hint: str) -> RegistrationResult:
        return _sandbox_lookup(gstin, name_hint)

    def verify_udyam(self, udyam: str, name_hint: str) -> RegistrationResult:
        return _sandbox_lookup(udyam, name_hint)


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

    def _lookup(self, path: str, payload: dict[str, str]) -> RegistrationResult:
        try:
            res = self.client.post(path, json=payload)
            if res.status_code == 404:
                return RegistrationResult(False, "not_found", reason="not in the register")
            res.raise_for_status()
            data: dict[str, Any] = res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterError(f"kyc: {exc}") from exc

        def day(key: str) -> date | None:
            v = data.get(key)
            try:
                return date.fromisoformat(str(v)[:10]) if v else None
            except ValueError:
                return None

        status = str(data.get("status", "active")).lower()
        return RegistrationResult(
            True,
            "cancelled" if status in {"cancelled", "inactive", "suspended"} else "active",
            data.get("legal_name"),
            data.get("trade_name"),
            day("registration_date"),
            day("commencement_date"),
            str(data.get("message", "")),
        )

    def verify_gstin(self, gstin: str, name_hint: str) -> RegistrationResult:
        return self._lookup("/api/v1/gstin/verify", {"gstin": gstin})

    def verify_udyam(self, udyam: str, name_hint: str) -> RegistrationResult:
        return self._lookup("/api/v1/udyam/verify", {"udyam": udyam})
