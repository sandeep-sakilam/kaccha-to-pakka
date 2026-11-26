from typing import Annotated

from fastapi import APIRouter, File, Header, UploadFile
from pydantic import BaseModel

from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.modules.imports import service

router = APIRouter(tags=["imports"])


class ImportOut(BaseModel):
    evidence_id: str
    source: str
    rows: int
    created: bool


@router.post("/businesses/{business_id}/imports/csv", response_model=ImportOut)
async def import_csv(
    business_id: str,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> ImportOut:
    biz = business_for(db, user, business_id)
    ev, created = service.import_csv(
        db, user, biz, await file.read(), file.filename or "", idempotency_key
    )
    db.commit()
    return ImportOut(
        evidence_id=ev.id, source=ev.source, rows=int(ev.meta.get("rows", 0)), created=created
    )
