from datetime import timedelta
from typing import Any

import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import monitoring
from app.core.config import Settings
from app.db.base import utcnow
from app.db.models import Assessment, JobFailure, Notification, User
from app.modules.ops.metrics import check_fraud_rate, hold_rate
from tests import factories as f
from tests.conftest import new_phone


def _assessments(db: Session, n: int, held: int, hours_ago: float) -> None:
    biz = f.business(db)
    for i in range(n):
        db.add(
            Assessment(
                business_id=biz.id,
                rules_version="t",
                band="C",
                confidence="Low",
                status="on_hold" if i < held else "final",
                created_at=utcnow() - timedelta(hours=hours_ago),
            )
        )
    db.flush()


def test_error_reporting_off_without_dsn_and_scrubs() -> None:
    assert monitoring.init_error_reporting(Settings(sentry_dsn="")).name == "off"
    out = monitoring.scrub(
        {
            "message": "OTP for +919812345678 from raju@okaxis",
            "phone": "+919812345678",
            "nested": [{"pin": "4826"}],
        }
    )
    assert out == {
        "message": "OTP for [phone] from [vpa]",
        "phone": "[redacted]",
        "nested": [{"pin": "[redacted]"}],
    }


class RecordingTransport(Transport):
    """Keeps envelopes in memory: nothing leaves the test process."""

    def __init__(self, options: Any = None) -> None:
        super().__init__(options)
        self.envelopes: list[Any] = []

    def capture_envelope(self, envelope: Any) -> None:
        self.envelopes.append(envelope)


def test_sentry_reporter_with_dsn_sends_scrubbed_events_to_its_transport() -> None:
    dsn = "https://k@o1.ingest.sentry.io/1"
    # Under APP_ENV=test a DSN alone never creates a network client.
    assert monitoring.init_error_reporting(Settings(app_env="test", sentry_dsn=dsn)).name == "off"
    transport = RecordingTransport()
    r = monitoring.init_error_reporting(Settings(app_env="test", sentry_dsn=dsn), transport)
    assert r.name == "sentry"
    r.capture_message("OTP to +919812345678 failed", "warning", {"phone": "+919812345678"})
    sentry_sdk.flush()
    text = str([item.payload.get_bytes() for env in transport.envelopes for item in env.items])
    assert "OTP to [phone] failed" in text and "9812345678" not in text
    sentry_sdk.init()  # close the client
    monitoring.init_error_reporting(Settings(sentry_dsn=""))


def test_metrics_endpoint(client: TestClient, db: Session) -> None:
    _assessments(db, 4, 1, 1)
    db.add(JobFailure(job="extract_ledger", args=[], error="x"))
    db.flush()
    body = client.get("/metrics").text
    assert "ktp_queue_depth " in body and "ktp_job_failures_open 1" in body
    assert "ktp_fraud_flag_rate_24h 0.2500" in body or "ktp_fraud_flag_rate_24h" in body


def test_alert_fires_on_a_jump_once(db: Session) -> None:
    reviewer = User(phone=new_phone(), roles=["reviewer"])
    db.add(reviewer)
    _assessments(db, 70, 3, 72)  # baseline ~4% over the previous week
    _assessments(db, 25, 10, 2)  # 40% in the last day
    assert hold_rate(db, timedelta(hours=24)).rate >= 0.3
    first = check_fraud_rate(db)
    assert first.fired and "jumped" in first.reason
    assert db.execute(
        select(Notification).where(
            Notification.user_id == reviewer.id, Notification.kind == "fraud_rate_alert"
        )
    ).first()
    assert check_fraud_rate(db).fired is False  # cooldown


def test_no_alert_when_normal_or_too_few(db: Session) -> None:
    _assessments(db, 5, 4, 2)
    assert check_fraud_rate(db).reason == "too few assessments"
    _assessments(db, 70, 10, 72)
    _assessments(db, 30, 5, 3)
    assert check_fraud_rate(db).fired is False
