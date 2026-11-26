from fastapi.testclient import TestClient


def test_tts_returns_audio(client: TestClient) -> None:
    r = client.post("/voice/tts", json={"text": "नमस्ते", "language": "hi"})
    assert r.status_code == 200 and r.content.startswith(b"RIFF")
    assert r.headers["X-Sandbox"] == "1"


def test_tts_rejects_unknown_language(client: TestClient) -> None:
    assert client.post("/voice/tts", json={"text": "x", "language": "zz"}).status_code == 400


def test_sandbox_meta(client: TestClient) -> None:
    body = client.get("/meta/sandbox").json()
    assert body["any_sandbox"] is True and body["services"]["ai"] is True
