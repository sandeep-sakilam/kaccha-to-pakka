from sqlalchemy.orm import Session

from app.adapters.ai import MockAI
from app.evaluation import extraction_eval, redteam
from app.evaluation.harness import credit_book_eval, reconciliation_eval, to_markdown
from app.evaluation.metrics import wer


def test_wer() -> None:
    assert wer("chaar hazaar mile", "chaar hazaar mile") == 0
    assert wer("chaar hazaar mile", "char hazaar mile") == 1 / 3


def test_extraction_scoring_on_sandbox_set() -> None:
    pages = extraction_eval.sandbox_golden(3)
    perfect = extraction_eval.score_provider(MockAI(), pages).as_dict()
    assert perfect["field_accuracy"] == {"date": 1.0, "party": 1.0, "amount": 1.0, "direction": 1.0}
    broken = extraction_eval.score_provider(MockAI(fail=True), pages).as_dict()
    assert broken["failures"] == 3 and broken["exact_amount_match_rate"] == 0.0


def test_red_team_catches_every_attack(db: Session) -> None:
    results = redteam.run(db)
    missed = [r.attack for r in results if not r.caught]
    assert len(results) == 14 and missed == []


def test_reconciliation_precision_recall(db: Session) -> None:
    r = reconciliation_eval(db, businesses=3)
    assert r["precision"] >= 0.95 and r["recall"] >= 0.75, r
    assert r["owner_questions"] > 0


def test_credit_book_precision_recall(db: Session) -> None:
    """Repayments in credit books are found despite late, lumped and part payments; the only
    false positives allowed are small spot purchases by customers who still owe."""
    r = credit_book_eval(db, businesses=4)
    assert r["recall"] == 1.0 and r["precision"] >= 0.9, r


def test_markdown_report_shape() -> None:
    md = to_markdown(
        {
            "generated_at": "now",
            "sandbox": True,
            "golden_set": {"pages": 1, "real_pages": False},
            "extraction": [],
            "reconciliation": {
                "precision": 1,
                "recall": 1,
                "businesses": 1,
                "tp": 1,
                "fp": 0,
                "fn": 0,
            },
            "credit_book": {
                "precision": 1,
                "recall": 1,
                "customers": 6,
                "tp": 1,
                "fp": 0,
                "fn": 0,
                "patterns": {"on_time": 6},
            },
            "red_team": {"caught": 1, "cases": 1, "catch_rate": 1.0, "results": []},
            "stt": {},
            "ai_cost": {"rupees_per_passport": 1, "note": ""},
            "band_distribution": {},
            "not_measured_here": [],
        }
    )
    assert "Catch rate **1/1**" in md
    assert "## Credit books (udhaar)" in md and "on_time 6" in md
