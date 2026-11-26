"""Reverse penny drop: the confirmer proves control of the exact account in the owner's payments.

They pay ₹1 from their own UPI app to our verification UPI ID. The gateway returns the payer's
UPI ID and bank-registered name; both must match the counterparty in the owner's history. The ₹1
is refunded either way. A friend paying from their own account cannot match, so the confirmation
is rejected and the business gets a red flag for review.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.payments import PennyDropRequest
from app.adapters.registry import get_adapters
from app.core.errors import DomainError
from app.db.models import Counterparty, CounterpartyInvite, Dispute
from app.modules.audit.service import record
from app.modules.reconciliation.names import similarity

NAME_MATCH = 80.0


def start(db: Session, inv: CounterpartyInvite) -> PennyDropRequest:
    if inv.status not in {"sent", "opened"}:
        raise DomainError("This invite can no longer be used", f"invite_{inv.status}", 409)
    try:
        req = get_adapters().payments.create_reverse_penny_drop(f"invite:{inv.id}")
    except AdapterError as exc:
        raise DomainError(
            "Payment check is not working right now. Please try later.", "payments_down", 503
        ) from exc
    inv.penny_ref = req.ref
    record(
        db, f"invite:{inv.id}", "penny_drop.start", f"business:{inv.business_id}", {"ref": req.ref}
    )
    return req


@dataclass(frozen=True)
class ProofResult:
    status: str  # pending, proven, rejected
    reason: str | None
    payer_vpa: str | None = None
    payer_name: str | None = None
    utr: str | None = None


def check(db: Session, inv: CounterpartyInvite) -> ProofResult:
    if inv.status == "proven":
        return ProofResult("proven", None)
    if inv.status == "rejected":
        return ProofResult("rejected", "already_rejected")
    if not inv.penny_ref:
        raise DomainError("Start the ₹1 check first", "no_penny_drop")
    gw = get_adapters().payments
    try:
        res = gw.get_result(inv.penny_ref)
    except AdapterError as exc:
        raise DomainError("Payment check is not working right now", "payments_down", 503) from exc
    if res.status != "PAID":
        return ProofResult("pending", res.status.lower())
    cp = db.get(Counterparty, inv.counterparty_id)
    assert cp is not None
    vpa_ok = (res.payer_vpa or "").lower() == cp.vpa_or_account.lower()
    name_score = similarity(res.payer_name, cp.registered_name) if cp.registered_name else 0.0
    name_ok = name_score >= NAME_MATCH
    try:
        gw.refund(inv.penny_ref)
    except AdapterError:
        record(db, "system", "penny_drop.refund_failed", f"invite:{inv.id}", {})
    proof = {
        "payer_vpa": res.payer_vpa,
        "payer_name": res.payer_name,
        "utr": res.utr,
        "vpa_match": vpa_ok,
        "name_score": round(name_score, 1),
        "sandbox": gw.sandbox,
    }
    if vpa_ok and name_ok:
        inv.status = "proven"
        record(db, f"invite:{inv.id}", "penny_drop.proven", f"business:{inv.business_id}", proof)
        return ProofResult("proven", None, res.payer_vpa, res.payer_name, res.utr)
    inv.status = "rejected"
    reason = "account_mismatch" if not vpa_ok else "name_mismatch"
    inv.flags = [*inv.flags, reason]
    db.add(
        Dispute(
            target_type="invite",
            target_id=inv.id,
            business_id=inv.business_id,
            raised_by="system",
            reason=f"Confirmation rejected: ₹1 came from a different account ({reason})",
        )
    )
    record(
        db,
        f"invite:{inv.id}",
        "penny_drop.rejected",
        f"business:{inv.business_id}",
        {**proof, "reason": reason},
    )
    return ProofResult("rejected", reason, res.payer_vpa, res.payer_name, res.utr)
