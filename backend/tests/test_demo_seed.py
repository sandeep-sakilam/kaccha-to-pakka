from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Business, CounterpartyInvite
from app.modules.passport.service import issue
from app.sandbox import demo


def test_demo_seed_and_fraud_scene(db: Session) -> None:
    out = demo.seed_all(db)
    kirana, namkeen, tailor = out["kirana"], out["namkeen"], out["tailor"]
    assert isinstance(kirana, dict) and isinstance(namkeen, dict) and isinstance(tailor, dict)
    print(out)
    # These are the bands the demo script and README promise; if they drift, update both.
    assert (kirana["band"], kirana["status"]) == ("B", "valid")
    assert (namkeen["band"], namkeen["status"]) == ("B", "valid")
    assert (tailor["band"], tailor["status"]) == ("C", "valid")  # PDF only: capped at C
    fraud = out["fraud"]
    assert isinstance(fraud, dict)
    assert fraud["first_attempt"] == "rejected" and fraud["passport_status"] == "on_hold"
    first = db.execute(
        select(CounterpartyInvite).where(
            CounterpartyInvite.business_id == fraud["business_id"],
            CounterpartyInvite.status == "rejected",
        )
    ).scalar_one()
    assert first.flags == ["account_mismatch"]
    # The replay invite (for the live scene) is rejected the same way.
    assert demo.play_fraud(db, str(fraud["replay_invite_token"])) == "rejected"
    biz = db.get(Business, str(fraud["business_id"]))
    assert biz is not None
    assert issue(db, biz, "test").status == "on_hold"


def test_demo_seed_shows_the_newer_evidence(db: Session) -> None:
    """F58-F66 in the demo: each shop carries the evidence the demo script talks about."""
    from app.modules.passport.service import history
    from app.modules.trust.features import gather

    out = demo.seed_all(db)
    kirana = db.get(Business, str(out["kirana"]["business_id"]))  # type: ignore[index]
    namkeen = db.get(Business, str(out["namkeen"]["business_id"]))  # type: ignore[index]
    assert kirana is not None and namkeen is not None

    k = gather(db, kirana)
    assert kirana.registration_status == "verified"  # Udyam, checked against the register
    assert k.presence.age_proof == "commencement" and (k.presence.proven_age_years or 0) > 15
    assert k.presence.address_proofs == 1  # electricity bill in the shop's name
    assert k.money.cash_deposit_months >= 12  # weekly cash deposits
    assert k.records.supplier_credit_entries == 6 and k.records.supplier_bank_paid_rate == 1.0
    assert [h["band"] for h in history(db, kirana.id)] == ["C", "B"]

    n = gather(db, namkeen)
    assert n.records.credit_entries == 9 and n.records.credit_customers == 3
    assert 0.5 < n.records.credit_bank_repaid_rate < 0.7  # one customer paid only part
    assert n.records.daily_sales_months_agree >= 2 and n.records.daily_sales_months_below_bank == 0
    assert namkeen.women_helpers_only
