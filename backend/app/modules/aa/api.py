from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.adapters.account_aggregator import MockAccountAggregator
from app.adapters.registry import get_adapters
from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import DomainError, NotFound
from app.jobs import RetryableJobError
from app.modules.aa import service

router = APIRouter(tags=["account-aggregator"])


class StartIn(BaseModel):
    monthly_refresh: bool = True


class StartOut(BaseModel):
    consent_id: str
    redirect_url: str
    sandbox: bool


@router.post("/businesses/{business_id}/aa/consent", response_model=StartOut)
def start(business_id: str, body: StartIn, db: DB, user: CurrentUser) -> StartOut:
    biz = business_for(db, user, business_id, allow_sahayak=False)
    c = service.start(db, user, biz, body.monthly_refresh)
    db.commit()
    return StartOut(
        consent_id=c.id,
        redirect_url=str(c.scope["redirect_url"]),
        sandbox=get_adapters().aa.sandbox,
    )


class FetchOut(BaseModel):
    accounts: list[dict[str, Any]]


@router.post("/businesses/{business_id}/aa/{consent_id}/fetch", response_model=FetchOut)
def fetch(business_id: str, consent_id: str, db: DB, user: CurrentUser) -> FetchOut:
    biz = business_for(db, user, business_id, action="money")
    try:
        items = service.fetch(db, biz, consent_id, f"user:{user.id}")
    except RetryableJobError as exc:
        raise DomainError(
            "Bank data could not be fetched now. Please try again later, or add a statement PDF.",
            "aa_down",
            503,
        ) from exc
    db.commit()
    return FetchOut(
        accounts=[
            {
                "evidence_id": e.id,
                "bank": e.meta.get("bank"),
                "account": e.meta.get("account_ref"),
                "txns": e.meta.get("txns"),
                "sandbox": e.meta.get("sandbox"),
            }
            for e in items
        ]
    )


@router.post("/businesses/{business_id}/aa/{consent_id}/revoke")
def revoke(business_id: str, consent_id: str, db: DB, user: CurrentUser) -> dict[str, bool]:
    biz = business_for(db, user, business_id, allow_sahayak=False)
    service.revoke(db, user, biz, consent_id)
    db.commit()
    return {"revoked": True}


class SandboxDecision(BaseModel):
    approve: bool


@router.post("/sandbox/aa/{handle}/decide")
def sandbox_decide(handle: str, body: SandboxDecision, user: CurrentUser) -> dict[str, str]:
    """Stands in for the owner's AA app. Only exists while the AA adapter is the Sandbox mock."""
    aa = get_adapters().aa
    if not isinstance(aa, MockAccountAggregator):
        raise NotFound("Not found", "not_found")
    if handle not in aa.consents:
        raise NotFound("Unknown request", "aa_consent_not_found")
    if aa.consents[handle][0] != user.phone:
        raise DomainError("This request is for another phone", "forbidden", 403)
    aa.approve(handle, body.approve)
    return {"status": aa.consent_status(handle).status}
