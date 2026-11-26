"""Reviewer queue and Sahayak anomaly monitoring.

Reviewers see case data only, and every read and decision is written to the audit log. A
decision changes the evidence it is about (e.g. a held statement counts again, or is rejected),
and the next assessment reflects it; old assessments are never rewritten.
"""

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, Forbidden, NotFound
from app.db.base import utcnow
from app.db.models import (
    Attestation,
    Business,
    CounterpartyInvite,
    Dispute,
    EvidenceItem,
    GraphFlag,
    LedgerEntry,
    User,
)
from app.modules.audit.service import record
from app.modules.presence.service import haversine_m

OWNER_TARGETS = {"ledger_entry", "attestation", "assessment", "evidence"}


def require_reviewer(user: User) -> None:
    if "reviewer" not in (user.roles or []):
        raise Forbidden("Reviewers only", "reviewer_only")


def raise_dispute(
    db: Session, actor: str, business_id: str, target_type: str, target_id: str, reason: str
) -> Dispute:
    if target_type not in OWNER_TARGETS:
        raise DomainError(
            "You can contest a ledger line, a confirmation or the result", "bad_target"
        )
    d = Dispute(
        target_type=target_type,
        target_id=target_id,
        business_id=business_id,
        raised_by=actor,
        reason=reason[:1000],
    )
    db.add(d)
    db.flush()
    record(
        db,
        actor,
        "dispute.raised",
        f"business:{business_id}",
        {"dispute_id": d.id, "target": f"{target_type}:{target_id}"},
    )
    return d


def queue(db: Session, reviewer: User, status: str = "open") -> list[Dispute]:
    require_reviewer(reviewer)
    record(db, f"reviewer:{reviewer.id}", "review.queue_viewed", "disputes", {"status": status})
    return list(
        db.execute(
            select(Dispute).where(Dispute.status == status).order_by(Dispute.created_at)
        ).scalars()
    )


def case(db: Session, reviewer: User, dispute_id: str) -> dict[str, Any]:
    require_reviewer(reviewer)
    d = db.get(Dispute, dispute_id)
    if d is None:
        raise NotFound("Not found", "dispute_not_found")
    record(
        db,
        f"reviewer:{reviewer.id}",
        "review.case_viewed",
        f"dispute:{d.id}",
        {"business_id": d.business_id},
    )
    biz = db.get(Business, d.business_id) if d.business_id else None
    target: dict[str, Any] = {}
    if d.target_type == "evidence":
        ev = db.get(EvidenceItem, d.target_id)
        if ev:
            target = {
                "type": ev.type,
                "status": ev.status,
                "source": ev.source,
                "tamper": ev.meta.get("tamper"),
                "checksum": ev.meta.get("checksum"),
                "file_hash": ev.file_hash,
            }
    elif d.target_type == "invite":
        inv = db.get(CounterpartyInvite, d.target_id)
        if inv:
            target = {"status": inv.status, "flags": inv.flags}
    elif d.target_type == "attestation":
        att = db.get(Attestation, d.target_id)
        if att:
            target = {"status": att.status, "claim": att.claim, "money_match": att.money_match}
    elif d.target_type == "ledger_entry":
        e = db.get(LedgerEntry, d.target_id)
        if e:
            target = {
                "amount_paise": e.amount_paise,
                "direction": e.direction,
                "entry_date": str(e.entry_date),
                "status": e.status,
            }
    elif d.target_type == "graph_flag":
        gf = db.get(GraphFlag, d.target_id)
        if gf:
            target = {"code": gf.code, "detail": gf.detail}
    elif d.target_type == "sahayak":
        target = {"sahayak_user_id": d.target_id}
    return {
        "id": d.id,
        "target_type": d.target_type,
        "target_id": d.target_id,
        "reason": d.reason,
        "status": d.status,
        "raised_by": d.raised_by,
        "business": {"id": biz.id, "name": biz.name, "category": biz.category} if biz else None,
        "target": target,
    }


def resolve(db: Session, reviewer: User, dispute_id: str, decision: str, note: str) -> Dispute:
    """decision: 'cleared' (the evidence is fine) or 'upheld' (the problem is real)."""
    require_reviewer(reviewer)
    if decision not in {"cleared", "upheld"}:
        raise DomainError("Decide cleared or upheld", "bad_decision")
    d = db.get(Dispute, dispute_id)
    if d is None or d.status != "open":
        raise NotFound("Open dispute not found", "dispute_not_found")
    if d.target_type == "evidence":
        ev = db.get(EvidenceItem, d.target_id)
        if ev is not None and ev.status in {"on_hold", "checksum_failed"}:
            if decision == "cleared":
                ev.status = "parsed" if ev.status == "on_hold" else "extracted"
                if ev.type in {"ledger_page", "bill"}:
                    for e in db.execute(
                        select(LedgerEntry).where(
                            LedgerEntry.evidence_id == ev.id, LedgerEntry.status == "on_review"
                        )
                    ).scalars():
                        e.status = "extracted"
            else:
                ev.status = "rejected"
    elif d.target_type == "attestation" and decision == "upheld":
        att = db.get(Attestation, d.target_id)
        if att is not None:
            att.status = "disproved"  # lowers the confirmer's standing everywhere
    elif d.target_type == "ledger_entry" and decision == "upheld":
        line = db.get(LedgerEntry, d.target_id)
        if line is not None:
            line.status = "rejected_by_owner"
    elif d.target_type == "graph_flag" and decision == "cleared":
        gf = db.get(GraphFlag, d.target_id)
        if gf is not None:
            gf.cleared_at = utcnow()
            gf.detail = {**gf.detail, "source": "reviewer"}
    elif d.target_type == "sahayak" and decision == "upheld":
        helper = db.get(User, d.target_id)
        if helper is not None:
            helper.status = "suspended"
    d.status, d.resolution, d.reviewer_id, d.resolved_at = (
        "resolved",
        decision,
        reviewer.id,
        utcnow(),
    )
    record(
        db,
        f"reviewer:{reviewer.id}",
        "review.resolved",
        f"dispute:{d.id}",
        {
            "decision": decision,
            "note": note[:500],
            "target": f"{d.target_type}:{d.target_id}",
            "business_id": d.business_id,
        },
    )
    return d


# ---------------------------------------------------------------- Sahayak monitoring

VOLUME_LIMIT_30D = 150
FAILURE_RATE_LIMIT = 0.3
SHARED_DEVICE_BUSINESSES = 5
GPS_CLUSTER_METERS = 25.0
GPS_CLUSTER_BUSINESSES = 3
BAD_STATUSES = {"duplicate", "checksum_failed", "on_hold", "rejected", "extraction_failed"}


@dataclass
class SahayakStats:
    sahayak_user_id: str
    actions_30d: int
    businesses: int
    failure_rate: float
    shared_device_businesses: int
    gps_cluster_businesses: int
    reasons: list[str]


def sahayak_stats(db: Session) -> list[SahayakStats]:
    since = utcnow() - timedelta(days=30)
    rows = list(
        db.execute(
            select(EvidenceItem).where(
                EvidenceItem.sahayak_user_id.is_not(None), EvidenceItem.created_at >= since
            )
        ).scalars()
    )
    by_s: dict[str, list[EvidenceItem]] = defaultdict(list)
    for e in rows:
        by_s[str(e.sahayak_user_id)].append(e)
    out = []
    for sid, items in by_s.items():
        businesses = {e.business_id for e in items}
        bad = sum(1 for e in items if e.status in BAD_STATUSES)
        devices: dict[str, set[str]] = defaultdict(set)
        for e in items:
            dev = (e.device_attestation or {}).get("device_id")
            if dev:
                devices[dev].add(e.business_id)
        shared = max((len(b) for b in devices.values()), default=0)
        homes = [
            (e.business_id, e.geo)
            for e in items
            if e.type in {"shop_front", "presence"} and e.geo and e.geo.get("lat")
        ]
        cluster = 0
        for bid, g in homes:
            near = {
                b2
                for b2, g2 in homes
                if b2 != bid
                and g2 is not None
                and g is not None
                and haversine_m(g, g2) <= GPS_CLUSTER_METERS
            }
            cluster = max(cluster, len(near) + 1)
        reasons = []
        if len(items) > VOLUME_LIMIT_30D:
            reasons.append("high_volume")
        if len(items) >= 10 and bad / len(items) > FAILURE_RATE_LIMIT:
            reasons.append("high_failure_rate")
        if shared >= SHARED_DEVICE_BUSINESSES:
            reasons.append("shared_device")
        if cluster >= GPS_CLUSTER_BUSINESSES:
            reasons.append("gps_cluster")
        out.append(
            SahayakStats(
                sid,
                len(items),
                len(businesses),
                round(bad / len(items), 3),
                shared,
                cluster,
                reasons,
            )
        )
    return out


def monitor(
    db: Session, audit_share: float = 0.05, rng: random.Random | None = None
) -> list[Dispute]:
    """Open review cases for anomalous Sahayaks and a random audit sample of their work."""
    rng = rng or random.Random()  # noqa: S311  (audit sampling, not security)
    created = []
    open_targets = {
        (d.target_type, d.target_id)
        for d in db.execute(select(Dispute).where(Dispute.status == "open")).scalars()
    }
    for st in sahayak_stats(db):
        if st.reasons and ("sahayak", st.sahayak_user_id) not in open_targets:
            d = Dispute(
                target_type="sahayak",
                target_id=st.sahayak_user_id,
                raised_by="system:sahayak_monitor",
                reason="Sahayak anomaly: " + ", ".join(st.reasons),
            )
            db.add(d)
            created.append(d)
    since = utcnow() - timedelta(days=7)
    recent = list(
        db.execute(
            select(EvidenceItem).where(
                EvidenceItem.sahayak_user_id.is_not(None), EvidenceItem.created_at >= since
            )
        ).scalars()
    )
    for e in recent:
        if rng.random() < audit_share and ("evidence", e.id) not in open_targets:
            d = Dispute(
                target_type="evidence",
                target_id=e.id,
                business_id=e.business_id,
                raised_by="system:random_audit",
                reason="Random audit of Sahayak-created evidence",
            )
            db.add(d)
            created.append(d)
    db.flush()
    for d in created:
        record(
            db,
            "system:sahayak_monitor",
            "review.case_opened",
            f"dispute:{d.id}",
            {"reason": d.reason},
        )
    return created
