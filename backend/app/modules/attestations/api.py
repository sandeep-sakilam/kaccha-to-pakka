from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.db.models import Business, Counterparty, CounterpartyInvite
from app.modules.attestations import penny_drop, selection

router = APIRouter(tags=["attestations"])


class TopOut(BaseModel):
    counterparty_id: str
    masked_id: str
    registered_name: str | None
    relationship: str
    value_paise: int
    txns: int
    months_active: int
    invite_status: str | None


@router.get("/businesses/{business_id}/counterparties/top", response_model=list[TopOut])
def top(business_id: str, db: DB, user: CurrentUser) -> list[TopOut]:
    business_for(db, user, business_id)
    invites = {
        i.counterparty_id: i.status
        for i in db.execute(
            select(CounterpartyInvite)
            .where(CounterpartyInvite.business_id == business_id)
            .order_by(CounterpartyInvite.created_at)
        ).scalars()
    }
    return [
        TopOut(
            counterparty_id=c.counterparty_id,
            masked_id=selection.mask_vpa(c.vpa_or_account),
            registered_name=c.registered_name,
            relationship=c.relationship,
            value_paise=c.value_paise,
            txns=c.txns,
            months_active=c.months_active,
            invite_status=invites.get(c.counterparty_id),
        )
        for c in selection.top_counterparties(db, business_id)
    ]


class InviteIn(BaseModel):
    counterparty_id: str
    phone: str
    language: str = "hi"


class InviteOut(BaseModel):
    id: str
    counterparty_id: str
    status: str
    flags: list[str]
    expires_at: datetime


def _out(i: CounterpartyInvite) -> InviteOut:
    return InviteOut(
        id=i.id,
        counterparty_id=i.counterparty_id,
        status=i.status,
        flags=i.flags,
        expires_at=i.expires_at,
    )


@router.post("/businesses/{business_id}/invites", response_model=InviteOut)
def create_invite(business_id: str, body: InviteIn, db: DB, user: CurrentUser) -> InviteOut:
    biz = business_for(db, user, business_id)
    inv = selection.invite(db, user, biz, body.counterparty_id, body.phone, body.language)
    db.commit()
    return _out(inv)


@router.get("/businesses/{business_id}/invites", response_model=list[InviteOut])
def list_invites(business_id: str, db: DB, user: CurrentUser) -> list[InviteOut]:
    business_for(db, user, business_id)
    return [
        _out(i)
        for i in db.execute(
            select(CounterpartyInvite).where(CounterpartyInvite.business_id == business_id)
        ).scalars()
    ]


class PublicInvite(BaseModel):
    """What a confirmer sees: only the claim they are asked to confirm."""

    business_name: str
    city: str | None
    relationship: str
    masked_id: str
    status: str
    language: str
    expires_at: datetime
    sandbox: bool = Field(default=True)


@router.get("/invites/{token}", response_model=PublicInvite)
def public_invite(token: str, db: DB) -> PublicInvite:
    from app.adapters.registry import get_adapters

    inv = selection.by_token(db, token)
    biz = db.get(Business, inv.business_id)
    cp = db.get(Counterparty, inv.counterparty_id)
    assert biz is not None and cp is not None
    if inv.status == "sent":
        inv.status = "opened"
    db.commit()
    return PublicInvite(
        business_name=biz.name,
        city=biz.city,
        relationship=inv.relationship_hint,
        masked_id=selection.mask_vpa(cp.vpa_or_account),
        status=inv.status,
        language=inv.language,
        expires_at=inv.expires_at,
        sandbox=get_adapters().payments.sandbox,
    )


class PennyDropOut(BaseModel):
    ref: str
    pay_to_vpa: str
    amount_paise: int
    upi_link: str
    sandbox: bool


@router.post("/invites/{token}/penny-drop", response_model=PennyDropOut)
def start_penny_drop(token: str, db: DB) -> PennyDropOut:
    from app.adapters.registry import get_adapters

    inv = selection.by_token(db, token)
    req = penny_drop.start(db, inv)
    db.commit()
    return PennyDropOut(
        ref=req.ref,
        pay_to_vpa=req.pay_to_vpa,
        amount_paise=req.amount_paise,
        upi_link=req.upi_link,
        sandbox=get_adapters().payments.sandbox,
    )


class ProofOut(BaseModel):
    status: str
    reason: str | None


@router.post("/invites/{token}/penny-drop/check", response_model=ProofOut)
def check_penny_drop(token: str, db: DB) -> ProofOut:
    inv = selection.by_token(db, token)
    res = penny_drop.check(db, inv)
    db.commit()
    return ProofOut(status=res.status, reason=res.reason)


class SandboxPayIn(BaseModel):
    payer_vpa: str = Field(min_length=3, max_length=128)
    payer_name: str = Field(min_length=1, max_length=200)


@router.post("/sandbox/payments/{ref}/pay")
def sandbox_pay(ref: str, body: SandboxPayIn) -> dict[str, str]:
    """Stands in for the confirmer's UPI app. Only exists while payments are simulated."""
    from app.adapters.payments import MockPaymentGateway
    from app.adapters.registry import get_adapters
    from app.core.errors import NotFound

    gw = get_adapters().payments
    if not isinstance(gw, MockPaymentGateway):
        raise NotFound("Not found", "not_found")
    gw.simulate_payment(ref, body.payer_vpa, body.payer_name)
    return {"status": "PAID"}
