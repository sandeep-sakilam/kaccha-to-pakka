"""The owner's spoken daily sales total ("aaj ki bikri ₹4,200"). Self-reported, so it never
counts on its own: a month counts only when the owner's daily average agrees with the money the
bank saw that month (UPI and bank payments in, plus cash deposited). Rules only."""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dates import today_ist
from app.core.errors import DomainError
from app.core.words import date_words, rupees_words
from app.db.models import BankTransaction, Business, DailySale, User
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.extraction import voice_parse

MAX_DAYS_BACK = 31
MIN_DAYS_PER_MONTH = 8  # a month is checked only when the owner told this many days of it
AGREE_LOW = 0.8  # the owner's sales should be at least what the bank saw (cash comes on top)
AGREE_HIGH = 3.0  # and not so far above it that most of the shop would have to be cash
MONTHS_CHECKED = 6


@dataclass(frozen=True)
class ParsedSale:
    amount_paise: int | None
    sale_date: date
    understood: bool


def parse(text: str, today: date | None = None) -> ParsedSale:
    today = today or today_ist()
    # remove a "12 October" date before reading the amount so 12 is not added to it
    rest = re.sub(
        r"\d{1,2}\s*(tarikh|तारीख)?\s*(" + "|".join(voice_parse.MONTHS) + r")\b",
        " ",
        text,
        flags=re.I,
    )
    amount = voice_parse.parse_amount(rest)
    when = voice_parse.parse_date(text, today) or today
    return ParsedSale(amount, when, amount is not None and amount > 0)


def prompt(amount_paise: int, sale_date: date, lang: str, today: date | None = None) -> str:
    today = today or today_ist()
    words = rupees_words(amount_paise, lang)
    if lang == "hi":
        day = "आज" if sale_date == today else f"{date_words(sale_date, 'hi')} को"
        return f"{day} की बिक्री {words}: सही?"
    day = "Today's sales" if sale_date == today else f"Sales on {date_words(sale_date, 'en')}"
    return f"{day}, {words}: right?"


def save(
    db: Session,
    user: User,
    biz: Business,
    sale_date: date,
    amount_paise: int,
    method: str,
    today: date | None = None,
) -> DailySale:
    """One total per day; telling a day again replaces it."""
    today = today or today_ist()
    consent.require(db, biz.owner_user_id, "build_passport", biz.id)
    if amount_paise <= 0:
        raise DomainError("Say the day's total sales", "bad_amount")
    if sale_date > today:
        raise DomainError("That day has not come yet", "future_date")
    if sale_date < today - timedelta(days=MAX_DAYS_BACK):
        raise DomainError("Only the last month's days can be added", "too_old")
    row = db.execute(
        select(DailySale).where(DailySale.business_id == biz.id, DailySale.sale_date == sale_date)
    ).scalar_one_or_none()
    replaced = row is not None
    if row is None:
        row = DailySale(business_id=biz.id, sale_date=sale_date)
        db.add(row)
    row.amount_paise, row.method, row.actor_user_id = amount_paise, method, user.id
    db.flush()
    record(
        db,
        f"user:{user.id}",
        "sales.daily_total",
        f"business:{biz.id}",
        {"date": str(sale_date), "replaced": replaced, "method": method},
    )
    return row


def recent(db: Session, business_id: str, days: int = 30) -> list[DailySale]:
    since = today_ist() - timedelta(days=days)
    return list(
        db.execute(
            select(DailySale)
            .where(DailySale.business_id == business_id, DailySale.sale_date >= since)
            .order_by(DailySale.sale_date.desc())
        ).scalars()
    )


@dataclass
class SalesCheck:
    days_told: int = 0  # in the last 90 days
    months_checked: int = 0
    months_agree: int = 0
    months_below_bank: int = 0  # the owner said less than the bank alone saw
    months_far_above_bank: int = 0  # so far above the bank that it is hard to believe
    months: dict[str, dict[str, float]] | None = None


def _days_in(ym: tuple[int, int], today: date) -> int:
    y, m = ym
    first = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    end = min(nxt, today + timedelta(days=1))
    return max(1, (end - first).days)


def check(
    db: Session,
    business_id: str,
    bank_inflows: list[BankTransaction],
    today: date,
) -> SalesCheck:
    """Compare, month by month, the owner's average day with the bank's average day.
    `bank_inflows` is what the bank saw come in: UPI and bank payments plus cash deposited."""
    told = list(
        db.execute(
            select(DailySale).where(
                DailySale.business_id == business_id,
                DailySale.sale_date >= today - timedelta(days=31 * MONTHS_CHECKED),
                DailySale.sale_date <= today,
            )
        ).scalars()
    )
    out = SalesCheck(
        days_told=sum(1 for s in told if s.sale_date >= today - timedelta(days=90)), months={}
    )
    by_month: dict[tuple[int, int], list[int]] = defaultdict(list)
    for s in told:
        by_month[(s.sale_date.year, s.sale_date.month)].append(s.amount_paise)
    bank: dict[tuple[int, int], int] = defaultdict(int)
    for t in bank_inflows:
        bank[(t.txn_date.year, t.txn_date.month)] += t.amount_paise
    for ym, amounts in sorted(by_month.items()):
        if len(amounts) < MIN_DAYS_PER_MONTH or not bank.get(ym):
            continue
        told_per_day = sum(amounts) / len(amounts)
        bank_per_day = bank[ym] / _days_in(ym, today)
        ratio = told_per_day / bank_per_day
        out.months_checked += 1
        if ratio < AGREE_LOW:
            out.months_below_bank += 1
        elif ratio > AGREE_HIGH:
            out.months_far_above_bank += 1
        else:
            out.months_agree += 1
        assert out.months is not None
        out.months[f"{ym[0]}-{ym[1]:02d}"] = {
            "days_told": len(amounts),
            "told_per_day_paise": round(told_per_day),
            "bank_per_day_paise": round(bank_per_day),
            "ratio": round(ratio, 2),
        }
    return out
