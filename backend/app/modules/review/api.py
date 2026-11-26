from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.db.models import Dispute
from app.modules.attestations import selection
from app.modules.review import service

router = APIRouter(tags=["review"])


class DisputeOut(BaseModel):
    id: str
    target_type: str
    target_id: str
    business_id: str | None
    raised_by: str
    reason: str | None
    status: str
    resolution: str | None
    created_at: datetime


def _out(d: Dispute) -> DisputeOut:
    return DisputeOut(
        id=d.id,
        target_type=d.target_type,
        target_id=d.target_id,
        business_id=d.business_id,
        raised_by=d.raised_by,
        reason=d.reason,
        status=d.status,
        resolution=d.resolution,
        created_at=d.created_at,
    )


class RaiseIn(BaseModel):
    target_type: str
    target_id: str
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/businesses/{business_id}/disputes", response_model=DisputeOut)
def raise_owner(business_id: str, body: RaiseIn, db: DB, user: CurrentUser) -> DisputeOut:
    business_for(db, user, business_id, allow_sahayak=False)
    d = service.raise_dispute(
        db, f"user:{user.id}", business_id, body.target_type, body.target_id, body.reason
    )
    db.commit()
    return _out(d)


class CounterpartyRaiseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/invites/{token}/dispute", response_model=DisputeOut)
def raise_counterparty(token: str, body: CounterpartyRaiseIn, db: DB) -> DisputeOut:
    inv = selection.by_token(db, token)
    d = service.raise_dispute(
        db, f"invite:{inv.id}", inv.business_id, "attestation", inv.id, body.reason
    )
    db.commit()
    return _out(d)


@router.get("/businesses/{business_id}/disputes", response_model=list[DisputeOut])
def owner_disputes(business_id: str, db: DB, user: CurrentUser) -> list[DisputeOut]:
    from sqlalchemy import select

    business_for(db, user, business_id, allow_sahayak=False)
    return [
        _out(d)
        for d in db.execute(
            select(Dispute)
            .where(Dispute.business_id == business_id)
            .order_by(Dispute.created_at.desc())
        ).scalars()
    ]


@router.get("/review/disputes", response_model=list[DisputeOut])
def review_queue(db: DB, user: CurrentUser, status: str = "open") -> list[DisputeOut]:
    rows = service.queue(db, user, status)
    db.commit()
    return [_out(d) for d in rows]


@router.get("/review/disputes/{dispute_id}")
def review_case(dispute_id: str, db: DB, user: CurrentUser) -> dict[str, Any]:
    data = service.case(db, user, dispute_id)
    db.commit()
    return data


class ResolveIn(BaseModel):
    decision: str
    note: str = Field("", max_length=500)


@router.post("/review/disputes/{dispute_id}/resolve", response_model=DisputeOut)
def resolve(dispute_id: str, body: ResolveIn, db: DB, user: CurrentUser) -> DisputeOut:
    d = service.resolve(db, user, dispute_id, body.decision, body.note)
    db.commit()
    return _out(d)


@router.get("/review/sahayaks")
def sahayak_monitor(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    service.require_reviewer(user)
    return [vars(s) for s in service.sahayak_stats(db)]


@router.post("/review/monitor")
def run_monitor(db: DB, user: CurrentUser) -> dict[str, int]:
    service.require_reviewer(user)
    created = service.monitor(db)
    db.commit()
    return {"opened": len(created)}
