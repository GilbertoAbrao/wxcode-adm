"""
Rate limiting module for wxcode-adm.

Provides a slowapi Limiter singleton backed by Redis for persistent rate limiting
across application restarts.

Usage:
    from wxcode_adm.common.rate_limit import limiter

    @router.post("/endpoint")
    @limiter.limit(settings.RATE_LIMIT_AUTH)
    async def endpoint(request: Request, ...):
        ...

CRITICAL: Always place @router.post() BEFORE @limiter.limit() in decorator order.
          The route decorator must come first or rate limiting silently breaks.

CRITICAL: Use SlowAPIASGIMiddleware (not SlowAPIMiddleware) — the non-ASGI variant
          does not work correctly with async FastAPI.

Re-exports for convenient import in main.py:
    - _rate_limit_exceeded_handler: Returns 429 with Retry-After header
    - RateLimitExceeded: Exception class for exception_handler registration
    - SlowAPIASGIMiddleware: ASGI-compatible middleware for FastAPI
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from slowapi.util import get_remote_address

from wxcode_adm.config import settings

# ---------------------------------------------------------------------------
# Limiter singleton — Redis-backed, global 60/minute default
# ---------------------------------------------------------------------------

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_GLOBAL],
    storage_uri=settings.REDIS_URL,
)

# Re-export for main.py convenience
__all__ = [
    "limiter",
    "_rate_limit_exceeded_handler",
    "RateLimitExceeded",
    "SlowAPIASGIMiddleware",
]
