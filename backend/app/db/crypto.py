"""Field-level encryption for sensitive columns (counterparty names, party text, account numbers).

AES-256-GCM with a key-encryption key from FIELD_ENCRYPTION_KEY. In production the key comes from a
managed KMS (envelope encryption); in development a fixed dev key is derived so the app still runs.
"""

import base64
import hashlib
import os
from functools import lru_cache
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings

_PREFIX = "enc1:"


@lru_cache
def _key() -> bytes:
    raw = get_settings().field_encryption_key
    if raw:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise ValueError("FIELD_ENCRYPTION_KEY must be base64 of 32 bytes")
        return key
    return hashlib.sha256(b"ktp-dev-field-key").digest()


def encrypt(plain: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, plain.encode(), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    if not token.startswith(_PREFIX):
        return token
    blob = base64.b64decode(token[len(_PREFIX) :])
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], None).decode()


class EncryptedString(TypeDecorator[str]):
    """Text column encrypted at the field level; transparent to application code."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else encrypt(str(value))

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else decrypt(str(value))
