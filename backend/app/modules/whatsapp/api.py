"""Meta WhatsApp Cloud API webhook."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import PlainTextResponse

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.config import get_settings
from app.core.deps import DB
from app.core.errors import DomainError, Forbidden
from app.modules.identity.service import normalise_phone
from app.modules.whatsapp.bot import Bot, Inbound

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook", response_class=PlainTextResponse)
def verify(
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    token: Annotated[str, Query(alias="hub.verify_token")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge")] = "",
) -> str:
    expected = get_settings().whatsapp_verify_token
    if mode == "subscribe" and expected and token == expected:
        return challenge
    raise Forbidden("verification failed", "forbidden")


def parse(payload: dict[str, Any]) -> list[Inbound]:
    out = []
    wa = get_adapters().whatsapp
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                try:
                    phone = normalise_phone("+" + str(msg.get("from", "")))
                except DomainError:
                    continue
                m = Inbound(phone=phone, message_id=msg.get("id"))
                kind = msg.get("type")
                if kind == "text":
                    m.text = msg.get("text", {}).get("body", "")
                elif kind == "interactive":
                    reply = msg.get("interactive", {}).get("button_reply", {})
                    m.button = reply.get("title") or reply.get("id")
                elif kind == "button":
                    m.button = msg.get("button", {}).get("text")
                elif kind in {"image", "audio"}:
                    try:
                        data, mime = wa.fetch_media(msg[kind]["id"])
                    except (AdapterError, KeyError):
                        continue
                    if kind == "image":
                        m.image = (data, mime.split(";")[0])
                    else:
                        m.audio = data
                out.append(m)
    return out


@router.post("/webhook")
async def receive(
    request: Request, db: DB, x_hub_signature_256: Annotated[str, Header()] = ""
) -> dict[str, int]:
    body = await request.body()
    wa = get_adapters().whatsapp
    if not wa.sandbox and not wa.verify_signature(body, x_hub_signature_256):
        raise Forbidden("bad signature", "bad_signature")
    bot = Bot(db)
    messages = parse(json.loads(body or b"{}"))
    for m in messages:
        with db.begin_nested():
            bot.handle(m)
    db.commit()
    return {"handled": len(messages)}
