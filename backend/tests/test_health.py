from fastapi.testclient import TestClient

from app.main import create_app


def test_health() -> None:
    client = TestClient(create_app())
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_ready() -> None:
    client = TestClient(create_app())
    assert client.get("/ready").json() == {"status": "ready"}
