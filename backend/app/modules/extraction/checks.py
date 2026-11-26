"""Page-total checksum and owner read-back. Pure rules, no AI.

Most ledger pages already carry a total. If the extracted entries do not add up to it, the page
does not count and goes to a reviewer: a misread digit cannot slip through silently.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.words import date_words, rupees_words
from app.db.base import utcnow
from app.db.models import Dispute, EvidenceItem, LedgerEntry
from app.modules.audit.service import record

COUNTABLE = {"extracted", "confirmed"}
EXCLUDED = {"rejected_by_owner", "on_review"}


@dataclass(frozen=True)
class ChecksumResult:
    status: str  # ok, mismatch, no_total
    expected_paise: int | None
    actual_paise: int


def entries_of(db: Session, evidence_id: str) -> list[LedgerEntry]:
    return list(
        db.execute(
            select(LedgerEntry)
            .where(LedgerEntry.evidence_id == evidence_id)
            .order_by(LedgerEntry.page_no)
        ).scalars()
    )


def page_sum(entries: list[LedgerEntry], direction: str | None) -> int:
    live = [e for e in entries if e.status != "rejected_by_owner"]
    if direction == "out":
        return sum(e.amount_paise for e in live if e.direction == "out")
    if direction == "net":
        return sum(e.amount_paise if e.direction == "in" else -e.amount_paise for e in live)
    if direction == "in":
        return sum(e.amount_paise for e in live if e.direction == "in")
    return sum(e.amount_paise for e in live)


def run_checksum(db: Session, ev: EvidenceItem) -> ChecksumResult:
    info = ev.meta.get("extraction", {})
    expected = info.get("page_total_paise")
    entries = entries_of(db, ev.id)
    actual = page_sum(entries, info.get("page_total_direction"))
    if expected is None:
        result = ChecksumResult("no_total", None, actual)
    elif expected == actual:
        result = ChecksumResult("ok", expected, actual)
    else:
        result = ChecksumResult("mismatch", expected, actual)
    ev.meta = {
        **ev.meta,
        "checksum": {"status": result.status, "expected_paise": expected, "actual_paise": actual},
    }
    if result.status == "mismatch":
        if ev.status != "checksum_failed":
            ev.status = "checksum_failed"
            for e in entries:
                if e.status in COUNTABLE | {"needs_readback"}:
                    e.status = "on_review"
            db.add(
                Dispute(
                    target_type="evidence",
                    target_id=ev.id,
                    business_id=ev.business_id,
                    raised_by="system",
                    reason=(f"Page total {expected} paise but entries add to {actual}"),
                )
            )
            record(
                db,
                "system",
                "evidence.checksum_failed",
                f"business:{ev.business_id}",
                {"evidence_id": ev.id, "expected": expected, "actual": actual},
            )
    elif ev.status == "checksum_failed":
        # Owner corrected the misread entry and the page now adds up.
        ev.status = "extracted"
        for e in entries:
            if e.status == "on_review":
                e.status = "confirmed" if e.confirmed_by_owner else "extracted"
        for d in db.execute(
            select(Dispute).where(
                Dispute.target_type == "evidence",
                Dispute.target_id == ev.id,
                Dispute.status == "open",
            )
        ).scalars():
            d.status, d.resolution, d.resolved_at = "resolved", "page total now matches", utcnow()
    db.flush()
    return result


def readback_prompt(e: LedgerEntry, lang: str) -> str:
    party = e.party_text or ("किसी" if lang == "hi" else "someone")
    amount = rupees_words(e.amount_paise, lang)
    when = date_words(e.entry_date, lang) if e.entry_date else None
    if lang == "hi":
        verb = "मिले" if e.direction == "in" else "दिए"
        return f"{party}, {amount}, {when + ' को ' if when else ''}{verb}: सही?"
    verb = "received" if e.direction == "in" else "paid"
    return f"{party}, {amount}, {verb}{' on ' + when if when else ''}: right?"


@dataclass
class Correction:
    amount_paise: int | None = None
    party_text: str | None = None
    entry_date: date | None = None
    direction: str | None = None


def confirm_entry(
    db: Session, e: LedgerEntry, actor: str, correct: bool, correction: Correction | None = None
) -> LedgerEntry:
    changed: dict[str, object] = {}
    if correct:
        e.confirmed_by_owner = True
    elif correction and any(v is not None for v in vars(correction).values()):
        for field, value in vars(correction).items():
            if value is not None and getattr(e, field) != value:
                changed[field] = value
                setattr(e, field, value)
        e.confirmed_by_owner = True
    else:
        e.confirmed_by_owner = False
    if e.status != "on_review":
        e.status = "confirmed" if e.confirmed_by_owner else "rejected_by_owner"
    elif not e.confirmed_by_owner:
        e.status = "rejected_by_owner"
    e.field_confidence = (
        {k: 1.0 for k in e.field_confidence} if e.confirmed_by_owner else e.field_confidence
    )
    record(
        db,
        actor,
        "ledger.readback",
        f"ledger_entry:{e.id}",
        {"correct": correct, "changed": sorted(changed)},
    )
    ev = db.get(EvidenceItem, e.evidence_id)
    if ev is not None:
        run_checksum(db, ev)
    return e
