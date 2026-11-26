"""FastAPI entry point. Every client goes through this one API."""

from fastapi import FastAPI

from app.adapters.registry import get_adapters
from app.core.config import get_settings
from app.core.errors import install_handlers
from app.db import triggers  # noqa: F401  (database guarantees)
from app.modules.identity.api import router as auth_router

ROUTERS = [auth_router]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Kaccha to Pakka API", version="0.1.0")
    install_handlers(app)
    for router in ROUTERS:
        app.include_router(router)

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
