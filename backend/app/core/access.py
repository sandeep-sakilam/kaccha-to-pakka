"""Who may act on a business. Owners always; a Sahayak only while linked by the owner, and only
for the actions the owner allowed. Every Sahayak action is tagged with the Sahayak's ID."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.db.models import Business, SahayakLink, User

SAHAYAK_ACTIONS = {
    "capture",
    "voice_entry",
    "readback",
    "import",
    "statement",
    "invite",
    "profile",
    "passport",
    "money",
}
DEFAULT_SAHAYAK_ACTIONS = [
    "capture",
    "voice_entry",
    "readback",
    "import",
    "statement",
    "invite",
    "passport",
]


def sahayak_link(db: Session, business_id: str, user_id: str) -> SahayakLink | None:
    return db.execute(
        select(SahayakLink).where(
            SahayakLink.business_id == business_id,
            SahayakLink.sahayak_user_id == user_id,
            SahayakLink.revoked_at.is_(None),
        )
    ).scalar_one_or_none()


def business_for(
    db: Session,
    user: User,
    business_id: str,
    *,
    allow_sahayak: bool = True,
    action: str | None = None,
) -> Business:
    biz = db.get(Business, business_id)
    if biz is None or biz.deleted_at is not None:
        raise NotFound("Business not found", "business_not_found")
    if biz.owner_user_id == user.id:
        return biz
    if allow_sahayak and "sahayak" in (user.roles or []) and user.status == "active":
        link = sahayak_link(db, biz.id, user.id)
        if link is not None:
            if action is None or action in (link.permissions or []):
                return biz
            raise Forbidden("The owner has not allowed you to do this", "sahayak_not_allowed")
    raise Forbidden("This business is not yours", "not_owner")


def actor_for(user: User, biz: Business) -> str:
    return f"user:{user.id}" if user.id == biz.owner_user_id else f"sahayak:{user.id}"


def owned_businesses(db: Session, user: User) -> list[Business]:
    return list(
        db.execute(
            select(Business)
            .where(Business.owner_user_id == user.id, Business.deleted_at.is_(None))
            .order_by(Business.created_at)
        ).scalars()
    )
