"""
Common API router for wxcode-adm.

Provides:
- /health: live status of all infrastructure dependencies (PostgreSQL, Redis)
- /integration/health: discovery endpoint for wxcode engine with service metadata,
  JWKS URL, and endpoint map

Mount with prefix=settings.API_V1_PREFIX in the app factory.
Full paths: GET /api/v1/health, GET /api/v1/integration/health
"""

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.common.rate_limit import limiter
from wxcode_adm.dependencies import get_redis, get_session

router = APIRouter(tags=["common"])


@router.get("/health")
@limiter.exempt
async def health_check(
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """
    Live infrastructure health check.

    Performs a real query against each dependency and returns the result.
    Returns 200 if all checks pass, 503 if any check fails.

    Response format:
        {
            "status": "healthy",
            "checks": {
                "postgresql": "ok",
                "redis": "ok"
            }
        }

    On failure:
        {
            "postgresql": "ok",
            "redis": "error: Connection refused"
        }
        (HTTP 503)
    """
    checks: dict[str, str] = {}

    # Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["postgresql"] = "ok"
    except Exception as e:
        checks["postgresql"] = f"error: {e}"

    # Check Redis
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # If any check failed, return 503 with details
    if any(v != "ok" for v in checks.values()):
        raise HTTPException(status_code=503, detail=checks)

    return {"status": "healthy", "checks": checks}


@router.get("/integration/health")
@limiter.exempt
async def integration_health(
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """
    Integration health endpoint for wxcode engine.

    Returns service status, version, and JWKS URL for JWT validation.
    No authentication required — this is a discovery endpoint.

    Status values:
    - "healthy": both PostgreSQL and Redis are operational
    - "degraded": PostgreSQL is operational but Redis is unavailable
    - "unhealthy": PostgreSQL is unavailable

    Response format:
        {
            "service": "wxcode-adm",
            "version": "0.1.0",
            "status": "healthy",
            "jwks_url": "/.well-known/jwks.json",
            "endpoints": {
                "wxcode_config": "/api/v1/tenants/{tenant_id}/wxcode-config",
                "token_exchange": "/api/v1/auth/wxcode/exchange",
                "health": "/api/v1/health"
            }
        }
    """
    # Check PostgreSQL
    pg_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        pg_ok = False

    # Check Redis
    redis_ok = True
    try:
        await redis.ping()
    except Exception:
        redis_ok = False

    # Determine overall status
    if not pg_ok:
        status = "unhealthy"
    elif not redis_ok:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "service": "wxcode-adm",
        "version": "0.1.0",
        "status": status,
        "jwks_url": "/.well-known/jwks.json",
        "endpoints": {
            "wxcode_config": "/api/v1/tenants/{tenant_id}/wxcode-config",
            "token_exchange": "/api/v1/auth/wxcode/exchange",
            "health": "/api/v1/health",
        },
    }
