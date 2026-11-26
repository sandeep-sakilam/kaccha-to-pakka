"""Run an assessment: gather features, apply the rules, store an immutable, versioned row."""

import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.signing import canonical
from app.db.base import utcnow
from app.db.models import Assessment, Business
from app.modules.audit.service import record
from app.modules.trust import rules
from app.modules.trust.features import gather, model_versions


def assess(db: Session, biz: Business, actor: str = "system") -> Assessment:
    features = gather(db, biz)
    result = rules.compute(features)
    snapshot = features.as_dict()
    versions = {"rules": rules.RULES_VERSION, **model_versions(db, biz)}
    a = Assessment(
        business_id=biz.id,
        rules_version=rules.RULES_VERSION,
        model_versions=versions,
        pillar_scores={
            "pillars": result.pillars,
            "combined": result.combined,
            "features": snapshot,
            "valid_days": result.valid_days,
        },
        band=result.band,
        confidence=result.confidence,
        reasons=result.reasons_dict(),
        flags=result.flags,
        status=result.status,
        inputs_hash=hashlib.sha256(canonical(snapshot)).hexdigest(),
    )
    db.add(a)
    db.flush()
    record(
        db,
        actor,
        "trust.assessed",
        f"business:{biz.id}",
        {
            "assessment_id": a.id,
            "band": a.band,
            "confidence": a.confidence,
            "status": a.status,
            "rules": rules.RULES_VERSION,
            "inputs_hash": a.inputs_hash,
        },
    )
    return a


def recompute(a: Assessment) -> rules.Result:
    """Re-run the stored features through the rules: the same version gives the same result."""
    return rules.compute(rules.Features.from_dict(a.pillar_scores["features"]))


def latest(db: Session, business_id: str) -> Assessment | None:
    return db.execute(
        select(Assessment)
        .where(Assessment.business_id == business_id)
        .order_by(Assessment.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def valid_until(a: Assessment) -> "timedelta":
    return timedelta(days=int(a.pillar_scores.get("valid_days", 0)))


def is_fresh(a: Assessment) -> bool:
    return utcnow() - a.created_at < timedelta(days=1)
