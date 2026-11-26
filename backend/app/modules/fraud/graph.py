"""Fraud graph over the trading network (NetworkX). Deterministic rules, no AI.

- Payment cycles: money that goes A → B → C → A between known businesses within days, in similar
  amounts, is round-tripping to inflate turnover. Every business in the cycle is held.
- Collusion rings: a cluster of businesses that confirm each other, are all new, and have almost
  no trade outside the cluster. Every member is held.
- Confirmer standing: a confirmation weighs more when the confirmer is older, trades with more
  independent partners, and has never been shown to confirm falsely.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    Attestation,
    BankTransaction,
    Business,
    Counterparty,
    EvidenceItem,
    GraphFlag,
)
from app.modules.audit.service import record

CYCLE_WINDOW_DAYS = 10
CYCLE_TOLERANCE = 0.05
MAX_CYCLE_LEN = 4
NEW_BUSINESS_DAYS = 365
RING_MIN_SIZE = 3
RING_MAX_OUTSIDE_PARTNERS = 2


@dataclass(frozen=True)
class Payment:
    payer: str
    payee: str
    amount_paise: int
    day: date


def business_payments(db: Session) -> list[Payment]:
    """Payments between two businesses we know (the counterparty node is linked to a business)."""
    cp_biz = {
        c.vpa_or_account: c.business_id
        for c in db.execute(
            select(Counterparty).where(Counterparty.business_id.is_not(None))
        ).scalars()
    }
    out = []
    rows = db.execute(
        select(BankTransaction, EvidenceItem.business_id)
        .join(EvidenceItem)
        .where(
            EvidenceItem.status.notin_(["on_hold", "rejected"]),
            BankTransaction.counterparty_vpa.in_(list(cp_biz) or [""]),
        )
    ).all()
    for t, owner_biz in rows:
        other = cp_biz.get(t.counterparty_vpa or "")
        if not other or other == owner_biz:
            continue
        payer, payee = (owner_biz, other) if t.direction == "out" else (other, owner_biz)
        out.append(Payment(payer, payee, t.amount_paise, t.txn_date))
    return out


def _chains(by_edge: dict[tuple[str, str], list[Payment]], cycle: list[str]) -> bool:
    """True when one payment per hop chains forward in time with a similar amount."""
    edges = list(zip(cycle, cycle[1:] + cycle[:1], strict=True))
    for first in by_edge[edges[0]]:
        amount, day, ok = first.amount_paise, first.day, True
        for e in edges[1:]:
            nxt = [
                p
                for p in by_edge[e]
                if 0 <= (p.day - day).days <= CYCLE_WINDOW_DAYS
                and abs(p.amount_paise - amount) <= amount * CYCLE_TOLERANCE
            ]
            if not nxt:
                ok = False
                break
            day = min(p.day for p in nxt)
        if ok:
            return True
    return False


def payment_cycles(payments: list[Payment]) -> list[list[str]]:
    g: nx.DiGraph = nx.DiGraph()
    by_edge: dict[tuple[str, str], list[Payment]] = defaultdict(list)
    for p in payments:
        by_edge[(p.payer, p.payee)].append(p)
        g.add_edge(p.payer, p.payee)
    found = []
    for cycle in nx.simple_cycles(g, length_bound=MAX_CYCLE_LEN):
        if len(cycle) < 2:
            continue
        if any(_chains(by_edge, cycle[i:] + cycle[:i]) for i in range(len(cycle))):
            found.append(sorted(cycle))
    unique = {tuple(c) for c in found}
    return [list(c) for c in sorted(unique)]


def partner_counts(db: Session) -> dict[str, set[str]]:
    """Distinct trading partners (UPI IDs) per business, from its own money data."""
    out: dict[str, set[str]] = defaultdict(set)
    rows = db.execute(
        select(EvidenceItem.business_id, BankTransaction.counterparty_vpa)
        .join(BankTransaction, BankTransaction.evidence_id == EvidenceItem.id)
        .where(BankTransaction.counterparty_vpa.is_not(None))
    ).all()
    for biz_id, vpa in rows:
        if vpa:
            out[biz_id].add(vpa)
    return out


def collusion_rings(db: Session, today: date | None = None) -> list[list[str]]:
    today = today or date.today()
    atts = list(
        db.execute(
            select(Attestation).where(
                Attestation.confirmer_business_id.is_not(None),
                Attestation.status.in_(["confirmed", "discrepancy"]),
            )
        ).scalars()
    )
    g: nx.Graph = nx.Graph()
    for a in atts:
        g.add_edge(a.confirmer_business_id, a.subject_business_id)
    partners = partner_counts(db)
    cp_owner = {c.vpa_or_account: c.business_id for c in db.execute(select(Counterparty)).scalars()}
    rings = []
    for comp in nx.connected_components(g):
        if len(comp) < RING_MIN_SIZE:
            continue
        members = [db.get(Business, b) for b in comp]
        if any(m is None for m in members):
            continue
        new = all(
            (today - m.created_at.date()).days < NEW_BUSINESS_DAYS for m in members if m is not None
        )
        outside = set()
        for b in comp:
            for vpa in partners.get(b, set()):
                if cp_owner.get(vpa) not in comp:
                    outside.add(vpa)
        if new and len(outside) <= RING_MAX_OUTSIDE_PARTNERS * len(comp):
            rings.append(sorted(comp))
    return rings


def confirmer_standing(
    db: Session, confirmer_business_id: str | None, today: date | None = None
) -> float:
    """0.3 .. 1.2. Grows with the confirmer's age and number of independent partners; drops when
    any of its confirmations was later shown to be false."""
    if not confirmer_business_id:
        return 1.0  # in-person confirmations carry their own fixed weight
    today = today or date.today()
    b = db.get(Business, confirmer_business_id)
    if b is None:
        return 0.5
    disproved = db.execute(
        select(Attestation.id).where(
            Attestation.confirmer_business_id == b.id, Attestation.status == "disproved"
        )
    ).first()
    years = min((today - b.created_at.date()).days / 365.25, 3.0)
    if b.started_on and b.category != "trading_partner":
        years = min(max(years, (today - b.started_on).days / 365.25), 3.0)
    partners = len(partner_counts(db).get(b.id, set()))
    # Confirmers who are other businesses' trading partners also count as having partners.
    confirms = db.execute(
        select(Attestation.subject_business_id).where(Attestation.confirmer_business_id == b.id)
    ).all()
    partners = max(partners, len({c[0] for c in confirms}))
    standing = 0.6 + 0.1 * years + 0.05 * min(partners, 6)
    if disproved:
        standing *= 0.3
    return round(max(0.3, min(1.2, standing)), 2)


def scan(db: Session, actor: str = "system:fraud_graph") -> list[GraphFlag]:
    """Recompute graph findings; new findings become active flags, gone ones are cleared."""
    findings: dict[tuple[str, str], dict[str, Any]] = {}
    for cycle in payment_cycles(business_payments(db)):
        for b in cycle:
            findings[(b, "payment_cycle")] = {"members": cycle}
    for ring in collusion_rings(db):
        for b in ring:
            findings[(b, "collusion_ring")] = {"members": ring}
    active = {
        (f.business_id, f.code): f
        for f in db.execute(select(GraphFlag).where(GraphFlag.cleared_at.is_(None))).scalars()
    }
    created = []
    for key, detail in findings.items():
        if key not in active:
            f = GraphFlag(business_id=key[0], code=key[1], detail=detail)
            db.add(f)
            created.append(f)
            record(db, actor, f"fraud.{key[1]}", f"business:{key[0]}", detail)
    for key, f in active.items():
        if key not in findings and f.detail.get("source") != "reviewer":
            f.cleared_at = utcnow()
    db.flush()
    return created


def active_flags(db: Session, business_id: str) -> list[GraphFlag]:
    return list(
        db.execute(
            select(GraphFlag).where(
                GraphFlag.business_id == business_id, GraphFlag.cleared_at.is_(None)
            )
        ).scalars()
    )
