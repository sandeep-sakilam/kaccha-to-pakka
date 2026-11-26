"""Account-takeover protection: a login from a new device freezes sharing for 24 hours (no new
shares, existing lender links paused) and the owner is told, so a stolen phone number cannot be
used to send the passport somewhere quietly."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.base import utcnow
from app.db.models import AuthSession, User

FREEZE = timedelta(hours=24)


class Frozen(DomainError):
    status_code = 423


def frozen_until(db: Session, user: User) -> datetime | None:
    since = utcnow() - FREEZE
    s = (
        db.execute(
            select(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.new_device.is_(True),
                AuthSession.created_at >= since,
            )
            .order_by(AuthSession.created_at.desc())
        )
        .scalars()
        .first()
    )
    return s.created_at + FREEZE if s else None


def check_share_allowed(db: Session, owner: User) -> None:
    until = frozen_until(db, owner)
    if until is not None:
        raise Frozen(
            "A new phone logged in, so sharing is paused for 24 hours for your safety.",
            "shares_frozen",
        )
