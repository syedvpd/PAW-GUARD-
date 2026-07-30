"""FastAPI application factory: lifespan, middleware, exception handlers, health checks."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from pawguard.api.v1.router import api_v1_router
from pawguard.core.config import get_settings
from pawguard.core.exceptions import register_exception_handlers
from pawguard.core.logging import configure_logging, get_logger
from pawguard.core.middleware import (
    RequestBodySizeMiddleware,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from pawguard.core.responses import ApiResponse
from pawguard.db.session import engine
from pawguard.redis.client import ping_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    logger.info("application_startup")
    await _seed_roles()
    yield
    await engine.dispose()
    logger.info("application_shutdown")


async def _seed_roles() -> None:
    """Seed roles + permissions on first startup (no-op if already seeded)."""
    from sqlalchemy import select

    from pawguard.db.session import AsyncSessionLocal
    from pawguard.modules.auth.models import Role

    async with AsyncSessionLocal() as session:
        exists = (await session.execute(select(Role).limit(1))).scalar_one_or_none()
        if exists is not None:
            return

    from scripts.seed_roles_and_permissions import seed_db
    await seed_db("Startup", get_settings().database_url)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestBodySizeMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.get("/health", response_model=ApiResponse[dict[str, str]])
    async def health() -> ApiResponse[dict[str, str]]:
        return ApiResponse(data={"status": "ok"})

    @app.get("/live", response_model=ApiResponse[dict[str, str]])
    async def live() -> ApiResponse[dict[str, str]]:
        return ApiResponse(data={"status": "alive"})

    @app.get("/ready", response_model=ApiResponse[dict[str, str]])
    async def ready() -> ApiResponse[dict[str, str]]:
        db_ok = False
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False

        redis_ok = await ping_redis()

        status_payload = {
            "database": "ok" if db_ok else "unavailable",
            "redis": "ok" if redis_ok else "unavailable",
        }
        return ApiResponse(data=status_payload, success=db_ok and redis_ok)

    return app


app = create_app()
