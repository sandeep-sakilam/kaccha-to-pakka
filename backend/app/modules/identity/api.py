from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.deps import DB, CurrentUser, SessionDep
from app.modules.identity import service

router = APIRouter(prefix="/auth", tags=["auth"])


class OtpRequest(BaseModel):
    phone: str
    language: str = "hi"


class OtpRequested(BaseModel):
    challenge_id: str
    expires_at: datetime
    sandbox_code: str | None = Field(None, description="Only present when SMS is Sandbox")


class OtpVerify(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)
    device_id: str = Field(min_length=8, max_length=128)
    language: str = "hi"


class LoginOut(BaseModel):
    token: str
    user_id: str
    stage: str
    has_pin: bool
    new_device: bool
    language: str


class PinIn(BaseModel):
    pin: str


class PinLogin(BaseModel):
    phone: str
    pin: str
    device_id: str = Field(min_length=8, max_length=128)


class Me(BaseModel):
    id: str
    phone: str
    name: str | None
    language: str
    roles: list[str]
    kyc_status: str


def _out(r: service.LoginResult) -> LoginOut:
    return LoginOut(
        token=r.token,
        user_id=r.user.id,
        stage=r.stage,
        has_pin=r.has_pin,
        new_device=r.new_device,
        language=r.user.language,
    )


@router.post("/otp/request", response_model=OtpRequested)
def otp_request(body: OtpRequest, db: DB, request: Request) -> OtpRequested:
    ip = request.client.host if request.client else None
    sent = service.request_otp(db, body.phone, body.language, ip)
    db.commit()
    return OtpRequested(
        challenge_id=sent.challenge_id, expires_at=sent.expires_at, sandbox_code=sent.sandbox_code
    )


@router.post("/otp/verify", response_model=LoginOut)
def otp_verify(body: OtpVerify, db: DB) -> LoginOut:
    try:
        result = service.verify_otp(db, body.phone, body.code, body.device_id, body.language)
    finally:
        db.commit()  # keep the attempt counter even when the code is wrong
    return _out(result)


@router.post("/pin/set")
def pin_set(body: PinIn, db: DB, session: SessionDep) -> dict[str, str]:
    service.set_pin(db, session, body.pin)
    db.commit()
    return {"stage": "full"}


@router.post("/pin/verify")
def pin_verify(body: PinIn, db: DB, session: SessionDep) -> dict[str, str]:
    try:
        service.verify_pin(db, session, body.pin)
    finally:
        db.commit()
    return {"stage": "full"}


@router.post("/login", response_model=LoginOut)
def pin_login(body: PinLogin, db: DB) -> LoginOut:
    try:
        result = service.pin_login(db, body.phone, body.pin, body.device_id)
    finally:
        db.commit()
    return _out(result)


@router.post("/logout")
def logout(db: DB, session: SessionDep) -> dict[str, bool]:
    service.logout(db, session)
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=Me)
def me(user: CurrentUser) -> Me:
    return Me(
        id=user.id,
        phone=user.phone,
        name=user.name,
        language=user.language,
        roles=list(user.roles or []),
        kyc_status=user.kyc_status,
    )


class IdentityIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=200)
    pan: str | None = Field(None, max_length=10)


class IdentityOut(BaseModel):
    name: str
    kyc_status: str
    message: str
    sandbox: bool


@router.post("/identity", response_model=IdentityOut)
def set_identity(body: IdentityIn, db: DB, user: CurrentUser) -> IdentityOut:
    from app.modules.identity.kyc import set_identity as do_set

    r = do_set(db, user, body.full_name, body.pan or None)
    db.commit()
    return IdentityOut(name=r.name, kyc_status=r.kyc_status, message=r.message, sandbox=r.sandbox)


class EraseIn(BaseModel):
    pin: str
    confirm: str


@router.post("/erase")
def erase(body: EraseIn, db: DB, user: CurrentUser) -> dict[str, object]:
    """Right to erase: delete the account and everything personal (PIN and DELETE required)."""
    from dataclasses import asdict

    from app.modules.erase.service import erase_account

    report = erase_account(db, user, body.pin, body.confirm)
    db.commit()
    return {"erased": True, **asdict(report)}
