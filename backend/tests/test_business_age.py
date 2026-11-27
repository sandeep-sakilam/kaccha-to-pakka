"""Business age counts fully only as far as the register or the bank shows it."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.models import BankTransaction, Business
from app.modules.trust.features import gather, proven_start
from app.modules.trust.rules import (
    Features,
    MoneyFeatures,
    NetworkFeatures,
    PresenceFeatures,
    RecordsFeatures,
    compute,
    presence_pillar,
)
from tests import factories as f

TODAY = date(2026, 11, 27)


def _aa(db: Session, biz: Business, first: date) -> None:
    ev = f.evidence(db, biz, "aa_fetch", "aa:mock")
    f.money(
        db,
        ev,
        [(first + timedelta(days=30 * i), 100_000, "in", f"c{i}@ybl", "C") for i in range(12)],
    )


def _verified(biz: Business, registered: date, started: date | None = None) -> None:
    biz.registration_status, biz.registration_source = "verified", "udyam"
    biz.registered_on, biz.registration_started_on = registered, started


def test_claimed_age_alone_counts_at_half() -> None:
    claimed = PresenceFeatures(business_age_years=17)
    proven = PresenceFeatures(business_age_years=17, proven_age_years=17)
    assert presence_pillar(claimed) == 15 and presence_pillar(proven) == 30


def test_bank_history_proves_age(db: Session) -> None:
    biz = f.business(db, started=date(2009, 1, 1))
    _aa(db, biz, date(2025, 10, 1))
    p = gather(db, biz, TODAY).presence
    assert p.age_proof == "bank" and p.proven_age_years == 1.2 and p.business_age_years == 17.9


def test_commencement_date_on_an_old_udyam_registration_proves_age(db: Session) -> None:
    biz = f.business(db, started=date(2009, 1, 1))
    _verified(biz, date(2021, 3, 2), date(2009, 6, 1))
    p = gather(db, biz, TODAY).presence
    assert (p.age_proof, p.proven_age_years) == ("commencement", 17.5)


def test_commencement_on_a_brand_new_registration_is_not_proof(db: Session) -> None:
    """Registering today and declaring 2009 is the owner's word again."""
    biz = f.business(db, started=date(2009, 1, 1))
    _verified(biz, TODAY - timedelta(days=20), date(2009, 6, 1))
    p = gather(db, biz, TODAY).presence
    assert p.age_proof == "registration" and p.proven_age_years == 0.1


def test_registration_that_did_not_verify_proves_nothing(db: Session) -> None:
    biz = f.business(db, started=date(2009, 1, 1))
    _verified(biz, date(2018, 1, 1), date(2009, 6, 1))
    biz.registration_status = "name_mismatch"
    assert proven_start(biz, [], {}, TODAY) == (None, "none")


def test_pdf_statements_do_not_prove_age(db: Session) -> None:
    biz = f.business(db)
    ev = f.evidence(db, biz, "bank_statement", "upload")
    t = BankTransaction(
        evidence_id=ev.id, txn_date=date(2015, 1, 1), amount_paise=1, direction="in"
    )
    assert proven_start(biz, [t], {ev.id: ev}, TODAY) == (None, "none")


def test_reasons_say_how_much_is_proven() -> None:
    res = compute(
        Features(
            as_of=str(TODAY),
            money=MoneyFeatures(source="aa", months_of_data=12, active_months=12),
            records=RecordsFeatures(),
            network=NetworkFeatures(),
            presence=PresenceFeatures(
                business_age_years=17, proven_age_years=1.2, age_proof="bank"
            ),
        )
    )
    gaps = {g.code: g.params for g in res.gaps}
    assert gaps.get("age_not_proven") == {"claimed": 17, "proven": 1}
    assert "business_age" not in [p.code for p in res.positives]
