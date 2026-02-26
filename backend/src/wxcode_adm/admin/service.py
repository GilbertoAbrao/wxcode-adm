"""
Admin service module for wxcode-adm.

Contains business logic for super-admin authentication:
- admin_login: authenticate a super-admin user and issue admin-audience tokens
- admin_refresh: rotate an admin refresh token
- admin_logout: invalidate an admin session

Admin tokens carry aud="wxcode-adm-admin" and are issued ONLY to users with
is_superuser=True. The refresh token lifecycle reuses the same RefreshToken
model as regular auth (no separate table needed for Phase 8).

Audit actions:
  admin_login  — successful admin authentication
  admin_logout — admin session termination
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.admin.jwt import create_admin_access_token
from wxcode_adm.audit.service import write_audit
from wxcode_adm.auth.exceptions import InvalidCredentialsError, InvalidTokenError, TokenExpiredError
from wxcode_adm.auth.models import RefreshToken, User
from wxcode_adm.auth.password import verify_password
from wxcode_adm.auth.service import blacklist_jti
from wxcode_adm.config import settings

logger = logging.getLogger(__name__)


async def admin_login(
    db: AsyncSession,
    redis: Redis,
    email: str,
    password: str,
    client_ip: str | None,
) -> dict:
    """
    Authenticate a super-admin user and issue an admin-audience token pair.

    Steps:
    1. Look up user by email — raise InvalidCredentialsError if not found.
    2. Verify is_superuser=True — raise InvalidCredentialsError if not.
    3. Verify password — raise InvalidCredentialsError if wrong.
    4. Issue admin access token via create_admin_access_token.
    5. Create a RefreshToken row (same pattern as regular auth).
    6. Write audit log entry (admin_login action).

    Returns:
        dict with access_token and refresh_token keys.

    Raises:
        InvalidCredentialsError: user not found, not superuser, or wrong password.
    """
    # 1. Load user by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentialsError()

    # 2. Must be a super-admin — same error as wrong password to prevent enumeration
    if not user.is_superuser:
        raise InvalidCredentialsError()

    # 3. Verify password — also guards against OAuth-only accounts (no password_hash)
    if not user.password_hash or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    # 4. Issue admin-audience access token
    access_token = create_admin_access_token(str(user.id))

    # 5. Create refresh token (reuse regular RefreshToken model — no separate table)
    refresh_token_str = secrets.token_urlsafe(32)
    rt = RefreshToken(
        token=refresh_token_str,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(rt)

    # 6. Write audit log (does NOT commit — session commit is caller's responsibility)
    await write_audit(
        db,
        action="admin_login",
        resource_type="user",
        actor_id=user.id,
        ip_address=client_ip,
    )

    logger.info("Admin login: user=%s (id=%s) ip=%s", user.email, user.id, client_ip)
    return {"access_token": access_token, "refresh_token": refresh_token_str}


async def admin_refresh(
    db: AsyncSession,
    redis: Redis,
    refresh_token_str: str,
) -> dict:
    """
    Rotate an admin refresh token: consume the old one and issue a new pair.

    Steps:
    1. Find RefreshToken row by token value — raise InvalidTokenError if not found.
    2. Check expiry — raise TokenExpiredError if expired, delete the row.
    3. Delete old row, create new RefreshToken + new admin access token.
    4. Return new access_token + refresh_token.

    Note: Admin refresh does NOT do replay detection (shadow keys) to keep the
    implementation simple — admin sessions are short-lived and the IP allowlist
    provides additional protection at the login gate.

    Returns:
        dict with access_token and refresh_token keys.

    Raises:
        InvalidTokenError: token not found in DB.
        TokenExpiredError: token has passed its expiry time.
    """
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token_str)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise InvalidTokenError()

    # Check expiry — handle both timezone-aware (PostgreSQL) and naive (SQLite test) datetimes
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.delete(row)
        raise TokenExpiredError()

    # Capture user_id before deleting
    user_id = row.user_id

    # Rotation: delete old refresh token
    await db.delete(row)
    await db.flush()

    # Issue new admin access token + new refresh token
    access_token = create_admin_access_token(str(user_id))
    new_refresh_str = secrets.token_urlsafe(32)
    new_rt = RefreshToken(
        token=new_refresh_str,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(new_rt)

    logger.info("Admin token refreshed for user_id=%s", user_id)
    return {"access_token": access_token, "refresh_token": new_refresh_str}


async def admin_logout(
    db: AsyncSession,
    redis: Redis,
    refresh_token_str: str,
    access_token_jti: str,
) -> None:
    """
    Invalidate an admin session.

    Steps:
    1. Delete the RefreshToken row (idempotent — ignore if not found).
    2. Blacklist the access token JTI in Redis.
    3. Write audit log entry (admin_logout action).

    Args:
        db: async database session
        redis: Redis client
        refresh_token_str: the refresh token string to revoke
        access_token_jti: the JTI of the access token to blacklist
    """
    # 1. Delete refresh token (idempotent)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token_str)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        actor_id = row.user_id
        await db.delete(row)
    else:
        actor_id = None

    # 2. Blacklist access token JTI
    await blacklist_jti(redis, access_token_jti)

    # 3. Write audit log
    await write_audit(
        db,
        action="admin_logout",
        resource_type="user",
        actor_id=actor_id,
    )

    logger.info("Admin logout: jti=%s", access_token_jti)
