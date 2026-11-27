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
