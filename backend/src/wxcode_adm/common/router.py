"""
Common API router for wxcode-adm.

Provides the /health endpoint that returns live status of all
infrastructure dependencies (PostgreSQL, Redis).

Mount with prefix=settings.API_V1_PREFIX in the app factory.
Full path: GET /api/v1/health
"""

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.dependencies import get_redis, get_session

router = APIRouter(tags=["common"])


@router.get("/health")
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
