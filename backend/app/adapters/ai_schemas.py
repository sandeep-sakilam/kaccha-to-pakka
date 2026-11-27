"""Strict schemas for everything AI returns. AI output is data only: it never calls tools and
never changes a score. Anything that does not validate is rejected, not guessed."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Script = Literal["devanagari", "latin", "mixed", "mahajani", "sarrafi", "other", "unreadable"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldConfidence(_Strict):
    date: float = Field(ge=0, le=1)
    party: float = Field(ge=0, le=1)
    amount: float = Field(ge=0, le=1)
    direction: float = Field(ge=0, le=1)


class ExtractedEntry(_Strict):
    entry_date: date | None
    party_text: str | None = Field(default=None, max_length=200)
    amount_paise: int = Field(ge=0, le=10_000_000_000)
    direction: Literal["in", "out"]
    confidence: FieldConfidence
    # credit_given: goods given on credit (udhaar / naam likha); credit_taken: goods bought on
    # credit from a supplier. No money moved that day in either case.
    kind: Literal["money", "credit_given", "credit_taken"] = "money"
    paid_by: Literal["cash", "upi", "bank"] | None = None  # only when the page says so


class LedgerExtraction(_Strict):
    entries: list[ExtractedEntry] = Field(max_length=200)
    page_total_paise: int | None = Field(default=None, ge=0)
    page_total_direction: Literal["in", "out", "net"] | None = None
    script: Script = "devanagari"
    page_confidence: float = Field(ge=0, le=1)


DocType = Literal[
    "electricity_bill",
    "water_bill",
    "gas_bill",
    "phone_bill",
    "shop_licence",
    "fssai_licence",
    "trade_licence",
    "other",
]


class DocumentExtraction(_Strict):
    """An address-proof document (utility bill or shop licence), read into fields only."""

    doc_type: DocType
    holder_name: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=400)
    issue_date: date | None = None  # bill date, or the date the licence was issued
    valid_until: date | None = None
    number: str | None = Field(default=None, max_length=64)  # consumer / licence number
    confidence: float = Field(ge=0, le=1)


class Transcript(_Strict):
    text: str
    language: str
    confidence: float = Field(ge=0, le=1)


class AIResult[T](BaseModel):
    """A validated AI result plus which provider and model produced it."""

    value: T
    provider: str
    model: str
    sandbox: bool
