"""Who paid? A son's phone, a UPI ID that is only a number, and names that only rhyme."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Business, EvidenceItem, ReconMatch
from app.modules.reconciliation.engine import answer, questions, reconcile
from app.modules.trust.rules import (
    RECORDS_OWNER_CAP,
    Features,
    MoneyFeatures,
    NetworkFeatures,
    PresenceFeatures,
    RecordsFeatures,
    compute,
    records_pillar,
)
from tests import factories as f

D = date(2026, 10, 12)


def _setup(db: Session) -> tuple[Business, EvidenceItem, EvidenceItem]:
    biz = f.business(db)
    return (
        biz,
        f.evidence(db, biz, "ledger_page", "camera", "extracted"),
        f.evidence(db, biz, "aa_fetch", "aa:mock"),
    )


def _rules(db: Session, biz: Business) -> dict[str, int]:
    s = reconcile(db, biz.id)
    return s.rules


def test_son_with_the_family_surname_is_matched_automatically(db: Session) -> None:
    biz, led, bank = _setup(db)
    f.ledger(db, led, [(D, "Sharma ji", 50_000, "in")])
    f.money(db, bank, [(D + timedelta(days=2), 50_000, "in", "amit.sharma@okaxis", "AMIT SHARMA")])
    assert _rules(db, biz) == {"amount_date_name": 1}


def test_son_with_another_name_is_asked_once_and_remembered_by_upi_id(db: Session) -> None:
    biz, led, bank = _setup(db)
    f.ledger(db, led, [(D, "Sharma ji", 50_000, "in")])
    first = f.money(db, bank, [(D + timedelta(days=1), 50_000, "in", "amitk@ybl", "AMIT KUMAR")])
    reconcile(db, biz.id)
    q = questions(db, biz.id)
    assert [x.prompt_en for x in q] == ["Is Sharma ji the same as AMIT KUMAR?"]
    s = answer(db, biz.id, "Sharma ji", "AMIT KUMAR", True, "user:o", first[0].id)
    assert s.rules == {"owner_confirmed": 1}
    # Next month the same phone pays, and its UPI app now shows a different name.
    f.ledger(db, led, [(D + timedelta(days=30), "Sharma ji", 70_000, "in")])
    f.money(db, bank, [(D + timedelta(days=31), 70_000, "in", "amitk@ybl", "A K")])
    assert _rules(db, biz) == {"owner_confirmed": 2}


def test_owner_no_by_upi_id_blocks_that_phone(db: Session) -> None:
    biz, led, bank = _setup(db)
    f.ledger(db, led, [(D, "Sharma ji", 50_000, "in")])
    t = f.money(db, bank, [(D, 50_000, "in", "amitk@ybl", "AMIT KUMAR")])
    reconcile(db, biz.id)
    s = answer(db, biz.id, "Sharma ji", "AMIT KUMAR", False, "user:o", t[0].id)
    assert s.matched_entries == 0 and questions(db, biz.id) == []


def test_number_only_upi_id_matches_when_it_is_the_only_candidate(db: Session) -> None:
    biz, led, bank = _setup(db)
    f.ledger(db, led, [(D, "Sharma ji", 50_000, "in")])
    f.money(db, bank, [(D + timedelta(days=1), 50_000, "in", "9826012345@ybl", None)])
    assert _rules(db, biz) == {"amount_date_only": 1}


def test_number_only_upi_id_with_two_candidates_is_asked_with_the_number_masked(
    db: Session,
) -> None:
    biz, led, bank = _setup(db)
    f.ledger(db, led, [(D, "Sharma ji", 50_000, "in")])
    f.money(
        db,
        bank,
        [
            (D, 50_000, "in", "9826012345@ybl", None),
            (D + timedelta(days=1), 50_000, "in", "9425098765@paytm", None),
        ],
    )
    assert reconcile(db, biz.id).matched_entries == 0
    # The nearer date is asked about first; the number is not shown in full.
    assert [q.prompt_en for q in questions(db, biz.id)] == [
        "Is Sharma ji the same as 98••••2345@ybl?"
    ]
    assert all("9826012345" not in q.prompt_en for q in questions(db, biz.id))


def test_names_that_only_rhyme_are_not_asked_about_when_there_is_a_better_candidate(
    db: Session,
) -> None:
    biz, led, bank = _setup(db)
    f.ledger(db, led, [(D, "Sharma ji", 50_000, "in")])
    f.money(
        db,
        bank,
        [
            (D, 50_000, "in", "priya.v@okhdfc", "PRIYA VERMA"),
            (D + timedelta(days=1), 50_000, "in", "mohan@ybl", "MOHAN DAS"),
        ],
    )
    s = reconcile(db, biz.id)
    assert s.matched_entries == 0 and questions(db, biz.id) == []


def test_a_name_that_differs_is_asked_once_when_it_is_the_only_payment(db: Session) -> None:
    biz, led, bank = _setup(db)
    f.ledger(db, led, [(D, "Sharma ji", 50_000, "in")])
    f.money(db, bank, [(D, 50_000, "in", "priya.v@okhdfc", "PRIYA VERMA")])
    assert reconcile(db, biz.id).matched_entries == 0  # never matched on its own
    assert [q.prompt_en for q in questions(db, biz.id)] == ["Is Sharma ji the same as PRIYA VERMA?"]


def test_credit_repaid_from_the_sons_phone_after_the_owner_says_yes(db: Session) -> None:
    biz, led, bank = _setup(db)
    f.ledger(
        db,
        led,
        [(D, "Sharma ji", 40_000, "credit"), (D + timedelta(days=20), "Sharma ji", 10_000, "in")],
    )
    t = f.money(
        db,
        bank,
        [
            (D + timedelta(days=21), 10_000, "in", "amitk@ybl", "AMIT KUMAR"),
            (D + timedelta(days=40), 30_000, "in", "amitk@ybl", "AMIT KUMAR"),
        ],
    )
    reconcile(db, biz.id)
    s = answer(db, biz.id, "Sharma ji", "AMIT KUMAR", True, "user:o", t[0].id)
    assert s.credit.repaid_bank_exact_paise == 40_000 and s.credit.outstanding_paise == 0
    rules = {m.rule for m in db.execute(select(ReconMatch)).scalars()}
    assert rules == {"owner_confirmed", "credit_repaid"}


def test_owner_confirmed_share_in_features_and_the_cap(db: Session) -> None:
    from app.modules.trust.features import gather

    biz, led, bank = _setup(db)
    f.ledger(
        db,
        led,
        [(D, "Sharma ji", 80_000, "in"), (D + timedelta(days=5), "Gupta ji", 20_000, "out")],
    )
    t = f.money(
        db,
        bank,
        [
            (D, 80_000, "in", "amitk@ybl", "AMIT KUMAR"),
            (D + timedelta(days=5), 20_000, "out", "gupta.t@oksbi", "GUPTA TRADERS"),
        ],
    )
    reconcile(db, biz.id)
    answer(db, biz.id, "Sharma ji", "AMIT KUMAR", True, "user:o", t[0].id)
    r = gather(db, biz, date(2026, 11, 27)).records
    assert r.match_rate == 1.0 and r.owner_confirmed_share == 0.8

    many = RecordsFeatures(independent_entries=30, match_rate=1.0, owner_confirmed_share=0.8)
    few = RecordsFeatures(independent_entries=30, match_rate=1.0, owner_confirmed_share=0.3)
    assert records_pillar(many) == RECORDS_OWNER_CAP and records_pillar(few) == 100.0
    res = compute(
        Features(
            as_of="2026-11-27",
            money=MoneyFeatures(source="aa", months_of_data=12, active_months=12),
            records=many,
            network=NetworkFeatures(),
            presence=PresenceFeatures(),
        )
    )
    assert "matches_rest_on_owner" in [g.code for g in res.gaps]
    assert "write_full_names" in [i.code for i in res.improve]


def test_answer_with_another_businesss_payment_is_ignored(db: Session) -> None:
    biz, _, _ = _setup(db)
    _, _, other_bank = _setup(db)
    t = f.money(db, other_bank, [(D, 50_000, "in", "amitk@ybl", "AMIT KUMAR")])
    answer(db, biz.id, "Sharma ji", "AMIT KUMAR", True, "user:o", t[0].id)
    from app.db.models import NameAlias

    keys = {a.counterparty_key for a in db.execute(select(NameAlias)).scalars()}
    assert keys == {"amit kumar"}  # remembered by name only, not by the other shop's UPI ID
