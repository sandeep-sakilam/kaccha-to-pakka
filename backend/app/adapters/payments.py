"""Payment gateway with reverse penny drop: the confirmer pays ₹1 from their own UPI app to our
verification UPI ID; the gateway returns the payer's UPI ID and bank-registered name; we refund."""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.adapters.errors import AdapterError, NotConfiguredError
from app.core.config import Settings


@dataclass(frozen=True)
class PennyDropRequest:
    ref: str
    pay_to_vpa: str
    amount_paise: int
    upi_link: str


@dataclass(frozen=True)
class PennyDropResult:
    ref: str
    status: str  # PENDING, PAID, EXPIRED, FAILED
    payer_vpa: str | None = None
    payer_name: str | None = None
    utr: str | None = None
    refunded: bool = False


class PaymentGateway(Protocol):
    name: str
    sandbox: bool

    def create_reverse_penny_drop(self, purpose_ref: str) -> PennyDropRequest: ...
    def get_result(self, ref: str) -> PennyDropResult: ...
    def refund(self, ref: str) -> None: ...


def _upi_link(vpa: str, ref: str, amount_paise: int) -> str:
    return f"upi://pay?pa={vpa}&pn=KacchaToPakkaVerify&am={amount_paise / 100:.2f}&tn={ref}&cu=INR"


@dataclass
class MockPaymentGateway:
    """Simulated gateway, labelled Sandbox. `simulate_payment` stands in for the confirmer
    paying ₹1 from their UPI app."""

    verification_vpa: str = "verify@sandbox"
    name: str = "simulated-gateway"
    sandbox: bool = True
    requests: dict[str, PennyDropResult] = field(default_factory=dict)

    def create_reverse_penny_drop(self, purpose_ref: str) -> PennyDropRequest:
        ref = (
            "rpd_" + hashlib.sha256(f"{purpose_ref}:{len(self.requests)}".encode()).hexdigest()[:14]
        )
        self.requests[ref] = PennyDropResult(ref, "PENDING")
        return PennyDropRequest(
            ref, self.verification_vpa, 100, _upi_link(self.verification_vpa, ref, 100)
        )

    def simulate_payment(self, ref: str, payer_vpa: str, payer_name: str) -> None:
        if ref not in self.requests:
            raise AdapterError("unknown penny drop ref")
        utr = "5" + hashlib.sha256(ref.encode()).hexdigest()[:11].upper()
        self.requests[ref] = PennyDropResult(ref, "PAID", payer_vpa.lower(), payer_name, utr)

    def get_result(self, ref: str) -> PennyDropResult:
        if ref not in self.requests:
            raise AdapterError("unknown penny drop ref")
        return self.requests[ref]

    def refund(self, ref: str) -> None:
        r = self.get_result(ref)
        self.requests[ref] = PennyDropResult(
            r.ref, r.status, r.payer_vpa, r.payer_name, r.utr, True
        )


class CashfreeGateway:
    """Real adapter for Cashfree's reverse penny drop (Verification Suite) in test or live mode."""

    name = "cashfree"
    sandbox = False

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not (settings.payments_client_id and settings.payments_client_secret):
            raise NotConfiguredError("PAYMENTS_CLIENT_ID / PAYMENTS_CLIENT_SECRET missing")
        self.client = client or httpx.Client(
            base_url=settings.payments_base_url,
            timeout=20,
            headers={
                "x-client-id": settings.payments_client_id,
                "x-client-secret": settings.payments_client_secret,
                "x-api-version": "2023-08-01",
            },
        )

    def _call(self, method: str, path: str, **kw: Any) -> Any:
        try:
            res = self.client.request(method, path, **kw)
            res.raise_for_status()
            return res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterError(f"cashfree {path}: {exc}") from exc

    def create_reverse_penny_drop(self, purpose_ref: str) -> PennyDropRequest:
        data = self._call(
            "POST",
            "/verification/reverse-penny-drop",
            json={"verification_id": purpose_ref[:50], "name": "verify"},
        )
        ref = str(data.get("ref_id") or data.get("verification_id"))
        vpa = str(data.get("upi_id", ""))
        return PennyDropRequest(
            ref, vpa, 100, str(data.get("upi_link") or _upi_link(vpa, ref, 100))
        )

    def get_result(self, ref: str) -> PennyDropResult:
        data = self._call("GET", "/verification/remitter/status", params={"ref_id": ref})
        status = str(data.get("status", "PENDING")).upper()
        mapped = "PAID" if status in {"SUCCESS", "VALID"} else status
        return PennyDropResult(
            ref,
            mapped,
            (data.get("vpa") or "").lower() or None,
            data.get("name_at_bank"),
            data.get("utr"),
        )

    def refund(self, ref: str) -> None:
        return None  # Cashfree refunds the ₹1 automatically for reverse penny drop.
