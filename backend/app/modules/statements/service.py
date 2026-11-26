import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapters
from app.core.errors import DomainError
from app.db.models import Business, EvidenceItem, User
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.statements.money import MoneyTxn, store_transactions
from app.modules.statements.parsers import ParsedStatement, StatementError, parse_statement

MAX_BYTES = 10 * 1024 * 1024


def ingest_statement(
    db: Session, user: User, biz: Business, data: bytes, filename: str, idempotency_key: str
) -> tuple[EvidenceItem, ParsedStatement | None]:
    existing = db.execute(
        select(EvidenceItem).where(EvidenceItem.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.business_id != biz.id:
            raise DomainError("Upload key already used", "idempotency_conflict", 409)
        return existing, None
    consent.require(db, biz.owner_user_id, "build_passport", biz.id)
    if len(data) > MAX_BYTES:
        raise DomainError("File is too large", "too_large", 413)
    if not data.startswith(b"%PDF"):
        raise DomainError("Please upload the statement PDF", "not_pdf")
    file_hash = hashlib.sha256(data).hexdigest()
    if db.execute(
        select(EvidenceItem.id).where(
            EvidenceItem.business_id == biz.id, EvidenceItem.file_hash == file_hash
        )
    ).first():
        raise DomainError("This statement was already added", "duplicate_file", 409)
    try:
        st = parse_statement(data, get_adapters().ai)
    except StatementError as exc:
        raise DomainError(str(exc), "bad_statement") from exc
    kind = "upi_statement" if st.layout.startswith("upi") else "bank_statement"
    ev = EvidenceItem(
        business_id=biz.id,
        type=kind,
        source=f"pdf:{st.layout}",
        file_hash=file_hash,
        status="parsed",
        idempotency_key=idempotency_key,
        actor_user_id=user.id,
        meta={
            "filename": filename[:100],
            "holder_name": st.holder_name,
            "account_ref": st.account_ref,
            "parsed_by": st.parsed_by,
            "opening_balance_paise": st.opening_balance_paise,
            "closing_balance_paise": st.closing_balance_paise,
            "first_date": str(min(t.txn_date for t in st.txns)),
            "last_date": str(max(t.txn_date for t in st.txns)),
            "pdf_meta": {
                k: st.metadata.get(k)
                for k in ("Producer", "Creator", "CreationDate", "ModDate", "pages")
            },
            "fonts": st.fonts,
        },
    )
    db.add(ev)
    db.flush()
    stored, skipped = store_transactions(
        db,
        biz.id,
        ev,
        [
            MoneyTxn(
                t.txn_date,
                t.amount_paise,
                t.direction,
                t.counterparty_vpa,
                t.counterparty_name,
                t.utr,
                t.balance_after_paise,
                t.description,
                st.account_ref,
            )
            for t in st.txns
        ],
    )
    ev.meta = {**ev.meta, "txns": stored, "duplicates_skipped": skipped}
    record(
        db,
        f"user:{user.id}",
        "money.statement_pdf",
        f"business:{biz.id}",
        {
            "evidence_id": ev.id,
            "layout": st.layout,
            "txns": stored,
            "skipped": skipped,
            "hash": file_hash[:16],
        },
    )
    return ev, st
