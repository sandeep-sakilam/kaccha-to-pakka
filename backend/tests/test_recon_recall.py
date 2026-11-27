from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.modules.reconciliation.engine import answer, questions, reconcile
from app.modules.reconciliation.names import similarity
from tests import factories as f

D = date(2026, 10, 1)


def test_marwari_honorific_and_business_words() -> None:
    assert similarity("Jain sa", "JAIN CLOTH HOUSE") >= 80
    assert similarity("Agrawal saab", "AGRAWAL BHANDAR") >= 80


def _nickname_case(db: Session, n: int) -> str:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    rows = [(D + timedelta(days=9 * i), (1234 + 111 * i) * 100) for i in range(n)]
    f.ledger(db, led, [(d, "Pappu", a, "in") for d, a in rows])
    f.money(
        db,
        bank,
        [(d + timedelta(days=1), a, "in", "pradeep.k@okicici", "PRADEEP KUMAR") for d, a in rows],
    )
    return biz.id


def test_nickname_learned_from_three_unique_exact_matches(db: Session) -> None:
    biz = _nickname_case(db, 4)
    s = reconcile(db, biz)
    assert s.matched_entries == 4 and s.rules == {"learned_alias": 4}
    assert questions(db, biz) == []


def test_two_matches_are_not_enough_to_learn(db: Session) -> None:
    biz = _nickname_case(db, 2)
    assert reconcile(db, biz).matched_entries == 0
    assert len(questions(db, biz)) == 1


def test_owner_no_overrides_learning(db: Session) -> None:
    biz = _nickname_case(db, 4)
    s = answer(db, biz, "Pappu", "PRADEEP KUMAR", False, "user:x")
    assert s.matched_entries == 0


def test_partial_payment_in_two_instalments(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.ledger(db, led, [(D, "Sharma ji", 1_000_000, "in")])
    f.money(
        db,
        bank,
        [
            (D, 600_000, "in", "rakesh@oksbi", "RAKESH SHARMA"),
            (D + timedelta(days=2), 400_000, "in", "rakesh@oksbi", "RAKESH SHARMA"),
            (D + timedelta(days=1), 400_000, "in", "other@ok", "SOMEONE ELSE"),
        ],
    )
    s = reconcile(db, biz.id)
    assert s.matched_entries == 1 and s.rules == {"one_to_many": 1}


def test_partial_payment_from_different_payers_is_not_matched(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.ledger(db, led, [(D, "Sharma ji", 1_000_000, "in")])
    f.money(
        db,
        bank,
        [
            (D, 600_000, "in", "rakesh@oksbi", "RAKESH SHARMA"),
            (D, 400_000, "in", "other@ok", "SOMEONE ELSE"),
        ],
    )
    assert reconcile(db, biz.id).matched_entries == 0
