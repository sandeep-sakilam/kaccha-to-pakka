"""Tamper-evident audit log: append-only and hash-chained.

hash(n) = sha256(prev_hash || canonical JSON of the record). Editing or deleting any row breaks
every later hash, and the database refuses UPDATE and DELETE on the table outright.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import AuditLog

GENESIS = "0" * 64
_LOCK_KEY = 7_311_001  # advisory lock id serialising appends


def _canonical(
    prev_hash: str, actor: str, action: str, obj: str, details: dict[str, Any], at: datetime
) -> bytes:
    payload = {
        "prev": prev_hash,
        "actor": actor,
        "action": action,
        "object": obj,
        "details": details,
        "at": at.isoformat(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def record(
    db: Session, actor: str, action: str, obj: str, details: dict[str, Any] | None = None
) -> AuditLog:
    """Append one entry. Runs inside the caller's transaction so the log and the change it
    describes commit together."""
    details = details or {}
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    last = db.execute(select(AuditLog.hash).order_by(AuditLog.seq.desc()).limit(1)).scalar()
    prev = last or GENESIS
    at = utcnow()
    digest = hashlib.sha256(_canonical(prev, actor, action, obj, details, at)).hexdigest()
    entry = AuditLog(
        prev_hash=prev, hash=digest, actor=actor, action=action, object=obj, details=details, at=at
    )
    db.add(entry)
    db.flush()
    return entry


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    checked: int
    broken_at_seq: int | None = None
    reason: str | None = None


def verify_chain(db: Session) -> ChainCheck:
    prev = GENESIS
    n = 0
    for row in db.execute(select(AuditLog).order_by(AuditLog.seq)).scalars():
        n += 1
        if row.prev_hash != prev:
            return ChainCheck(False, n, row.seq, "prev_hash does not link to previous entry")
        expected = hashlib.sha256(
            _canonical(row.prev_hash, row.actor, row.action, row.object, row.details, row.at)
        ).hexdigest()
        if expected != row.hash:
            return ChainCheck(False, n, row.seq, "entry content changed")
        prev = row.hash
    return ChainCheck(True, n)


def entries_for(db: Session, obj_prefix: str, limit: int = 100) -> list[AuditLog]:
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.object.startswith(obj_prefix))
            .order_by(AuditLog.seq.desc())
            .limit(limit)
        ).scalars()
    )
