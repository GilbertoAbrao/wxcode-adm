"""
FastAPI shared dependencies for wxcode-adm.

Provides:
- get_session: yields an AsyncSession with commit-on-success and rollback-on-error
- get_redis: re-exported from common.redis_client for convenient import

Usage:
    from wxcode_adm.dependencies import get_session, get_redis
    ...
    async def my_endpoint(
        db: AsyncSession = Depends(get_session),
        redis: Redis = Depends(get_redis),
    ):
        ...
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.db.engine import async_session_maker

# Re-export for convenient access from a single module
from wxcode_adm.common.redis_client import get_redis as get_redis  # noqa: F401


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession with commit-on-success and rollback-on-error lifecycle.

    Pattern:
        - A new session is opened from async_session_maker.
        - If no exception is raised, the session is committed before closing.
        - If any exception occurs (domain or HTTP), the session is rolled back,
          and the exception is re-raised to FastAPI's exception handling chain.

    Usage:
        async def endpoint(db: AsyncSession = Depends(get_session)):
            result = await db.execute(select(User))
            # No need to call db.commit() — handled here on success
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
