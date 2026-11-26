from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import Forbidden
from app.db.models import SahayakLink, User
from app.modules.sahayak import service

router = APIRouter(tags=["sahayak"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    gender: str | None = Field(None, pattern="^(female|male|other)$")
    in_directory: bool = True


@router.post("/sahayak/register")
def register(body: RegisterIn, db: DB, user: CurrentUser) -> dict[str, list[str]]:
    service.register(db, user, body.name, body.gender, body.in_directory)
    db.commit()
    return {"roles": list(user.roles)}


@router.get("/sahayak/directory")
def directory(db: DB, user: CurrentUser, women_only: bool = False) -> list[dict[str, str]]:
    return [
        {"name": u.name or "", "phone_last4": u.phone[-4:], "gender": u.gender or ""}
        for u in service.directory(db, women_only)
    ]


@router.get("/sahayak/businesses")
def my_owners(db: DB, user: CurrentUser) -> list[dict[str, str]]:
    if "sahayak" not in (user.roles or []):
        raise Forbidden("Register as a Sahayak first", "not_sahayak")
    return [
        {"id": b.id, "name": b.name, "category": b.category}
        for b in service.helped_businesses(db, user)
    ]


class AddIn(BaseModel):
    phone: str
    permissions: list[str] | None = None


class LinkOut(BaseModel):
    id: str
    sahayak_name: str | None
    phone_last4: str
    permissions: list[str]
    granted_at: datetime
    revoked_at: datetime | None


def _out(db: DB, link: SahayakLink) -> LinkOut:
    helper = db.get(User, link.sahayak_user_id)
    assert helper is not None
    return LinkOut(
        id=link.id,
        sahayak_name=helper.name,
        phone_last4=helper.phone[-4:],
        permissions=link.permissions,
        granted_at=link.granted_at,
        revoked_at=link.revoked_at,
    )


@router.post("/businesses/{business_id}/sahayaks", response_model=LinkOut)
def add(business_id: str, body: AddIn, db: DB, user: CurrentUser) -> LinkOut:
    biz = business_for(db, user, business_id, allow_sahayak=False)
    link = service.add(db, user, biz, body.phone, body.permissions)
    db.commit()
    return _out(db, link)


@router.get("/businesses/{business_id}/sahayaks", response_model=list[LinkOut])
def list_links(business_id: str, db: DB, user: CurrentUser) -> list[LinkOut]:
    business_for(db, user, business_id, allow_sahayak=False)
    return [
        _out(db, link)
        for link in db.execute(
            select(SahayakLink).where(SahayakLink.business_id == business_id)
        ).scalars()
    ]


@router.post("/businesses/{business_id}/sahayaks/{link_id}/revoke", response_model=LinkOut)
def remove(business_id: str, link_id: str, db: DB, user: CurrentUser) -> LinkOut:
    biz = business_for(db, user, business_id, allow_sahayak=False)
    service.remove(db, user, biz, link_id)
    db.commit()
    link = db.get(SahayakLink, link_id)
    assert link is not None
    return _out(db, link)
