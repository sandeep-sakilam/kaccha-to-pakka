from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.db.models import Assessment
from app.modules.trust import service
from app.modules.trust.rules import RULES_VERSION

router = APIRouter(tags=["trust"])


class AssessmentOut(BaseModel):
    id: str
    band: str
    confidence: str
    status: str
    combined: float
    pillars: dict[str, float]
    reasons: dict[str, Any]
    flags: list[dict[str, Any]]
    rules_version: str
    model_versions: dict[str, str]
    inputs_hash: str | None
    valid_days: int
    created_at: datetime


def out(a: Assessment) -> AssessmentOut:
    return AssessmentOut(
        id=a.id,
        band=a.band,
        confidence=a.confidence,
        status=a.status,
        combined=float(a.pillar_scores.get("combined", 0)),
        pillars=a.pillar_scores.get("pillars", {}),
        reasons=a.reasons,
        flags=a.flags,
        rules_version=a.rules_version,
        model_versions=a.model_versions,
        inputs_hash=a.inputs_hash,
        valid_days=int(a.pillar_scores.get("valid_days", 0)),
        created_at=a.created_at,
    )


@router.post("/businesses/{business_id}/assess", response_model=AssessmentOut)
def run(business_id: str, db: DB, user: CurrentUser) -> AssessmentOut:
    biz = business_for(db, user, business_id)
    a = service.assess(db, biz, f"user:{user.id}")
    db.commit()
    return out(a)


@router.get("/businesses/{business_id}/assessments/latest", response_model=AssessmentOut)
def latest(business_id: str, db: DB, user: CurrentUser) -> AssessmentOut:
    business_for(db, user, business_id)
    a = service.latest(db, business_id)
    if a is None:
        raise NotFound("No assessment yet", "no_assessment")
    return out(a)


@router.get("/assessments/{assessment_id}/verify")
def verify(assessment_id: str, db: DB, user: CurrentUser) -> dict[str, object]:
    """Recompute a past assessment from its stored features and compare."""
    a = db.get(Assessment, assessment_id)
    if a is None:
        raise NotFound("Not found", "not_found")
    business_for(db, user, a.business_id)
    r = service.recompute(a)
    same = r.band == a.band and r.confidence == a.confidence and r.status == a.status
    return {
        "reproducible": same and a.rules_version == RULES_VERSION,
        "band": r.band,
        "rules_version": a.rules_version,
    }


class ExplanationOut(BaseModel):
    language: str
    band: str
    band_label: str
    confidence: str
    confidence_label: str
    status: str
    status_label: str
    headline: str
    positives: list[str]
    gaps: list[str]
    improve: list[str]
    source: str


@router.get("/businesses/{business_id}/explanation", response_model=ExplanationOut)
def explanation(
    business_id: str, db: DB, user: CurrentUser, language: str = "hi"
) -> ExplanationOut:
    from app.adapters.registry import get_adapters
    from app.modules.trust.explain import explain

    business_for(db, user, business_id)
    a = service.latest(db, business_id)
    if a is None:
        raise NotFound("No assessment yet", "no_assessment")
    e = explain(a.band, a.confidence, a.status, a.reasons, language, get_adapters().ai)
    return ExplanationOut(
        language=e.language,
        band=a.band,
        band_label=e.band_label,
        confidence=a.confidence,
        confidence_label=e.confidence_label,
        status=a.status,
        status_label=e.status_label,
        headline=e.headline,
        positives=e.positives,
        gaps=e.gaps,
        improve=e.improve,
        source=e.source,
    )
