"""Abuse limits. Filled in by F34; shares call this hook now."""

from sqlalchemy.orm import Session

from app.db.models import User


def check_share_allowed(db: Session, owner: User) -> None:
    return None
