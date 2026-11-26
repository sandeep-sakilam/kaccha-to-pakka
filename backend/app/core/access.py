"""Who may act on a business. Owners always; Sahayaks only while linked (see F31)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.db.models import Business, SahayakLink, User


def business_for(
    db: Session, user: User, business_id: str, *, allow_sahayak: bool = True
) -> Business:
    biz = db.get(Business, business_id)
    if biz is None or biz.deleted_at is not None:
        raise NotFound("Business not found", "business_not_found")
    if biz.owner_user_id == user.id:
        return biz
    if allow_sahayak:
        link = db.execute(
            select(SahayakLink).where(
                SahayakLink.business_id == biz.id,
                SahayakLink.sahayak_user_id == user.id,
                SahayakLink.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if link is not None:
            return biz
    raise Forbidden("This business is not yours", "not_owner")


def owned_businesses(db: Session, user: User) -> list[Business]:
    return list(
        db.execute(
            select(Business)
            .where(Business.owner_user_id == user.id, Business.deleted_at.is_(None))
            .order_by(Business.created_at)
        ).scalars()
    )
