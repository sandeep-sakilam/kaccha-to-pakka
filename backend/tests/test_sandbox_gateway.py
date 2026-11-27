"""Seeded (Sandbox) businesses use the simulated gateway even when real payment keys are set."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.payments import CashfreeGateway, MockPaymentGateway
from app.adapters.registry import get_adapters
from app.core.config import Settings
from app.db.models import Business
from app.modules.attestations.penny_drop import gateway_for
from app.sandbox import demo
from tests import factories as f
from tests.test_penny_drop import invite_token


def test_sandbox_business_uses_simulated_gateway_with_real_keys(db: Session) -> None:
    adapters = get_adapters()
    real = CashfreeGateway(Settings(payments_client_id="id", payments_client_secret="s"))
    saved = adapters.payments, adapters.sandbox_payments
    adapters.payments, adapters.sandbox_payments = real, MockPaymentGateway()
    try:
        normal = f.business(db, "Real Shop")
        sandbox = f.business(db, "Demo Shop")
        sandbox.is_sandbox = True
        assert gateway_for(db, normal.id) is real
        assert isinstance(gateway_for(db, sandbox.id), MockPaymentGateway)
        out = demo.seed_all(db)  # must not touch the real gateway
        fraud = out["fraud"]
        assert isinstance(fraud, dict)
        assert fraud["first_attempt"] == "rejected"
        assert db.get(Business, str(fraud["business_id"])) is not None
    finally:
        adapters.payments, adapters.sandbox_payments = saved


def test_sandbox_pay_route_only_for_simulated_refs(client: TestClient, db: Session) -> None:
    _, _, token = invite_token(client, db, "9844400001")
    pd = client.post(f"/invites/{token}/penny-drop").json()
    ok = client.post(
        f"/sandbox/payments/{pd['ref']}/pay", json={"payer_vpa": "a@ok", "payer_name": "A"}
    )
    assert ok.status_code == 200
    assert (
        client.post(
            "/sandbox/payments/rpd_unknown/pay", json={"payer_vpa": "a@ok", "payer_name": "A"}
        ).status_code
        == 404
    )
