import base64
from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.access import business_for, owned_businesses
from app.core.deps import DB, CurrentUser
from app.core.errors import DomainError
from app.db.models import Business
from app.modules.business import interview, service

router = APIRouter(tags=["business"])


class BusinessIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(max_length=64)
    sells: str | None = None
    started_year: int | None = None
    address: str | None = None
    city: str | None = "Indore"
    udyam: str | None = None
    gstin: str | None = None
    geo_home: dict[str, Any] | None = None
    women_owned: bool = False


class BusinessPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    sells: str | None = None
    started_year: int | None = None
    address: str | None = None
    city: str | None = None
    udyam: str | None = None
    gstin: str | None = None
    geo_home: dict[str, Any] | None = None
    women_owned: bool | None = None


class BusinessOut(BaseModel):
    id: str
    name: str
    category: str
    sells: str | None
    started_on: date | None
    address: str | None
    city: str | None
    udyam: str | None
    gstin: str | None
    women_owned: bool
    is_sandbox: bool


def _out(b: Business) -> BusinessOut:
    return BusinessOut(
        id=b.id,
        name=b.name,
        category=b.category,
        sells=b.sells,
        started_on=b.started_on,
        address=b.address,
        city=b.city,
        udyam=b.udyam,
        gstin=b.gstin,
        women_owned=b.women_owned,
        is_sandbox=b.is_sandbox,
    )


@router.post("/businesses", response_model=BusinessOut)
def create_business(body: BusinessIn, db: DB, user: CurrentUser) -> BusinessOut:
    biz = service.create(db, user, service.ProfileIn(**body.model_dump()))
    db.commit()
    return _out(biz)


@router.get("/businesses", response_model=list[BusinessOut])
def my_businesses(db: DB, user: CurrentUser) -> list[BusinessOut]:
    return [_out(b) for b in owned_businesses(db, user)]


@router.get("/businesses/{business_id}", response_model=BusinessOut)
def get_business(business_id: str, db: DB, user: CurrentUser) -> BusinessOut:
    return _out(business_for(db, user, business_id))


@router.patch("/businesses/{business_id}", response_model=BusinessOut)
def patch_business(business_id: str, body: BusinessPatch, db: DB, user: CurrentUser) -> BusinessOut:
    biz = business_for(db, user, business_id, action="profile")
    service.update(db, user, biz, body.model_dump(exclude_unset=True))
    db.commit()
    return _out(biz)


class InterpretIn(BaseModel):
    question: str = Field(pattern="^(category|since|place|name|full_name)$")
    language: str = "hi"
    transcript: str | None = Field(None, max_length=1000)
    audio_b64: str | None = Field(None, max_length=4_000_000)


class InterpretOut(BaseModel):
    field: str
    value: str | int | None
    transcript: str
    confirm: str
    understood: bool
    sandbox: bool


@router.post("/onboarding/interpret", response_model=InterpretOut)
def interpret(body: InterpretIn, user: CurrentUser) -> InterpretOut:
    sandbox = True
    text = body.transcript or ""
    if body.audio_b64:
        try:
            res = get_adapters().ai.transcribe(base64.b64decode(body.audio_b64), body.language)
        except AdapterError as exc:
            raise DomainError(
                "Could not hear that. Please try again or tap your answer.", "stt_down", 503
            ) from exc
        text, sandbox = res.value.text, res.sandbox
    result = interview.INTERPRETERS[body.question](text)
    return InterpretOut(
        field=result.field,
        value=result.value,
        transcript=text,
        confirm=result.confirm_hi if body.language == "hi" else result.confirm_en,
        understood=result.understood,
        sandbox=sandbox,
    )
