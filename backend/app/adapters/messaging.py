"""WhatsApp (Meta Cloud API) and SMS (OTP and fallback links)."""

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.adapters.errors import AdapterError, NotConfiguredError
from app.core.config import Settings


@dataclass(frozen=True)
class OutboundMessage:
    to: str
    text: str
    buttons: tuple[str, ...] = ()
    media_url: str | None = None
    channel: str = "whatsapp"
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


class WhatsApp(Protocol):
    name: str
    sandbox: bool

    def send(
        self, to: str, text: str, buttons: list[str] | None = None, media_url: str | None = None
    ) -> str: ...
    def verify_signature(self, body: bytes, signature: str) -> bool: ...
    def fetch_media(self, media_id: str) -> tuple[bytes, str]: ...


class SMS(Protocol):
    name: str
    sandbox: bool

    def send(self, to: str, text: str) -> str: ...


@dataclass
class MockWhatsApp:
    """Records messages instead of sending. Nothing ever reaches a real person."""

    name: str = "mock-whatsapp"
    sandbox: bool = True
    outbox: list[OutboundMessage] = field(default_factory=list)
    down: bool = False

    def send(
        self, to: str, text: str, buttons: list[str] | None = None, media_url: str | None = None
    ) -> str:
        if self.down:
            raise AdapterError("whatsapp down (simulated)")
        self.outbox.append(OutboundMessage(to, text, tuple(buttons or ()), media_url))
        return f"wamid.mock.{len(self.outbox)}"

    def verify_signature(self, body: bytes, signature: str) -> bool:
        return True

    media: dict[str, tuple[bytes, str]] = field(default_factory=dict)

    def fetch_media(self, media_id: str) -> tuple[bytes, str]:
        if media_id not in self.media:
            raise AdapterError("unknown media")
        return self.media[media_id]

    def last_to(self, to: str) -> OutboundMessage | None:
        return next((m for m in reversed(self.outbox) if m.to == to), None)


@dataclass
class MockSMS:
    name: str = "mock-sms"
    sandbox: bool = True
    outbox: list[OutboundMessage] = field(default_factory=list)

    def send(self, to: str, text: str) -> str:
        self.outbox.append(OutboundMessage(to, text, channel="sms"))
        return f"sms.mock.{len(self.outbox)}"


class MetaWhatsApp:
    name = "meta-whatsapp"
    sandbox = False

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not (settings.whatsapp_token and settings.whatsapp_phone_number_id):
            raise NotConfiguredError("WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID missing")
        self.s = settings
        self.client = client or httpx.Client(
            base_url="https://graph.facebook.com/v21.0",
            timeout=15,
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        )

    def send(
        self, to: str, text: str, buttons: list[str] | None = None, media_url: str | None = None
    ) -> str:
        body: dict[str, Any] = {"messaging_product": "whatsapp", "to": to.lstrip("+")}
        if buttons:
            body |= {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": text[:1024]},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": f"b{i}", "title": b[:20]}}
                            for i, b in enumerate(buttons[:3])
                        ]
                    },
                },
            }
        elif media_url:
            body |= {"type": "document", "document": {"link": media_url, "caption": text[:1024]}}
        else:
            body |= {"type": "text", "text": {"body": text[:4096]}}
        try:
            res = self.client.post(f"/{self.s.whatsapp_phone_number_id}/messages", json=body)
            res.raise_for_status()
            return str(res.json()["messages"][0]["id"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise AdapterError(f"whatsapp: {exc}") from exc

    def fetch_media(self, media_id: str) -> tuple[bytes, str]:
        try:
            meta = self.client.get(f"/{media_id}")
            meta.raise_for_status()
            info = meta.json()
            data = self.client.get(str(info["url"]))
            data.raise_for_status()
            return data.content, str(info.get("mime_type", "application/octet-stream"))
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise AdapterError(f"whatsapp media: {exc}") from exc

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not self.s.whatsapp_app_secret:
            return False
        expected = (
            "sha256="
            + hmac.new(self.s.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
        )
        return hmac.compare_digest(expected, signature)


class Msg91SMS:
    name = "msg91"
    sandbox = False

    def __init__(self, settings: Settings) -> None:
        if not settings.sms_api_key:
            raise NotConfiguredError("SMS_API_KEY missing")
        self.client = httpx.Client(
            base_url="https://control.msg91.com",
            timeout=15,
            headers={"authkey": settings.sms_api_key},
        )

    def send(self, to: str, text: str) -> str:
        try:
            res = self.client.post(
                "/api/v5/flow", json={"recipients": [{"mobiles": to.lstrip("+"), "message": text}]}
            )
            res.raise_for_status()
            return str(res.json().get("request_id", ""))
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterError(f"sms: {exc}") from exc
