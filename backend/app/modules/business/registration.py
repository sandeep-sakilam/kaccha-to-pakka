"""Udyam / GSTIN checked against the government register through the licensed KYC provider.
A number the owner types is a claim; the register's answer is evidence. Rules only."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.db.base import utcnow
from app.db.models import Business, User
from app.modules.audit.service import record
from app.modules.reconciliation.names import similarity

NAME_MATCH = 60.0


@dataclass(frozen=True)
class RegistrationCheck:
    status: str  # none | verified | name_mismatch | cancelled | not_found | failed
    source: str | None
    registered_name: str | None
    registered_on: date | None
    started_on: date | None
    sandbox: bool


def _names_agree(biz: Business, owner: User | None, *names: str | None) -> bool:
    """A proprietor's register entry carries their own name; the trade name is the shop's."""
    mine = [biz.name, owner.name if owner else None]
    return any(
        similarity(theirs, ours) >= NAME_MATCH
        for theirs in names
        if theirs
        for ours in mine
        if ours
    )


def check(db: Session, biz: Business, actor: str) -> RegistrationCheck:
    """Look up the Udyam number (preferred: it carries the commencement date), else the GSTIN."""
    kyc = get_adapters().kyc
    owner = db.get(User, biz.owner_user_id)
    numbers = [("udyam", biz.udyam), ("gstin", biz.gstin)]
    source, number = next(((s, n) for s, n in numbers if n), (None, None))
    if not number or not source:
        biz.registration_status = "none"
        return RegistrationCheck("none", None, None, None, None, kyc.sandbox)
    try:
        res = (
            kyc.verify_udyam(number, biz.name)
            if source == "udyam"
            else kyc.verify_gstin(number, biz.name)
        )
    except AdapterError:
        # The provider is down: keep the previous answer, if any, and say we could not check.
        if biz.registration_status in {"none", "failed"}:
            biz.registration_status = "failed"
        return RegistrationCheck("failed", source, None, None, None, kyc.sandbox)
    if not res.found:
        status = "not_found"
    elif res.status == "cancelled":
        status = "cancelled"
    elif _names_agree(biz, owner, res.legal_name, res.trade_name):
        status = "verified"
    else:
        status = "name_mismatch"
    shown = res.trade_name or res.legal_name
    biz.registration_status = status
    biz.registration_source = source
    biz.registration_name = shown
    biz.registered_on = res.registered_on if res.found else None
    biz.registration_started_on = res.started_on if res.found else None
    biz.registration_checked_at = utcnow()
    record(
        db,
        actor,
        "business.registration_check",
        f"business:{biz.id}",
        {"source": source, "status": status, "sandbox": kyc.sandbox},
    )
    return RegistrationCheck(
        status, source, shown, biz.registered_on, biz.registration_started_on, kyc.sandbox
    )
