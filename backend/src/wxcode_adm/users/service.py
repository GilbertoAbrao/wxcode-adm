"""
User profile service module for wxcode-adm.

Contains business logic for:
- get_profile: build UserProfileResponse dict from User model
- update_profile: update display_name and/or email (with email re-verification)
- upload_avatar: validate, resize, and save JPEG avatar to filesystem
- change_password: verify current password, hash new password, invalidate other sessions
- list_sessions: return all active sessions with rich metadata for the user
- revoke_session: blacklist a single session JTI and delete its RefreshToken
- revoke_all_other_sessions: bulk-revoke all sessions except the current one
"""

from __future__ import annotations

import logging
import os

from fastapi import UploadFile
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth.models import RefreshToken, User, UserSession
from wxcode_adm.auth.password import hash_password, verify_password
from wxcode_adm.common.exceptions import AppError, ConflictError
from wxcode_adm.config import settings
from wxcode_adm.users.schemas import UpdateProfileRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Profile service functions
# ---------------------------------------------------------------------------


def get_profile(user: User) -> dict:
    """
    Build a profile dict from the User model for GET /users/me.

    Returns dict with id (str), email, email_verified, display_name,
    avatar_url, mfa_enabled. All fields available directly on the User model
    after Phase 7 Plan 01 column additions.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "email_verified": user.email_verified,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "mfa_enabled": user.mfa_enabled,
    }


async def update_profile(
    db: AsyncSession,
    redis: Redis,
    user: User,
    data: UpdateProfileRequest,
) -> User:
    """
    Update a user's display_name and/or email.

    - If data.display_name is not None, updates user.display_name.
    - If data.email is not None AND differs from current email:
        - Checks email uniqueness (raises ConflictError if taken).
        - Sets user.email and resets email_verified to False.
        - Generates new OTP and enqueues verification email.

    Returns the updated User instance (session commit handled by get_session).
    """
    if data.display_name is not None:
        user.display_name = data.display_name

    if data.email is not None and data.email != user.email:
        # Check email uniqueness
        result = await db.execute(select(User).where(User.email == data.email))
        existing = result.scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                error_code="EMAIL_ALREADY_EXISTS",
                message="This email address is already in use",
            )

        user.email = data.email
        user.email_verified = False

        # Generate OTP and enqueue verification email
        from wxcode_adm.auth.service import create_verification_code  # noqa: PLC0415
        from wxcode_adm.tasks.worker import get_arq_pool  # noqa: PLC0415

        code = await create_verification_code(redis, str(user.id))
        pool = await get_arq_pool()
        try:
            await pool.enqueue_job(
                "send_verification_email", str(user.id), user.email, code
            )
        finally:
            await pool.aclose()

        logger.info(
            f"Email update for user {user.id}: new email set, verification required"
        )

    return user


async def upload_avatar(user: User, file: UploadFile, db: AsyncSession) -> str:
    """
    Validate, resize, and save a JPEG avatar for the user.

    Validation:
    - Content type must be image/jpeg or image/png. Raises AppError(400) otherwise.
    - File size must be <= 2MB (2 * 1024 * 1024 bytes). Raises AppError(400) if too large.

    Processing:
    - Opens image with Pillow, resizes to 256x256 (LANCZOS resampling), converts to RGB.
    - Saves as JPEG to {AVATAR_UPLOAD_DIR}/{user.id}.jpg (creates directory if needed).
    - Sets user.avatar_url = f"/avatars/{user.id}.jpg" (relative path).

    Returns the avatar_url string (session commit handled by get_session).
    """
    # Validate content type
    allowed_types = {"image/jpeg", "image/png"}
    if file.content_type not in allowed_types:
        raise AppError(
            error_code="INVALID_AVATAR_TYPE",
            message="Avatar must be a JPEG or PNG image",
            status_code=400,
        )

    # Read file content
    content = await file.read()

    # Validate file size (<= 2MB)
    max_size = 2 * 1024 * 1024  # 2MB in bytes
    if len(content) > max_size:
        raise AppError(
            error_code="AVATAR_TOO_LARGE",
            message="Avatar image must be 2MB or smaller",
            status_code=400,
        )

    # Process image with Pillow
    try:
        from PIL import Image  # noqa: PLC0415
        import io  # noqa: PLC0415

        img = Image.open(io.BytesIO(content))
        img = img.resize((256, 256), Image.LANCZOS)
        img = img.convert("RGB")

        # Ensure upload directory exists
        upload_dir = settings.AVATAR_UPLOAD_DIR
        os.makedirs(upload_dir, exist_ok=True)

        # Save as JPEG
        file_path = os.path.join(upload_dir, f"{user.id}.jpg")
        img.save(file_path, format="JPEG", quality=85)

    except AppError:
        raise
    except Exception as exc:
        logger.error(f"Avatar processing failed for user {user.id}: {exc}")
        raise AppError(
            error_code="AVATAR_PROCESSING_ERROR",
            message="Failed to process avatar image",
            status_code=400,
        ) from exc

    # Update user's avatar_url with relative path
    avatar_url = f"/avatars/{user.id}.jpg"
    user.avatar_url = avatar_url

    logger.info(f"Avatar uploaded for user {user.id}: {avatar_url}")
    return avatar_url


async def change_password(
    db: AsyncSession,
    redis: Redis,
    user: User,
    current_password: str,
    new_password: str,
    current_jti: str | None = None,
) -> None:
    """
    Change a user's password with current password verification.

    Steps:
    1. If user.password_hash is None (OAuth-only account), raise AppError(400).
    2. Verify current_password against user.password_hash. Raise error if wrong.
    3. Hash new_password and set user.password_hash.
    4. Invalidate ALL OTHER sessions:
       - Query all RefreshToken rows for user.id.
       - For each, find the associated UserSession to get access_token_jti.
       - Blacklist each access_token_jti in Redis (except current_jti if provided).
       - Delete all RefreshToken rows for user.id except those matching current_jti.
         (UserSession rows are CASCADE deleted with their RefreshToken.)

    Args:
        db: async database session
        redis: Redis client
        user: the authenticated User
        current_password: the user's current plain-text password
        new_password: the new plain-text password
        current_jti: optional JTI of the current session to preserve (skip revocation)

    Returns None. Session commit is handled by get_session in the router.

    Raises:
        AppError(400, OAUTH_ONLY_ACCOUNT): user has no password to verify against.
        InvalidCredentialsError: current_password does not match stored hash.
    """
    # 1. OAuth-only account check
    if user.password_hash is None:
        raise AppError(
            error_code="OAUTH_ONLY_ACCOUNT",
            message=(
                "Cannot change password — account uses OAuth only. "
                "Use password reset to set a password."
            ),
            status_code=400,
        )

    # 2. Verify current password
    from wxcode_adm.auth.exceptions import InvalidCredentialsError  # noqa: PLC0415

    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError()

    # 3. Hash and update new password
    user.password_hash = hash_password(new_password)

    # 4. Invalidate all OTHER sessions
    # Query all RefreshTokens and their associated UserSession access_token_jti
    rt_result = await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    )
    refresh_tokens = rt_result.scalars().all()

    from wxcode_adm.auth.service import blacklist_access_token  # noqa: PLC0415
    from wxcode_adm.auth.jwt import create_access_token  # noqa: PLC0415

    # Build a fake token for blacklisting by JTI — we need to blacklist JTIs not tokens.
    # Instead, look up UserSession rows directly by user_id to get access_token_jti.
    session_result = await db.execute(
        select(UserSession).where(UserSession.user_id == user.id)
    )
    user_sessions = session_result.scalars().all()

    # Collect JTIs to blacklist (skip current_jti if provided)
    for session_record in user_sessions:
        jti = session_record.access_token_jti
        if current_jti is not None and jti == current_jti:
            # Skip current session — keep it alive
            continue
        # Blacklist the JTI in Redis with ACCESS_TOKEN_TTL_HOURS TTL
        await redis.set(
            f"auth:blacklist:jti:{jti}",
            "1",
            ex=int(settings.ACCESS_TOKEN_TTL_HOURS * 3600),
        )

    # Delete all RefreshToken rows for this user EXCEPT those linked to current session
    if current_jti is not None:
        # Find the RefreshToken linked to the current session via UserSession
        current_session_result = await db.execute(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.access_token_jti == current_jti,
            )
        )
        current_session = current_session_result.scalar_one_or_none()

        if current_session is not None:
            # Delete all RefreshTokens EXCEPT the one linked to current session
            await db.execute(
                delete(RefreshToken).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.id != current_session.refresh_token_id,
                )
            )
        else:
            # No current session found — delete all
            await db.execute(
                delete(RefreshToken).where(RefreshToken.user_id == user.id)
            )
    else:
        # No current_jti — delete all sessions
        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id == user.id)
        )

    logger.info(
        f"Password changed for user {user.id} — "
        f"other sessions invalidated (current_jti={'preserved' if current_jti else 'none'})"
    )


# ---------------------------------------------------------------------------
# Phase 7 Plan 03: Session management service functions
# ---------------------------------------------------------------------------


async def list_sessions(
    db: AsyncSession,
    redis: Redis,
    user: User,
    current_jti: str,
) -> list[dict]:
    """
    Return all active sessions for a user with rich metadata.

    Steps:
    1. Query all UserSession rows for user.id joined with RefreshToken to confirm
       the session is still active (RefreshToken row must exist via FK).
    2. For each session, check Redis key auth:session:last_active:{jti} for the
       freshest last_active timestamp. Falls back to session.last_active_at from DB.
    3. Mark is_current = (session.access_token_jti == current_jti).
    4. Return sorted by last_active_at descending (most recent first).

    Args:
        db: async database session
        redis: Redis client
        user: the authenticated User
        current_jti: the JTI of the current request's access token

    Returns:
        List of session dicts with id, device_type, browser_name, browser_version,
        ip_address, city, last_active_at, is_current, created_at.
    """
    # Query UserSession rows joined with RefreshToken (inner join = active sessions only)
    from wxcode_adm.auth.models import RefreshToken  # noqa: PLC0415 (avoid circular at module level)

    result = await db.execute(
        select(UserSession)
        .join(RefreshToken, RefreshToken.id == UserSession.refresh_token_id)
        .where(UserSession.user_id == user.id)
    )
    sessions = result.scalars().all()

    session_dicts: list[dict] = []
    for session_record in sessions:
        jti = session_record.access_token_jti

        # Check Redis for real-time last_active (falls back to DB value if not set)
        redis_last_active = await redis.get(f"auth:session:last_active:{jti}")
        if redis_last_active is not None:
            last_active_str = (
                redis_last_active
                if isinstance(redis_last_active, str)
                else redis_last_active.decode()
            )
        elif session_record.last_active_at is not None:
            last_active_str = session_record.last_active_at.isoformat()
        else:
            last_active_str = None

        session_dicts.append({
            "id": str(session_record.id),
            "device_type": session_record.device_type,
            "browser_name": session_record.browser_name,
            "browser_version": session_record.browser_version,
            "ip_address": session_record.ip_address,
            "city": session_record.city,
            "last_active_at": last_active_str,
            "is_current": jti == current_jti,
            "created_at": session_record.created_at.isoformat(),
        })

    # Sort by last_active_at descending (most recent first).
    # None values sort to the end.
    session_dicts.sort(
        key=lambda s: s["last_active_at"] or "",
        reverse=True,
    )

    return session_dicts


async def revoke_session(
    db: AsyncSession,
    redis: Redis,
    user: User,
    session_id: str,
    current_jti: str,
) -> None:
    """
    Revoke a single session by session_id.

    Steps:
    1. Load UserSession by id AND user_id (ownership check). Raise NotFoundError if missing.
    2. Prevent self-revocation (locked decision): raise AppError(400) if session is current.
    3. Blacklist the access token JTI in Redis immediately.
    4. Delete the RefreshToken row (CASCADE deletes UserSession via FK).

    Args:
        db: async database session
        redis: Redis client
        user: the authenticated User
        session_id: UUID string of the session to revoke
        current_jti: the JTI of the current request's access token

    Raises:
        NotFoundError: session not found or does not belong to this user.
        AppError(400, CANNOT_REVOKE_CURRENT): attempt to revoke the current session.
    """
    from wxcode_adm.common.exceptions import NotFoundError  # noqa: PLC0415
    import uuid as _uuid  # noqa: PLC0415

    try:
        session_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise NotFoundError(
            error_code="SESSION_NOT_FOUND",
            message="Session not found",
        )

    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_uuid,
            UserSession.user_id == user.id,
        )
    )
    session_record = result.scalar_one_or_none()
    if session_record is None:
        raise NotFoundError(
            error_code="SESSION_NOT_FOUND",
            message="Session not found",
        )

    # Locked decision: prevent accidental self-revocation
    if session_record.access_token_jti == current_jti:
        raise AppError(
            error_code="CANNOT_REVOKE_CURRENT",
            message="Cannot revoke your current session. Use logout instead.",
            status_code=400,
        )

    # Blacklist the JTI in Redis immediately (direct write — we have the JTI)
    from wxcode_adm.auth.service import blacklist_jti  # noqa: PLC0415

    await blacklist_jti(redis, session_record.access_token_jti)

    # Delete the RefreshToken row — CASCADE deletes UserSession via FK
    from wxcode_adm.auth.models import RefreshToken  # noqa: PLC0415

    await db.execute(
        delete(RefreshToken).where(RefreshToken.id == session_record.refresh_token_id)
    )

    logger.info(
        f"Session revoked for user {user.id}: session_id={session_id}"
    )


async def revoke_all_other_sessions(
    db: AsyncSession,
    redis: Redis,
    user: User,
    current_jti: str,
) -> int:
    """
    Revoke all sessions for a user EXCEPT the current one.

    Steps:
    1. Query all UserSession rows for user.id WHERE access_token_jti != current_jti.
    2. For each, blacklist the JTI in Redis.
    3. Find the current session's refresh_token_id (to exclude from DELETE).
    4. Delete all RefreshToken rows for user.id EXCEPT the current one.
    5. Return count of revoked sessions.

    Args:
        db: async database session
        redis: Redis client
        user: the authenticated User
        current_jti: the JTI of the current request's access token (preserved)

    Returns:
        Number of sessions revoked.
    """
    from wxcode_adm.auth.service import blacklist_jti  # noqa: PLC0415
    from wxcode_adm.auth.models import RefreshToken  # noqa: PLC0415

    # Find other sessions (all except current)
    other_sessions_result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.access_token_jti != current_jti,
        )
    )
    other_sessions = other_sessions_result.scalars().all()

    # Blacklist each JTI in Redis
    for session_record in other_sessions:
        await blacklist_jti(redis, session_record.access_token_jti)

    revoked_count = len(other_sessions)

    # Find the current session's RefreshToken FK to exclude from DELETE
    current_session_result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.access_token_jti == current_jti,
        )
    )
    current_session = current_session_result.scalar_one_or_none()

    if current_session is not None:
        # Delete all RefreshTokens for this user EXCEPT the current session's
        await db.execute(
            delete(RefreshToken).where(
                RefreshToken.user_id == user.id,
                RefreshToken.id != current_session.refresh_token_id,
            )
        )
    else:
        # No current session found (edge case) — delete all
        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id == user.id)
        )

    logger.info(
        f"Revoked {revoked_count} other sessions for user {user.id}"
    )
    return revoked_count
