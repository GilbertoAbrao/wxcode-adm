"""
FastAPI application factory for wxcode-adm.

Responsibilities:
- App factory (create_app) with lifespan context manager
- Lifespan: verifies PostgreSQL and Redis connectivity on startup
- Lifespan: installs tenant isolation guard on session factory
- Lifespan: graceful shutdown (disposes engine, closes Redis pool)
- CORS middleware with configured allowed origins (static + dynamic tenant wxcode_urls)
- AppError exception handler that translates domain errors to JSON responses
- Module-level app instance for uvicorn: `uvicorn wxcode_adm.main:app`

Do NOT use @app.on_event("startup"/"shutdown") — deprecated in FastAPI >= 0.93.
Do NOT start the arq worker here — it must run as a separate process:
    arq wxcode_adm.tasks.worker.WorkerSettings
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from wxcode_adm.common.exceptions import AppError
from wxcode_adm.common.redis_client import redis_client
from wxcode_adm.config import settings
from wxcode_adm.db.engine import engine, async_session_maker
from wxcode_adm.db.tenant import install_tenant_guard

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dynamic CORS: tenant wxcode_url origin cache
# ---------------------------------------------------------------------------

# Module-level cache of tenant wxcode_url values.
# Populated at lifespan startup from the DB. Used by DynamicCORSMiddleware
# to allow CORS requests from per-tenant custom domains at runtime.
_tenant_origin_cache: set[str] = set()


def _build_cors_origins() -> list[str]:
    """
    Build the static CORS origins list from settings.

    Starts with ALLOWED_ORIGINS and adds FRONTEND_URL as a safety net
    in case it was not included in the explicit list.
    """
    origins = list(settings.ALLOWED_ORIGINS)
    if settings.FRONTEND_URL not in origins:
        origins.append(settings.FRONTEND_URL)
    return origins


class DynamicCORSMiddleware(CORSMiddleware):
    """
    CORS middleware that checks static origins plus tenant wxcode_urls from DB cache.

    Extends CORSMiddleware to add a second-pass origin check against
    _tenant_origin_cache, which is populated at lifespan startup with
    all non-null Tenant.wxcode_url values.
    """

    def __init__(self, app, tenant_origins_loader, **kwargs):
        super().__init__(app, **kwargs)
        self._tenant_origins_loader = tenant_origins_loader

    def is_allowed_origin(self, origin: str) -> bool:
        # Check static origins first (CORSMiddleware default behavior)
        if super().is_allowed_origin(origin):
            return True
        # Check dynamic tenant wxcode_url origins
        return origin in self._tenant_origins_loader()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Startup sequence:
    1. Verify PostgreSQL connectivity (fail fast if DB is unreachable)
    2. Install tenant isolation guard on session factory
    3. Verify Redis connectivity (fail fast if Redis is unreachable)
    4. Seed super-admin user if not exists
    5. Yield control to FastAPI (app is now running)

    Shutdown sequence:
    6. Dispose SQLAlchemy engine (closes all pool connections)
    7. Close Redis connection pool
    """
    # --- Startup ---

    # 1. Verify PostgreSQL connectivity
    logger.info("Verifying PostgreSQL connectivity...")
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("PostgreSQL connection verified.")

    # 2. Install tenant isolation guard on session factory
    install_tenant_guard(async_session_maker)
    logger.info("Tenant isolation guard installed.")

    # 3. Verify Redis connectivity
    logger.info("Verifying Redis connectivity...")
    await redis_client.ping()
    logger.info("Redis connection verified.")

    # 4. Seed super-admin user if not exists
    from wxcode_adm.auth.seed import seed_super_admin  # noqa: PLC0415
    await seed_super_admin(async_session_maker, settings)

    # 5. Load tenant wxcode_url values into CORS origin cache
    logger.info("Loading tenant wxcode_url origins into CORS cache...")
    from wxcode_adm.tenants.models import Tenant  # noqa: PLC0415
    async with async_session_maker() as session:
        result = await session.execute(
            select(Tenant.wxcode_url).where(Tenant.wxcode_url.isnot(None))
        )
        _tenant_origin_cache.update(row[0] for row in result.all())
    logger.info("Tenant CORS origins loaded: %d entries.", len(_tenant_origin_cache))

    yield

    # --- Shutdown ---

    # 5. Dispose SQLAlchemy engine (gracefully close all pool connections)
    logger.info("Disposing SQLAlchemy engine...")
    await engine.dispose()
    logger.info("SQLAlchemy engine disposed.")

    # 6. Close Redis connection pool
    logger.info("Closing Redis connection pool...")
    await redis_client.aclose()
    logger.info("Redis connection pool closed.")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.

    Returns a fully configured FastAPI app with:
    - Lifespan for startup/shutdown infrastructure checks
    - Common router with health endpoint
    - CORS middleware for configured origins
    - AppError exception handler for domain-to-HTTP error translation
    """
    app = FastAPI(
        title="wxcode-adm",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    )

    # --- Rate Limiting (SlowAPI) ---
    # Must be wired BEFORE routers so global default_limits apply to all endpoints.
    # Use SlowAPIASGIMiddleware (not SlowAPIMiddleware) — required for async FastAPI.
    from wxcode_adm.common.rate_limit import (  # noqa: PLC0415
        RateLimitExceeded,
        SlowAPIASGIMiddleware,
        _rate_limit_exceeded_handler,
        limiter,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIASGIMiddleware)

    # --- Session Middleware (Phase 6 -- OAuth) ---
    # Required by authlib for OAuth state and PKCE code_verifier storage.
    # Must be added AFTER SlowAPI and BEFORE CORS so session data is available
    # to all OAuth redirect/callback handlers.
    from starlette.middleware.sessions import SessionMiddleware  # noqa: PLC0415
    app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY.get_secret_value())

    # --- CORS Middleware ---
    # Production-safe CORS: uses explicit ALLOWED_ORIGINS from settings (no wildcard regex).
    # DynamicCORSMiddleware additionally checks tenant wxcode_url values loaded at startup.
    app.add_middleware(
        DynamicCORSMiddleware,
        tenant_origins_loader=lambda: _tenant_origin_cache,
        allow_origins=_build_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Exception Handlers ---
    @app.exception_handler(AppError)
    async def app_error_handler(request, exc: AppError) -> JSONResponse:
        """
        Translate domain AppError exceptions to structured JSON responses.

        All domain errors (NotFoundError, ForbiddenError, ConflictError, etc.)
        inherit from AppError and carry error_code, message, and status_code.
        This handler converts them to the standard error response format.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
            },
        )

    # --- Routers ---
    # Import here to avoid circular imports at module load time
    from wxcode_adm.common.router import router as common_router  # noqa: PLC0415
    from wxcode_adm.auth.router import router as auth_router  # noqa: PLC0415
    from wxcode_adm.auth.router import auth_api_router  # noqa: PLC0415
    from wxcode_adm.tenants.router import router as tenant_router  # noqa: PLC0415
    from wxcode_adm.tenants.router import onboarding_router  # noqa: PLC0415
    from wxcode_adm.tenants.router import invitation_router  # noqa: PLC0415

    app.include_router(common_router, prefix=settings.API_V1_PREFIX)

    # JWKS router: mounted WITHOUT prefix — /.well-known/jwks.json must be at root.
    app.include_router(auth_router)

    # Auth API router: signup, verify-email, resend-verification under /api/v1/auth
    app.include_router(auth_api_router, prefix=settings.API_V1_PREFIX)

    # Tenant routers: workspace creation (onboarding) and tenant management
    app.include_router(tenant_router, prefix=settings.API_V1_PREFIX)
    app.include_router(onboarding_router, prefix=settings.API_V1_PREFIX)

    # Invitation acceptance router: /api/v1/invitations/accept (no tenant context needed)
    app.include_router(invitation_router, prefix=settings.API_V1_PREFIX)

    # Billing routers (Phase 4):
    # - billing_admin_router: super-admin plan CRUD at /api/v1/admin/billing/plans
    # - billing_router: public plan catalog at /api/v1/billing/plans
    from wxcode_adm.billing.router import billing_admin_router, billing_router  # noqa: PLC0415
    app.include_router(billing_admin_router, prefix=settings.API_V1_PREFIX)
    app.include_router(billing_router, prefix=settings.API_V1_PREFIX)

    # Webhook router: no JWT auth — uses Stripe-Signature header
    from wxcode_adm.billing.webhook_router import webhook_router as billing_webhook_router  # noqa: PLC0415
    app.include_router(billing_webhook_router, prefix=settings.API_V1_PREFIX)

    # Audit router (Phase 5): super-admin-only audit log query endpoint
    from wxcode_adm.audit.router import audit_router  # noqa: PLC0415
    app.include_router(audit_router, prefix=settings.API_V1_PREFIX)

    # Users router (Phase 7): user profile management
    from wxcode_adm.users.router import users_router  # noqa: PLC0415
    app.include_router(users_router, prefix=settings.API_V1_PREFIX)

    # Admin router (Phase 8): super-admin management endpoints
    from wxcode_adm.admin.router import admin_router  # noqa: PLC0415
    app.include_router(admin_router, prefix=settings.API_V1_PREFIX)

    return app


# Module-level app instance for uvicorn:
#   uvicorn wxcode_adm.main:app --host 0.0.0.0 --port 8060
app = create_app()
