from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.words import rupees_words
from app.db.models import Dispute, EvidenceItem
from tests.conftest import setup_business
from tests.test_extraction import _entry, page, upload


def test_words() -> None:
    assert rupees_words(400000, "hi") == "चार हज़ार रुपये"
    assert rupees_words(4000000, "hi") == "चालीस हज़ार रुपये"
    assert (
        rupees_words(12345650, "en")
        == "one lakh twenty-three thousand four hundred fifty-six rupees fifty paise"
    )


def test_matching_total_passes(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client)
    ev = upload(
        client, h, biz, page([_entry("A", 1000), _entry("B", 2500)], total=3500), "key-readback-1"
    )
    stored = db.get(EvidenceItem, str(ev["id"]))
    assert stored is not None and stored.meta["checksum"]["status"] == "ok"
    assert client.get(f"/businesses/{biz}/readback", headers=h).json() == []


def test_mismatch_goes_to_review_then_owner_fixes_it(client: TestClient, db: Session) -> None:
    h, biz = setup_business(client)
    # The AI misread 4,000 as 1,000; the page total says 6,500.
    data = page([_entry("Sharma ji", 100000), _entry("Gupta", 250000)], total=650000)
    ev = upload(client, h, biz, data, "key-readback-2")
    stored = db.get(EvidenceItem, str(ev["id"]))
    assert stored is not None and stored.status == "checksum_failed"
    assert (
        db.execute(select(Dispute).where(Dispute.target_id == stored.id)).scalar_one().status
        == "open"
    )
    queue = client.get(f"/businesses/{biz}/readback?language=hi", headers=h).json()
    assert len(queue) == 2 and all(q["reason"] == "page_total" for q in queue)
    assert queue[0]["prompt"] == "Sharma ji, एक हज़ार रुपये, 12 अक्टूबर को मिले: सही?"
    sharma = queue[0]["entry"]["id"]
    gupta = queue[1]["entry"]["id"]
    client.post(f"/ledger/{gupta}/confirm", json={"correct": True}, headers=h)
    r = client.post(
        f"/ledger/{sharma}/confirm", json={"correct": False, "amount_paise": 400000}, headers=h
    )
    assert r.json()["amount_paise"] == 400000 and r.json()["status"] == "confirmed"
    db.refresh(stored)
    assert stored.status == "extracted" and stored.meta["checksum"]["status"] == "ok"
    pages = client.get(f"/businesses/{biz}/pages", headers=h).json()
    assert pages[0]["checksum"]["status"] == "ok"


def test_low_confidence_readback_yes_and_no(client: TestClient) -> None:
    h, biz = setup_business(client)
    upload(
        client,
        h,
        biz,
        page([_entry("Ramesh", 50000, conf=0.5), _entry("Suresh", 20000, "out", conf=0.5)]),
        "key-readback-3",
    )
    queue = client.get(f"/businesses/{biz}/readback?language=en", headers=h).json()
    assert queue[0]["prompt"] == "Ramesh, five hundred rupees, received on 12 October: right?"
    yes = client.post(
        f"/ledger/{queue[0]['entry']['id']}/confirm", json={"correct": True}, headers=h
    ).json()
    no = client.post(
        f"/ledger/{queue[1]['entry']['id']}/confirm", json={"correct": False}, headers=h
    ).json()
    assert yes["status"] == "confirmed" and yes["confirmed_by_owner"] is True
    assert no["status"] == "rejected_by_owner"
    assert client.get(f"/businesses/{biz}/readback", headers=h).json() == []


def test_correct_date_and_direction(client: TestClient) -> None:
    h, biz = setup_business(client)
    upload(client, h, biz, page([_entry("X", 1000, conf=0.4)]), "key-readback-4")
    q = client.get(f"/businesses/{biz}/readback", headers=h).json()[0]
    r = client.post(
        f"/ledger/{q['entry']['id']}/confirm",
        headers=h,
        json={"correct": False, "entry_date": str(date(2026, 10, 13)), "direction": "out"},
    ).json()
    assert r["entry_date"] == "2026-10-13" and r["direction"] == "out"
