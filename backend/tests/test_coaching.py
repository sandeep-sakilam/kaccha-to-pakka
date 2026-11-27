from datetime import date

from sqlalchemy.orm import Session

from app.modules.trust import service as trust
from app.modules.trust.explain import explain
from app.modules.trust.rules import Reason, RecordsFeatures, compute
from tests import factories as f
from tests.test_trust_rules import strong


def codes(reasons: list[Reason]) -> list[str]:
    return [r.code for r in reasons]


def test_unconfirmed_pages_say_confirm_not_add() -> None:
    feats = strong()
    feats.records = RecordsFeatures(pending_confirmation=4)
    r = compute(feats)
    assert "confirm_ledger_entries" in codes(r.improve)
    assert "add_ledger" not in codes(r.improve)
    assert "ledger_unconfirmed" in codes(r.gaps) and "no_ledger" not in codes(r.gaps)


def test_no_pages_still_say_add() -> None:
    feats = strong()
    feats.records = RecordsFeatures()
    r = compute(feats)
    assert "add_ledger" in codes(r.improve) and "confirm_ledger_entries" not in codes(r.improve)


def test_from_db_and_text(db: Session) -> None:
    biz = f.business(db)
    ev = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    f.ledger(db, ev, [(date(2026, 10, 1), "Sharma", 1000, "in")], status="needs_readback")
    a = trust.assess(db, biz)
    assert "confirm_ledger_entries" in [r["code"] for r in a.reasons["improve"]]
    e = explain(a.band, a.confidence, a.status, a.reasons, "en")
    assert "Confirm your ledger entries" in e.improve
    assert "Add your ledger pages" not in e.improve


def test_old_snapshots_still_load() -> None:
    d = strong().as_dict()
    d["records"].pop("pending_confirmation")
    from app.modules.trust.rules import Features

    assert Features.from_dict(d).records.pending_confirmation == 0
