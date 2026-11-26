"""FastAPI entry point. Every client goes through this one API."""

from fastapi import FastAPI

from app.adapters.registry import get_adapters
from app.core.config import get_settings
from app.db import triggers  # noqa: F401  (database guarantees)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Kaccha to Pakka API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    @app.get("/meta/sandbox")
    def sandbox() -> dict[str, object]:
        """Which outside services are mocks, so the UI can label them "Sandbox"."""
        status = get_adapters().sandbox_status()
        return {"any_sandbox": any(status.values()), "services": status}

    return app


app = create_app()
