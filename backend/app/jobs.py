"""Background jobs. Every job is idempotent and retried with backoff; after the last try it goes
to the dead-letter table with its error (never dropped). JOBS_INLINE runs jobs in-process."""

import asyncio
import contextlib
import logging
import traceback
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import _session_factory
from app.db.models import JobFailure

log = logging.getLogger(__name__)
MAX_TRIES = 5

JobFn = Callable[..., None]
REGISTRY: dict[str, JobFn] = {}


class RetryableJobError(Exception):
    """Raise for transient failures (outside service down). The job is retried."""


def job(name: str) -> Callable[[JobFn], JobFn]:
    def deco(fn: JobFn) -> JobFn:
        REGISTRY[name] = fn
        return fn

    return deco


def run_now(db: Session, name: str, *args: Any, attempt: int = 1) -> bool:
    """Run a job synchronously in `db`. Returns True on success. Used inline and by the worker."""
    if name not in REGISTRY:
        import app.job_registry  # noqa: F401  (registers every job)
    fn = REGISTRY[name]
    try:
        with db.begin_nested():
            fn(db, *args)
        return True
    except RetryableJobError as exc:
        if attempt >= MAX_TRIES:
            db.add(JobFailure(job=name, args=list(args), error=str(exc), attempts=attempt))
            db.flush()
            _on_dead(db, name, args)
        raise
    except Exception as exc:
        db.add(
            JobFailure(
                job=name,
                args=list(args),
                error="".join(traceback.format_exception(exc))[-4000:],
                attempts=attempt,
            )
        )
        db.flush()
        _on_dead(db, name, args)
        return False


DEAD_HANDLERS: dict[str, Callable[[Session, tuple[Any, ...]], None]] = {}


def _on_dead(db: Session, name: str, args: tuple[Any, ...]) -> None:
    handler = DEAD_HANDLERS.get(name)
    if handler:
        handler(db, args)


def enqueue(db: Session, name: str, *args: Any) -> None:
    """Queue a job after the current transaction. Inline mode runs it right away in `db`."""
    if get_settings().jobs_inline or get_settings().app_env == "test":
        with contextlib.suppress(RetryableJobError):
            run_now(db, name, *args, attempt=MAX_TRIES)
        return

    def _send(_session: Session) -> None:
        # Only after commit, so the worker never sees a row that is not saved yet.
        try:
            asyncio.get_running_loop()
            running = True
        except RuntimeError:
            running = False
        coro = _enqueue_arq(name, *args)
        if running:
            asyncio.ensure_future(coro)  # noqa: RUF006
        else:
            asyncio.run(coro)

    event.listen(db, "after_commit", _send, once=True)


async def _enqueue_arq(name: str, *args: Any) -> None:
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await pool.enqueue_job("run_job", name, *args)
    await pool.close()


async def run_job(ctx: dict[str, Any], name: str, *args: Any) -> None:
    """Arq entry point: one DB session per try, exponential backoff on retryable errors."""
    from arq import Retry

    attempt = int(ctx.get("job_try", 1))
    db = _session_factory()()
    try:
        run_now(db, name, *args, attempt=attempt)
        db.commit()
    except RetryableJobError as exc:
        db.commit()
        if attempt < MAX_TRIES:
            raise Retry(defer=2**attempt * 5) from exc
    finally:
        db.close()
