"""Assessments built from real rows in the database."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Attestation, Business
from app.modules.trust import service
from app.modules.trust.features import gather
from tests import factories as f

TODAY = date.today()


def strong_business(db: Session, source: str = "aa", months: int = 12) -> Business:
    biz = f.business(db, "Strong Kirana", started=date(2012, 1, 1))
    money_ev = f.evidence(
        db,
        biz,
        "aa_fetch" if source == "aa" else "bank_statement",
        "aa:mock" if source == "aa" else "pdf:bank",
    )
    led_ev = f.evidence(db, biz, "ledger_page", "camera", "extracted")
    f.evidence(db, biz, "shop_front", "camera", "received")
    money_rows, ledger_rows = [], []
    for d in range(months * 30, 0, -2):
        day = TODAY - timedelta(days=d)
        amt = (2000 + (d % 7) * 150) * 100
        money_rows.append((day, amt, "in", f"cust{d % 9}@oksbi", f"CUSTOMER {d % 9}"))
        if d % 4 == 0:
            ledger_rows.append((day + timedelta(days=1), f"Customer {d % 9}", amt, "in"))
        if d % 10 == 0:
            ledger_rows.append((day, "Cash sale", 50_000, "in"))  # cash: no bank match
    f.money(db, money_ev, money_rows)
    f.ledger(db, led_ev, ledger_rows)
    for _ in range(3):
        db.add(
            Attestation(
                subject_business_id=biz.id,
                evidence_type="penny_drop",
                claim={},
                money_match=True,
                status="confirmed",
                weight=1.0,
                expires_at=utcnow() + timedelta(days=100),
            )
        )
    db.flush()
    return biz


def test_strong_business_end_to_end(db: Session) -> None:
    biz = strong_business(db)
    a = service.assess(db, biz)
    assert a.band in {"A", "B"} and a.confidence == "High" and a.status == "final"
    assert a.rules_version and a.inputs_hash and a.model_versions["rules"]
    r = service.recompute(a)
    assert r.band == a.band


def test_pdf_source_caps(db: Session) -> None:
    biz = strong_business(db, source="pdf")
    assert service.assess(db, biz).band == "C"


def test_assessments_are_immutable(db: Session) -> None:
    biz = strong_business(db)
    a = service.assess(db, biz)
    db.commit()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE assessments SET band='A' WHERE id=:i"), {"i": a.id})
    db.rollback()


def test_round_tripping_is_flagged(db: Session) -> None:
    biz = strong_business(db, months=4)
    ev = f.evidence(db, biz, "aa_fetch", "aa:mock")
    rows = []
    for k in range(4):
        day = TODAY - timedelta(days=10 * k + 3)
        rows += [
            (day, 5_000_000, "out", "friend@okaxis", "FRIEND"),
            (day + timedelta(days=2), 5_000_000, "in", "friend@okaxis", "FRIEND"),
        ]
    f.money(db, ev, rows)
    feats = gather(db, biz)
    assert any(fl["code"] == "round_tripping" for fl in feats.flags)
    assert feats.money.netted_round_trip_paise == 4 * 5_000_000
    assert service.assess(db, biz).status == "on_hold"


def test_ledger_typed_from_bank_counts_once(db: Session) -> None:
    biz = f.business(db)
    money_ev = f.evidence(db, biz, "aa_fetch", "aa:mock")
    led_ev = f.evidence(db, biz, "ledger_export", "khatabook", "extracted")
    rows = [
        (TODAY - timedelta(days=i), (100 + i) * 100, "in", f"c{i}@ok", f"C{i}") for i in range(20)
    ]
    f.money(db, money_ev, rows)
    f.ledger(db, led_ev, [(d, n, a, dr) for d, a, dr, _, n in rows])
    feats = gather(db, biz)
    assert feats.records.mirrored_ledgers == 1 and feats.records.independent_entries == 0


def test_tampered_statement_holds(db: Session) -> None:
    biz = strong_business(db)
    f.evidence(db, biz, "bank_statement", "pdf", "on_hold")
    assert service.assess(db, biz).status == "on_hold"


def test_api(client: TestClient) -> None:
    from tests.conftest import setup_business

    h, biz = setup_business(client)
    assert client.get(f"/businesses/{biz}/assessments/latest", headers=h).status_code == 404
    a = client.post(f"/businesses/{biz}/assess", headers=h).json()
    assert a["band"] == "U" and a["confidence"] == "Low"
    assert client.get(f"/assessments/{a['id']}/verify", headers=h).json()["reproducible"]
