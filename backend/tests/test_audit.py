import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.audit.service import GENESIS, entries_for, record, verify_chain


def test_chain_links_and_verifies(db: Session) -> None:
    a = record(db, "user:1", "consent.grant", "business:1", {"purpose": "build"})
    b = record(db, "user:1", "share.create", "business:1", {"lender": "SBI"})
    assert b.prev_hash == a.hash
    assert a.prev_hash == GENESIS or a.prev_hash
    check = verify_chain(db)
    assert check.ok and check.checked >= 2
    assert [e.action for e in entries_for(db, "business:1")] == ["share.create", "consent.grant"]


def test_database_refuses_update_and_delete(db: Session) -> None:
    record(db, "system", "score", "business:2")
    db.commit()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE audit_log SET actor='attacker'"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_log"))
    db.rollback()


def test_tampering_is_detected(db: Session) -> None:
    record(db, "system", "a", "x")
    target = record(db, "system", "b", "x", {"amount_paise": 100})
    record(db, "system", "c", "x")
    db.flush()
    # Simulate an attacker with superuser rights bypassing the trigger.
    db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
    db.execute(
        text("UPDATE audit_log SET details='{\"amount_paise\": 999}' WHERE seq=:s"),
        {"s": target.seq},
    )
    db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))
    db.expire_all()
    check = verify_chain(db)
    assert not check.ok and check.broken_at_seq == target.seq
