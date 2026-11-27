"""Goods bought on credit from suppliers, cleared by later payments to them, oldest first."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.models import Business, EvidenceItem, LedgerEntry
from app.modules.extraction.checks import readback_prompt
from app.modules.extraction.voice_parse import parse_entry
from app.modules.reconciliation.engine import reconcile
from app.modules.trust.features import gather
from app.modules.trust.rules import (
    Features,
    MoneyFeatures,
    NetworkFeatures,
    PresenceFeatures,
    RecordsFeatures,
    compute,
    records_pillar,
)
from tests import factories as f

SEP, OCT = date(2026, 9, 1), date(2026, 10, 1)
GUPTA = ("gupta.traders@oksbi", "GUPTA TRADERS")


def _book(db: Session) -> tuple[Business, EvidenceItem, EvidenceItem]:
    biz = f.business(db)
    return (
        biz,
        f.evidence(db, biz, "ledger_page", "camera", "extracted"),
        f.evidence(db, biz, "aa_fetch", "aa:mock"),
    )


def test_two_purchases_paid_together_by_bank(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(
        db,
        led,
        [(SEP, "Gupta Traders", 1_200_000, "bought"), (OCT, "Gupta Traders", 800_000, "bought")],
    )
    f.money(db, bank, [(OCT + timedelta(days=12), 2_000_000, "out", *GUPTA)])
    s = reconcile(db, biz.id)
    sc = s.supplier_credit
    assert (sc.entries, sc.customers, sc.repeat_customers) == (2, 1, 1)
    assert sc.repaid_bank_exact_paise == 2_000_000 and sc.outstanding_paise == 0
    assert sorted(sc.days_to_repay) == [12, 42]
    assert s.rules == {"supplier_paid": 2}
    assert s.credit.entries == 0 and s.ledger_entries == 0  # nothing else in this book


def test_money_coming_in_does_not_pay_a_supplier(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(db, led, [(SEP, "Gupta Traders", 500_000, "bought")])
    f.money(db, bank, [(SEP + timedelta(days=5), 500_000, "in", *GUPTA)])  # a refund, say
    assert reconcile(db, biz.id).supplier_credit.repaid_bank_paise == 0


def test_written_supplier_payment_in_cash(db: Session) -> None:
    biz, led, _ = _book(db)
    f.ledger(
        db,
        led,
        [
            (SEP, "Gupta Traders", 500_000, "bought"),
            (SEP + timedelta(days=20), "Gupta Traders", 500_000, "out", "cash"),
        ],
    )
    sc = reconcile(db, biz.id).supplier_credit
    assert sc.repaid_cash_paise == 500_000 and sc.days_to_repay == [20]


def test_customer_and_supplier_books_side_by_side(db: Session) -> None:
    biz, led, bank = _book(db)
    f.ledger(
        db,
        led,
        [
            (SEP, "Sharma ji", 60_000, "credit"),
            (SEP, "Gupta Traders", 900_000, "bought"),
        ],
    )
    f.money(
        db,
        bank,
        [
            (SEP + timedelta(days=25), 60_000, "in", "rakesh.sharma@oksbi", "RAKESH SHARMA"),
            (SEP + timedelta(days=30), 900_000, "out", *GUPTA),
        ],
    )
    s = reconcile(db, biz.id)
    assert s.credit.repaid_bank_exact_paise == 60_000
    assert s.supplier_credit.repaid_bank_exact_paise == 900_000
    r = gather(db, biz, date(2026, 11, 27)).records
    assert r.supplier_credit_entries == 1 and r.supplier_bank_paid_rate == 1.0
    assert r.median_days_to_pay_suppliers == 30 and r.counted_entries == 2


def test_supplier_book_counts_in_records_and_reasons() -> None:
    r = RecordsFeatures(
        supplier_credit_entries=30, supplier_bank_paid_rate=0.9, supplier_credit_suppliers=4
    )
    assert records_pillar(r) == 90.0
    res = compute(
        Features(
            as_of="2026-11-27",
            money=MoneyFeatures(source="aa", months_of_data=12, active_months=12),
            records=r,
            network=NetworkFeatures(),
            presence=PresenceFeatures(),
        )
    )
    assert "suppliers_paid_bank" in [p.code for p in res.positives]
    assert "no_ledger" not in [g.code for g in res.gaps]


def test_voice_and_readback_for_goods_bought_on_credit() -> None:
    e = parse_entry("Gupta Traders se 12000 ka maal udhaar liya")
    assert (e.party_text, e.amount_paise, e.kind, e.direction) == (
        "Gupta Traders",
        1_200_000,
        "credit_taken",
        "in",
    )
    paid = parse_entry("Gupta Traders ko udhaar ke 12000 chukaye")
    assert (paid.kind, paid.direction) == ("money", "out")
    assert parse_entry("Sharma ji ko 500 ka udhaar diya").kind == "credit_given"
    entry = LedgerEntry(
        party_text="Gupta Traders",
        amount_paise=1_200_000,
        direction="in",
        kind="credit_taken",
        entry_date=date(2026, 10, 12),
    )
    assert readback_prompt(entry, "hi") == (
        "Gupta Traders से बारह हज़ार रुपये का सामान 12 अक्टूबर को उधार लिया: सही?"
    )
    assert readback_prompt(entry, "en") == (
        "Bought twelve thousand rupees of goods on credit from Gupta Traders on 12 October: right?"
    )
