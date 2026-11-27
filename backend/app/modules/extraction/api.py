import base64
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import DomainError, NotFound
from app.db.models import EvidenceItem, LedgerEntry
from app.jobs import enqueue
from app.modules.extraction import checks, voice_entry, voice_parse

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
    kind: str = "money"
    paid_by: str | None = None


def entry_out(e: LedgerEntry) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=e.id,
        evidence_id=e.evidence_id,
        entry_date=e.entry_date,
        party_text=e.party_text,
        amount_paise=e.amount_paise,
        direction=e.direction,
        kind=e.kind or "money",
        paid_by=e.paid_by,
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
    business_for(db, user, ev.business_id, action="capture")
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
    kind: str | None = Field(None, pattern="^(money|credit_given|credit_taken)$")
    paid_by: str | None = Field(None, pattern="^(cash|upi|bank)$")


@router.post("/ledger/{entry_id}/confirm", response_model=LedgerEntryOut)
def confirm(entry_id: str, body: ConfirmIn, db: DB, user: CurrentUser) -> LedgerEntryOut:
    e = db.get(LedgerEntry, entry_id)
    ev = db.get(EvidenceItem, e.evidence_id) if e else None
    if e is None or ev is None:
        raise NotFound("Not found", "entry_not_found")
    business_for(db, user, ev.business_id, action="readback")
    checks.confirm_entry(
        db,
        e,
        f"user:{user.id}",
        body.correct,
        checks.Correction(
            body.amount_paise,
            body.party_text,
            body.entry_date,
            body.direction,
            body.kind,
            body.paid_by,
        ),
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


class VoiceParseIn(BaseModel):
    language: str = "hi"
    transcript: str | None = Field(None, max_length=500)
    audio_b64: str | None = Field(None, max_length=4_000_000)


class VoiceParseOut(BaseModel):
    transcript: str
    amount_paise: int | None
    party_text: str | None
    direction: str | None
    entry_date: date | None
    kind: str = "money"
    paid_by: str | None = None
    understood: bool
    prompt: str | None
    stt_confidence: float
    sandbox: bool


@router.post("/businesses/{business_id}/voice-entries/parse", response_model=VoiceParseOut)
def parse_voice(business_id: str, body: VoiceParseIn, db: DB, user: CurrentUser) -> VoiceParseOut:
    business_for(db, user, business_id)
    text, conf, sandbox = body.transcript or "", 0.9, True
    if body.audio_b64:
        try:
            res = get_adapters().ai.transcribe(base64.b64decode(body.audio_b64), body.language)
        except AdapterError as exc:
            raise DomainError(
                "Could not hear that. Use the big buttons instead.", "stt_down", 503
            ) from exc
        text, conf, sandbox = res.value.text, res.value.confidence, res.sandbox
    p = voice_parse.parse_entry(text)
    prompt = None
    if p.understood:
        probe = LedgerEntry(
            amount_paise=p.amount_paise or 0,
            direction=p.direction or "in",
            party_text=p.party_text,
            entry_date=p.entry_date,
            kind=p.kind,
            paid_by=p.paid_by,
        )
        prompt = checks.readback_prompt(probe, "hi" if body.language == "hi" else "en")
    return VoiceParseOut(
        transcript=text,
        amount_paise=p.amount_paise,
        party_text=p.party_text,
        direction=p.direction,
        entry_date=p.entry_date,
        kind=p.kind,
        paid_by=p.paid_by,
        understood=p.understood,
        prompt=prompt,
        stt_confidence=conf,
        sandbox=sandbox,
    )


class VoiceEntryItem(BaseModel):
    amount_paise: int = Field(gt=0)
    direction: str = Field(pattern="^(in|out)$")
    party_text: str | None = Field(None, max_length=200)
    entry_date: date | None = None
    method: str = Field("voice", pattern="^(voice|buttons)$")
    stt_confidence: float = Field(0.9, ge=0, le=1)
    kind: str = Field("money", pattern="^(money|credit_given|credit_taken)$")
    paid_by: str | None = Field(None, pattern="^(cash|upi|bank)$")


class VoiceEntriesIn(BaseModel):
    entries: list[VoiceEntryItem] = Field(min_length=1, max_length=200)
    source_evidence_id: str | None = None


@router.post("/businesses/{business_id}/voice-entries")
def save_voice_entries(
    business_id: str,
    body: VoiceEntriesIn,
    db: DB,
    user: CurrentUser,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, object]:
    biz = business_for(db, user, business_id, action="voice_entry")
    ev, created = voice_entry.save_entries(
        db,
        user,
        biz,
        [
            voice_entry.VoiceEntryIn(
                e.amount_paise,
                e.direction,
                e.party_text,
                e.entry_date,
                e.method,
                e.stt_confidence,
                e.kind,
                e.paid_by,
            )
            for e in body.entries
        ],
        idempotency_key,
        body.source_evidence_id,
    )
    db.commit()
    return {"evidence_id": ev.id, "created": created, "entries": ev.meta.get("entries")}


@router.get("/businesses/{business_id}/needs-voice")
def needs_voice(business_id: str, db: DB, user: CurrentUser) -> list[dict[str, str]]:
    business_for(db, user, business_id)
    rows = db.execute(
        select(EvidenceItem).where(
            EvidenceItem.business_id == business_id, EvidenceItem.status == "needs_voice"
        )
    ).scalars()
    return [
        {"evidence_id": e.id, "script": str(e.meta.get("extraction", {}).get("script"))}
        for e in rows
    ]
