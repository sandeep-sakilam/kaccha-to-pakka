from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app.core import signing
from app.core.access import business_for
from app.core.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.db.models import Passport
from app.modules.passport import credential, pdf, service

router = APIRouter(tags=["passport"])


class PassportOut(BaseModel):
    id: str
    status: str
    valid_until: datetime
    vc: dict[str, Any]
    qr_token: str
    verify_url: str
    qr_png_b64: str


def _out(p: Passport) -> PassportOut:
    token = credential.qr_token(p.vc_json)
    url = credential.verify_url(p.id, token)
    return PassportOut(
        id=p.id,
        status=service.live_status(p),
        valid_until=p.valid_until,
        vc=p.vc_json,
        qr_token=token,
        verify_url=url,
        qr_png_b64=pdf.qr_png_b64(url),
    )


@router.post("/businesses/{business_id}/passport", response_model=PassportOut)
def issue(business_id: str, db: DB, user: CurrentUser) -> PassportOut:
    biz = business_for(db, user, business_id, action="passport")
    p = service.issue(db, biz, f"user:{user.id}")
    db.commit()
    return _out(p)


@router.get("/businesses/{business_id}/passport", response_model=PassportOut)
def current(business_id: str, db: DB, user: CurrentUser) -> PassportOut:
    business_for(db, user, business_id)
    p = service.latest(db, business_id)
    if p is None:
        raise NotFound("No passport yet", "no_passport")
    return _out(p)


class HistoryItem(BaseModel):
    issued_at: datetime
    band: str
    confidence: str
    status: str
    rules_version: str


@router.get("/businesses/{business_id}/passport/history", response_model=list[HistoryItem])
def passport_history(business_id: str, db: DB, user: CurrentUser) -> list[HistoryItem]:
    business_for(db, user, business_id)
    return [HistoryItem(**h) for h in service.history(db, business_id)]


@router.post("/businesses/{business_id}/passport/revoke", response_model=PassportOut)
def revoke(business_id: str, db: DB, user: CurrentUser) -> PassportOut:
    """The owner withdraws the current passport. Lenders and QR checks then see "revoked"."""
    business_for(db, user, business_id, allow_sahayak=False)
    p = service.latest(db, business_id)
    if p is None:
        raise NotFound("No passport yet", "no_passport")
    if p.status not in {"revoked", "superseded"}:
        service.revoke(db, p, f"user:{user.id}")
    db.commit()
    return _out(p)


@router.get("/businesses/{business_id}/passport.pdf")
def passport_pdf(business_id: str, db: DB, user: CurrentUser, language: str = "hi") -> Response:
    business_for(db, user, business_id)
    p = service.latest(db, business_id)
    if p is None:
        raise NotFound("No passport yet", "no_passport")
    lang = "hi" if language == "hi" else "en"
    url = credential.verify_url(p.id, credential.qr_token(p.vc_json))
    data = pdf.render_pdf(p.vc_json, service.explanation_for(db, p, lang), url, lang)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="passport-{lang}.pdf"'},
    )


@router.get("/passports/{passport_id}/status")
def status(passport_id: str, db: DB) -> dict[str, Any]:
    """Public live status for lenders and offline verifiers."""
    p = service.get(db, passport_id)
    return {"id": p.id, "status": service.live_status(p), "valid_until": p.valid_until.isoformat()}


@router.get("/.well-known/ktp-keys.json")
def keys() -> dict[str, Any]:
    return {
        "issuer": credential.issuer_did(),
        "keys": [
            {"kid": signing.key_id(), "alg": "Ed25519", "public_key": signing.public_key_b64()}
        ],
    }


class VerifyIn(BaseModel):
    vc: dict[str, Any] | None = None
    qr_token: str | None = None


@router.post("/passports/verify")
def verify(body: VerifyIn, db: DB) -> dict[str, Any]:
    """Check a signature (full VC or QR token) and fetch live status."""
    if body.vc is not None:
        ok = credential.verify_vc(body.vc)
        pid = str(body.vc.get("id", "")).removeprefix("urn:uuid:")
        summary: dict[str, Any] = body.vc.get("credentialSubject", {})
    elif body.qr_token:
        ok, payload = credential.read_qr_token(body.qr_token)
        pid, summary = str(payload.get("id", "")), payload
    else:
        return {"signature_valid": False, "status": "unknown"}
    p = db.get(Passport, pid) if ok else None
    return {
        "signature_valid": ok,
        "status": service.live_status(p) if p else "unknown",
        "summary": summary if ok else {},
    }
