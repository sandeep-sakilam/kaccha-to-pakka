"""Scoped, expiring, revocable shares: one per named lender. Every view is logged and the owner
is told ("SBI Rajwada branch viewed your passport")."""

import secrets
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError, NotFound
from app.db.base import utcnow
from app.db.models import (
    AccessLog,
    Assessment,
    Attestation,
    BankTransaction,
    Business,
    Consent,
    EvidenceItem,
    Passport,
    PresenceRequest,
    Share,
    User,
)
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.notify import notify
from app.modules.passport import service as passports

SCOPES = {"summary", "evidence"}
DEFAULT_DAYS = 30
MAX_DAYS = 90


class Gone(DomainError):
    status_code = 410


def create(
    db: Session, owner: User, biz: Business, lender_org: str, scope: str, days: int = DEFAULT_DAYS
) -> Share:
    if biz.owner_user_id != owner.id:
        raise DomainError("Only the owner can share the passport", "owner_only", 403)
    if scope not in SCOPES:
        raise DomainError("Choose summary or summary with evidence", "bad_scope")
    if not 1 <= days <= MAX_DAYS:
        raise DomainError("Share for 1 to 90 days", "bad_days")
    p = passports.latest(db, biz.id)
    if p is None:
        raise DomainError("Make your passport first", "no_passport", 409)
    from app.modules.abuse.service import check_share_allowed

    check_share_allowed(db, owner)
    s = Share(
        passport_id=p.id,
        lender_org=lender_org.strip()[:200],
        scope=scope,
        token=secrets.token_urlsafe(24),
        expires_at=utcnow() + timedelta(days=days),
    )
    db.add(s)
    db.flush()
    consent.grant(
        db,
        owner,
        "share_lender",
        biz.id,
        {"share_id": s.id, "lender": s.lender_org, "scope": scope},
        days,
    )
    record(
        db,
        f"user:{owner.id}",
        "share.create",
        f"business:{biz.id}",
        {"share_id": s.id, "lender": s.lender_org, "scope": scope, "days": days},
    )
    return s


def link(s: Share) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/l/{s.token}"


def business_of(db: Session, s: Share) -> Business:
    p = db.get(Passport, s.passport_id)
    biz = db.get(Business, p.business_id) if p else None
    assert biz is not None
    return biz


def revoke(db: Session, owner: User, s: Share) -> None:
    biz = business_of(db, s)
    if biz.owner_user_id != owner.id:
        raise NotFound("Share not found", "share_not_found")
    if s.revoked_at is None:
        s.revoked_at = utcnow()
        for c in db.execute(
            select(Consent).where(
                Consent.user_id == owner.id,
                Consent.purpose == "share_lender",
                Consent.revoked_at.is_(None),
            )
        ).scalars():
            if c.scope.get("share_id") == s.id:
                consent.revoke(db, owner, c.id)
        record(db, f"user:{owner.id}", "share.revoke", f"business:{biz.id}", {"share_id": s.id})


def state(s: Share) -> str:
    if s.revoked_at:
        return "revoked"
    if s.expires_at < utcnow():
        return "expired"
    return "active"


def by_token(db: Session, token: str) -> Share:
    s = db.execute(select(Share).where(Share.token == token)).scalar_one_or_none()
    if s is None:
        raise NotFound("This link is not valid", "share_not_found")
    st = state(s)
    if st != "active":
        raise Gone(f"This share has {st}. Ask the owner for a new link.", f"share_{st}")
    from app.modules.abuse.limits import hit
    from app.modules.abuse.service import Frozen, frozen_until

    hit("lender_views", s.id)
    owner = db.get(User, business_of(db, s).owner_user_id)
    if owner is not None and frozen_until(db, owner) is not None:
        raise Frozen("This share is paused for 24 hours for the owner's safety.", "share_paused")
    return s


def log_view(db: Session, s: Share, viewer: str | None, ip: str | None) -> AccessLog:
    who = (viewer or s.lender_org)[:200]
    log = AccessLog(share_id=s.id, viewer=who, ip=(ip or "")[:64])
    db.add(log)
    db.flush()
    biz = business_of(db, s)
    owner = db.get(User, biz.owner_user_id)
    if owner is not None:
        notify(
            db, owner, "share_viewed", f"{who} ने आपका पासपोर्ट देखा।", f"{who} viewed your passport."
        )
    record(
        db,
        f"lender:{s.lender_org[:40]}",
        "share.view",
        f"business:{biz.id}",
        {"share_id": s.id, "viewer": who},
    )
    return log


def lender_view(db: Session, s: Share) -> dict[str, Any]:
    """What the lender sees: only the shared scope. Partner names and phones never appear."""
    biz = business_of(db, s)
    p = passports.latest(db, biz.id) or db.get(Passport, s.passport_id)
    assert p is not None
    a = db.get(Assessment, p.assessment_id)
    assert a is not None
    out: dict[str, Any] = {
        "lender_org": s.lender_org,
        "scope": s.scope,
        "expires_at": s.expires_at.isoformat(),
        "passport": {
            "id": p.id,
            "status": passports.live_status(p),
            "valid_until": p.valid_until.isoformat(),
            "vc": p.vc_json,
        },
        "explanation": passports.explanation_for(db, p, "en"),
        "business": {
            "name": biz.name,
            "category": biz.category,
            "city": biz.city,
            "since": biz.started_on.year if biz.started_on else None,
        },
    }
    if s.scope == "evidence":
        out["evidence"] = evidence_summary(db, biz, a)
    return out


def evidence_summary(db: Session, biz: Business, a: Assessment) -> dict[str, Any]:
    features = a.pillar_scores.get("features", {})
    ev = list(db.execute(select(EvidenceItem).where(EvidenceItem.business_id == biz.id)).scalars())
    money_ids = [
        e.id
        for e in ev
        if e.type in {"aa_fetch", "bank_statement", "upi_statement"}
        and e.status not in {"on_hold", "rejected"}
    ]
    monthly: dict[str, dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0})
    for t in db.execute(
        select(BankTransaction).where(BankTransaction.evidence_id.in_(money_ids or [""]))
    ).scalars():
        monthly[f"{t.txn_date.year}-{t.txn_date.month:02d}"][t.direction] += t.amount_paise
    confirmations = []
    for att in db.execute(
        select(Attestation).where(Attestation.subject_business_id == biz.id)
    ).scalars():
        claim = att.claim or {}
        label = (
            (
                f"verified {claim.get('relationship', 'partner')}, trading "
                f"{claim.get('years_trading', '?')} years"
            )
            if att.evidence_type == "penny_drop"
            else "confirmed in person by a field officer"
        )
        confirmations.append(
            {
                "label": label,
                "status": att.status,
                "money_match": att.money_match,
                "expires_at": att.expires_at.isoformat() if att.expires_at else None,
            }
        )
    reqs = list(
        db.execute(select(PresenceRequest).where(PresenceRequest.business_id == biz.id)).scalars()
    )
    return {
        "money_source": features.get("money", {}).get("source"),
        "monthly_totals_paise": dict(sorted(monthly.items())),
        "records": features.get("records", {}),
        "avg_monthly_inflow_paise": features.get("money", {}).get("avg_monthly_inflow_paise"),
        "confirmations": confirmations,
        "presence": {
            "done": sum(r.status == "done" for r in reqs),
            "failed": sum(r.status == "failed" for r in reqs),
            "missed": sum(r.status == "missed" for r in reqs),
        },
        "evidence_items": [
            {
                "type": e.type,
                "source": e.source,
                "status": e.status,
                "file_hash": e.file_hash,
                "captured_at": e.captured_at.isoformat() if e.captured_at else None,
            }
            for e in ev
        ],
        "flags": a.flags,
        "rules_version": a.rules_version,
    }
