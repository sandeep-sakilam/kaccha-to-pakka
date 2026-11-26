from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import photo, setup_business


def _upload(
    client: TestClient,
    h: dict[str, str],
    biz: str,
    data: bytes,
    key: str,
    when: datetime | None = None,
    kind: str = "ledger_page",
    mime: str = "image/png",
) -> dict[str, object]:
    when = when or datetime.now(UTC)
    r = client.post(
        f"/businesses/{biz}/captures",
        headers={**h, "Idempotency-Key": key},
        files={"file": ("p.png", data, mime)},
        data={
            "kind": kind,
            "captured_at": when.isoformat(),
            "device_id": "device-test-1",
            "lat": "22.7186",
            "lng": "75.8553",
            "accuracy_m": "12",
            "client_quality": '{"blur": 210}',
        },
    )
    body: dict[str, object] = r.json()
    body["_status"] = r.status_code
    return body


def test_capture_and_idempotent_retry(client: TestClient) -> None:
    h, biz = setup_business(client)
    first = _upload(client, h, biz, photo(), "key-aaaaaaaa")
    assert first["_status"] == 200 and first["status"] == "received" and first["has_geo"]
    again = _upload(client, h, biz, photo(), "key-aaaaaaaa")
    assert again["id"] == first["id"]
    listing = client.get(f"/businesses/{biz}/evidence", headers=h).json()
    assert len(listing) == 1


def test_same_photo_new_key_is_flagged_duplicate(client: TestClient) -> None:
    h, biz = setup_business(client)
    _upload(client, h, biz, photo(), "key-bbbbbbb1")
    dup = _upload(client, h, biz, photo(), "key-bbbbbbb2")
    assert dup["status"] == "duplicate"


def test_quality_rejections(client: TestClient) -> None:
    h, biz = setup_business(client)
    assert _upload(client, h, biz, photo("blurry"), "key-c1111111")["code"] == "quality:blurry"
    assert _upload(client, h, biz, photo("dark"), "key-c2222222")["code"] == "quality:too_dark"
    assert (
        _upload(client, h, biz, b"not an image", "key-c3333333")["code"] == "quality:not_an_image"
    )
    assert (
        _upload(client, h, biz, photo(), "key-c4444444", mime="application/pdf")["code"]
        == "bad_mime"
    )


def test_capture_time_rules(client: TestClient) -> None:
    h, biz = setup_business(client)
    old = datetime.now(UTC) - timedelta(days=8)
    assert _upload(client, h, biz, photo(), "key-d1111111", when=old)["code"] == "bad_time"
    future = datetime.now(UTC) + timedelta(hours=1)
    assert _upload(client, h, biz, photo(), "key-d2222222", when=future)["code"] == "bad_time"
    queued = datetime.now(UTC) - timedelta(days=2)  # offline queue sync later is fine
    assert _upload(client, h, biz, photo(), "key-d3333333", when=queued)["_status"] == 200


def test_old_gallery_photo_rejected(client: TestClient) -> None:
    import io

    from PIL import Image

    h, biz = setup_business(client)
    src = Image.open(io.BytesIO(photo()))
    exif = Image.Exif()
    exif[306] = "2019:01:01 10:00:00"
    buf = io.BytesIO()
    src.convert("RGB").save(buf, format="JPEG", exif=exif.tobytes(), quality=95)
    r = _upload(client, h, biz, buf.getvalue(), "key-e1111111", mime="image/jpeg")
    assert r["code"] == "quality:not_live"


def test_other_user_cannot_upload(client: TestClient) -> None:
    _, biz = setup_business(client)
    h2, _ = setup_business(client, device="device-test-2")
    assert _upload(client, h2, biz, photo(), "key-f1111111")["_status"] == 403
