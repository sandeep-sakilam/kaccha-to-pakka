"""Ledger extraction: AI reads the page into a strict schema; rules decide what happens next.

- Each field keeps its own confidence. Any entry with a field below READBACK_THRESHOLD is read
  back to the owner (F11) before it can count.
- Trader scripts (Mahajani, Sarrafi) or an unreadable page switch to voice entry (F12).
- The raw photo is deleted after extraction unless the owner chose to keep originals.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.ai_schemas import LedgerExtraction
from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.db.models import Business, EvidenceItem, LedgerEntry, User
from app.jobs import DEAD_HANDLERS, RetryableJobError
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.notify import notify

READBACK_THRESHOLD = 0.8
VOICE_SCRIPTS = {"mahajani", "sarrafi", "unreadable"}
MIN_PAGE_CONFIDENCE = 0.4


@dataclass(frozen=True)
class ExtractionOutcome:
    status: str
    entries: int
    needs_readback: int


def _entry_status(e_conf: dict[str, float]) -> str:
    return "needs_readback" if min(e_conf.values()) < READBACK_THRESHOLD else "extracted"


def apply_extraction(
    db: Session,
    ev: EvidenceItem,
    result: LedgerExtraction,
    provider: str,
    model: str,
    sandbox: bool,
) -> ExtractionOutcome:
    ev.meta = {
        **ev.meta,
        "extraction": {
            "provider": provider,
            "model": model,
            "sandbox": sandbox,
            "script": result.script,
            "page_confidence": result.page_confidence,
            "page_total_paise": result.page_total_paise,
            "page_total_direction": result.page_total_direction,
            "entries": len(result.entries),
        },
    }
    if result.script in VOICE_SCRIPTS or (
        not result.entries and result.page_confidence < MIN_PAGE_CONFIDENCE
    ):
        ev.status = "needs_voice"
        return ExtractionOutcome("needs_voice", 0, 0)
    needs = 0
    for i, e in enumerate(result.entries):
        conf = e.confidence.model_dump()
        status = _entry_status(conf)
        needs += status == "needs_readback"
        db.add(
            LedgerEntry(
                evidence_id=ev.id,
                entry_date=e.entry_date,
                party_text=e.party_text,
                amount_paise=e.amount_paise,
                direction="out" if e.kind == "credit_given" else e.direction,
                kind=e.kind,
                paid_by=e.paid_by if e.kind == "money" else None,
                confidence=min(conf.values()),
                field_confidence=conf,
                page_no=i,
                status=status,
            )
        )
    ev.status = "extracted"
    db.flush()
    return ExtractionOutcome("extracted", len(result.entries), needs)


def _discard_original(db: Session, ev: EvidenceItem, biz: Business) -> None:
    if ev.storage_key and not consent.has(db, biz.owner_user_id, "keep_originals", biz.id):
        get_adapters().storage.delete(ev.storage_key)
        ev.meta = {**ev.meta, "original_deleted": True}
        ev.storage_key = None


def extract_evidence(db: Session, evidence_id: str) -> ExtractionOutcome:
    ev = db.get(EvidenceItem, evidence_id)
    if ev is None:
        raise ValueError(f"no evidence {evidence_id}")
    if ev.status not in {"received", "extraction_failed"}:
        n = len(db.execute(select(LedgerEntry.id).where(LedgerEntry.evidence_id == ev.id)).all())
        return ExtractionOutcome(ev.status, n, 0)  # idempotent: already done
    biz = db.get(Business, ev.business_id)
    assert biz is not None
    if not ev.storage_key:
        ev.status = "needs_voice"
        return ExtractionOutcome("needs_voice", 0, 0)
    storage = get_adapters().storage
    image = storage.get(ev.storage_key)
    gateway = get_adapters().ai
    try:
        result = gateway.extract_ledger(image, ev.meta.get("mime", "image/jpeg"))
    except AdapterError as exc:
        ev.status = "extraction_failed"
        db.flush()
        raise RetryableJobError(str(exc)) from exc
    outcome = apply_extraction(db, ev, result.value, result.provider, result.model, result.sandbox)
    if outcome.status == "extracted":
        from app.modules.extraction.checks import run_checksum

        run_checksum(db, ev)
    _discard_original(db, ev, biz)
    record(
        db,
        "system",
        "evidence.extracted",
        f"business:{biz.id}",
        {
            "evidence_id": ev.id,
            "status": outcome.status,
            "entries": outcome.entries,
            "needs_readback": outcome.needs_readback,
            "provider": result.provider,
            "model": result.model,
        },
    )
    owner = db.get(User, biz.owner_user_id)
    if owner is not None and ev.meta.get("retried"):
        notify(
            db,
            owner,
            "extraction_done",
            "आपके खाते का पन्ना पढ़ लिया गया है। ऐप में देखें।",
            "Your ledger page has been read. Open the app to check it.",
        )
    return outcome


def _dead_extraction(db: Session, args: tuple[object, ...]) -> None:
    ev = db.get(EvidenceItem, str(args[0]))
    if ev is None:
        return
    ev.status = "extraction_failed"
    ev.meta = {**ev.meta, "retried": True}
    biz = db.get(Business, ev.business_id)
    owner = db.get(User, biz.owner_user_id) if biz else None
    if owner is not None:
        notify(
            db,
            owner,
            "extraction_delayed",
            "पन्ना अभी पढ़ा नहीं जा सका। हम फिर कोशिश करेंगे, या आप बोलकर लिखवा सकते हैं।",
            "We could not read the page yet. We will try again, or you can read it aloud.",
        )


DEAD_HANDLERS["extract_ledger"] = _dead_extraction
