from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.db.models import Attestation, Business, Counterparty, CounterpartyInvite
from app.modules.attestations import claims, penny_drop, selection

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
    biz = business_for(db, user, business_id, action="invite")
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


class ClaimBody(BaseModel):
    relationship: str
    years_trading: str
    monthly_value: str
    payment_behaviour: str
    gstin: str | None = None
    udyam: str | None = None
    business_name: str | None = Field(None, max_length=200)


class AttestationOut(BaseModel):
    id: str
    status: str
    evidence_type: str
    money_match: bool | None
    weight: float
    claim: dict[str, object]
    expires_at: datetime | None
    signature_valid: bool


def att_out(a: Attestation) -> AttestationOut:
    from app.core import signing

    return AttestationOut(
        id=a.id,
        status=a.status,
        evidence_type=a.evidence_type,
        money_match=a.money_match,
        weight=a.weight,
        claim=a.claim,
        expires_at=a.expires_at,
        signature_valid=bool(a.signature)
        and signing.verify(claims.attestation_payload(a), a.signature or ""),
    )


@router.post("/invites/{token}/claim", response_model=AttestationOut)
def submit_claim(token: str, body: ClaimBody, db: DB) -> AttestationOut:
    from app.adapters.registry import get_adapters

    inv = selection.by_token(db, token)
    payer_name = None
    if inv.penny_ref:
        payer_name = get_adapters().payments.get_result(inv.penny_ref).payer_name
    att = claims.submit(db, inv, claims.ClaimIn(**body.model_dump()), payer_name)
    db.commit()
    return att_out(att)


@router.get("/businesses/{business_id}/attestations", response_model=list[AttestationOut])
def list_attestations(business_id: str, db: DB, user: CurrentUser) -> list[AttestationOut]:
    business_for(db, user, business_id)
    rows = db.execute(
        select(Attestation)
        .where(Attestation.subject_business_id == business_id)
        .order_by(Attestation.created_at)
    ).scalars()
    return [att_out(a) for a in rows]


class InPersonIn(BaseModel):
    relationship: str = Field(pattern="^(supplier|customer|neighbour|visited)$")
    years_trading: str = "1-3"
    note: str = Field("", max_length=300)


@router.post("/businesses/{business_id}/attestations/in-person", response_model=AttestationOut)
def in_person(business_id: str, body: InPersonIn, db: DB, user: CurrentUser) -> AttestationOut:
    from app.core.errors import NotFound

    biz = db.get(Business, business_id)
    if biz is None:
        raise NotFound("Business not found", "business_not_found")
    att = claims.in_person(db, user, biz, body.relationship, body.years_trading, body.note)
    db.commit()
    return att_out(att)
