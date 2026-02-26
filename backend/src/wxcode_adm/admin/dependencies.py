"""
FastAPI admin dependencies for wxcode-adm.

Provides:
- admin_oauth2_scheme: separate OAuth2PasswordBearer for admin endpoints
- require_admin: validates admin-audience JWT, checks Redis blacklist, and
  enforces is_superuser=True on the loaded user

Security design:
- Admin tokens carry aud="wxcode-adm-admin" — regular tokens are rejected.
- Regular tokens are NOT accepted even for is_superuser users.
- Blacklisted tokens (from logout) are rejected via Redis check.
- Non-superuser accounts are rejected with ForbiddenError (403).

Usage:
    from wxcode_adm.admin.dependencies import require_admin

    @router.get("/admin/something")
    async def endpoint(admin: User = Depends(require_admin)):
        ...
"""

import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.admin.jwt import decode_admin_access_token
from wxcode_adm.auth.exceptions import InvalidTokenError
from wxcode_adm.auth.models import User
from wxcode_adm.auth.service import is_token_blacklisted
from wxcode_adm.common.exceptions import ForbiddenError
from wxcode_adm.dependencies import get_redis, get_session

# ---------------------------------------------------------------------------
# Admin OAuth2 scheme — separate tokenUrl from regular auth to avoid confusion
# ---------------------------------------------------------------------------

admin_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/admin/login",
    auto_error=True,
)


# ---------------------------------------------------------------------------
# Admin dependency
# ---------------------------------------------------------------------------


async def require_admin(
    token: str = Depends(admin_oauth2_scheme),
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> User:
    """
    Validate an admin-audience JWT and return the authenticated super-admin User.

    Steps:
    1. Decode token via decode_admin_access_token — enforces aud="wxcode-adm-admin".
       Raises TokenExpiredError or InvalidTokenError if invalid.
    2. Extract 'sub' (user_id UUID) and 'jti' from payload.
    3. Check Redis blacklist — raise InvalidTokenError if jti is blacklisted.
    4. Load User from database — raise InvalidTokenError if not found or inactive.
    5. Verify is_superuser=True — raise ForbiddenError if not a super-admin.

    Returns:
        The authenticated super-admin User instance.

    Raises:
        TokenExpiredError: token has passed its expiry time.
        InvalidTokenError: token is malformed, wrong audience, blacklisted,
                          or user is not found/active.
        ForbiddenError: user is not a super-admin (is_superuser=False).
    """
    # 1. Decode admin token (raises TokenExpiredError / InvalidTokenError)
    payload = decode_admin_access_token(token)

    # 2. Extract sub and jti
    sub: str | None = payload.get("sub")
    jti: str | None = payload.get("jti")
    if not sub or not jti:
        raise InvalidTokenError()

    # 3. Check Redis blacklist
    if await is_token_blacklisted(redis, jti):
        raise InvalidTokenError()

    # 4. Load user
    try:
        user_uuid = uuid.UUID(sub)
    except ValueError:
        raise InvalidTokenError()

    user: User | None = await db.get(User, user_uuid)
    if user is None or not user.is_active:
        raise InvalidTokenError()

    # 5. Enforce super-admin access
    if not user.is_superuser:
        raise ForbiddenError(
            error_code="ADMIN_REQUIRED",
            message="Super-admin access required",
        )

    return user
