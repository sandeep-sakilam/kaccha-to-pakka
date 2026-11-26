"""Ed25519 signing for attestations and passports. Canonical JSON (sorted keys, no spaces) is
signed so a verifier can recompute it exactly, even offline."""

import base64
import hashlib
import json
import logging
from functools import lru_cache
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from app.core.config import get_settings

log = logging.getLogger(__name__)


def canonical(data: Any) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode()


@lru_cache
def signing_key() -> SigningKey:
    raw = get_settings().passport_signing_key
    if raw:
        return SigningKey(base64.b64decode(raw))
    if get_settings().app_env == "production":
        raise RuntimeError("PASSPORT_SIGNING_KEY must be set in production")
    log.warning("PASSPORT_SIGNING_KEY not set; using a fixed development key (Sandbox)")
    return SigningKey(hashlib.sha256(b"ktp-dev-signing-key").digest())


def public_key_b64() -> str:
    return base64.b64encode(bytes(signing_key().verify_key)).decode()


def key_id() -> str:
    return "ktp-" + hashlib.sha256(bytes(signing_key().verify_key)).hexdigest()[:12]


def sign(data: Any) -> str:
    return base64.urlsafe_b64encode(signing_key().sign(canonical(data)).signature).decode()


def verify(data: Any, signature: str, public_key: str | None = None) -> bool:
    key = VerifyKey(base64.b64decode(public_key)) if public_key else signing_key().verify_key
    try:
        key.verify(canonical(data), base64.urlsafe_b64decode(signature))
    except (BadSignatureError, ValueError):
        return False
    return True


def new_key_b64() -> str:
    return base64.b64encode(bytes(SigningKey.generate())).decode()
