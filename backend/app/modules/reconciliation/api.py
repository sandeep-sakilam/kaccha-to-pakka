from fastapi import APIRouter
from pydantic import BaseModel

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.modules.reconciliation import engine

router = APIRouter(tags=["reconciliation"])


class StatsOut(BaseModel):
    ledger_entries: int
    matched_entries: int
    ledger_value_paise: int
    matched_value_paise: int
    match_rate: float
    ambiguous: int
    bank_txns: int
    rules: dict[str, int]


def _out(s: engine.ReconStats) -> StatsOut:
    return StatsOut(
        ledger_entries=s.ledger_entries,
        matched_entries=s.matched_entries,
        ledger_value_paise=s.ledger_value_paise,
        matched_value_paise=s.matched_value_paise,
        match_rate=round(s.match_rate, 4),
        ambiguous=s.ambiguous,
        bank_txns=s.bank_txns,
        rules=s.rules,
    )


@router.post("/businesses/{business_id}/reconcile", response_model=StatsOut)
def run(business_id: str, db: DB, user: CurrentUser) -> StatsOut:
    business_for(db, user, business_id)
    stats = engine.reconcile(db, business_id, f"user:{user.id}")
    db.commit()
    return _out(stats)


class QuestionOut(BaseModel):
    party_text: str
    counterparty_name: str
    prompt: str


@router.get("/businesses/{business_id}/recon/questions", response_model=list[QuestionOut])
def list_questions(
    business_id: str, db: DB, user: CurrentUser, language: str = "hi"
) -> list[QuestionOut]:
    business_for(db, user, business_id)
    return [
        QuestionOut(
            party_text=q.party_text,
            counterparty_name=q.counterparty_name,
            prompt=q.prompt_hi if language == "hi" else q.prompt_en,
        )
        for q in engine.questions(db, business_id)
    ]


class AnswerIn(BaseModel):
    party_text: str
    counterparty_name: str
    same: bool


@router.post("/businesses/{business_id}/recon/answer", response_model=StatsOut)
def answer(business_id: str, body: AnswerIn, db: DB, user: CurrentUser) -> StatsOut:
    business_for(db, user, business_id, action="readback")
    stats = engine.answer(
        db, business_id, body.party_text, body.counterparty_name, body.same, f"user:{user.id}"
    )
    db.commit()
    return _out(stats)
