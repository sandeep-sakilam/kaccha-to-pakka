"""Right to erase (DPDP Act 2023): deleting an account revokes every share, passport, consent and
helper link, deletes the files and the financial records, and anonymises what has to stay
(immutable assessments, the hash-chained audit log, rows other people's data points to).
Only the legally required, anonymised audit trail remains."""

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.errors import DomainError
from app.db.base import utcnow
from app.db.models import (
    AccessLog,
    Attestation,
    AuthSession,
    BankTransaction,
    Business,
    Consent,
    Counterparty,
    CounterpartyInvite,
    DeviceBinding,
    Dispute,
    EvidenceItem,
    LedgerEntry,
    NameAlias,
    Notification,
    OtpChallenge,
    Passport,
    PresenceRequest,
    ReconMatch,
    SahayakLink,
    Share,
    User,
    WaConversation,
)
from app.modules.audit.service import record
from app.modules.identity import security

CONFIRM_WORD = "DELETE"


@dataclass
class EraseReport:
    businesses: int = 0
    shares_revoked: int = 0
    passports_revoked: int = 0
    files_deleted: int = 0
    records_deleted: dict[str, int] = field(default_factory=dict)


def _count(db: Session, stmt: object) -> int:
    res = db.execute(stmt)  # type: ignore[call-overload]
    return int(getattr(res, "rowcount", 0) or 0)


def erase_account(db: Session, user: User, pin: str, confirm: str) -> EraseReport:
    if confirm.strip().upper() != CONFIRM_WORD:
        raise DomainError("Type DELETE to confirm", "confirm_required")
    if not security.verify_pin(pin, user.pin_hash):
        raise DomainError("Wrong PIN", "pin_wrong", 401)
    now = utcnow()
    rep = EraseReport()
    adapters = get_adapters()
    tag = "erased-" + hashlib.sha256(user.id.encode()).hexdigest()[:8]

    businesses = list(
        db.execute(select(Business).where(Business.owner_user_id == user.id)).scalars()
    )
    rep.businesses = len(businesses)
    for biz in businesses:
        passport_ids = [
            p.id
            for p in db.execute(select(Passport).where(Passport.business_id == biz.id)).scalars()
        ]
        rep.shares_revoked += _count(
            db,
            update(Share)
            .where(Share.passport_id.in_(passport_ids or [""]), Share.revoked_at.is_(None))
            .values(revoked_at=now),
        )
        share_ids = [
            s
            for (s,) in db.execute(
                select(Share.id).where(Share.passport_id.in_(passport_ids or [""]))
            ).all()
        ]
        db.execute(
            update(AccessLog)
            .where(AccessLog.share_id.in_(share_ids or [""]))
            .values(ip=None, viewer="erased")
        )
        rep.passports_revoked += _count(
            db,
            update(Passport)
            .where(Passport.business_id == biz.id)
            .values(status="revoked", vc_json={"erased": True}, signature="erased"),
        )
        # Bank link at the Account Aggregator
        for c in db.execute(
            select(Consent).where(Consent.business_id == biz.id, Consent.purpose == "aa_fetch")
        ).scalars():
            if c.scope.get("aa_handle"):
                try:
                    adapters.aa.revoke(str(c.scope["aa_handle"]))
                except AdapterError:
                    record(db, "system", "erase.aa_revoke_failed", f"business:{biz.id}", {})
        db.execute(
            update(SahayakLink)
            .where(SahayakLink.business_id == biz.id, SahayakLink.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        # Files and financial records
        evidence = list(
            db.execute(select(EvidenceItem).where(EvidenceItem.business_id == biz.id)).scalars()
        )
        ev_ids = [e.id for e in evidence]
        for e in evidence:
            if e.storage_key:
                adapters.storage.delete(e.storage_key)
                rep.files_deleted += 1
        entry_ids = [
            i
            for (i,) in db.execute(
                select(LedgerEntry.id).where(LedgerEntry.evidence_id.in_(ev_ids or [""]))
            ).all()
        ]
        txn_ids = [
            i
            for (i,) in db.execute(
                select(BankTransaction.id).where(BankTransaction.evidence_id.in_(ev_ids or [""]))
            ).all()
        ]
        counts = {
            "recon_matches": _count(
                db,
                delete(ReconMatch).where(
                    ReconMatch.ledger_entry_id.in_(entry_ids or [""])
                    | ReconMatch.bank_txn_id.in_(txn_ids or [""])
                ),
            ),
            "ledger_entries": _count(
                db, delete(LedgerEntry).where(LedgerEntry.id.in_(entry_ids or [""]))
            ),
            "bank_transactions": _count(
                db, delete(BankTransaction).where(BankTransaction.id.in_(txn_ids or [""]))
            ),
            "presence_requests": _count(
                db, delete(PresenceRequest).where(PresenceRequest.business_id == biz.id)
            ),
            "evidence_items": _count(
                db, delete(EvidenceItem).where(EvidenceItem.id.in_(ev_ids or [""]))
            ),
            "name_aliases": _count(db, delete(NameAlias).where(NameAlias.business_id == biz.id)),
        }
        for k, v in counts.items():
            rep.records_deleted[k] = rep.records_deleted.get(k, 0) + v
        # Third parties' phone numbers given for this business
        db.execute(
            update(CounterpartyInvite)
            .where(CounterpartyInvite.business_id == biz.id)
            .values(phone="erased", status="expired", penny_ref=None)
        )
        db.execute(
            update(Dispute)
            .where(Dispute.business_id == biz.id)
            .values(reason=None, resolution=None)
        )
        # Where this business confirmed others or appears as a partner node
        db.execute(
            update(Counterparty)
            .where(Counterparty.business_id == biz.id)
            .values(business_id=None, registered_name=None)
        )
        db.execute(
            update(Attestation)
            .where(Attestation.subject_business_id == biz.id)
            .values(status="erased", claim={}, proof_txn_ref=None)
        )
        biz.name, biz.address, biz.city, biz.sells = "Erased business", None, None, None
        biz.udyam = biz.gstin = None
        biz.geo_home = biz.merchant_geo = None
        biz.deleted_at = now
        record(db, f"user:{user.id}", "business.erased", f"business:{biz.id}", {})

    # The person: consents, helper links, sessions, devices, messages
    db.execute(
        update(Consent)
        .where(Consent.user_id == user.id, Consent.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.execute(update(Consent).where(Consent.user_id == user.id).values(scope={}))
    db.execute(
        update(SahayakLink)
        .where(SahayakLink.sahayak_user_id == user.id, SahayakLink.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(DeviceBinding).where(DeviceBinding.user_id == user.id))
    db.execute(delete(Notification).where(Notification.user_id == user.id))
    db.execute(delete(OtpChallenge).where(OtpChallenge.phone == user.phone))
    db.execute(delete(WaConversation).where(WaConversation.phone == user.phone))
    db.execute(
        update(CounterpartyInvite)
        .where(CounterpartyInvite.phone == user.phone)
        .values(phone="erased")
    )
    user.phone, user.name, user.pin_hash, user.gender = tag[:16], None, None, None
    user.device_ids, user.kyc_status, user.status, user.deleted_at = [], "erased", "erased", now
    record(
        db,
        "system",
        "account.erased",
        f"user:{user.id}",
        {
            "businesses": rep.businesses,
            "shares_revoked": rep.shares_revoked,
            "files_deleted": rep.files_deleted,
        },
    )
    db.flush()
    return rep
