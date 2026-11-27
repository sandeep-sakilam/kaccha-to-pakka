from dataclasses import asdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapters
from app.core.errors import NotFound
from app.db.base import utcnow
from app.db.models import Business, Passport
from app.modules.audit.service import record
from app.modules.passport import credential
from app.modules.trust import service as trust
from app.modules.trust.api import out as assessment_out
from app.modules.trust.explain import explain

MIN_VALID_DAYS = 1


def issue(db: Session, biz: Business, actor: str) -> Passport:
    """Assess now and issue a new signed passport. Older passports are superseded."""
    a = trust.assess(db, biz, actor)
    now = utcnow()
    days = max(MIN_VALID_DAYS, int(a.pillar_scores.get("valid_days", 0)))
    valid_until = now + timedelta(days=days)
    ao = assessment_out(a).model_dump(mode="json")
    sandbox = any(get_adapters().sandbox_status().values()) or biz.is_sandbox
    p = Passport(
        business_id=biz.id,
        assessment_id=a.id,
        vc_json={},
        signature="",
        valid_until=valid_until,
        status={"final": "valid", "on_hold": "on_hold", "stale": "expired"}[a.status],
    )
    db.add(p)
    db.flush()
    vc = credential.sign_vc(
        credential.build_vc(
            p.id,
            {"id": biz.id, "name": biz.name, "category": biz.category, "city": biz.city},
            ao,
            now,
            valid_until,
            sandbox,
        )
    )
    p.vc_json, p.signature = vc, vc["proof"]["proofValue"]
    for old in db.execute(
        select(Passport).where(
            Passport.business_id == biz.id,
            Passport.id != p.id,
            Passport.status.in_(["valid", "on_hold"]),
        )
    ).scalars():
        old.status = "superseded"
    record(
        db,
        actor,
        "passport.issued",
        f"business:{biz.id}",
        {
            "passport_id": p.id,
            "band": a.band,
            "status": p.status,
            "valid_until": valid_until.isoformat(),
        },
    )
    return p


def live_status(p: Passport) -> str:
    if p.status == "valid" and p.valid_until < utcnow():
        return "expired"
    return p.status


def get(db: Session, passport_id: str) -> Passport:
    p = db.get(Passport, passport_id)
    if p is None:
        raise NotFound("Passport not found", "passport_not_found")
    return p


def latest(db: Session, business_id: str) -> Passport | None:
    return db.execute(
        select(Passport)
        .where(Passport.business_id == business_id)
        .order_by(Passport.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def explanation_for(db: Session, p: Passport, lang: str) -> dict[str, Any]:
    from app.db.models import Assessment

    a = db.get(Assessment, p.assessment_id)
    assert a is not None
    return asdict(explain(a.band, a.confidence, a.status, a.reasons, lang, get_adapters().ai))


def revoke(db: Session, p: Passport, actor: str) -> None:
    p.status = "revoked"
    record(db, actor, "passport.revoked", f"business:{p.business_id}", {"passport_id": p.id})


HISTORY_LIMIT = 12


def history(db: Session, business_id: str) -> list[dict[str, Any]]:
    """Every passport issued to the business, oldest first, with the band it carried. Assessments
    are immutable, so this is exactly what the owner (and any lender) saw at the time."""
    from app.db.models import Assessment

    rows = db.execute(
        select(Passport, Assessment)
        .join(Assessment, Passport.assessment_id == Assessment.id)
        .where(Passport.business_id == business_id)
        .order_by(Passport.created_at.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    return [
        {
            "issued_at": p.created_at.isoformat(),
            "band": a.band,
            "confidence": a.confidence,
            "status": a.status,
            "rules_version": a.rules_version,
        }
        for p, a in reversed(rows)
    ]
