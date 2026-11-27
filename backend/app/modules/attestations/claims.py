"""Bucketed claims, ID check and money match; then a signed attestation.

Confirmers answer in buckets (quicker to answer honestly, harder to tune to a target). The money
decides: the claimed relationship and monthly-value bucket are compared with the actual flows
between the two accounts. A mismatch is stored as a discrepancy that lowers the Network pillar.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import signing
from app.core.errors import DomainError
from app.core.identifiers import valid_gstin, valid_udyam
from app.db.base import utcnow
from app.db.models import (
    Attestation,
    BankTransaction,
    Business,
    Counterparty,
    CounterpartyInvite,
    EvidenceItem,
    User,
)
from app.modules.audit.service import record
from app.modules.reconciliation.names import similarity

VALUE_BUCKETS: list[tuple[str, int, int | None]] = [
    ("0-10k", 0, 10_000_00),
    ("10k-25k", 10_000_00, 25_000_00),
    ("25k-50k", 25_000_00, 50_000_00),
    ("50k-1L", 50_000_00, 100_000_00),
    ("1L-5L", 100_000_00, 500_000_00),
    ("5L+", 500_000_00, None),
]
YEARS = ["<1", "1-3", "3-5", "5+"]
BEHAVIOUR = ["on_time", "sometimes_late", "often_late"]
ATTESTATION_TTL = timedelta(days=183)
WEIGHT_FULL = 1.0
WEIGHT_NO_ID = 0.7
WEIGHT_DISCREPANCY = 0.2


def bucket_for(paise: int) -> str:
    for name, lo, hi in VALUE_BUCKETS:
        if paise >= lo and (hi is None or paise < hi):
            return name
    return VALUE_BUCKETS[-1][0]


@dataclass(frozen=True)
class ClaimIn:
    relationship: str
    years_trading: str
    monthly_value: str
    payment_behaviour: str
    gstin: str | None = None
    udyam: str | None = None
    business_name: str | None = None


def validate(c: ClaimIn) -> None:
    if c.relationship not in {"supplier", "customer"}:
        raise DomainError("Choose supplier or customer", "bad_relationship")
    if c.years_trading not in YEARS:
        raise DomainError("Choose how many years", "bad_years")
    if c.monthly_value not in {b[0] for b in VALUE_BUCKETS}:
        raise DomainError("Choose a monthly value", "bad_value")
    if c.payment_behaviour not in BEHAVIOUR:
        raise DomainError("Choose how they pay", "bad_behaviour")


@dataclass(frozen=True)
class MoneyMatch:
    matched: bool
    actual_bucket: str
    actual_relationship: str
    months: int
    reasons: list[str]


def money_match(
    db: Session, subject_business_id: str, vpa: str, claim: ClaimIn, today: date | None = None
) -> MoneyMatch:
    today = today or date.today()
    since = today - timedelta(days=365)
    rows = list(
        db.execute(
            select(BankTransaction)
            .join(EvidenceItem)
            .where(
                EvidenceItem.business_id == subject_business_id,
                EvidenceItem.status.notin_(["on_hold", "rejected"]),
                BankTransaction.counterparty_vpa == vpa,
                BankTransaction.txn_date >= since,
            )
        ).scalars()
    )
    per_month: dict[tuple[int, int], int] = defaultdict(int)
    out_total = in_total = 0
    for t in rows:
        per_month[(t.txn_date.year, t.txn_date.month)] += t.amount_paise
        if t.direction == "out":
            out_total += t.amount_paise
        else:
            in_total += t.amount_paise
    months = len(per_month)
    avg = sum(per_month.values()) // months if months else 0
    actual_bucket = bucket_for(avg)
    # The subject pays a supplier ("out"); a customer pays the subject ("in").
    actual_rel = "supplier" if out_total >= in_total else "customer"
    reasons = []
    if claim.relationship != actual_rel:
        reasons.append("relationship_mismatch")
    if claim.monthly_value != actual_bucket:
        reasons.append("value_mismatch")
    if claim.years_trading == "<1" and months >= 12:
        reasons.append("years_mismatch")
    return MoneyMatch(not reasons, actual_bucket, actual_rel, months, reasons)


def _confirmer_business(
    db: Session, inv: CounterpartyInvite, cp: Counterparty, claim: ClaimIn
) -> Business:
    """The attestation is saved against the confirmer's own profile."""
    if cp.business_id:
        biz = db.get(Business, cp.business_id)
        if biz is not None:
            return biz
    from app.modules.identity.service import primary_user

    user = primary_user(db, inv.phone)
    if user is not None:
        # An owner who confirms a partner confirms as their own business, so their own history
        # gives the confirmation its weight. Never the business being confirmed.
        own = (
            db.execute(
                select(Business)
                .where(
                    Business.owner_user_id == user.id,
                    Business.deleted_at.is_(None),
                    Business.id != inv.business_id,
                )
                .order_by(Business.category == "trading_partner", Business.created_at)
            )
            .scalars()
            .first()
        )
        if own is not None:
            cp.business_id = own.id
            return own
    if user is None:
        user = User(phone=inv.phone, language=inv.language, roles=["confirmer"], device_ids=[])
        db.add(user)
        db.flush()
    biz = Business(
        owner_user_id=user.id,
        name=claim.business_name or cp.registered_name or "Trading partner",
        category="trading_partner",
        gstin=(claim.gstin or "").upper() or None,
        udyam=(claim.udyam or "").upper() or None,
    )
    db.add(biz)
    db.flush()
    cp.business_id = biz.id
    return biz


def submit(
    db: Session, inv: CounterpartyInvite, claim: ClaimIn, payer_name: str | None
) -> Attestation:
    if inv.status != "proven":
        raise DomainError("Prove your account with ₹1 first", "not_proven", 409)
    validate(claim)
    from app.modules.abuse.limits import count_distinct

    count_distinct("confirmer_month", inv.phone, inv.business_id)
    cp = db.get(Counterparty, inv.counterparty_id)
    assert cp is not None
    id_status = "none"
    if claim.gstin:
        id_status = "gstin_valid" if valid_gstin(claim.gstin) else "gstin_invalid"
    elif claim.udyam:
        id_status = "udyam_valid" if valid_udyam(claim.udyam) else "udyam_invalid"
    if id_status.endswith("invalid"):
        raise DomainError(
            "That GSTIN / Udyam number does not look right. You can leave it empty.", "bad_id"
        )
    bank_name = payer_name or cp.registered_name
    if (
        id_status != "none"
        and claim.business_name
        and bank_name
        and similarity(claim.business_name, bank_name) < 70
    ):
        id_status += "_name_mismatch"
    mm = money_match(db, inv.business_id, cp.vpa_or_account, claim)
    if not mm.matched:
        weight = WEIGHT_DISCREPANCY
    elif id_status in {"gstin_valid", "udyam_valid"}:
        weight = WEIGHT_FULL
    else:
        weight = WEIGHT_NO_ID
    confirmer = _confirmer_business(db, inv, cp, claim)
    now = utcnow()
    claim_json: dict[str, Any] = {
        "relationship": claim.relationship,
        "years_trading": claim.years_trading,
        "monthly_value": claim.monthly_value,
        "payment_behaviour": claim.payment_behaviour,
        "id_status": id_status,
        "actual_bucket": mm.actual_bucket,
        "actual_relationship": mm.actual_relationship,
        "months_of_money": mm.months,
        "discrepancies": mm.reasons,
    }
    att = Attestation(
        subject_business_id=inv.business_id,
        confirmer_business_id=confirmer.id,
        counterparty_id=cp.id,
        evidence_type="penny_drop",
        claim=claim_json,
        proof_txn_ref=inv.penny_ref,
        money_match=mm.matched,
        status="confirmed" if mm.matched else "discrepancy",
        weight=weight,
        expires_at=now + ATTESTATION_TTL,
    )
    db.add(att)
    db.flush()
    att.signature = signing.sign(attestation_payload(att))
    inv.status = "confirmed"
    record(
        db,
        f"invite:{inv.id}",
        "attestation.signed",
        f"business:{inv.business_id}",
        {
            "attestation_id": att.id,
            "money_match": mm.matched,
            "weight": weight,
            "id_status": id_status,
            "discrepancies": mm.reasons,
        },
    )
    return att


def attestation_payload(att: Attestation) -> dict[str, Any]:
    return {
        "id": att.id,
        "subject": att.subject_business_id,
        "confirmer": att.confirmer_business_id,
        "counterparty": att.counterparty_id,
        "type": att.evidence_type,
        "claim": att.claim,
        "proof": att.proof_txn_ref,
        "money_match": att.money_match,
        "weight": att.weight,
        "expires_at": att.expires_at.isoformat() if att.expires_at else None,
    }


def in_person(
    db: Session, officer: User, subject: Business, relationship: str, years_trading: str, note: str
) -> Attestation:
    """Fallback when a cash-only partner cannot do a penny drop: a Sahayak or a lender's field
    officer confirms in person. A different evidence type with its own, lower weight."""
    if not {"sahayak", "field_officer"} & set(officer.roles or []):
        raise DomainError("Only a Sahayak or field officer can confirm in person", "forbidden", 403)
    if subject.owner_user_id == officer.id:
        raise DomainError("You cannot confirm your own business", "forbidden", 403)
    now = utcnow()
    att = Attestation(
        subject_business_id=subject.id,
        confirmer_business_id=None,
        evidence_type="in_person",
        claim={
            "relationship": relationship,
            "years_trading": years_trading,
            "note": note[:300],
            "officer_user_id": officer.id,
        },
        money_match=None,
        status="confirmed",
        weight=0.5,
        expires_at=now + ATTESTATION_TTL,
    )
    db.add(att)
    db.flush()
    att.signature = signing.sign(attestation_payload(att))
    record(
        db,
        f"user:{officer.id}",
        "attestation.in_person",
        f"business:{subject.id}",
        {"attestation_id": att.id},
    )
    return att
