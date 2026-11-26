"""Sahayak (helper) mode: a CSC operator, bank correspondent, SHG leader or family member helps an
owner who can't use the phone alone. The owner adds them, chooses what they may do, and can
remove them at any time. Women owners can ask for a woman Sahayak."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import DEFAULT_SAHAYAK_ACTIONS, SAHAYAK_ACTIONS
from app.core.errors import DomainError, NotFound
from app.db.base import utcnow
from app.db.models import Business, SahayakLink, User
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.identity.service import normalise_phone
from app.modules.notify import notify


def register(db: Session, user: User, name: str, gender: str | None, in_directory: bool) -> User:
    user.name = name.strip()[:200]
    user.gender = gender
    roles = set(user.roles or [])
    roles.add("sahayak")
    if in_directory:
        roles.add("sahayak_directory")
    else:
        roles.discard("sahayak_directory")
    user.roles = sorted(roles)
    record(
        db, f"user:{user.id}", "sahayak.register", f"user:{user.id}", {"directory": in_directory}
    )
    return user


def directory(db: Session, women_only: bool) -> list[User]:
    rows = db.execute(select(User).where(User.status == "active")).scalars()
    out = [u for u in rows if "sahayak_directory" in (u.roles or [])]
    if women_only:
        out = [u for u in out if u.gender == "female"]
    return out


def add(
    db: Session, owner: User, biz: Business, phone: str, permissions: list[str] | None
) -> SahayakLink:
    if biz.owner_user_id != owner.id:
        raise DomainError("Only the owner can add a Sahayak", "owner_only", 403)
    phone = normalise_phone(phone)
    if phone == owner.phone:
        raise DomainError("You cannot add yourself", "self")
    perms = sorted(set(permissions or DEFAULT_SAHAYAK_ACTIONS))
    if not set(perms) <= SAHAYAK_ACTIONS:
        raise DomainError("Unknown permission", "bad_permission")
    helper = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    if helper is None or "sahayak" not in (helper.roles or []):
        raise DomainError("This number is not registered as a Sahayak yet", "not_sahayak", 404)
    if helper.status != "active":
        raise DomainError("This Sahayak is suspended", "sahayak_suspended", 403)
    existing = db.execute(
        select(SahayakLink).where(
            SahayakLink.business_id == biz.id,
            SahayakLink.sahayak_user_id == helper.id,
            SahayakLink.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing:
        existing.permissions = perms
        return existing
    link = SahayakLink(business_id=biz.id, sahayak_user_id=helper.id, permissions=perms)
    db.add(link)
    db.flush()
    consent.grant(
        db, owner, "sahayak_help", biz.id, {"sahayak_user_id": helper.id, "permissions": perms}
    )
    record(
        db,
        f"user:{owner.id}",
        "sahayak.added",
        f"business:{biz.id}",
        {"sahayak": helper.id, "permissions": perms},
    )
    notify(
        db,
        helper,
        "sahayak_added",
        f"{biz.name} ने आपको सहायक बनाया है।",
        f"{biz.name} added you as their Sahayak.",
    )
    return link


def remove(db: Session, owner: User, biz: Business, link_id: str) -> None:
    link = db.get(SahayakLink, link_id)
    if link is None or link.business_id != biz.id or biz.owner_user_id != owner.id:
        raise NotFound("Not found", "link_not_found")
    if link.revoked_at is None:
        link.revoked_at = utcnow()
        consent.revoke_purpose(db, owner, "sahayak_help", biz.id)
        record(
            db,
            f"user:{owner.id}",
            "sahayak.removed",
            f"business:{biz.id}",
            {"sahayak": link.sahayak_user_id},
        )


def helped_businesses(db: Session, helper: User) -> list[Business]:
    return list(
        db.execute(
            select(Business)
            .join(SahayakLink, SahayakLink.business_id == Business.id)
            .where(
                SahayakLink.sahayak_user_id == helper.id,
                SahayakLink.revoked_at.is_(None),
                Business.deleted_at.is_(None),
            )
        ).scalars()
    )
