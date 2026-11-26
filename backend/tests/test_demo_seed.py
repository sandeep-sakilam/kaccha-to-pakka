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
    assert kirana["band"] in {"A", "B"} and kirana["status"] == "valid"
    assert namkeen["band"] in {"A", "B", "C"} and namkeen["status"] == "valid"
    assert tailor["band"] in {"C", "D"} and tailor["status"] == "valid"  # PDF only: max C
    fraud = out["fraud"]
    assert isinstance(fraud, dict)
    assert demo.play_fraud(db, str(fraud["invite_token"])) == "rejected"
    inv = db.execute(
        select(CounterpartyInvite).where(CounterpartyInvite.token == fraud["invite_token"])
    ).scalar_one()
    assert inv.flags == ["account_mismatch"]
    biz = db.get(Business, str(fraud["business_id"]))
    assert biz is not None
    p = issue(db, biz, "test")
    assert p.status == "on_hold"
