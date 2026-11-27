import base64
import os

import pytest

from app.core.config import Settings
from app.core.startup import (
    DEV_FIELD_KEY,
    DEV_SECRET_KEY,
    DEV_SIGNING_SEED,
    UnsafeConfiguration,
    check,
    problems,
)


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


GOOD = {
    "secret_key": "s" * 64,
    "field_encryption_key": b64(os.urandom(32)),
    "passport_signing_key": b64(os.urandom(32)),
}


def prod(**kw: str) -> Settings:
    return Settings(app_env="production", **{**GOOD, **kw})  # type: ignore[arg-type]


def test_good_production_settings_start() -> None:
    check(prod())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("secret_key", "", "SECRET_KEY is missing"),
        ("secret_key", DEV_SECRET_KEY, "SECRET_KEY is the development default"),
        ("secret_key", "short", "at least 32"),
        ("field_encryption_key", "", "FIELD_ENCRYPTION_KEY is missing"),
        ("field_encryption_key", b64(DEV_FIELD_KEY), "FIELD_ENCRYPTION_KEY is the development"),
        ("field_encryption_key", b64(b"x" * 16), "32 bytes"),
        ("field_encryption_key", "not base64!", "not valid base64"),
        ("passport_signing_key", "", "PASSPORT_SIGNING_KEY is missing"),
        ("passport_signing_key", b64(DEV_SIGNING_SEED), "PASSPORT_SIGNING_KEY is the development"),
    ],
)
def test_unsafe_production_refuses(field: str, value: str, message: str) -> None:
    with pytest.raises(UnsafeConfiguration, match=message):
        check(prod(**{field: value}))


def test_development_is_not_blocked() -> None:
    check(Settings(app_env="development", secret_key=DEV_SECRET_KEY))
    assert problems(Settings(app_env="development", secret_key=DEV_SECRET_KEY))


def test_app_refuses_to_build_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", DEV_SECRET_KEY)
    get_settings.cache_clear()
    try:
        with pytest.raises(UnsafeConfiguration):
            create_app()
    finally:
        get_settings.cache_clear()
