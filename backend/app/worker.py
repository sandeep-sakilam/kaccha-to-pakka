"""Background worker (Arq). Extraction, reconciliation and scoring jobs run here."""

from typing import Any, ClassVar

from arq.connections import RedisSettings

from app import job_registry  # noqa: F401  (register jobs)
from app.core.config import get_settings
from app.jobs import MAX_TRIES, run_job


async def ping(ctx: dict[str, Any]) -> str:
    return "pong"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping, run_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = MAX_TRIES
