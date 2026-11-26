import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import Business, EvidenceItem, LedgerEntry, User
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.imports.csv_parsers import CSVFormatError, parse_export

MAX_BYTES = 5 * 1024 * 1024


def import_csv(
    db: Session, user: User, biz: Business, data: bytes, filename: str, idempotency_key: str
) -> tuple[EvidenceItem, bool]:
    existing = db.execute(
        select(EvidenceItem).where(EvidenceItem.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.business_id != biz.id:
            raise DomainError("Upload key already used", "idempotency_conflict", 409)
        return existing, False
    consent.require(db, biz.owner_user_id, "build_passport", biz.id)
    if len(data) > MAX_BYTES:
        raise DomainError("File is too large", "too_large", 413)
    file_hash = hashlib.sha256(data).hexdigest()
    same = db.execute(
        select(EvidenceItem).where(
            EvidenceItem.business_id == biz.id, EvidenceItem.file_hash == file_hash
        )
    ).scalar()
    if same is not None:
        raise DomainError("This file was already added", "duplicate_file", 409)
    try:
        source, rows = parse_export(data)
    except CSVFormatError as exc:
        raise DomainError(str(exc), "bad_csv") from exc
    if not rows:
        raise DomainError("No entries found in the file", "empty_csv")
    ev = EvidenceItem(
        business_id=biz.id,
        type="ledger_export",
        source=source,
        file_hash=file_hash,
        status="extracted",
        idempotency_key=idempotency_key,
        actor_user_id=user.id,
        meta={
            "filename": filename[:100],
            "rows": len(rows),
            "extraction": {"provider": source, "page_total_paise": None},
            "first_date": str(min(r.entry_date for r in rows)),
            "last_date": str(max(r.entry_date for r in rows)),
        },
    )
    db.add(ev)
    db.flush()
    full = {"date": 1.0, "party": 1.0, "amount": 1.0, "direction": 1.0}
    for i, r in enumerate(rows):
        db.add(
            LedgerEntry(
                evidence_id=ev.id,
                entry_date=r.entry_date,
                party_text=r.party_text,
                amount_paise=r.amount_paise,
                direction=r.direction,
                confidence=1.0,
                field_confidence=full,
                page_no=i,
                status="extracted",
            )
        )
    db.flush()
    record(
        db,
        f"user:{user.id}",
        "ledger.csv_import",
        f"business:{biz.id}",
        {"evidence_id": ev.id, "source": source, "rows": len(rows), "hash": file_hash[:16]},
    )
    return ev, True
