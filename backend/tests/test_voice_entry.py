import base64
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import EvidenceItem
from app.modules.extraction.voice_parse import parse_amount, parse_entry
from tests.conftest import setup_business
from tests.test_extraction import page, upload

TODAY = date(2026, 11, 26)


def test_parse_amounts() -> None:
    assert parse_amount("chaar hazaar") == 400000
    assert parse_amount("चार हज़ार पाँच सौ") == 450000
    assert parse_amount("ek lakh pachchis hazaar") == 12500000
    assert parse_amount("dedh lakh") == 15000000
    assert parse_amount("4,000 rupaye") == 400000
    assert parse_amount("paanch sau") == 50000
    assert parse_amount("kuch nahi") is None


def test_parse_entries() -> None:
    e = parse_entry("Sharma ji se chaar hazaar mile 12 October", TODAY)
    assert (e.party_text, e.amount_paise, e.direction, e.entry_date) == (
        "Sharma ji",
        400000,
        "in",
        date(2026, 10, 12),
    )
    e = parse_entry("Gupta ko 1250 diye kal", TODAY)
    assert (e.party_text, e.amount_paise, e.direction, e.entry_date) == (
        "Gupta",
        125000,
        "out",
        date(2026, 11, 25),
    )
    assert not parse_entry("pata nahi", TODAY).understood
    assert parse_entry("15 december ko 500 jama", TODAY).entry_date == date(2025, 12, 15)


def test_unreadable_page_then_voice_entry(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client)
    photo_ev = upload(client, h, biz, page([], script="sarrafi", page_conf=0.1), "key-voice-01")
    pending = client.get(f"/businesses/{biz}/needs-voice", headers=h).json()
    assert pending == [{"evidence_id": photo_ev["id"], "script": "sarrafi"}]

    audio = base64.b64encode(b"MOCK:Sharma ji se chaar hazaar mile 12 October").decode()
    parsed = client.post(
        f"/businesses/{biz}/voice-entries/parse",
        headers=h,
        json={"audio_b64": audio, "language": "hi"},
    ).json()
    assert parsed["understood"] and parsed["amount_paise"] == 400000
    assert "चार हज़ार रुपये" in parsed["prompt"]

    body = {
        "source_evidence_id": photo_ev["id"],
        "entries": [
            {k: parsed[k] for k in ("amount_paise", "direction", "party_text", "entry_date")}
            | {"method": "voice", "stt_confidence": parsed["stt_confidence"]},
            {"amount_paise": 20000, "direction": "out", "method": "buttons"},
        ],
    }
    key = {**h, "Idempotency-Key": "voice-save-0001"}
    r1 = client.post(f"/businesses/{biz}/voice-entries", headers=key, json=body).json()
    r2 = client.post(f"/businesses/{biz}/voice-entries", headers=key, json=body).json()
    assert r1["created"] and not r2["created"] and r1["evidence_id"] == r2["evidence_id"]
    ledger = client.get(f"/businesses/{biz}/ledger", headers=h).json()
    assert len(ledger) == 2 and all(e["confirmed_by_owner"] for e in ledger)
    src = db.get(EvidenceItem, str(photo_ev["id"]))
    assert src is not None and src.status == "voice_entered"
    assert client.get(f"/businesses/{biz}/needs-voice", headers=h).json() == []


def test_parse_not_understood(client: TestClient) -> None:
    h, biz = setup_business(client)
    r = client.post(
        f"/businesses/{biz}/voice-entries/parse",
        headers=h,
        json={"transcript": "hmm", "language": "en"},
    ).json()
    assert r["understood"] is False and r["prompt"] is None


def test_amounts_are_exact_integers() -> None:
    assert parse_amount("1.5 lakh") == 15_000_000
    assert parse_amount("sawa lakh") == 12_500_000
    assert parse_amount("paune do hazaar") == 175_000
    assert parse_amount("sawa do hazaar") == 225_000
    assert parse_amount("saadhe teen hazaar") == 350_000
    assert parse_amount("paune lakh") == 7_500_000
    assert parse_amount("dhai hazaar") == 250_000
    assert parse_amount("0.1 lakh") == 1_000_000  # float math would give 999999.99...
    assert parse_amount("2.005") == 201  # half up, from the exact value
    assert parse_amount("1,23,456.78") == 12_345_678
    for text in ("dedh lakh", "4,000", "चार हज़ार पाँच सौ"):
        assert isinstance(parse_amount(text), int)
