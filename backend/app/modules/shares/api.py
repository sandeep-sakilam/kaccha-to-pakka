from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.db.models import AccessLog, Passport, Share
from app.modules.shares import service

router = APIRouter(tags=["shares"])


class ShareIn(BaseModel):
    lender_org: str = Field(min_length=2, max_length=200)
    scope: str = "summary"
    days: int = service.DEFAULT_DAYS


class ShareOut(BaseModel):
    id: str
    lender_org: str
    scope: str
    expires_at: datetime
    state: str
    link: str
    views: int


def _out(db: DB, s: Share) -> ShareOut:
    views = db.execute(
        select(func.count()).select_from(AccessLog).where(AccessLog.share_id == s.id)
    ).scalar_one()
    return ShareOut(
        id=s.id,
        lender_org=s.lender_org,
        scope=s.scope,
        expires_at=s.expires_at,
        state=service.state(s),
        link=service.link(s),
        views=int(views),
    )


@router.post("/businesses/{business_id}/shares", response_model=ShareOut)
def create(business_id: str, body: ShareIn, db: DB, user: CurrentUser) -> ShareOut:
    biz = business_for(db, user, business_id, allow_sahayak=False)
    s = service.create(db, user, biz, body.lender_org, body.scope, body.days)
    db.commit()
    return _out(db, s)


@router.get("/businesses/{business_id}/shares", response_model=list[ShareOut])
def list_shares(business_id: str, db: DB, user: CurrentUser) -> list[ShareOut]:
    business_for(db, user, business_id, allow_sahayak=False)
    rows = db.execute(
        select(Share)
        .join(Passport)
        .where(Passport.business_id == business_id)
        .order_by(Share.created_at.desc())
    ).scalars()
    return [_out(db, s) for s in rows]


@router.post("/shares/{share_id}/revoke", response_model=ShareOut)
def revoke(share_id: str, db: DB, user: CurrentUser) -> ShareOut:
    s = db.get(Share, share_id)
    if s is None:
        raise NotFound("Share not found", "share_not_found")
    service.revoke(db, user, s)
    db.commit()
    return _out(db, s)


class AccessOut(BaseModel):
    share_id: str
    lender_org: str
    viewer: str
    viewed_at: datetime


@router.get("/businesses/{business_id}/access-logs", response_model=list[AccessOut])
def access_logs(business_id: str, db: DB, user: CurrentUser) -> list[AccessOut]:
    business_for(db, user, business_id, allow_sahayak=False)
    rows = db.execute(
        select(AccessLog, Share)
        .join(Share)
        .join(Passport)
        .where(Passport.business_id == business_id)
        .order_by(AccessLog.viewed_at.desc())
    ).all()
    return [
        AccessOut(share_id=s.id, lender_org=s.lender_org, viewer=a.viewer, viewed_at=a.viewed_at)
        for a, s in rows
    ]


@router.get("/l/{token}")
def lender_view(
    token: str,
    request: Request,
    db: DB,
    x_viewer: Annotated[str | None, Header(max_length=200)] = None,
) -> dict[str, Any]:
    """Lender access through a share link. Logged and shown to the owner."""
    s = service.by_token(db, token)
    service.log_view(db, s, x_viewer, request.client.host if request.client else None)
    data = service.lender_view(db, s)
    db.commit()
    return data
