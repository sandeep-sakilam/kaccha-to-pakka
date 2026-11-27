"""Startup safety: production refuses to run with missing or development secrets.

A missing SECRET_KEY would make sessions and OTP hashes predictable; a missing
FIELD_ENCRYPTION_KEY would encrypt names with a key published in this repository; a missing
PASSPORT_SIGNING_KEY would sign passports with a public development key.
"""

import base64
import binascii
import hashlib

from app.core.config import Settings

DEV_SECRET_KEY = "dev-only-insecure-secret-change-me"  # noqa: S105  (the value we refuse)
DEV_FIELD_KEY = hashlib.sha256(b"ktp-dev-field-key").digest()
DEV_SIGNING_SEED = hashlib.sha256(b"ktp-dev-signing-key").digest()


class UnsafeConfiguration(RuntimeError):
    pass


def _key32(value: str, name: str, dev: bytes, problems: list[str]) -> None:
    if not value:
        problems.append(f"{name} is missing")
        return
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        problems.append(f"{name} is not valid base64")
        return
    if len(raw) != 32:
        problems.append(f"{name} must be base64 of 32 bytes")
    elif raw == dev:
        problems.append(f"{name} is the development default")


def problems(s: Settings) -> list[str]:
    out: list[str] = []
    if not s.secret_key:
        out.append("SECRET_KEY is missing")
    elif s.secret_key == DEV_SECRET_KEY:
        out.append("SECRET_KEY is the development default")
    elif len(s.secret_key) < 32:
        out.append("SECRET_KEY must be at least 32 characters")
    _key32(s.field_encryption_key, "FIELD_ENCRYPTION_KEY", DEV_FIELD_KEY, out)
    _key32(s.passport_signing_key, "PASSPORT_SIGNING_KEY", DEV_SIGNING_SEED, out)
    return out


def check(s: Settings) -> None:
    """Raise in production when a secret is missing or a development default."""
    if s.app_env != "production":
        return
    found = problems(s)
    if found:
        raise UnsafeConfiguration(
            "Refusing to start in production: " + "; ".join(found) + ". See docs/deploy.md step 4."
        )
