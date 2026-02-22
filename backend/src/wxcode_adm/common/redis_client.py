"""
Redis async client singleton for wxcode-adm.

Uses redis.asyncio (NOT the deprecated aioredis package).
The module-level singleton is initialized from settings.REDIS_URL.

Usage in FastAPI dependency injection:
    from wxcode_adm.common.redis_client import get_redis
    ...
    async def my_endpoint(redis: Redis = Depends(get_redis)):
        ...
"""

from redis.asyncio import Redis

from wxcode_adm.config import settings

# Module-level singleton — shared across all requests in the same process.
# Redis connection pool is managed internally by the redis.asyncio client.
redis_client: Redis = Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,  # return str instead of bytes
)


async def get_redis() -> Redis:
    """
    FastAPI dependency that yields the Redis singleton.

    This does NOT yield (no resource to clean up per-request).
    The connection pool is shared and managed by the redis.asyncio client.
    Close happens in app lifespan shutdown via redis_client.aclose().
    """
    return redis_client
