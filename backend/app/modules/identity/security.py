"""Hashing helpers for OTPs, PINs and session tokens."""

import hashlib
import hmac
import os
import secrets

from app.core.config import get_settings

WEAK_PINS = {
    "0000",
    "1111",
    "2222",
    "3333",
    "4444",
    "5555",
    "6666",
    "7777",
    "8888",
    "9999",
    "1234",
    "4321",
    "1212",
    "0123",
    "9876",
}


def hash_token(token: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_hex, digest_hex = stored.split("$")
    digest = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(digest.hex(), digest_hex)


def pin_problem(pin: str) -> str | None:
    if len(pin) != 4 or not pin.isdigit():
        return "PIN must be 4 digits"
    if pin in WEAK_PINS:
        return "PIN is too easy to guess"
    return None
