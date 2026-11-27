"""Identity binding: the owner's full name, checked by a licensed KYC provider (PAN through the
KYC adapter; Sandbox mock by default). The verified name is what the bank account holder name
from Account Aggregator must match, so nobody can build a passport on someone else's account."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.errors import DomainError
from app.db.models import User
from app.modules.audit.service import record
from app.modules.reconciliation.names import similarity

NAME_MATCH = 60.0


@dataclass(frozen=True)
class IdentityResult:
    name: str
    kyc_status: str  # self_declared | verified | name_mismatch | failed
    message: str
    sandbox: bool


def set_identity(db: Session, user: User, full_name: str, pan: str | None) -> IdentityResult:
    declared = " ".join(full_name.split())[:200]
    if len(declared) < 3:
        raise DomainError("Please give your full name", "bad_name")
    kyc = get_adapters().kyc
    if not pan:
        user.name, user.kyc_status = declared, "self_declared"
        result = IdentityResult(
            declared, "self_declared", "Name saved. Add your PAN to verify it.", kyc.sandbox
        )
    else:
        try:
            res = kyc.verify_pan(pan.strip().upper(), declared)
        except AdapterError as exc:
            raise DomainError(
                "Identity check is not working right now. Try again later.", "kyc_down", 503
            ) from exc
        if not res.verified or not res.registered_name:
            user.name, user.kyc_status = declared, "failed"
            result = IdentityResult(
                declared, "failed", res.reason or "PAN not verified", kyc.sandbox
            )
        elif similarity(res.registered_name, declared) < NAME_MATCH:
            # Keep the registered name: it is the one the bank account must match.
            user.name, user.kyc_status = res.registered_name, "name_mismatch"
            result = IdentityResult(
                res.registered_name,
                "name_mismatch",
                "The PAN belongs to a different name.",
                kyc.sandbox,
            )
        else:
            user.name, user.kyc_status = res.registered_name, "verified"
            result = IdentityResult(
                res.registered_name, "verified", "Identity verified.", kyc.sandbox
            )
    record(
        db,
        f"user:{user.id}",
        "identity.set",
        f"user:{user.id}",
        {"kyc_status": user.kyc_status, "with_pan": bool(pan), "sandbox": kyc.sandbox},
    )
    return result
