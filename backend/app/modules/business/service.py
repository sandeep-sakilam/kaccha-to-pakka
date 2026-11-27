from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.identifiers import valid_gstin, valid_udyam
from app.db.models import Business, User
from app.modules.audit.service import record
from app.modules.consent import service as consent


@dataclass
class ProfileIn:
    name: str
    category: str
    sells: str | None = None
    started_year: int | None = None
    address: str | None = None
    city: str | None = "Indore"
    udyam: str | None = None
    gstin: str | None = None
    geo_home: dict[str, Any] | None = None
    women_owned: bool = False


def _check_ids(p: ProfileIn) -> None:
    if p.gstin and not valid_gstin(p.gstin):
        raise DomainError("This GSTIN does not look right. You can leave it empty.", "bad_gstin")
    if p.udyam and not valid_udyam(p.udyam):
        raise DomainError(
            "This Udyam number does not look right. You can leave it empty.", "bad_udyam"
        )
    if p.started_year and not (1940 <= p.started_year <= date.today().year):
        raise DomainError("Start year looks wrong", "bad_year")


PARTNER_PROFILE = "trading_partner"


def partner_profile(db: Session, user_id: str) -> Business | None:
    """The profile made when someone confirmed a partner, before they joined as an owner."""
    return (
        db.execute(
            select(Business)
            .where(
                Business.owner_user_id == user_id,
                Business.category == PARTNER_PROFILE,
                Business.deleted_at.is_(None),
            )
            .order_by(Business.created_at)
        )
        .scalars()
        .first()
    )


def _claim_partner_profile(
    db: Session, user: User, biz: Business, p: ProfileIn, actor: str | None
) -> Business:
    """A confirmer who joins as an owner gets one business, not two: the partner profile becomes
    their business, so the confirmations they gave stay linked to it."""
    biz.name = p.name.strip()
    biz.category = p.category
    biz.sells = p.sells
    biz.started_on = date(p.started_year, 1, 1) if p.started_year else None
    biz.address = p.address
    biz.city = p.city
    biz.udyam = (p.udyam or "").upper() or biz.udyam
    biz.gstin = (p.gstin or "").upper() or biz.gstin
    biz.geo_home = p.geo_home
    biz.women_owned = p.women_owned
    db.flush()
    record(
        db,
        actor or f"user:{user.id}",
        "business.claim_partner_profile",
        f"business:{biz.id}",
        {"category": p.category, "has_gstin": bool(biz.gstin), "has_udyam": bool(biz.udyam)},
    )
    _check_registration(db, biz, actor or f"user:{user.id}")
    return biz


def create(db: Session, user: User, p: ProfileIn, actor: str | None = None) -> Business:
    consent.require(db, user.id, "build_passport")
    _check_ids(p)
    existing = partner_profile(db, user.id)
    if existing is not None:
        return _claim_partner_profile(db, user, existing, p, actor)
    biz = _new_business(db, user, p)
    record(
        db,
        actor or f"user:{user.id}",
        "business.create",
        f"business:{biz.id}",
        {"category": p.category, "has_gstin": bool(p.gstin), "has_udyam": bool(p.udyam)},
    )
    _check_registration(db, biz, actor or f"user:{user.id}")
    return biz


def _check_registration(db: Session, biz: Business, actor: str) -> None:
    if biz.udyam or biz.gstin:
        from app.modules.business import registration

        registration.check(db, biz, actor)


def _new_business(db: Session, user: User, p: ProfileIn) -> Business:
    biz = Business(
        owner_user_id=user.id,
        name=p.name.strip(),
        category=p.category,
        sells=p.sells,
        started_on=date(p.started_year, 1, 1) if p.started_year else None,
        address=p.address,
        city=p.city,
        udyam=(p.udyam or "").upper() or None,
        gstin=(p.gstin or "").upper() or None,
        geo_home=p.geo_home,
        women_owned=p.women_owned,
    )
    db.add(biz)
    db.flush()
    return biz


UPDATABLE = {
    "name",
    "category",
    "sells",
    "address",
    "city",
    "udyam",
    "gstin",
    "geo_home",
    "women_owned",
}


def update(
    db: Session, user: User, biz: Business, changes: dict[str, Any], actor: str | None = None
) -> Business:
    probe = ProfileIn(
        name=biz.name,
        category=biz.category,
        udyam=changes.get("udyam"),
        gstin=changes.get("gstin"),
        started_year=changes.get("started_year"),
    )
    _check_ids(probe)
    for key, value in changes.items():
        if key == "started_year":
            biz.started_on = date(value, 1, 1) if value else None
        elif key in UPDATABLE:
            if key in {"udyam", "gstin"} and value:
                value = str(value).upper()
            setattr(biz, key, value)
    record(
        db,
        actor or f"user:{user.id}",
        "business.update",
        f"business:{biz.id}",
        {"fields": sorted(changes)},
    )
    if {"udyam", "gstin", "name"} & set(changes):
        _check_registration(db, biz, actor or f"user:{user.id}")
    return biz
