from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Attestation, Business, Counterparty
from app.modules.fraud.graph import (
    Payment,
    collusion_rings,
    confirmer_standing,
    payment_cycles,
    scan,
)
from app.modules.trust import service as trust
from tests import factories as f

D = date(2026, 10, 1)


def test_cycle_detection_pure() -> None:
    pays = [
        Payment("A", "B", 100_000_00, D),
        Payment("B", "C", 99_000_00, D + timedelta(days=2)),
        Payment("C", "A", 100_500_00, D + timedelta(days=4)),
    ]
    assert payment_cycles(pays) == [["A", "B", "C"]]
    slow = [*pays[:2], Payment("C", "A", 100_000_00, D + timedelta(days=60))]
    assert payment_cycles(slow) == []
    different = [*pays[:2], Payment("C", "A", 10_000_00, D + timedelta(days=4))]
    assert payment_cycles(different) == []


def _link(db: Session, biz: Business, vpa: str) -> None:
    db.add(Counterparty(vpa_or_account=vpa, registered_name=biz.name.upper(), business_id=biz.id))
    db.flush()


def test_cycle_across_three_businesses_holds_all(db: Session) -> None:
    a, b, c = (f.business(db, n) for n in ("Cycle A", "Cycle B", "Cycle C"))
    for biz, vpa in ((a, "cyc.a@ok"), (b, "cyc.b@ok"), (c, "cyc.c@ok")):
        _link(db, biz, vpa)
    for payer, payee_vpa, day in ((a, "cyc.b@ok", 0), (b, "cyc.c@ok", 2), (c, "cyc.a@ok", 5)):
        ev = f.evidence(db, payer, "aa_fetch", "aa:mock")
        f.money(db, ev, [(D + timedelta(days=day), 5_000_000, "out", payee_vpa, "X")])
    flags = scan(db)
    assert {(fl.business_id, fl.code) for fl in flags} == {
        (a.id, "payment_cycle"),
        (b.id, "payment_cycle"),
        (c.id, "payment_cycle"),
    }
    assert trust.assess(db, a).status == "on_hold"
    assert scan(db) == []  # same findings are not duplicated


def test_collusion_ring_of_new_accounts(db: Session) -> None:
    ring = [f.business(db, f"Ring {i}", started=date(2010, 1, 1)) for i in range(3)]
    for i, subject in enumerate(ring):
        confirmer = ring[(i + 1) % 3]
        db.add(
            Attestation(
                subject_business_id=subject.id,
                confirmer_business_id=confirmer.id,
                evidence_type="penny_drop",
                claim={},
                money_match=True,
                status="confirmed",
                weight=1.0,
                expires_at=utcnow() + timedelta(days=90),
            )
        )
    db.flush()
    assert sorted(b.id for b in ring) in collusion_rings(db)
    codes = {fl.code for fl in scan(db)}
    assert "collusion_ring" in codes


def test_established_confirmer_is_not_a_ring(db: Session) -> None:
    subjects = [f.business(db, f"Shop {i}") for i in range(3)]
    wholesaler = f.business(db, "Old Wholesaler")
    wholesaler.created_at = utcnow() - timedelta(days=900)
    ev = f.evidence(db, wholesaler, "aa_fetch", "aa:mock")
    f.money(db, ev, [(D, 1000, "in", f"cust{i}@ok", f"C{i}") for i in range(20)])
    for s in subjects:
        db.add(
            Attestation(
                subject_business_id=s.id,
                confirmer_business_id=wholesaler.id,
                evidence_type="penny_drop",
                claim={},
                money_match=True,
                status="confirmed",
                weight=1.0,
                expires_at=utcnow() + timedelta(days=90),
            )
        )
    db.flush()
    assert collusion_rings(db) == [] or all(wholesaler.id not in r for r in collusion_rings(db))
    assert confirmer_standing(db, wholesaler.id) > 1.0


def test_false_confirmation_drops_all_weight(db: Session) -> None:
    confirmer = f.business(db, "Liar Traders")
    subject = f.business(db, "Some Shop")
    before = confirmer_standing(db, confirmer.id)
    db.add(
        Attestation(
            subject_business_id=subject.id,
            confirmer_business_id=confirmer.id,
            evidence_type="penny_drop",
            claim={},
            status="disproved",
            weight=0,
        )
    )
    db.flush()
    assert confirmer_standing(db, confirmer.id) < before * 0.5
