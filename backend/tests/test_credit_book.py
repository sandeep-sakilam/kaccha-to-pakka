"""Credit books (udhaar): dues given on credit are cleared by the customer's later payments,
oldest first, within 90 days. Built from the ways real customers pay."""

from datetime import date, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Business, EvidenceItem, ReconMatch
from app.modules.reconciliation.engine import reconcile
from tests import factories as f

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.modules.trust.rules import RecordsFeatures

SEP, OCT, NOV = date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)
RAKESH = ("rakesh.sharma@oksbi", "RAKESH SHARMA")


def _book(db: Session) -> tuple[Business, EvidenceItem, EvidenceItem]:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    return biz, led, bank


def _rules(db: Session) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in db.execute(select(ReconMatch).where(ReconMatch.status == "matched")).scalars():
        out[m.rule] = out.get(m.rule, 0) + 1
    return out


def test_monthly_credit_paid_on_time_by_upi(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(db, led, [(SEP, "Sharma ji", 120_000, "credit"), (OCT, "Sharma ji", 90_000, "credit")])
    f.money(
        db,
        bank,
        [
            (SEP + timedelta(days=30), 120_000, "in", *RAKESH),
            (OCT + timedelta(days=31), 90_000, "in", *RAKESH),
        ],
    )
    s = reconcile(db, biz.id)
    c = s.credit
    assert (c.entries, c.customers, c.repeat_customers) == (2, 1, 1)
    assert c.repaid_bank_exact_paise == 210_000 and c.outstanding_paise == 0
    assert c.bank_repaid_rate == 1.0 and c.median_days_to_repay == 31
    # Credit given is not money, so it is not in the cash-book match rate.
    assert s.ledger_entries == 0 and s.rules == {"credit_repaid": 2}


def test_two_months_paid_together_late(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(db, led, [(SEP, "Sharma ji", 40_000, "credit"), (OCT, "Sharma ji", 60_000, "credit")])
    f.money(db, bank, [(NOV + timedelta(days=4), 100_000, "in", *RAKESH)])
    c = reconcile(db, biz.id).credit
    assert c.repaid_bank_exact_paise == 100_000 and c.outstanding_paise == 0
    assert sorted(c.days_to_repay) == [35, 65]  # October's due after 35 days, September's 65
    assert _rules(db) == {"credit_repaid": 2}  # one payment, linked to both dues


def test_partial_payment_clears_the_oldest_due_first_and_counts_half(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(db, led, [(SEP, "Sharma ji", 40_000, "credit"), (OCT, "Sharma ji", 60_000, "credit")])
    f.money(db, bank, [(OCT + timedelta(days=20), 70_000, "in", *RAKESH)])
    c = reconcile(db, biz.id).credit
    assert c.repaid_bank_partial_paise == 70_000 and c.repaid_bank_exact_paise == 0
    assert c.outstanding_paise == 30_000  # ₹300 of October still owed
    assert c.days_to_repay == [50]  # September cleared; October not yet
    assert c.bank_repaid_rate == 0.35  # 700 of 1,000 repaid, partial counts half
    rows = db.execute(select(ReconMatch)).scalars().all()
    assert sorted((m.rule, m.amount_paise) for m in rows) == [
        ("credit_repaid_partial", 30_000),
        ("credit_repaid_partial", 40_000),
    ]


def test_payment_larger_than_the_dues_is_a_spot_purchase_not_a_repayment(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(db, led, [(SEP, "Sharma ji", 40_000, "credit")])
    f.money(db, bank, [(SEP + timedelta(days=10), 90_000, "in", *RAKESH)])
    c = reconcile(db, biz.id).credit
    assert c.repaid_bank_paise == 0 and c.outstanding_paise == 40_000


def test_repayment_after_90_days_does_not_count(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(db, led, [(SEP, "Sharma ji", 40_000, "credit")])
    f.money(db, bank, [(SEP + timedelta(days=95), 40_000, "in", *RAKESH)])
    assert reconcile(db, biz.id).credit.repaid_bank_paise == 0


def test_payment_from_someone_else_does_not_clear_the_dues(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(db, led, [(SEP, "Sharma ji", 40_000, "credit")])
    f.money(db, bank, [(SEP + timedelta(days=10), 40_000, "in", "x@okaxis", "MOHAN DAS")])
    c = reconcile(db, biz.id).credit
    assert c.repaid_bank_paise == 0 and c.outstanding_paise == 40_000


def test_written_repayments_cash_and_upi(db: Session) -> None:
    """The owner writes the repayments: the UPI one is found in the bank, the cash one is not
    looked for there and is shown as cash."""
    biz, led, bank = _book(db)
    f.ledger(
        db,
        led,
        [
            (SEP, "Sharma ji", 50_000, "credit"),
            (SEP + timedelta(days=12), "Sharma ji", 20_000, "in", "cash"),
            (SEP + timedelta(days=25), "Sharma ji", 30_000, "in", "upi"),
        ],
    )
    f.money(
        db,
        bank,
        [
            (SEP + timedelta(days=12), 20_000, "in", *RAKESH),  # same amount, but written as cash
            (SEP + timedelta(days=26), 30_000, "in", *RAKESH),
        ],
    )
    s = reconcile(db, biz.id)
    assert s.cash_entries == 1 and s.ledger_entries == 1 and s.matched_entries == 1
    c = s.credit
    assert c.repaid_cash_paise == 20_000 and c.repaid_bank_exact_paise == 30_000
    assert c.outstanding_paise == 0 and c.days_to_repay == [25]


def test_ticked_dues_with_no_repayment_written_are_found_in_the_bank(db: Session) -> None:
    """Many owners just tick a due when it is paid. The payment is still in the bank."""
    biz, led, bank = _book(db)
    dues = [(SEP + timedelta(days=i * 10), "Gupta ji", 25_000, "credit") for i in range(4)]
    f.ledger(db, led, dues)
    f.money(db, bank, [(OCT + timedelta(days=2), 100_000, "in", "gupta.r@ybl", "RAJESH GUPTA")])
    c = reconcile(db, biz.id).credit
    assert c.repaid_bank_exact_paise == 100_000 and c.outstanding_paise == 0
    assert c.repeat_customers == 1  # credit in September and October


def test_cash_book_and_credit_book_together(db: Session) -> None:
    """Spot sales by UPI never appear in the ledger and cost nothing; ledger money entries are
    matched as before; credit is cleared separately."""
    biz, led, bank = _book(db)
    f.ledger(
        db,
        led,
        [
            (SEP, "Verma ji", 300_000, "out"),  # paid a supplier
            (SEP + timedelta(days=3), "Sharma ji", 45_000, "credit"),
        ],
    )
    spot_sales = [
        (SEP + timedelta(days=i), 6_000 + i * 100, "in", f"c{i}@ybl", f"CUST {i}")
        for i in range(20)
    ]
    f.money(
        db,
        bank,
        [
            (SEP + timedelta(days=1), 300_000, "out", "verma.traders@oksbi", "VERMA TRADERS"),
            *spot_sales,
            (SEP + timedelta(days=40), 45_000, "in", *RAKESH),
        ],
    )
    s = reconcile(db, biz.id)
    assert s.matched_entries == 1 and s.match_rate == 1.0
    assert s.credit.repaid_bank_exact_paise == 45_000


# ---------------------------------------------------------------- scoring


def _records(**kw: object) -> "RecordsFeatures":
    from app.modules.trust.rules import RecordsFeatures

    return RecordsFeatures(**kw)  # type: ignore[arg-type]


def test_records_pillar_from_a_credit_book_alone() -> None:
    from app.modules.trust.rules import records_pillar

    # 30 dues, 80% of the credit came back through the bank
    assert records_pillar(_records(credit_entries=30, credit_bank_repaid_rate=0.8)) == 80.0
    # the same with fewer entries counts for less
    assert records_pillar(_records(credit_entries=6, credit_bank_repaid_rate=0.8)) == 48.0


def test_records_pillar_mixes_cash_book_and_credit_book_by_entries() -> None:
    from app.modules.trust.rules import records_pillar

    r = _records(
        independent_entries=30, match_rate=1.0, credit_entries=30, credit_bank_repaid_rate=0.5
    )
    assert records_pillar(r) == 75.0


def test_mostly_cash_ledger_is_capped() -> None:
    from app.modules.trust.rules import RECORDS_CASH_CAP, records_pillar

    r = _records(independent_entries=10, match_rate=1.0, cash_entries=25)
    assert records_pillar(r) == RECORDS_CASH_CAP
    # Same ledger without the cash entries is not capped.
    assert records_pillar(_records(independent_entries=10, match_rate=1.0)) > RECORDS_CASH_CAP


def test_reasons_for_a_credit_book() -> None:
    from app.modules.trust.rules import (
        Features,
        MoneyFeatures,
        NetworkFeatures,
        PresenceFeatures,
        compute,
    )

    def codes(**kw: object) -> tuple[list[str], list[str], list[str]]:
        res = compute(
            Features(
                as_of="2026-11-27",
                money=MoneyFeatures(source="aa", months_of_data=12, active_months=12),
                records=_records(**kw),
                network=NetworkFeatures(),
                presence=PresenceFeatures(),
            )
        )
        return (
            [r.code for r in res.positives],
            [r.code for r in res.gaps],
            [r.code for r in res.improve],
        )

    pos, gaps, _ = codes(credit_entries=20, credit_customers=6, credit_bank_repaid_rate=0.7)
    assert "credit_repaid_bank" in pos and "no_ledger" not in gaps
    _, gaps, imp = codes(credit_entries=20, credit_customers=6, credit_bank_repaid_rate=0.2)
    assert "credit_repaid_bank" in gaps and "ask_customers_upi" in imp
    _, gaps, _ = codes(independent_entries=2, match_rate=1.0, cash_entries=9)
    assert "mostly_cash_entries" in gaps


def test_features_carry_the_credit_book(db: Session) -> None:
    from app.modules.trust.features import gather

    biz, led, bank = _book(db)
    f.ledger(
        db,
        led,
        [
            (SEP, "Sharma ji", 40_000, "credit"),
            (OCT, "Sharma ji", 60_000, "credit"),
            (OCT, "Meena ji", 30_000, "credit"),
            (OCT + timedelta(days=9), "Meena ji", 30_000, "in", "cash"),
        ],
    )
    f.money(db, bank, [(NOV + timedelta(days=4), 100_000, "in", *RAKESH)])
    r = gather(db, biz, date(2026, 11, 27)).records
    assert (r.credit_entries, r.credit_customers, r.repeat_credit_customers) == (3, 2, 1)
    assert r.credit_given_paise == 130_000 and r.credit_repaid_bank_paise == 100_000
    assert r.credit_repaid_cash_paise == 30_000 and r.credit_outstanding_paise == 0
    assert r.cash_entries == 1 and r.independent_entries == 0
    assert r.median_days_to_repay == 35
    assert r.counted_entries == 4


# ---------------------------------------------------------------- capture, voice, read-back


def test_voice_understands_credit_and_how_it_was_paid() -> None:
    from app.modules.extraction.voice_parse import parse_entry

    e = parse_entry("Sharma ji ke naam 1200 likhe")
    assert (e.party_text, e.amount_paise, e.kind, e.direction) == (
        "Sharma ji",
        120_000,
        "credit_given",
        "out",
    )
    assert parse_entry("शर्मा जी को 500 का उधार दिया").kind == "credit_given"
    back = parse_entry("Sharma ji se udhaar ke 500 wapas mile")
    assert (back.kind, back.direction) == ("money", "in")
    assert parse_entry("Sharma ji se 500 nakad mile").paid_by == "cash"
    assert parse_entry("Gupta ji ko 2000 PhonePe se diye").paid_by == "upi"


def test_readback_says_credit_in_words() -> None:
    from app.db.models import LedgerEntry
    from app.modules.extraction.checks import readback_prompt

    e = LedgerEntry(
        party_text="Sharma ji",
        amount_paise=50_000,
        direction="out",
        kind="credit_given",
        entry_date=date(2026, 10, 12),
    )
    assert (
        readback_prompt(e, "hi") == "Sharma ji को पाँच सौ रुपये का सामान 12 अक्टूबर को उधार दिया: सही?"
    )
    assert readback_prompt(e, "en") == (
        "Sharma ji took five hundred rupees of goods on credit on 12 October: right?"
    )
    cash = LedgerEntry(party_text="Sharma ji", amount_paise=50_000, direction="in", paid_by="cash")
    assert readback_prompt(cash, "en") == "Sharma ji, five hundred rupees, received in cash: right?"


def test_photo_with_credit_entries_and_owner_correction(client: "TestClient") -> None:
    from tests.conftest import setup_business
    from tests.test_extraction import _entry, page, upload

    h, biz = setup_business(client)
    credit = {**_entry("Sharma ji", 50_000, "out", conf=0.5), "kind": "credit_given"}
    paid = {**_entry("Gupta ji", 20_000, "in", conf=0.5), "paid_by": "cash"}
    upload(client, h, biz, page([credit, paid]), "key-credit-page-1")
    queue = client.get(f"/businesses/{biz}/readback?language=en", headers=h).json()
    by_party = {q["entry"]["party_text"]: q for q in queue}
    assert by_party["Sharma ji"]["entry"]["kind"] == "credit_given"
    assert "on credit" in by_party["Sharma ji"]["prompt"]
    assert by_party["Gupta ji"]["entry"]["paid_by"] == "cash"
    # The owner says the Gupta ji line was really goods on credit, not cash received.
    gid = by_party["Gupta ji"]["entry"]["id"]
    r = client.post(
        f"/ledger/{gid}/confirm", json={"correct": False, "kind": "credit_given"}, headers=h
    ).json()
    assert (r["kind"], r["direction"], r["paid_by"], r["status"]) == (
        "credit_given",
        "out",
        None,
        "confirmed",
    )
