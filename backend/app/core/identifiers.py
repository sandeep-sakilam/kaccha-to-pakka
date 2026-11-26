"""Format and checksum checks for Indian business identifiers. Deterministic, no AI."""

import re

GSTIN_RE = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = _GST_CHARS.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return _GST_CHARS[(36 - total % 36) % 36]


def valid_gstin(gstin: str) -> bool:
    g = gstin.strip().upper()
    return bool(GSTIN_RE.match(g)) and gstin_check_char(g[:14]) == g[14]


def gstin_pan(gstin: str) -> str:
    return gstin.strip().upper()[2:12]


def valid_udyam(udyam: str) -> bool:
    return bool(UDYAM_RE.match(udyam.strip().upper()))


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    """Build a checksum-valid GSTIN (used for sandbox seed data)."""
    first = f"{state}{pan}{entity}Z"
    return first + gstin_check_char(first)
