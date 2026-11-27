"""Direct-to-DB builders for scoring and reconciliation tests."""

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import BankTransaction, Business, EvidenceItem, LedgerEntry, User
from app.modules.consent import service as consent
from tests.conftest import new_phone

FULL = {"date": 1.0, "party": 1.0, "amount": 1.0, "direction": 1.0}


def business(
    db: Session,
    name: str = "Biz",
    category: str = "kirana",
    started: date | None = date(2015, 1, 1),
    owner_name: str | None = None,
) -> Business:
    u = User(phone=new_phone(), name=owner_name)
    db.add(u)
    db.flush()
    consent.grant(db, u, "build_passport")
    b = Business(owner_user_id=u.id, name=name, category=category, started_on=started)
    db.add(b)
    db.flush()
    return b


def evidence(
    db: Session, biz: Business, type_: str, source: str, status: str = "parsed", **meta: object
) -> EvidenceItem:
    ev = EvidenceItem(business_id=biz.id, type=type_, source=source, status=status, meta=dict(meta))
    db.add(ev)
    db.flush()
    return ev


def ledger(
    db: Session,
    ev: EvidenceItem,
    rows: Sequence[tuple[Any, ...]],
    status: str = "extracted",
) -> list[LedgerEntry]:
    out = []
    for i, row in enumerate(rows):
        # (date, party, paise, "in" | "out" | "credit" | "bought"[, paid_by]): goods on credit
        # given to a customer ("credit") or bought from a supplier ("bought")
        d, party, paise, direction = row[:4]
        paid_by = row[4] if len(row) > 4 else None
        e = LedgerEntry(
            evidence_id=ev.id,
            entry_date=d,
            party_text=party,
            amount_paise=paise,
            direction={"credit": "out", "bought": "in"}.get(direction, direction),
            kind={"credit": "credit_given", "bought": "credit_taken"}.get(direction, "money"),
            paid_by=paid_by,
            confidence=1.0,
            field_confidence=FULL,
            page_no=i,
            status=status,
        )
        db.add(e)
        out.append(e)
    db.flush()
    return out


def money(db: Session, ev: EvidenceItem, rows: Sequence[tuple[Any, ...]]) -> list[BankTransaction]:
    out = []
    for i, (d, paise, direction, vpa, name) in enumerate(rows):
        t = BankTransaction(
            evidence_id=ev.id,
            txn_date=d,
            amount_paise=paise,
            direction=direction,
            counterparty_vpa=vpa,
            counterparty_name=name,
            utr=f"{abs(hash((ev.id, i))) % 10**12:012d}",
        )
        db.add(t)
        out.append(t)
    db.flush()
    return out
