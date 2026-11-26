"""Store money data (from AA or a statement PDF) once: overlapping statements or a re-fetch never
double-count a payment. Counterparties (UPI IDs / accounts) become graph nodes."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BankTransaction, Counterparty, EvidenceItem


@dataclass(frozen=True)
class MoneyTxn:
    txn_date: date
    amount_paise: int
    direction: str
    counterparty_vpa: str | None
    counterparty_name: str | None
    utr: str | None
    balance_after_paise: int | None
    narration: str | None
    account_ref: str | None


def _key(t: BankTransaction | MoneyTxn) -> tuple[object, ...]:
    if t.utr:
        return ("utr", t.utr)
    return (
        "row",
        t.txn_date,
        t.amount_paise,
        t.direction,
        t.balance_after_paise,
        t.counterparty_vpa,
    )


def upsert_counterparty(db: Session, vpa: str, name: str | None) -> Counterparty:
    cp = db.execute(
        select(Counterparty).where(Counterparty.vpa_or_account == vpa)
    ).scalar_one_or_none()
    if cp is None:
        cp = Counterparty(vpa_or_account=vpa, registered_name=name)
        db.add(cp)
        db.flush()
    elif name and not cp.registered_name:
        cp.registered_name = name
    return cp


def store_transactions(
    db: Session, business_id: str, ev: EvidenceItem, txns: list[MoneyTxn]
) -> tuple[int, int]:
    """Returns (stored, skipped_as_duplicates)."""
    existing = db.execute(
        select(BankTransaction)
        .join(EvidenceItem)
        .where(EvidenceItem.business_id == business_id, EvidenceItem.status.notin_(["rejected"]))
    ).scalars()
    seen = {_key(t) for t in existing}
    stored = skipped = 0
    for t in txns:
        k = _key(t)
        if k in seen:
            skipped += 1
            continue
        seen.add(k)
        db.add(
            BankTransaction(
                evidence_id=ev.id,
                txn_date=t.txn_date,
                amount_paise=t.amount_paise,
                direction=t.direction,
                counterparty_vpa=t.counterparty_vpa,
                counterparty_name=t.counterparty_name,
                utr=t.utr,
                balance_after_paise=t.balance_after_paise,
                narration=t.narration,
                account_ref=t.account_ref,
            )
        )
        if t.counterparty_vpa:
            upsert_counterparty(db, t.counterparty_vpa, t.counterparty_name)
        stored += 1
    db.flush()
    return stored, skipped
