from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.db.models import Consent
from app.modules.consent import service

router = APIRouter(prefix="/consents", tags=["consent"])


class PurposeOut(BaseModel):
    key: str
    why: str
    default_days: int | None


class NoticeOut(BaseModel):
    language: str
    lines: list[str]
    purposes: list[PurposeOut]


class GrantIn(BaseModel):
    purpose: str
    business_id: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    days: int | None = Field(None, ge=1, le=365)


class ConsentOut(BaseModel):
    id: str
    purpose: str
    business_id: str | None
    scope: dict[str, Any]
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    active: bool


class RevokePurposeIn(BaseModel):
    purpose: str
    business_id: str | None = None


def _out(c: Consent) -> ConsentOut:
    return ConsentOut(
        id=c.id,
        purpose=c.purpose,
        business_id=c.business_id,
        scope=c.scope,
        granted_at=c.granted_at,
        expires_at=c.expires_at,
        revoked_at=c.revoked_at,
        active=service.is_active(c),
    )


@router.get("/notice", response_model=NoticeOut)
def get_notice(language: str = "hi") -> NoticeOut:
    lang = "hi" if language == "hi" else "en"
    return NoticeOut(
        language=lang,
        lines=service.notice(lang),
        purposes=[
            PurposeOut(
                key=p.key, why=p.why_hi if lang == "hi" else p.why_en, default_days=p.default_days
            )
            for p in service.PURPOSES.values()
        ],
    )


@router.post("", response_model=ConsentOut)
def grant(body: GrantIn, db: DB, user: CurrentUser) -> ConsentOut:
    if body.business_id:
        business_for(db, user, body.business_id, allow_sahayak=False)
    c = service.grant(db, user, body.purpose, body.business_id, body.scope, body.days)
    db.commit()
    return _out(c)


@router.get("", response_model=list[ConsentOut])
def list_consents(db: DB, user: CurrentUser) -> list[ConsentOut]:
    return [_out(c) for c in service.list_all(db, user.id)]


@router.post("/{consent_id}/revoke", response_model=ConsentOut)
def revoke(consent_id: str, db: DB, user: CurrentUser) -> ConsentOut:
    c = service.revoke(db, user, consent_id)
    db.commit()
    return _out(c)


@router.post("/revoke-purpose")
def revoke_purpose(body: RevokePurposeIn, db: DB, user: CurrentUser) -> dict[str, int]:
    n = service.revoke_purpose(db, user, body.purpose, body.business_id)
    db.commit()
    return {"revoked": n}
