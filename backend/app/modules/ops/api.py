from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.core.deps import DB
from app.core.errors import Forbidden
from app.modules.ops.metrics import render

router = APIRouter(tags=["ops"])


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(db: DB, authorization: Annotated[str | None, Header()] = None) -> str:
    """Prometheus metrics. In production a METRICS_TOKEN bearer token is required."""
    s = get_settings()
    if s.metrics_token and authorization != f"Bearer {s.metrics_token}":
        raise Forbidden("metrics token required", "forbidden")
    if s.app_env == "production" and not s.metrics_token:
        raise Forbidden("set METRICS_TOKEN to expose metrics", "forbidden")
    return render(db)
