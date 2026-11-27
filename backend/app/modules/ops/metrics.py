"""Operational metrics (Prometheus text) and the fraud-flag-rate alert."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.monitoring import reporter
from app.core.config import get_settings
from app.db.base import utcnow
from app.db.models import Assessment, AuditLog, JobFailure, Notification, User
from app.jobs import job
from app.modules.audit.service import record

QUEUE_KEY = "arq:queue"
ALERT_COOLDOWN = timedelta(hours=6)


def queue_depth() -> int | None:
    from redis import Redis

    try:
        n: Any = Redis.from_url(get_settings().redis_url, socket_timeout=1).zcard(QUEUE_KEY)
        return int(n)
    except Exception:
        return None


@dataclass(frozen=True)
class HoldRate:
    window: int
    held: int

    @property
    def rate(self) -> float:
        return self.held / self.window if self.window else 0.0


def hold_rate(db: Session, since: timedelta, until: timedelta = timedelta(0)) -> HoldRate:
    now = utcnow()
    q = select(Assessment.status).where(
        Assessment.created_at >= now - since, Assessment.created_at < now - until
    )
    statuses = [s for (s,) in db.execute(q).all()]
    return HoldRate(len(statuses), sum(1 for s in statuses if s == "on_hold"))


def render(db: Session) -> str:
    depth = queue_depth()
    failures = db.execute(
        select(func.count()).select_from(JobFailure).where(JobFailure.resolved_at.is_(None))
    ).scalar_one()
    day = hold_rate(db, timedelta(hours=24))
    lines = [
        "# HELP ktp_queue_depth Jobs waiting in the background queue.",
        "# TYPE ktp_queue_depth gauge",
        f"ktp_queue_depth {depth if depth is not None else 'NaN'}",
        "# HELP ktp_job_failures_open Dead-letter jobs not yet resolved.",
        "# TYPE ktp_job_failures_open gauge",
        f"ktp_job_failures_open {failures}",
        "# HELP ktp_assessments_24h Assessments in the last 24 hours.",
        "# TYPE ktp_assessments_24h gauge",
        f"ktp_assessments_24h {day.window}",
        "# HELP ktp_fraud_flag_rate_24h Share of last-24h assessments put on hold.",
        "# TYPE ktp_fraud_flag_rate_24h gauge",
        f"ktp_fraud_flag_rate_24h {day.rate:.4f}",
    ]
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class AlertResult:
    fired: bool
    reason: str
    current: float
    baseline: float


def check_fraud_rate(db: Session) -> AlertResult:
    """Alert when the last-24h hold rate jumps above the previous 7 days: at least twice the
    baseline and 10 points higher, with enough assessments to mean something."""
    cur = hold_rate(db, timedelta(hours=24))
    base = hold_rate(db, timedelta(days=8), timedelta(hours=24))
    min_n = get_settings().fraud_alert_min_assessments
    if cur.window < min_n:
        return AlertResult(False, "too few assessments", cur.rate, base.rate)
    if not (cur.rate >= 2 * base.rate and cur.rate >= base.rate + 0.10):
        return AlertResult(False, "within normal range", cur.rate, base.rate)
    recent = db.execute(
        select(AuditLog.seq).where(
            AuditLog.action == "ops.fraud_rate_alert", AuditLog.at >= utcnow() - ALERT_COOLDOWN
        )
    ).first()
    if recent:
        return AlertResult(False, "already alerted in the last 6 hours", cur.rate, base.rate)
    msg = (
        f"Fraud-flag rate jumped: {cur.rate:.0%} of {cur.window} assessments on hold in 24h "
        f"vs {base.rate:.0%} over the previous 7 days"
    )
    reporter().capture_message(
        msg, "error", {"current": cur.rate, "baseline": base.rate, "assessments_24h": cur.window}
    )
    for u in db.execute(select(User).where(User.status == "active")).scalars():
        if "reviewer" in (u.roles or []):
            db.add(Notification(user_id=u.id, channel="app", text=msg, kind="fraud_rate_alert"))
    record(
        db,
        "system:monitor",
        "ops.fraud_rate_alert",
        "ops",
        {"current": round(cur.rate, 4), "baseline": round(base.rate, 4), "n": cur.window},
    )
    return AlertResult(True, msg, cur.rate, base.rate)


@job("fraud_rate_check")
def fraud_rate_job(db: Session) -> None:
    check_fraud_rate(db)
