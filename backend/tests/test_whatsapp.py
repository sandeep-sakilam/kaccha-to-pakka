from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.messaging import MockWhatsApp
from app.adapters.registry import get_adapters
from app.db.models import Business, User
from tests.conftest import new_phone
from tests.test_extraction import _entry, page

_n = iter(range(1_000_000))


def wa() -> MockWhatsApp:
    w = get_adapters().whatsapp
    assert isinstance(w, MockWhatsApp)
    return w


def msg(phone: str, **kind: Any) -> dict[str, Any]:
    m: dict[str, Any] = {"from": phone.lstrip("+"), "id": f"wamid.{next(_n)}"}
    if "text" in kind:
        m |= {"type": "text", "text": {"body": kind["text"]}}
    if "button" in kind:
        m |= {"type": "interactive", "interactive": {"button_reply": {"title": kind["button"]}}}
    if "image" in kind:
        wa().media[m["id"]] = (kind["image"], "image/png")
        m |= {"type": "image", "image": {"id": m["id"]}}
    if "audio" in kind:
        wa().media[m["id"]] = (kind["audio"], "audio/ogg")
        m |= {"type": "audio", "audio": {"id": m["id"]}}
    return {"entry": [{"changes": [{"value": {"messages": [m]}}]}]}


def say(client: TestClient, phone: str, **kind: Any) -> str:
    r = client.post("/whatsapp/webhook", json=msg(phone, **kind))
    assert r.status_code == 200, r.text
    last = wa().last_to(phone)
    assert last is not None
    return last.text


def test_full_whatsapp_journey(client: TestClient, db: Session) -> None:
    phone = new_phone()
    assert "भाषा" in say(client, phone, text="Hi")
    assert "PIN" in say(client, phone, button="English")
    assert "too easy" in say(client, phone, text="1234")
    reply = say(client, phone, text="4826")
    assert "never sell" in reply and "Do you agree?" in reply
    assert "shop's name" in say(client, phone, button="Yes")
    assert "Sharma Kirana" in say(client, phone, text="Sharma Kirana")
    assert "What do you sell" in say(client, phone, button="Yes")
    say(client, phone, audio=b"MOCK:kirana ki dukaan")
    say(client, phone, button="Yes")
    say(client, phone, text="2012 se")
    say(client, phone, button="Yes")
    say(client, phone, text="Rajwada")
    assert "profile is ready" in say(client, phone, button="Yes")
    user = db.execute(select(User).where(User.phone == phone)).scalar_one()
    biz = db.execute(select(Business).where(Business.owner_user_id == user.id)).scalar_one()
    assert biz.category == "kirana" and biz.started_on is not None

    reply = say(client, phone, image=page([_entry("Sharma ji", 400000, conf=0.5)]))
    assert reply.startswith("Sharma ji, four thousand rupees")
    assert wa().last_to(phone).buttons == ("Yes", "No")  # type: ignore[union-attr]
    assert "No entries to check" in say(client, phone, button="Yes")
    assert "No passport yet" in say(client, phone, text="passport")


def test_duplicate_webhook_is_handled_once(client: TestClient) -> None:
    phone = new_phone()
    payload = msg(phone, text="Hi")
    client.post("/whatsapp/webhook", json=payload)
    n = len(wa().outbox)
    client.post("/whatsapp/webhook", json=payload)
    assert len(wa().outbox) == n


def test_decline_consent(client: TestClient) -> None:
    phone = new_phone()
    say(client, phone, text="Hi")
    say(client, phone, button="हिन्दी")
    say(client, phone, text="4826")
    assert "हाँ के बिना" in say(client, phone, button="नहीं")


def test_verify_endpoint(client: TestClient) -> None:
    r = client.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "123"},
    )
    assert r.status_code == 403
