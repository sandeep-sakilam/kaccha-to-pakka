"""Background worker (Arq). Extraction, reconciliation and scoring jobs run here."""

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app import job_registry  # noqa: F401  (register jobs)
from app.core.config import get_settings
from app.jobs import MAX_TRIES, run_job


async def presence_tick(ctx: dict[str, Any]) -> None:
    await run_job(ctx, "presence_send_due")


async def nightly_fraud_scan(ctx: dict[str, Any]) -> None:
    await run_job(ctx, "fraud_graph_scan")


async def nightly_sahayak_monitor(ctx: dict[str, Any]) -> None:
    await run_job(ctx, "sahayak_monitor")


async def daily_aa_refresh(ctx: dict[str, Any]) -> None:
    await run_job(ctx, "aa_refresh_due")


async def ping(ctx: dict[str, Any]) -> str:
    return "pong"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping, run_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = MAX_TRIES
    cron_jobs: ClassVar[list[Any]] = [
        cron(daily_aa_refresh, hour={2}, minute={15}),
        cron(presence_tick, minute=set(range(0, 60, 10))),
        cron(nightly_fraud_scan, hour={1}, minute={5}),
        cron(nightly_sahayak_monitor, hour={1}, minute={35}),
    ]
