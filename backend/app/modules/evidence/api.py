import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, UploadFile
from pydantic import BaseModel

from app.core.access import actor_for, business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import DomainError
from app.db.models import EvidenceItem
from app.modules.evidence import service

router = APIRouter(tags=["evidence"])


class EvidenceOut(BaseModel):
    id: str
    type: str
    source: str
    status: str
    captured_at: datetime | None
    created_at: datetime
    has_geo: bool
    meta: dict[str, Any]


def out(e: EvidenceItem) -> EvidenceOut:
    return EvidenceOut(
        id=e.id,
        type=e.type,
        source=e.source,
        status=e.status,
        captured_at=e.captured_at,
        created_at=e.created_at,
        has_geo=e.geo is not None,
        meta=e.meta,
    )


@router.post("/businesses/{business_id}/captures", response_model=EvidenceOut)
async def upload_capture(
    business_id: str,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()],
    captured_at: Annotated[datetime, Form()],
    device_id: Annotated[str, Form()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    lat: Annotated[float | None, Form()] = None,
    lng: Annotated[float | None, Form()] = None,
    accuracy_m: Annotated[float | None, Form()] = None,
    client_quality: Annotated[str, Form()] = "{}",
) -> EvidenceOut:
    biz = business_for(db, user, business_id, action="capture")
    if captured_at.tzinfo is None:
        raise DomainError("captured_at needs a time zone", "bad_time")
    try:
        quality = json.loads(client_quality)
    except json.JSONDecodeError:
        quality = {}
    geo = (
        {"lat": lat, "lng": lng, "accuracy_m": accuracy_m}
        if lat is not None and lng is not None
        else None
    )
    data = await file.read()
    ev, _ = service.ingest_capture(
        db,
        user,
        biz,
        service.CaptureIn(
            kind=kind,
            mime=file.content_type or "",
            data=data,
            captured_at=captured_at,
            idempotency_key=idempotency_key,
            device_id=device_id,
            geo=geo,
            client_quality=quality if isinstance(quality, dict) else {},
        ),
        actor_for(user, biz),
    )
    db.commit()
    return out(ev)


@router.get("/businesses/{business_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(
    business_id: str, db: DB, user: CurrentUser, kind: str | None = None
) -> list[EvidenceOut]:
    business_for(db, user, business_id)
    return [out(e) for e in service.list_for(db, business_id, kind)]
