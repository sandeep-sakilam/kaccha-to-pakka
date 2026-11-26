import random
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Business, Dispute, EvidenceItem, User
from app.modules.review.service import monitor, sahayak_stats
from app.modules.trust import service as trust
from tests import factories as f
from tests.conftest import login, new_phone
from tests.test_trust_engine import strong_business


def reviewer(client: TestClient, db: Session) -> dict[str, str]:
    phone = new_phone()
    h = login(client, phone, device="device-reviewer-1")
    u = db.execute(select(User).where(User.phone == phone)).scalar_one()
    u.roles = ["reviewer"]
    db.flush()
    return h


def test_reviewer_clears_a_held_statement(client: TestClient, db: Session) -> None:
    biz = strong_business(db)
    held = f.evidence(db, biz, "bank_statement", "pdf", "on_hold")
    db.add(
        Dispute(
            target_type="evidence",
            target_id=held.id,
            business_id=biz.id,
            raised_by="system",
            reason="tamper",
        )
    )
    db.flush()
    assert trust.assess(db, biz).status == "on_hold"
    owner_h = login(client, device="device-not-reviewer")
    assert client.get("/review/disputes", headers=owner_h).status_code == 403
    h = reviewer(client, db)
    queue = client.get("/review/disputes", headers=h).json()
    case_id = next(d["id"] for d in queue if d["target_id"] == held.id)
    case = client.get(f"/review/disputes/{case_id}", headers=h).json()
    assert case["business"]["name"] == "Strong Kirana" and case["target"]["status"] == "on_hold"
    r = client.post(
        f"/review/disputes/{case_id}/resolve",
        headers=h,
        json={"decision": "cleared", "note": "bank confirmed by phone"},
    ).json()
    assert r["status"] == "resolved" and r["resolution"] == "cleared"
    db.refresh(held)
    assert held.status == "parsed"
    assert trust.assess(db, biz).status == "final"
    logged = {
        a.action
        for a in db.execute(
            select(AuditLog).where(AuditLog.actor.startswith("reviewer:"))
        ).scalars()
    }
    assert {"review.queue_viewed", "review.case_viewed", "review.resolved"} <= logged


def test_upheld_false_confirmation_disproves_attestation(client: TestClient, db: Session) -> None:
    from app.db.base import utcnow
    from app.db.models import Attestation

    biz = f.business(db)
    confirmer = f.business(db, "Confirmer")
    att = Attestation(
        subject_business_id=biz.id,
        confirmer_business_id=confirmer.id,
        evidence_type="penny_drop",
        claim={},
        status="confirmed",
        weight=1.0,
        expires_at=utcnow() + timedelta(days=30),
    )
    db.add(att)
    db.flush()
    owner = db.get(User, biz.owner_user_id)
    assert owner is not None
    oh = login(client, owner.phone, device="device-owner-dispute")
    d = client.post(
        f"/businesses/{biz.id}/disputes",
        headers=oh,
        json={
            "target_type": "attestation",
            "target_id": att.id,
            "reason": "This person never traded with me",
        },
    ).json()
    h = reviewer(client, db)
    client.post(f"/review/disputes/{d['id']}/resolve", headers=h, json={"decision": "upheld"})
    db.refresh(att)
    assert att.status == "disproved"


def test_sahayak_anomalies_and_suspension(client: TestClient, db: Session) -> None:
    helper = User(phone=new_phone(), roles=["sahayak"])
    db.add(helper)
    db.flush()
    for i in range(6):
        biz = f.business(db, f"Fake {i}")
        db.add(
            EvidenceItem(
                business_id=biz.id,
                type="shop_front",
                source="web_camera",
                status="received",
                sahayak_user_id=helper.id,
                device_attestation={"device_id": "one-phone"},
                geo={"lat": 22.70001 + i * 0.00001, "lng": 75.8},
            )
        )
    db.flush()
    st = next(s for s in sahayak_stats(db) if s.sahayak_user_id == helper.id)
    assert {"shared_device", "gps_cluster"} <= set(st.reasons)
    opened = monitor(db, audit_share=1.0, rng=random.Random(1))
    case = next(d for d in opened if d.target_type == "sahayak" and d.target_id == helper.id)
    assert any(d.raised_by == "system:random_audit" for d in opened)
    h = reviewer(client, db)
    client.post(f"/review/disputes/{case.id}/resolve", headers=h, json={"decision": "upheld"})
    db.refresh(helper)
    assert helper.status == "suspended"
    assert db.execute(select(Business)).first()
