"""Cash sales: deposits at the bank count at half weight; the owner's spoken daily totals count
only when they agree with the bank month after month."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.account_aggregator import _narration
from app.core.dates import today_ist
from app.core.errors import DomainError
from app.db.models import BankTransaction, Business, DailySale, User
from app.modules.sales import service as sales
from app.modules.statements.money import MoneyTxn, is_cash_deposit
from app.modules.trust.features import gather
from app.modules.trust.rules import (
    DAILY_SALES_BONUS,
    Features,
    MoneyFeatures,
    NetworkFeatures,
    PresenceFeatures,
    RecordsFeatures,
    compute,
    records_pillar,
)
from tests import factories as f
from tests.conftest import login, setup_business

TODAY = date(2026, 11, 27)


def _txn(narration: str, direction: str = "in", vpa: str | None = None) -> MoneyTxn:
    return MoneyTxn(TODAY, 100_000, direction, vpa, None, None, None, narration, None)


@pytest.mark.parametrize(
    ("narration", "cash"),
    [
        ("BY CASH", True),
        ("CASH DEP 001234 RAJWADA BR", True),
        ("CSH DEP/CDM/00981", True),
        ("CDM DEPOSIT 4471", True),
        ("NEFT/GUPTA TRADERS", False),
        ("CASHBACK FROM PAYTM", False),
        ("", False),
    ],
)
def test_cash_deposit_is_recognised_from_the_narration(narration: str, cash: bool) -> None:
    assert is_cash_deposit(_txn(narration)) is cash


def test_only_money_in_without_a_payer_is_a_cash_deposit() -> None:
    assert not is_cash_deposit(_txn("BY CASH", direction="out"))  # a cash withdrawal
    assert not is_cash_deposit(_txn("BY CASH", vpa="x@ybl"))


def test_aa_cash_mode_is_kept_in_the_narration() -> None:
    assert _narration({"mode": "CASH", "narration": "DEP 1234"}) == "BY CASH DEP 1234"
    assert _narration({"mode": "UPI", "narration": "UPI/x@ybl"}) == "UPI/x@ybl"
    assert _narration({"mode": "CASH", "narration": "CASH DEP"}) == "CASH DEP"


def _bank(db: Session, biz: Business, rows: list[tuple[date, int, str | None, str]]) -> None:
    ev = f.evidence(db, biz, "aa_fetch", "aa:mock")
    for i, (d, paise, vpa, narration) in enumerate(rows):
        db.add(
            BankTransaction(
                evidence_id=ev.id,
                txn_date=d,
                amount_paise=paise,
                direction="in",
                counterparty_vpa=vpa,
                counterparty_name=vpa.split("@")[0].upper() if vpa else None,
                narration=narration,
                utr=f"u{biz.id[:6]}{i:06d}",
            )
        )
    db.flush()


def test_cash_deposits_count_at_half_weight(db: Session) -> None:
    biz = f.business(db)
    rows: list[tuple[date, int, str | None, str]] = []
    for m in range(4):
        start = date(2026, 8 + m, 1)
        rows.append((start + timedelta(days=2), 1_000_000, f"c{m}@ybl", "UPI"))
        rows.append((start + timedelta(days=9), 600_000, None, "BY CASH"))
    _bank(db, biz, rows)
    money = gather(db, biz, TODAY).money
    assert money.cash_deposit_paise == 2_400_000 and money.cash_deposit_months == 4
    assert money.avg_monthly_inflow_paise == 1_300_000  # ₹10,000 UPI + half of ₹6,000 cash
    res = compute(
        Features(
            as_of=str(TODAY),
            money=money,
            records=RecordsFeatures(),
            network=NetworkFeatures(),
            presence=PresenceFeatures(),
        )
    )
    assert "cash_sales_deposited" in [p.code for p in res.positives]


# ---------------------------------------------------------------- the owner's daily total


def test_parse_spoken_daily_sales() -> None:
    p = sales.parse("aaj ki bikri 4200", TODAY)
    assert (p.amount_paise, p.sale_date, p.understood) == (420_000, TODAY, True)
    assert sales.parse("आज की बिक्री चार हज़ार दो सौ", TODAY).amount_paise == 420_000
    p = sales.parse("12 November ko 3500 ki bikri hui", TODAY)
    assert (p.amount_paise, p.sale_date) == (350_000, date(2026, 11, 12))
    assert not sales.parse("pata nahi", TODAY).understood


def test_daily_sales_prompt_in_words() -> None:
    assert sales.prompt(420_000, TODAY, "hi", TODAY) == "आज की बिक्री चार हज़ार दो सौ रुपये: सही?"
    assert sales.prompt(350_000, date(2026, 11, 12), "en", TODAY) == (
        "Sales on 12 November, three thousand five hundred rupees: right?"
    )


def _owner(db: Session, biz: Business) -> User:
    u = db.get(User, biz.owner_user_id)
    assert u is not None
    return u


def test_one_total_per_day_and_limits(db: Session) -> None:
    biz = f.business(db)
    u = _owner(db, biz)
    sales.save(db, u, biz, TODAY, 400_000, "voice", TODAY)
    sales.save(db, u, biz, TODAY, 420_000, "typed", TODAY)  # said again: replaces
    rows = db.execute(select(DailySale).where(DailySale.business_id == biz.id)).scalars().all()
    assert [(r.amount_paise, r.method) for r in rows] == [(420_000, "typed")]
    with pytest.raises(DomainError):
        sales.save(db, u, biz, TODAY + timedelta(days=1), 1, "voice", TODAY)
    with pytest.raises(DomainError):
        sales.save(db, u, biz, TODAY - timedelta(days=40), 1, "voice", TODAY)


def _months_of_sales(db: Session, biz: Business, per_day: dict[int, int], days: int = 10) -> None:
    for month, paise in per_day.items():
        for d in range(1, days + 1):
            db.add(
                DailySale(
                    business_id=biz.id,
                    sale_date=date(2026, month, d),
                    amount_paise=paise,
                    method="voice",
                )
            )
    db.flush()


def _bank_month(db: Session, biz: Business, months: list[int], per_month: int) -> None:
    rows: list[tuple[date, int, str | None, str]] = []
    for m in months:
        rows += [
            (date(2026, m, 3 + k * 7), per_month // 4, f"c{m}{k}@ybl", "UPI") for k in range(4)
        ]
    _bank(db, biz, rows)


def test_daily_sales_that_agree_with_the_bank(db: Session) -> None:
    biz = f.business(db)
    _bank_month(db, biz, [8, 9, 10], 3_000_000)  # ₹30,000 a month: about ₹1,000 a day
    _months_of_sales(db, biz, {8: 150_000, 9: 150_000, 10: 140_000})  # ₹1,500 a day, cash on top
    r = gather(db, biz, TODAY).records
    assert (r.daily_sales_months_checked, r.daily_sales_months_agree) == (3, 3)
    assert r.daily_sales_months_below_bank == r.daily_sales_months_far_above_bank == 0


def test_daily_sales_below_or_far_above_the_bank(db: Session) -> None:
    biz = f.business(db)
    _bank_month(db, biz, [8, 9, 10], 3_000_000)
    _months_of_sales(db, biz, {8: 50_000, 9: 900_000, 10: 150_000})  # ₹500, ₹9,000, ₹1,500
    r = gather(db, biz, TODAY).records
    assert r.daily_sales_months_below_bank == 1 and r.daily_sales_months_far_above_bank == 1
    assert r.daily_sales_months_agree == 1


def test_a_few_days_told_are_not_checked(db: Session) -> None:
    biz = f.business(db)
    _bank_month(db, biz, [10], 3_000_000)
    _months_of_sales(db, biz, {10: 150_000}, days=5)
    r = gather(db, biz, TODAY).records
    assert r.daily_sales_days == 5 and r.daily_sales_months_checked == 0  # 8 days needed
    assert r.daily_sales_months_agree == 0


def test_daily_sales_bonus_and_reasons() -> None:
    base = RecordsFeatures(independent_entries=30, match_rate=0.6)
    agree = RecordsFeatures(
        independent_entries=30,
        match_rate=0.6,
        daily_sales_months_checked=3,
        daily_sales_months_agree=3,
    )
    mixed = RecordsFeatures(
        independent_entries=30,
        match_rate=0.6,
        daily_sales_months_checked=3,
        daily_sales_months_agree=2,
        daily_sales_months_below_bank=1,
    )
    assert records_pillar(agree) == records_pillar(base) + DAILY_SALES_BONUS
    assert records_pillar(mixed) == records_pillar(base)

    def codes(r: RecordsFeatures) -> tuple[list[str], list[str]]:
        res = compute(
            Features(
                as_of=str(TODAY),
                money=MoneyFeatures(source="aa", months_of_data=12, active_months=12),
                records=r,
                network=NetworkFeatures(),
                presence=PresenceFeatures(),
            )
        )
        return [x.code for x in res.positives], [x.code for x in res.gaps]

    assert "daily_sales_agree" in codes(agree)[0]
    assert "daily_sales_below_bank" in codes(mixed)[1]


def test_daily_sales_api(client: TestClient) -> None:
    h, biz = setup_business(client)
    p = client.post(
        f"/businesses/{biz}/daily-sales/parse",
        json={"language": "en", "transcript": "aaj ki bikri 4200"},
        headers=h,
    ).json()
    assert p["understood"] and p["amount_paise"] == 420_000
    assert p["prompt"] == "Today's sales, four thousand two hundred rupees: right?"
    saved = client.post(
        f"/businesses/{biz}/daily-sales",
        json={"sale_date": p["sale_date"], "amount_paise": p["amount_paise"], "method": "voice"},
        headers=h,
    )
    assert saved.status_code == 200, saved.text
    assert client.get(f"/businesses/{biz}/daily-sales", headers=h).json() == [
        {"sale_date": str(today_ist()), "amount_paise": 420_000, "method": "voice"}
    ]
    other = login(client)
    assert client.get(f"/businesses/{biz}/daily-sales", headers=other).status_code == 403


def test_today_is_indian_time() -> None:
    # 20:00 UTC on 27 Nov is 01:30 on 28 Nov in India
    assert today_ist(datetime(2026, 11, 27, 20, 0, tzinfo=UTC)) == date(2026, 11, 28)


def test_erase_removes_daily_sales(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client)
    client.post(
        f"/businesses/{biz}/daily-sales",
        json={"sale_date": str(today_ist()), "amount_paise": 100_000},
        headers=h,
    )
    r = client.post("/auth/erase", headers=h, json={"pin": "4826", "confirm": "DELETE"}).json()
    assert r["records_deleted"]["daily_sales"] == 1
