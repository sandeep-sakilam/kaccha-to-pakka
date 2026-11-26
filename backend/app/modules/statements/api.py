from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, File, Header, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.db.models import BankTransaction, EvidenceItem
from app.modules.statements import service

router = APIRouter(tags=["money"])


class StatementOut(BaseModel):
    evidence_id: str
    type: str
    source: str
    status: str
    meta: dict[str, Any]


@router.post("/businesses/{business_id}/statements", response_model=StatementOut)
async def upload_statement(
    business_id: str,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> StatementOut:
    biz = business_for(db, user, business_id)
    ev, _ = service.ingest_statement(
        db, user, biz, await file.read(), file.filename or "", idempotency_key
    )
    db.commit()
    return StatementOut(
        evidence_id=ev.id,
        type=ev.type,
        source=ev.source,
        status=ev.status,
        meta={k: v for k, v in ev.meta.items() if k not in {"fonts"}},
    )


class TxnOut(BaseModel):
    id: str
    txn_date: date
    amount_paise: int
    direction: str
    counterparty_vpa: str | None
    counterparty_name: str | None
    utr: str | None
    source: str


@router.get("/businesses/{business_id}/transactions", response_model=list[TxnOut])
def transactions(business_id: str, db: DB, user: CurrentUser) -> list[TxnOut]:
    business_for(db, user, business_id)
    rows = db.execute(
        select(BankTransaction, EvidenceItem.source)
        .join(EvidenceItem)
        .where(EvidenceItem.business_id == business_id)
        .order_by(BankTransaction.txn_date)
    ).all()
    return [
        TxnOut(
            id=t.id,
            txn_date=t.txn_date,
            amount_paise=t.amount_paise,
            direction=t.direction,
            counterparty_vpa=t.counterparty_vpa,
            counterparty_name=t.counterparty_name,
            utr=t.utr,
            source=src,
        )
        for t, src in rows
    ]
