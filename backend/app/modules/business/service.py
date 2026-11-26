from dataclasses import dataclass
from datetime import date
from typing import Any

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


def create(db: Session, user: User, p: ProfileIn, actor: str | None = None) -> Business:
    consent.require(db, user.id, "build_passport")
    _check_ids(p)
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
    record(
        db,
        actor or f"user:{user.id}",
        "business.create",
        f"business:{biz.id}",
        {"category": p.category, "has_gstin": bool(p.gstin), "has_udyam": bool(p.udyam)},
    )
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
    return biz
