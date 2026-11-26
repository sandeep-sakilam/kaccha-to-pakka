from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.db.models import EvidenceItem, LedgerEntry
from app.jobs import enqueue
from app.modules.extraction import checks

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


class ReadbackItem(BaseModel):
    entry: LedgerEntryOut
    prompt: str
    reason: str


@router.get("/businesses/{business_id}/readback", response_model=list[ReadbackItem])
def readback_queue(
    business_id: str, db: DB, user: CurrentUser, language: str = "hi"
) -> list[ReadbackItem]:
    """Entries the owner must hear and confirm: low confidence, or on a page that doesn't add up."""
    business_for(db, user, business_id)
    lang = "hi" if language == "hi" else "en"
    rows = db.execute(
        select(LedgerEntry)
        .join(EvidenceItem)
        .where(
            EvidenceItem.business_id == business_id,
            LedgerEntry.confirmed_by_owner.is_(None),
            LedgerEntry.status.in_(["needs_readback", "on_review"]),
        )
        .order_by(LedgerEntry.entry_date, LedgerEntry.page_no)
    ).scalars()
    return [
        ReadbackItem(
            entry=entry_out(e),
            prompt=checks.readback_prompt(e, lang),
            reason="page_total" if e.status == "on_review" else "low_confidence",
        )
        for e in rows
    ]


class ConfirmIn(BaseModel):
    correct: bool
    amount_paise: int | None = Field(None, ge=0)
    party_text: str | None = Field(None, max_length=200)
    entry_date: date | None = None
    direction: str | None = Field(None, pattern="^(in|out)$")


@router.post("/ledger/{entry_id}/confirm", response_model=LedgerEntryOut)
def confirm(entry_id: str, body: ConfirmIn, db: DB, user: CurrentUser) -> LedgerEntryOut:
    e = db.get(LedgerEntry, entry_id)
    ev = db.get(EvidenceItem, e.evidence_id) if e else None
    if e is None or ev is None:
        raise NotFound("Not found", "entry_not_found")
    business_for(db, user, ev.business_id)
    checks.confirm_entry(
        db,
        e,
        f"user:{user.id}",
        body.correct,
        checks.Correction(body.amount_paise, body.party_text, body.entry_date, body.direction),
    )
    db.commit()
    return entry_out(e)


class PageCheckOut(BaseModel):
    evidence_id: str
    status: str
    checksum: dict[str, object] | None


@router.get("/businesses/{business_id}/pages", response_model=list[PageCheckOut])
def pages(business_id: str, db: DB, user: CurrentUser) -> list[PageCheckOut]:
    business_for(db, user, business_id)
    evs = db.execute(
        select(EvidenceItem)
        .where(
            EvidenceItem.business_id == business_id,
            EvidenceItem.type.in_(["ledger_page", "bill", "voice_entry"]),
        )
        .order_by(EvidenceItem.created_at)
    ).scalars()
    return [
        PageCheckOut(evidence_id=e.id, status=e.status, checksum=e.meta.get("checksum"))
        for e in evs
    ]
