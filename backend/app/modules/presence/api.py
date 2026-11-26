from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.access import business_for
from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.db.base import utcnow
from app.db.models import PresenceRequest
from app.modules.presence import service

router = APIRouter(tags=["presence"])


class RequestOut(BaseModel):
    id: str
    status: str
    requested_at: datetime | None
    due_by: datetime | None
    result: dict[str, object]


def _out(r: PresenceRequest, now: datetime) -> RequestOut:
    # Future check dates stay hidden so the owner cannot prepare for them.
    hidden = r.status == "scheduled" and r.requested_at > now
    return RequestOut(
        id=r.id,
        status=r.status,
        requested_at=None if hidden else r.requested_at,
        due_by=None if hidden else r.due_by,
        result=r.result,
    )


@router.get("/businesses/{business_id}/presence", response_model=list[RequestOut])
def list_requests(business_id: str, db: DB, user: CurrentUser) -> list[RequestOut]:
    business_for(db, user, business_id)
    service.send_due(db)
    db.commit()
    now = utcnow()
    rows = db.execute(
        select(PresenceRequest)
        .where(PresenceRequest.business_id == business_id)
        .order_by(PresenceRequest.requested_at)
    ).scalars()
    return [_out(r, now) for r in rows]


@router.post("/businesses/{business_id}/presence/start", response_model=list[RequestOut])
def start(business_id: str, db: DB, user: CurrentUser) -> list[RequestOut]:
    biz = business_for(db, user, business_id)
    reqs = service.start_checks(db, user, biz)
    db.commit()
    now = utcnow()
    return [_out(r, now) for r in reqs]


@router.post("/sandbox/presence/{business_id}/now", response_model=RequestOut)
def sandbox_now(business_id: str, db: DB, user: CurrentUser) -> RequestOut:
    """Demo helper: bring the next random check forward to now. Not available in production."""
    if get_settings().app_env == "production":
        raise NotFound("Not found", "not_found")
    business_for(db, user, business_id)
    req = (
        db.execute(
            select(PresenceRequest)
            .where(
                PresenceRequest.business_id == business_id, PresenceRequest.status == "scheduled"
            )
            .order_by(PresenceRequest.requested_at)
        )
        .scalars()
        .first()
    )
    if req is None:
        raise NotFound("No scheduled check", "none_scheduled")
    now = utcnow()
    req.requested_at, req.due_by = now, now + service.WINDOW
    service.send_due(db, now)
    db.commit()
    return _out(req, now)
