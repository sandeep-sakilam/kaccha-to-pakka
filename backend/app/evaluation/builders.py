"""Small builders for evaluation scenarios (synthetic, Sandbox)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Business, EvidenceItem, LedgerEntry, User
from app.modules.consent import service as consent

FULL = {"date": 1.0, "party": 1.0, "amount": 1.0, "direction": 1.0}


def phone() -> str:
    return "+9197" + str(uuid.uuid4().int % 10**8).zfill(8)


def business(
    db: Session,
    name: str,
    category: str = "kirana",
    started: date | None = date(2015, 1, 1),
    owner_name: str | None = None,
    gender: str | None = None,
) -> Business:
    u = User(phone=phone(), name=owner_name, gender=gender, roles=["owner"], device_ids=[])
    db.add(u)
    db.flush()
    consent.grant(db, u, "build_passport")
    b = Business(
        owner_user_id=u.id,
        name=name,
        category=category,
        started_on=started,
        is_sandbox=True,
        women_owned=gender == "female",
    )
    db.add(b)
    db.flush()
    return b


def evidence(
    db: Session, biz: Business, type_: str, source: str, status: str = "parsed", **meta: Any
) -> EvidenceItem:
    ev = EvidenceItem(business_id=biz.id, type=type_, source=source, status=status, meta=dict(meta))
    db.add(ev)
    db.flush()
    return ev


def money(db: Session, ev: EvidenceItem, rows: list[tuple[Any, ...]]) -> None:
    from app.modules.statements.money import MoneyTxn, store_transactions

    store_transactions(
        db,
        ev.business_id,
        ev,
        [
            MoneyTxn(
                d,
                paise,
                direction,
                vpa,
                name,
                f"{uuid.uuid4().int % 10**12:012d}",
                None,
                None,
                None,
            )
            for d, paise, direction, vpa, name in rows
        ],
    )


def ledger(db: Session, ev: EvidenceItem, rows: list[tuple[Any, ...]]) -> list[LedgerEntry]:
    out = []
    for i, row in enumerate(rows):
        # (date, party, paise, "in" | "out" | "credit"[, paid_by]); "credit" is goods on credit
        d, party, paise, direction = row[:4]
        e = LedgerEntry(
            evidence_id=ev.id,
            entry_date=d,
            party_text=party,
            amount_paise=paise,
            direction="out" if direction == "credit" else direction,
            kind="credit_given" if direction == "credit" else "money",
            paid_by=row[4] if len(row) > 4 else None,
            confidence=1.0,
            field_confidence=FULL,
            page_no=i,
            status="extracted",
        )
        db.add(e)
        out.append(e)
    db.flush()
    return out
