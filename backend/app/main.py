"""FastAPI entry point. Every client goes through this one API."""

from fastapi import FastAPI

from app import job_registry  # noqa: F401  (register jobs)
from app.adapters.registry import get_adapters
from app.core.config import get_settings
from app.core.errors import install_handlers
from app.db import triggers  # noqa: F401  (database guarantees)
from app.modules.aa.api import router as aa_router
from app.modules.attestations.api import router as attest_router
from app.modules.business.api import router as business_router
from app.modules.consent.api import router as consent_router
from app.modules.evidence.api import router as evidence_router
from app.modules.extraction.api import router as ledger_router
from app.modules.identity.api import router as auth_router
from app.modules.imports.api import router as imports_router
from app.modules.passport.api import router as passport_router
from app.modules.presence.api import router as presence_router
from app.modules.reconciliation.api import router as recon_router
from app.modules.sahayak.api import router as sahayak_router
from app.modules.shares.api import router as shares_router
from app.modules.statements.api import router as statements_router
from app.modules.trust.api import router as trust_router
from app.modules.voice.api import router as voice_router
from app.modules.whatsapp.api import router as whatsapp_router

ROUTERS = [
    auth_router,
    consent_router,
    voice_router,
    business_router,
    evidence_router,
    ledger_router,
    imports_router,
    statements_router,
    aa_router,
    recon_router,
    attest_router,
    presence_router,
    trust_router,
    passport_router,
    shares_router,
    whatsapp_router,
    sahayak_router,
]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Kaccha to Pakka API", version="0.1.0")
    install_handlers(app)
    for router in ROUTERS:
        app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        """Readiness: database and Redis reachable (used by deploy checks)."""
        from redis import Redis
        from sqlalchemy import text

        from app.db.base import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        Redis.from_url(settings.redis_url, socket_timeout=2).ping()
        return {"status": "ready"}

    @app.get("/meta/sandbox")
    def sandbox() -> dict[str, object]:
        """Which outside services are mocks, so the UI can label them "Sandbox"."""
        status = get_adapters().sandbox_status()
        return {"any_sandbox": any(status.values()), "services": status}

    return app


app = create_app()
