from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.db.models import EvidenceItem, LedgerEntry
from app.jobs import enqueue

router = APIRouter(tags=["ledger"])


class LedgerEntryOut(BaseModel):
    id: str
    evidence_id: str
    entry_date: date | None
    party_text: str | None
    amount_paise: int
    direction: str
    confidence: float
    field_confidence: dict[str, float]
    confirmed_by_owner: bool | None
    status: str


def entry_out(e: LedgerEntry) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=e.id,
        evidence_id=e.evidence_id,
        entry_date=e.entry_date,
        party_text=e.party_text,
        amount_paise=e.amount_paise,
        direction=e.direction,
        confidence=e.confidence,
        field_confidence=e.field_confidence,
        confirmed_by_owner=e.confirmed_by_owner,
        status=e.status,
    )


@router.get("/businesses/{business_id}/ledger", response_model=list[LedgerEntryOut])
def ledger(business_id: str, db: DB, user: CurrentUser) -> list[LedgerEntryOut]:
    business_for(db, user, business_id)
    rows = db.execute(
        select(LedgerEntry)
        .join(EvidenceItem)
        .where(EvidenceItem.business_id == business_id)
        .order_by(LedgerEntry.entry_date, LedgerEntry.page_no)
    ).scalars()
    return [entry_out(e) for e in rows]


@router.post("/evidence/{evidence_id}/extract")
def retry_extract(evidence_id: str, db: DB, user: CurrentUser) -> dict[str, str]:
    ev = db.get(EvidenceItem, evidence_id)
    if ev is None:
        raise NotFound("Not found", "evidence_not_found")
    business_for(db, user, ev.business_id)
    enqueue(db, "extract_ledger", ev.id)
    db.commit()
    return {"status": ev.status}
