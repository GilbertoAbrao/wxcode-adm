"""
FastAPI auth dependencies for wxcode-adm.

Provides:
- oauth2_scheme: OAuth2PasswordBearer scheme configured for /api/v1/auth/login
- get_current_user: extracts and validates a JWT Bearer token, checks Redis blacklist,
  and returns the active User instance
- require_verified: wraps get_current_user and additionally enforces email verification

Usage:
    from wxcode_adm.auth.dependencies import get_current_user, require_verified
    ...
    @router.get("/profile")
    async def profile(user: User = Depends(require_verified)):
        ...
"""

import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth.exceptions import EmailNotVerifiedError, InvalidTokenError
from wxcode_adm.auth.jwt import decode_access_token
from wxcode_adm.auth.models import User
from wxcode_adm.auth.service import is_token_blacklisted
from wxcode_adm.dependencies import get_redis, get_session

# ---------------------------------------------------------------------------
# OAuth2 scheme
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=True,
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> User:
    """
    Extract and validate the JWT access token from the Authorization header.

    Steps:
    1. Decode token — raises TokenExpiredError or InvalidTokenError if invalid.
    2. Extract 'sub' (user_id UUID) and 'jti' from payload.
    3. Check Redis blacklist — raise InvalidTokenError if jti is blacklisted.
    4. Load User from database — raise InvalidTokenError if not found or inactive.

    Returns:
        The authenticated User instance.

    Raises:
        TokenExpiredError: token has passed its expiry time (caught by AppError handler).
        InvalidTokenError: token is malformed, blacklisted, or user is not found/active.
    """
    # 1. Decode token (raises TokenExpiredError / InvalidTokenError via AppError handler)
    payload = decode_access_token(token)

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

    return user


async def require_verified(
    user: User = Depends(get_current_user),
) -> User:
    """
    Extend get_current_user with email verification enforcement.

    Raises:
        EmailNotVerifiedError: if the user's email has not been verified (HTTP 403).

    Returns:
        The authenticated and verified User instance.
    """
    if not user.email_verified:
        raise EmailNotVerifiedError(
            error_code="EMAIL_NOT_VERIFIED",
            message="Email verification required",
        )
    return user
