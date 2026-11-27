"""Voice entry for ledgers the AI cannot read (Mahajani, Sarrafi, messy handwriting).

The owner reads each entry aloud; every entry is heard back in words and confirmed before it is
saved, so voice entries are stored as confirmed by the owner. After two misses the app switches
to large-button entry (keypad + received/paid), recorded as method "buttons".
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import Business, EvidenceItem, LedgerEntry, User
from app.modules.audit.service import record
from app.modules.consent import service as consent


@dataclass(frozen=True)
class VoiceEntryIn:
    amount_paise: int
    direction: str
    party_text: str | None
    entry_date: date | None
    method: str  # voice or buttons
    stt_confidence: float
    kind: str = "money"  # money | credit_given
    paid_by: str | None = None  # cash | upi | bank


def save_entries(
    db: Session,
    user: User,
    biz: Business,
    entries: list[VoiceEntryIn],
    idempotency_key: str,
    source_evidence_id: str | None = None,
) -> tuple[EvidenceItem, bool]:
    existing = db.execute(
        select(EvidenceItem).where(EvidenceItem.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.business_id != biz.id:
            raise DomainError("Upload key already used", "idempotency_conflict", 409)
        return existing, False
    consent.require(db, biz.owner_user_id, "build_passport", biz.id)
    if not entries:
        raise DomainError("No entries", "empty")
    source = None
    if source_evidence_id:
        source = db.get(EvidenceItem, source_evidence_id)
        if source is None or source.business_id != biz.id:
            raise DomainError("Unknown ledger photo", "bad_source")
    ev = EvidenceItem(
        business_id=biz.id,
        type="voice_entry",
        source="voice",
        status="extracted",
        idempotency_key=idempotency_key,
        actor_user_id=user.id,
        sahayak_user_id=user.id if user.id != biz.owner_user_id else None,
        meta={
            "methods": sorted({e.method for e in entries}),
            "entries": len(entries),
            "source_evidence_id": source_evidence_id,
            "extraction": {"provider": "owner_voice", "page_total_paise": None},
        },
    )
    db.add(ev)
    db.flush()
    for i, e in enumerate(entries):
        if e.direction not in {"in", "out"} or e.amount_paise <= 0:
            raise DomainError("Each entry needs an amount and received/paid", "bad_entry")
        conf = round(e.stt_confidence, 2) if e.method == "voice" else 1.0
        db.add(
            LedgerEntry(
                evidence_id=ev.id,
                entry_date=e.entry_date,
                party_text=e.party_text,
                amount_paise=e.amount_paise,
                direction="out" if e.kind == "credit_given" else e.direction,
                kind=e.kind,
                paid_by=e.paid_by if e.kind == "money" else None,
                confidence=conf,
                field_confidence={"date": conf, "party": conf, "amount": 1.0, "direction": 1.0},
                confirmed_by_owner=True,
                page_no=i,
                status="confirmed",
            )
        )
    if source is not None:
        source.status = "voice_entered"
        source.meta = {**source.meta, "voice_evidence_id": ev.id}
    db.flush()
    record(
        db,
        f"user:{user.id}",
        "ledger.voice_entry",
        f"business:{biz.id}",
        {"evidence_id": ev.id, "entries": len(entries), "source": source_evidence_id},
    )
    return ev, True
