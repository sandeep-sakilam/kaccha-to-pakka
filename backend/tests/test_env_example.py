"""Every setting the code reads is listed in .env.example, and nothing listed is dead."""

import re
from pathlib import Path

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
COMPOSE_ONLY = {
    "DOMAIN",
    "ACME_EMAIL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "BACKUP_PASSPHRASE",
}


def listed() -> set[str]:
    return {m.group(1) for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE.read_text(), re.M)}


def test_every_setting_is_listed() -> None:
    fields = {name.upper() for name in Settings.model_fields}
    assert fields - listed() == set()


def test_nothing_listed_is_unused() -> None:
    fields = {name.upper() for name in Settings.model_fields}
    assert listed() - fields - COMPOSE_ONLY == set()


def test_secrets_have_no_values() -> None:
    text = ENV_EXAMPLE.read_text()
    for key in (
        "SECRET_KEY",
        "FIELD_ENCRYPTION_KEY",
        "PASSPORT_SIGNING_KEY",
        "SARVAM_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "PAYMENTS_CLIENT_SECRET",
        "WHATSAPP_TOKEN",
        "POSTGRES_PASSWORD",
        "BACKUP_PASSPHRASE",
        "METRICS_TOKEN",
    ):
        assert re.search(rf"^{key}=$", text, re.M), key
