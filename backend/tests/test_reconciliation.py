from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.reconciliation.engine import questions, reconcile
from app.modules.reconciliation.names import similarity, transliterate
from tests import factories as f
from tests.conftest import setup_business

D = date(2026, 10, 12)


def test_transliteration_and_similarity() -> None:
    assert transliterate("शर्मा") == "sharmaa"
    assert similarity("शर्मा जी", "RAKESH SHARMA") >= 80
    assert similarity("Sharmaji", "RAKESH SHARMA") >= 80
    assert similarity("गुप्ता ट्रेडर्स", "GUPTA TRADERS") >= 80
    assert similarity("Meena", "RAKESH SHARMA") < 45


def test_exact_match_with_hindi_name(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.ledger(
        db,
        led,
        [(D, "शर्मा जी", 400000, "in"), (D, "Gupta", 250000, "out"), (D, "Unbacked", 99900, "in")],
    )
    f.money(
        db,
        bank,
        [
            (date(2026, 10, 13), 400000, "in", "rakesh.sharma@oksbi", "RAKESH SHARMA"),
            (D, 250000, "out", "gupta@okhdfc", "GUPTA TRADERS"),
            (D, 400000, "out", "x@ok", "RAKESH SHARMA"),
        ],
    )
    s = reconcile(db, biz.id)
    assert s.matched_entries == 2 and s.rules == {"amount_date_name": 2}
    assert round(s.match_rate, 3) == round(650000 / 749900, 3)


def test_outside_date_window_or_wrong_direction_no_match(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.ledger(db, led, [(D, "Sharma", 400000, "in"), (D, "Sharma", 100, "in")])
    f.money(
        db,
        bank,
        [(date(2026, 10, 16), 400000, "in", None, "SHARMA"), (D, 100, "out", None, "SHARMA")],
    )
    assert reconcile(db, biz.id).matched_entries == 0


def test_ambiguous_name_asks_owner_and_answer_is_remembered(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.ledger(db, led, [(D, "Pappu", 300000, "in"), (date(2026, 10, 20), "Pappu", 150000, "in")])
    f.money(
        db,
        bank,
        [
            (D, 300000, "in", "pradeep.k@okicici", "PRADEEP KUMAR"),
            (date(2026, 10, 21), 150000, "in", "pradeep.k@okicici", "PRADEEP KUMAR"),
        ],
    )
    s = reconcile(db, biz.id)
    assert s.matched_entries == 0
    qs = questions(db, biz.id)
    assert len(qs) == 1 and qs[0].prompt_en == "Is Pappu the same as PRADEEP KUMAR?"
    from app.modules.reconciliation.engine import answer

    s2 = answer(db, biz.id, "Pappu", "PRADEEP KUMAR", True, "user:x")
    assert s2.matched_entries == 2 and questions(db, biz.id) == []
    s3 = answer(db, biz.id, "Pappu", "PRADEEP KUMAR", False, "user:x")
    assert s3.matched_entries == 0


def test_nameless_single_candidate_is_weak_match(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.ledger(db, led, [(D, None, 123400, "in")])
    f.money(db, bank, [(D, 123400, "in", "a@ok", "A")])
    s = reconcile(db, biz.id)
    assert s.rules == {"amount_date_only": 1}


def test_many_to_one(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.ledger(db, led, [(D, "Gupta", 100000, "out"), (date(2026, 10, 13), "Gupta", 50000, "out")])
    f.money(db, bank, [(date(2026, 10, 13), 150000, "out", "gupta@okhdfc", "GUPTA TRADERS")])
    s = reconcile(db, biz.id)
    assert s.matched_entries == 2 and s.rules == {"many_to_one": 1}


def test_low_confidence_and_held_money_do_not_count(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    held = f.evidence(db, biz, "bank_statement", "pdf", "on_hold")
    f.ledger(db, led, [(D, "Sharma", 400000, "in")], status="needs_readback")
    f.ledger(db, led, [(D, "Gupta", 200000, "in")])
    f.money(db, held, [(D, 200000, "in", None, "GUPTA")])
    s = reconcile(db, biz.id)
    assert s.ledger_entries == 1 and s.matched_entries == 0


def test_rerun_is_idempotent(db: Session) -> None:
    biz = f.business(db)
    led = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    bank = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.ledger(db, led, [(D, "Sharma", 400000, "in")])
    f.money(db, bank, [(D, 400000, "in", None, "RAKESH SHARMA")])
    assert reconcile(db, biz.id).matched_entries == reconcile(db, biz.id).matched_entries == 1


def test_api(client: TestClient) -> None:
    h, biz = setup_business(client)
    r = client.post(f"/businesses/{biz}/reconcile", headers=h).json()
    assert r["ledger_entries"] == 0 and r["match_rate"] == 0
    assert client.get(f"/businesses/{biz}/recon/questions", headers=h).json() == []
