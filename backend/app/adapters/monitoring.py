"""Error reporting. Sentry when SENTRY_DSN is set; otherwise off (errors still go to the logs).
Personal data is scrubbed before anything leaves the server."""

import logging
import re
from typing import Any, Protocol

from app.core.config import Settings

log = logging.getLogger(__name__)
PHONE = re.compile(r"\+?91[\s-]?[6-9]\d{9}|\b[6-9]\d{9}\b")
VPA = re.compile(r"[\w.\-]{2,}@[a-z]{2,}", re.I)
SENSITIVE_KEYS = {
    "phone",
    "pin",
    "pan",
    "token",
    "authorization",
    "otp",
    "code",
    "name",
    "full_name",
    "party_text",
    "counterparty_name",
    "payer_name",
    "payer_vpa",
}


def scrub(value: Any) -> Any:
    if isinstance(value, str):
        return VPA.sub("[vpa]", PHONE.sub("[phone]", value))
    if isinstance(value, dict):
        return {
            k: "[redacted]" if str(k).lower() in SENSITIVE_KEYS else scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


class ErrorReporter(Protocol):
    name: str

    def capture_message(
        self, message: str, level: str = "error", extra: dict[str, Any] | None = None
    ) -> None: ...


class LogReporter:
    """Default without a DSN: alerts go to the log only."""

    name = "off"

    def capture_message(
        self, message: str, level: str = "error", extra: dict[str, Any] | None = None
    ) -> None:
        log.log(
            logging.ERROR if level == "error" else logging.WARNING,
            "%s %s",
            message,
            scrub(extra or {}),
        )


class SentryReporter:
    name = "sentry"

    def __init__(self, s: Settings) -> None:
        import sentry_sdk

        def before_send(event: Any, hint: Any) -> Any:
            return scrub(event)

        # sentry-sdk 3 sends no default PII; before_send scrubs phones, UPI IDs and names too.
        sentry_sdk.init(
            dsn=s.sentry_dsn, environment=s.app_env, traces_sample_rate=0.0, before_send=before_send
        )
        self._sdk = sentry_sdk

    def capture_message(
        self, message: str, level: str = "error", extra: dict[str, Any] | None = None
    ) -> None:
        with self._sdk.new_scope() as scope:
            for k, v in scrub(extra or {}).items():
                scope.set_extra(k, v)
            self._sdk.capture_message(message, level=level)  # type: ignore[arg-type]


_reporter: ErrorReporter = LogReporter()


def init_error_reporting(s: Settings) -> ErrorReporter:
    global _reporter
    _reporter = SentryReporter(s) if s.sentry_dsn else LogReporter()
    return _reporter


def reporter() -> ErrorReporter:
    return _reporter
