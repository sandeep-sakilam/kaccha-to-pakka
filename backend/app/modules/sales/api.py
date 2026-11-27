import base64
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import DomainError
from app.modules.sales import service

router = APIRouter(tags=["sales"])


class ParseIn(BaseModel):
    language: str = "hi"
    transcript: str | None = Field(None, max_length=300)
    audio_b64: str | None = Field(None, max_length=4_000_000)


class ParseOut(BaseModel):
    transcript: str
    amount_paise: int | None
    sale_date: date
    understood: bool
    prompt: str | None
    sandbox: bool


@router.post("/businesses/{business_id}/daily-sales/parse", response_model=ParseOut)
def parse(business_id: str, body: ParseIn, db: DB, user: CurrentUser) -> ParseOut:
    business_for(db, user, business_id, action="voice_entry")
    text, sandbox = body.transcript or "", True
    if body.audio_b64:
        try:
            res = get_adapters().ai.transcribe(base64.b64decode(body.audio_b64), body.language)
        except AdapterError as exc:
            raise DomainError(
                "Could not hear that. Type the amount instead.", "stt_down", 503
            ) from exc
        text, sandbox = res.value.text, res.sandbox
    p = service.parse(text)
    lang = "hi" if body.language == "hi" else "en"
    return ParseOut(
        transcript=text,
        amount_paise=p.amount_paise,
        sale_date=p.sale_date,
        understood=p.understood,
        prompt=service.prompt(p.amount_paise, p.sale_date, lang) if p.amount_paise else None,
        sandbox=sandbox,
    )


class SaleIn(BaseModel):
    sale_date: date
    amount_paise: int = Field(gt=0, le=100_000_000_00)
    method: str = Field("voice", pattern="^(voice|typed|buttons)$")


class SaleOut(BaseModel):
    sale_date: date
    amount_paise: int
    method: str


@router.post("/businesses/{business_id}/daily-sales", response_model=SaleOut)
def save(business_id: str, body: SaleIn, db: DB, user: CurrentUser) -> SaleOut:
    biz = business_for(db, user, business_id, action="voice_entry")
    row = service.save(db, user, biz, body.sale_date, body.amount_paise, body.method)
    db.commit()
    return SaleOut(sale_date=row.sale_date, amount_paise=row.amount_paise, method=row.method)


@router.get("/businesses/{business_id}/daily-sales", response_model=list[SaleOut])
def recent(business_id: str, db: DB, user: CurrentUser) -> list[SaleOut]:
    business_for(db, user, business_id)
    return [
        SaleOut(sale_date=s.sale_date, amount_paise=s.amount_paise, method=s.method)
        for s in service.recent(db, business_id)
    ]
