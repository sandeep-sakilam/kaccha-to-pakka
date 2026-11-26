"""Evidence intake for live-camera captures (ledger pages, shop front, presence photos).

Uploads are idempotent: the phone's offline queue retries with the same key and never creates a
duplicate. The same photo sent twice under different keys is flagged, not counted twice.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapters
from app.core.errors import DomainError
from app.db.base import utcnow
from app.db.models import Business, EvidenceItem, User
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.evidence.quality import check_image

CAPTURE_KINDS = {"ledger_page", "shop_front", "presence", "bill"}
MAX_BYTES = 6 * 1024 * 1024
MAX_QUEUE_AGE = timedelta(days=7)  # offline captures older than this are refused
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True)
class CaptureIn:
    kind: str
    mime: str
    data: bytes
    captured_at: datetime
    idempotency_key: str
    device_id: str
    geo: dict[str, Any] | None
    client_quality: dict[str, Any]
    source: str = "web_camera"


def storage_key(business_id: str, evidence_id: str, ext: str) -> str:
    return f"businesses/{business_id}/evidence/{evidence_id}.{ext}"


def ingest_capture(
    db: Session, user: User, biz: Business, c: CaptureIn, actor: str | None = None
) -> tuple[EvidenceItem, bool]:
    """Returns (evidence, created). A repeated idempotency key returns the original item."""
    existing = db.execute(
        select(EvidenceItem).where(EvidenceItem.idempotency_key == c.idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.business_id != biz.id:
            raise DomainError("Upload key already used", "idempotency_conflict", 409)
        return existing, False
    consent.require(db, biz.owner_user_id, "build_passport", biz.id)
    from app.modules.abuse.limits import hit

    hit("capture_device", c.device_id)
    if user.id != biz.owner_user_id:
        hit("sahayak_actions", user.id)
    if c.kind not in CAPTURE_KINDS:
        raise DomainError("Unknown capture kind", "bad_kind")
    if c.mime not in ALLOWED_MIME:
        raise DomainError("Only camera photos are accepted", "bad_mime")
    if len(c.data) > MAX_BYTES:
        raise DomainError("Photo is too large", "too_large", 413)
    now = utcnow()
    if c.captured_at > now + timedelta(minutes=10) or now - c.captured_at > MAX_QUEUE_AGE:
        raise DomainError("Photo time is not valid. Please take a new photo.", "bad_time")
    check = check_image(c.data, c.captured_at)
    if not check.ok:
        raise DomainError(f"Please retake the photo ({check.reason}).", f"quality:{check.reason}")

    file_hash = hashlib.sha256(c.data).hexdigest()
    duplicate = db.execute(
        select(EvidenceItem.id).where(
            EvidenceItem.business_id == biz.id, EvidenceItem.file_hash == file_hash
        )
    ).first()
    ev = EvidenceItem(
        business_id=biz.id,
        type=c.kind,
        source=c.source,
        file_hash=file_hash,
        captured_at=c.captured_at,
        geo=c.geo,
        device_attestation={"device_id": c.device_id, "integrity": "web_unattested"},
        status="duplicate" if duplicate else "received",
        meta={
            "mime": c.mime,
            "bytes": len(c.data),
            "width": check.width,
            "height": check.height,
            "sharpness": check.sharpness,
            "brightness": check.brightness,
            "client_quality": c.client_quality,
            "duplicate_of": duplicate[0] if duplicate else None,
        },
        idempotency_key=c.idempotency_key,
        actor_user_id=user.id,
        sahayak_user_id=user.id if user.id != biz.owner_user_id else None,
    )
    db.add(ev)
    db.flush()
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[c.mime]
    ev.storage_key = get_adapters().storage.put(storage_key(biz.id, ev.id, ext), c.data, c.mime)
    if c.kind in {"ledger_page", "bill"} and ev.status == "received":
        from app.jobs import enqueue

        enqueue(db, "extract_ledger", ev.id)
    if c.kind in {"shop_front", "presence"}:
        from app.modules.presence.service import on_capture

        on_capture(db, biz, ev)
    record(
        db,
        actor or f"user:{user.id}",
        "evidence.capture",
        f"business:{biz.id}",
        {
            "evidence_id": ev.id,
            "kind": c.kind,
            "hash": file_hash[:16],
            "duplicate": bool(duplicate),
            "has_geo": c.geo is not None,
        },
    )
    return ev, True


def list_for(db: Session, business_id: str, kind: str | None = None) -> list[EvidenceItem]:
    q = select(EvidenceItem).where(EvidenceItem.business_id == business_id)
    if kind:
        q = q.where(EvidenceItem.type == kind)
    return list(db.execute(q.order_by(EvidenceItem.created_at.desc())).scalars())
