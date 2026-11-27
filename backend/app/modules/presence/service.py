"""Presence checks: the business physically exists and keeps running.

On random days (the owner cannot choose them) we ask for a live photo of the shop. A check passes
when the photo arrives within the window, carries GPS within 150 m of the shop's home location
with usable accuracy, and is not a re-sent photo. A photo of someone else's shop taken once
cannot pass weeks of random checks.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.base import utcnow
from app.db.models import Business, EvidenceItem, PresenceRequest, User
from app.jobs import job
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.notify import notify

WINDOW = timedelta(hours=24)
MAX_DISTANCE_M = 150.0
# UPI merchant addresses are coarse; only clearly different places count.
MERCHANT_NEAR_M = 500.0
MERCHANT_FAR_M = 5000.0
MAX_ACCURACY_M = 100.0
CHECKS_PER_CYCLE = 4
CYCLE_DAYS = 28


def haversine_m(a: dict[str, float], b: dict[str, float]) -> float:
    r = 6_371_000.0
    la1, la2 = math.radians(a["lat"]), math.radians(b["lat"])
    dla, dlo = la2 - la1, math.radians(b["lng"] - a["lng"])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def schedule_cycle(
    db: Session, biz: Business, start: datetime | None = None, rng: random.Random | None = None
) -> list[PresenceRequest]:
    """Pick CHECKS_PER_CYCLE random days (and hours 9:00-19:00 IST) in the next 28 days."""
    start = start or utcnow()
    rng = rng or random.Random()  # noqa: S311  (unpredictable to the owner, not cryptographic)
    days = sorted(rng.sample(range(1, CYCLE_DAYS), CHECKS_PER_CYCLE))
    out = []
    for d in days:
        at = (start + timedelta(days=d)).replace(hour=3, minute=30, second=0, microsecond=0)
        at += timedelta(minutes=rng.randrange(0, 600))  # 09:00-19:00 IST
        req = PresenceRequest(business_id=biz.id, requested_at=at, due_by=at + WINDOW)
        db.add(req)
        out.append(req)
    db.flush()
    record(db, "system", "presence.scheduled", f"business:{biz.id}", {"count": len(out)})
    return out


def open_request(
    db: Session, business_id: str, at: datetime | None = None
) -> PresenceRequest | None:
    at = at or utcnow()
    return (
        db.execute(
            select(PresenceRequest)
            .where(
                PresenceRequest.business_id == business_id,
                PresenceRequest.status == "sent",
                PresenceRequest.requested_at <= at,
                PresenceRequest.due_by >= at,
            )
            .order_by(PresenceRequest.requested_at)
        )
        .scalars()
        .first()
    )


def send_due(db: Session, at: datetime | None = None) -> int:
    """Send requests whose time has come; mark missed ones. Run every few minutes."""
    at = at or utcnow()
    n = 0
    for req in db.execute(
        select(PresenceRequest).where(PresenceRequest.status.in_(["scheduled", "sent"]))
    ).scalars():
        if req.status == "sent" and req.due_by < at:
            req.status = "missed"
            continue
        if req.status == "scheduled" and req.requested_at <= at:
            if req.due_by < at:
                req.status = "missed"
                continue
            req.status = "sent"
            biz = db.get(Business, req.business_id)
            owner = db.get(User, biz.owner_user_id) if biz else None
            if owner is not None:
                notify(
                    db,
                    owner,
                    "presence_request",
                    "आज अपनी दुकान की एक फ़ोटो लें (24 घंटे के अंदर)। ऐप में 'आज की फ़ोटो' दबाएँ।",
                    "Please take a photo of your shop today (within 24 hours). Tap "
                    "'Shop photo for today' in the app.",
                )
            n += 1
    db.flush()
    return n


@dataclass(frozen=True)
class PresenceResult:
    passed: bool
    reasons: list[str]
    distance_m: float | None


def evaluate(biz: Business, ev: EvidenceItem) -> PresenceResult:
    reasons = []
    geo = ev.geo or {}
    distance = None
    if not geo.get("lat"):
        reasons.append("no_gps")
    elif (geo.get("accuracy_m") or 999) > MAX_ACCURACY_M:
        reasons.append("gps_inaccurate")
    if biz.geo_home and geo.get("lat"):
        distance = round(haversine_m(biz.geo_home, geo), 1)
        if distance > MAX_DISTANCE_M:
            reasons.append("far_from_shop")
    if ev.status == "duplicate":
        reasons.append("same_photo_again")
    if biz.merchant_geo and geo.get("lat") and haversine_m(biz.merchant_geo, geo) > MERCHANT_NEAR_M:
        reasons.append("far_from_merchant_location")
    return PresenceResult(not reasons, reasons, distance)


def on_capture(db: Session, biz: Business, ev: EvidenceItem) -> None:
    """Called for every shop_front / presence capture."""
    if (
        ev.type == "shop_front"
        and not biz.geo_home
        and ev.geo
        and ev.geo.get("lat")
        and (ev.geo.get("accuracy_m") or 999) <= MAX_ACCURACY_M
    ):
        biz.geo_home = {"lat": ev.geo["lat"], "lng": ev.geo["lng"], "source": ev.id}
        record(db, "system", "presence.home_set", f"business:{biz.id}", {"evidence_id": ev.id})
        return
    if ev.type != "presence":
        return
    req = open_request(db, biz.id, ev.captured_at or utcnow())
    result = evaluate(biz, ev)
    ev.meta = {
        **ev.meta,
        "presence": {
            "passed": result.passed,
            "reasons": result.reasons,
            "distance_m": result.distance_m,
            "request_id": req.id if req else None,
        },
    }
    if req is not None:
        req.status = "done" if result.passed else "failed"
        req.evidence_id = ev.id
        req.result = {"reasons": result.reasons, "distance_m": result.distance_m}
    record(
        db,
        "system",
        "presence.checked",
        f"business:{biz.id}",
        {
            "evidence_id": ev.id,
            "passed": result.passed,
            "reasons": result.reasons,
            "on_request": req is not None,
        },
    )


def start_checks(db: Session, user: User, biz: Business) -> list[PresenceRequest]:
    consent.require(db, biz.owner_user_id, "presence_location", biz.id)
    pending = db.execute(
        select(PresenceRequest.id).where(
            PresenceRequest.business_id == biz.id, PresenceRequest.status.in_(["scheduled", "sent"])
        )
    ).first()
    if pending:
        raise DomainError("Presence checks are already scheduled", "already_scheduled", 409)
    return schedule_cycle(db, biz)


@job("presence_send_due")
def send_due_job(db: Session) -> None:
    send_due(db)
