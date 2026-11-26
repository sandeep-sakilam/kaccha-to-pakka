"""Shared FastAPI dependencies: database session and the caller's identity."""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import DomainError, Forbidden
from app.db.base import get_db
from app.db.models import AuthSession, User

DB = Annotated[Session, Depends(get_db)]


class Unauthorized(DomainError):
    status_code = 401


def current_session(db: DB, authorization: Annotated[str | None, Header()] = None) -> AuthSession:
    from app.modules.identity.service import session_for

    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("Please log in", "no_session")
    session = session_for(db, authorization[7:].strip())
    if session is None:
        raise Unauthorized("Your login has expired", "session_expired")
    return session


SessionDep = Annotated[AuthSession, Depends(current_session)]


def current_user(db: DB, session: SessionDep) -> User:
    if session.stage != "full":
        raise Unauthorized("Enter your PIN", "pin_required")
    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        raise Unauthorized("Account not active", "inactive")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(user: User, role: str) -> None:
    if role not in (user.roles or []):
        raise Forbidden("You are not allowed to do this", "forbidden")
