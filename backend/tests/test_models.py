from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.crypto import decrypt, encrypt
from app.db.models import BankTransaction, Business, EvidenceItem, LedgerEntry, User

SPEC_TABLES = {
    "users",
    "businesses",
    "sahayak_links",
    "consents",
    "evidence_items",
    "ledger_entries",
    "bank_transactions",
    "counterparties",
    "recon_matches",
    "attestations",
    "assessments",
    "passports",
    "shares",
    "access_logs",
    "disputes",
    "audit_log",
}


def test_all_spec_tables_exist() -> None:
    assert set(Base.metadata.tables) >= SPEC_TABLES


def test_money_columns_are_integers() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if col.name.endswith("_paise"):
                assert col.type.python_type is int, f"{table.name}.{col.name}"


def _business(db: Session) -> Business:
    user = User(phone="+919800000001")
    db.add(user)
    db.flush()
    biz = Business(owner_user_id=user.id, name="Test Kirana", category="kirana")
    db.add(biz)
    db.flush()
    return biz


def test_ledger_entry_roundtrip_and_encryption(db: Session) -> None:
    biz = _business(db)
    ev = EvidenceItem(business_id=biz.id, type="ledger_photo", source="camera")
    db.add(ev)
    db.flush()
    entry = LedgerEntry(
        evidence_id=ev.id,
        entry_date=date(2026, 10, 12),
        party_text="Sharma ji",
        amount_paise=400000,
        direction="in",
    )
    db.add(entry)
    db.commit()
    raw = db.execute(
        text("select party_text from ledger_entries where id=:i"), {"i": entry.id}
    ).scalar_one()
    assert raw.startswith("enc1:") and "Sharma" not in raw
    db.expire_all()
    assert db.get(LedgerEntry, entry.id).party_text == "Sharma ji"  # type: ignore[union-attr]


def test_negative_amount_rejected(db: Session) -> None:
    biz = _business(db)
    ev = EvidenceItem(business_id=biz.id, type="aa_fetch", source="aa")
    db.add(ev)
    db.flush()
    db.add(
        BankTransaction(
            evidence_id=ev.id, txn_date=date(2026, 1, 1), amount_paise=-1, direction="in"
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_encrypt_roundtrip() -> None:
    token = encrypt("RAKESH SHARMA")
    assert token != encrypt("RAKESH SHARMA")
    assert decrypt(token) == "RAKESH SHARMA"
