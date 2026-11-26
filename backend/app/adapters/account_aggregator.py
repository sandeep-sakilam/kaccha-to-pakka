"""Account Aggregator: consented bank data straight from banks (Setu AA sandbox for real)."""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Protocol

import httpx

from app.adapters.errors import AdapterError, NotConfiguredError
from app.core.config import Settings
from app.core.money import to_paise


@dataclass(frozen=True)
class AATransaction:
    txn_date: date
    amount_paise: int
    direction: str
    counterparty_vpa: str | None
    counterparty_name: str | None
    utr: str | None
    balance_after_paise: int | None
    narration: str


@dataclass(frozen=True)
class AAAccount:
    masked_account: str
    holder_name: str
    bank: str
    transactions: list[AATransaction]


@dataclass(frozen=True)
class AAConsent:
    handle: str
    redirect_url: str
    status: str  # PENDING, ACTIVE, REJECTED, REVOKED


class AccountAggregator(Protocol):
    name: str
    sandbox: bool

    def create_consent(self, phone: str, months: int, purpose: str) -> AAConsent: ...
    def consent_status(self, handle: str) -> AAConsent: ...
    def fetch(self, handle: str, months: int) -> list[AAAccount]: ...
    def revoke(self, handle: str) -> None: ...


@dataclass
class MockAccountAggregator:
    """Sandbox AA. Profiles can be registered per phone (seed data); otherwise a deterministic
    synthetic account is generated from the phone number."""

    name: str = "mock-aa"
    sandbox: bool = True
    profiles: dict[str, list[AAAccount]] = field(default_factory=dict)
    consents: dict[str, tuple[str, str]] = field(default_factory=dict)  # handle -> (phone, status)

    def register(self, phone: str, accounts: list[AAAccount]) -> None:
        self.profiles[phone] = accounts

    def create_consent(self, phone: str, months: int, purpose: str) -> AAConsent:
        handle = (
            "aa-"
            + hashlib.sha256(f"{phone}:{purpose}:{len(self.consents)}".encode()).hexdigest()[:16]
        )
        self.consents[handle] = (phone, "PENDING")
        return AAConsent(handle, f"/sandbox/aa/approve/{handle}", "PENDING")

    def approve(self, handle: str, approve: bool = True) -> None:
        phone, _ = self.consents[handle]
        self.consents[handle] = (phone, "ACTIVE" if approve else "REJECTED")

    def consent_status(self, handle: str) -> AAConsent:
        if handle not in self.consents:
            raise AdapterError("unknown consent handle")
        return AAConsent(handle, f"/sandbox/aa/approve/{handle}", self.consents[handle][1])

    def revoke(self, handle: str) -> None:
        if handle in self.consents:
            self.consents[handle] = (self.consents[handle][0], "REVOKED")

    def fetch(self, handle: str, months: int) -> list[AAAccount]:
        phone, status = self.consents.get(handle, ("", "UNKNOWN"))
        if status != "ACTIVE":
            raise AdapterError(f"consent not active: {status}")
        if phone in self.profiles:
            return self.profiles[phone]
        return [synthetic_account(phone, months)]


def synthetic_account(phone: str, months: int, end: date | None = None) -> AAAccount:
    rng = random.Random(phone)  # noqa: S311  (deterministic sandbox data, not security)
    end = end or date.today()
    start = end - timedelta(days=30 * months)
    balance = 2_000_000
    txns: list[AATransaction] = []
    day = start
    n = 0
    while day <= end:
        for _ in range(rng.randint(0, 3)):
            n += 1
            inflow = rng.random() < 0.6
            amount = rng.randint(200, 8000) * 100
            balance += amount if inflow else -min(amount, balance)
            vpa = f"cust{rng.randint(1, 30)}@okaxis" if inflow else f"supp{rng.randint(1, 6)}@oksbi"
            txns.append(
                AATransaction(
                    day,
                    amount,
                    "in" if inflow else "out",
                    vpa,
                    vpa.split("@")[0].upper(),
                    f"6{n:011d}",
                    balance,
                    f"UPI/{vpa}",
                )
            )
        day += timedelta(days=1)
    return AAAccount("XXXX" + phone[-4:], "SANDBOX HOLDER", "Sandbox Bank", txns)


class SetuAccountAggregator:
    """Real adapter for Setu's FIU APIs (sandbox or production per AA_BASE_URL)."""

    name = "setu-aa"
    sandbox = False

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not (settings.aa_client_id and settings.aa_client_secret):
            raise NotConfiguredError("AA_CLIENT_ID / AA_CLIENT_SECRET missing")
        self.s = settings
        self.client = client or httpx.Client(
            base_url=settings.aa_base_url,
            timeout=30,
            headers={
                "x-client-id": settings.aa_client_id,
                "x-client-secret": settings.aa_client_secret,
                "x-product-instance-id": settings.aa_product_instance_id,
            },
        )

    def _call(self, method: str, path: str, **kw: Any) -> Any:
        try:
            res = self.client.request(method, path, **kw)
            res.raise_for_status()
            return res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterError(f"setu {path}: {exc}") from exc

    def create_consent(self, phone: str, months: int, purpose: str) -> AAConsent:
        data = self._call(
            "POST",
            "/v2/consents",
            json={
                "consentDuration": {"unit": "MONTH", "value": 12},
                "vua": f"{phone.lstrip('+')[-10:]}@onemoney",
                "dataRange": {
                    "from": (date.today() - timedelta(days=30 * months)).isoformat(),
                    "to": date.today().isoformat(),
                },
                "context": [],
                "purpose": {"code": "101", "text": purpose},
            },
        )
        return AAConsent(str(data["id"]), str(data.get("url", "")), str(data.get("status")))

    def consent_status(self, handle: str) -> AAConsent:
        data = self._call("GET", f"/v2/consents/{handle}")
        return AAConsent(handle, str(data.get("url", "")), str(data.get("status")))

    def revoke(self, handle: str) -> None:
        self._call("POST", f"/v2/consents/{handle}/revoke")

    def fetch(self, handle: str, months: int) -> list[AAAccount]:
        session = self._call(
            "POST",
            "/v2/sessions",
            json={
                "consentId": handle,
                "dataRange": {
                    "from": (date.today() - timedelta(days=30 * months)).isoformat() + "T00:00:00Z",
                    "to": date.today().isoformat() + "T00:00:00Z",
                },
                "format": "json",
            },
        )
        data = self._call("GET", f"/v2/sessions/{session['id']}")
        accounts: list[AAAccount] = []
        for fip in data.get("fips", []):
            for acc in fip.get("accounts", []):
                fi = acc.get("data", {}).get("account", {})
                holder = fi.get("profile", {}).get("holders", {}).get("holder", {})
                txns = [
                    AATransaction(
                        date.fromisoformat(t["valueDate"][:10]),
                        to_paise(str(t["amount"])),
                        "in" if t["type"] == "CREDIT" else "out",
                        _vpa_from_narration(t.get("narration", "")),
                        None,
                        t.get("reference"),
                        to_paise(str(t["currentBalance"])) if t.get("currentBalance") else None,
                        t.get("narration", ""),
                    )
                    for t in fi.get("transactions", {}).get("transaction", [])
                ]
                accounts.append(
                    AAAccount(
                        acc.get("maskedAccNumber", ""),
                        holder.get("name", ""),
                        fip.get("fipID", ""),
                        txns,
                    )
                )
        return accounts


def _vpa_from_narration(narration: str) -> str | None:
    for part in narration.replace("/", " ").split():
        if "@" in part:
            return part.lower()
    return None
