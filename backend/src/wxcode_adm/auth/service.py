"""
Auth service module for wxcode-adm.

Contains business logic for:
- signup: create user account and send verification email
- verify_email: verify OTP code and mark email as verified
- resend_verification: resend OTP with cooldown enforcement
- login: authenticate user and issue access + refresh tokens
- refresh: rotate refresh token and issue new access token
- logout: invalidate refresh token and blacklist access token in Redis
- forgot_password: enqueue reset email (enumeration-safe, always succeeds)
- reset_password: verify token, update password, revoke all sessions

Redis OTP key pattern:
  auth:otp:{user_id}          — the 6-digit code (TTL 600s)
  auth:otp:attempts:{user_id} — failed attempt counter (TTL 600s)
  auth:otp:cooldown:{user_id} — cooldown flag (TTL 60s)

Redis blacklist/replay key patterns:
  auth:blacklist:jti:{jti}    — blacklisted access token jti (TTL = remaining token lifetime)
  auth:replay:{sha256}        — shadow key mapping consumed refresh token hash to user_id
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from itsdangerous import URLSafeTimedSerializer
from itsdangerous.exc import BadSignature, SignatureExpired
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth.exceptions import (
    EmailAlreadyExistsError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidTokenError,
    ReplayDetectedError,
    TokenExpiredError,
)
from wxcode_adm.auth.jwt import create_access_token
from wxcode_adm.auth.models import RefreshToken, User
from wxcode_adm.auth.password import hash_password, verify_password
from wxcode_adm.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    ResendVerificationRequest,
    SignupRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from wxcode_adm.common.exceptions import AppError
from wxcode_adm.config import settings
from wxcode_adm.tasks.worker import get_arq_pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password reset serializer
# ---------------------------------------------------------------------------

# Use JWT_PRIVATE_KEY as secret — strong random secret already in settings.
# salt="password-reset" namespaces it from JWT usage.
reset_serializer = URLSafeTimedSerializer(
    settings.JWT_PRIVATE_KEY.get_secret_value(),
    salt="password-reset",
)


# ---------------------------------------------------------------------------
# OTP helper functions
# ---------------------------------------------------------------------------


async def create_verification_code(redis: Redis, user_id: str) -> str:
    """
    Generate and store a 6-digit OTP for the given user.

    - Stores the code in Redis at auth:otp:{user_id} with 10-minute TTL.
    - Resets the failed-attempt counter to 0 (same TTL).
    - Sets a 60-second cooldown flag to prevent rapid resend requests.

    Returns the plain-text code (must be sent to the user — not stored in DB).
    """
    code = str(secrets.randbelow(900000) + 100000)

    # Store OTP code with 10-minute TTL
    await redis.set(f"auth:otp:{user_id}", code, ex=600)

    # Reset attempt counter with same TTL
    await redis.set(f"auth:otp:attempts:{user_id}", "0", ex=600)

    # Set cooldown flag with 60-second TTL
    await redis.set(f"auth:otp:cooldown:{user_id}", "1", ex=60)

    return code


async def verify_otp_code(redis: Redis, user_id: str, submitted: str) -> bool:
    """
    Verify a submitted OTP code against the stored value.

    Logic:
    1. If no stored code (expired or never set) → return False.
    2. If submitted matches stored → delete keys, return True (success).
    3. Increment attempt counter.
    4. If attempts >= 3 → delete keys, return False (lockout — force resend).
    5. Otherwise → return False (still valid, 1st or 2nd failure).

    The code check happens BEFORE the counter increment so a correct
    code on the 3rd attempt still succeeds (not locked out).
    """
    stored = await redis.get(f"auth:otp:{user_id}")

    if stored is None:
        # Code expired or never existed
        return False

    if submitted == stored:
        # Correct — clean up keys and return success
        await redis.delete(f"auth:otp:{user_id}", f"auth:otp:attempts:{user_id}")
        return True

    # Wrong code — increment attempt counter
    new_attempts = await redis.incr(f"auth:otp:attempts:{user_id}")

    if new_attempts >= 3:
        # 3rd consecutive failure — invalidate the code
        await redis.delete(f"auth:otp:{user_id}", f"auth:otp:attempts:{user_id}")
        return False

    return False


async def check_resend_cooldown(redis: Redis, user_id: str) -> bool:
    """
    Check whether the resend cooldown is active for the given user.

    Returns True if cooldown is active (must wait), False if resend is allowed.
    """
    cooldown = await redis.exists(f"auth:otp:cooldown:{user_id}")
    return bool(cooldown)


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


async def signup(db: AsyncSession, redis: Redis, body: SignupRequest) -> User:
    """
    Create a new user account and enqueue a verification email.

    Steps:
    1. Check if email is already taken — raise EmailAlreadyExistsError (409) if so.
    2. Hash the password with Argon2id.
    3. Persist the User row (flush to get user.id, committed by get_session).
    4. Generate a 6-digit OTP and store in Redis with 10-minute TTL.
    5. Enqueue the send_verification_email arq job.

    Returns the created User instance.
    """
    # 1. Check for duplicate email
    result = await db.execute(select(User).where(User.email == body.email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyExistsError()

    # 2. Hash password
    password_hash = hash_password(body.password)

    # 3. Create user
    user = User(
        email=body.email,
        password_hash=password_hash,
        email_verified=False,
    )
    db.add(user)
    await db.flush()  # Assigns user.id without committing the transaction

    # 4. Generate OTP
    code = await create_verification_code(redis, str(user.id))

    # 5. Enqueue email job
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job("send_verification_email", str(user.id), user.email, code)
    finally:
        await pool.aclose()

    logger.info(f"User signed up: {user.email} (id={user.id})")
    return user


async def verify_email(
    db: AsyncSession, redis: Redis, body: VerifyEmailRequest
) -> None:
    """
    Verify a user's email address using the submitted OTP code.

    Steps:
    1. Find user by email — raise InvalidCredentialsError (401) if not found
       (prevents user enumeration).
    2. If already verified, return silently (idempotent).
    3. Validate the OTP — raise AppError (400) on failure.
    4. Set email_verified=True (committed by get_session).
    """
    # 1. Find user by email
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentialsError()

    # 2. Already verified — idempotent
    if user.email_verified:
        return

    # 3. Validate OTP
    valid = await verify_otp_code(redis, str(user.id), body.code)
    if not valid:
        raise AppError(
            error_code="AUTH_INVALID_CODE",
            message="Invalid or expired verification code",
            status_code=400,
        )

    # 4. Mark as verified
    user.email_verified = True
    logger.info(f"Email verified for user: {user.email} (id={user.id})")


async def resend_verification(
    db: AsyncSession, redis: Redis, body: ResendVerificationRequest
) -> None:
    """
    Resend a verification email for the given email address.

    Steps:
    1. Find user by email — return silently if not found (prevents enumeration).
    2. If already verified, return silently.
    3. Check cooldown — raise AppError (429) if within 60-second cooldown.
    4. Generate new OTP and enqueue email job.
    """
    # 1. Find user by email — silent on not found
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        return

    # 2. Already verified — nothing to do
    if user.email_verified:
        return

    # 3. Check cooldown
    if await check_resend_cooldown(redis, str(user.id)):
        raise AppError(
            error_code="AUTH_COOLDOWN",
            message="Please wait before requesting a new code",
            status_code=429,
        )

    # 4. Generate new OTP and enqueue email
    code = await create_verification_code(redis, str(user.id))
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job("send_verification_email", str(user.id), user.email, code)
    finally:
        await pool.aclose()

    logger.info(f"Verification code resent for: {user.email} (id={user.id})")


# ---------------------------------------------------------------------------
# Access token blacklist helpers
# ---------------------------------------------------------------------------


async def blacklist_access_token(redis: Redis, token: str) -> None:
    """
    Blacklist an access token by storing its jti in Redis with a TTL equal
    to the token's remaining lifetime.

    Uses verify_exp=False so we can extract the jti even if the token has
    already expired (e.g., on logout of a nearly-expired token).
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.JWT_PUBLIC_KEY.get_secret_value(),
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
    except pyjwt.InvalidTokenError:
        # Malformed token — nothing to blacklist
        return

    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return

    remaining = int(exp - datetime.now(timezone.utc).timestamp())
    if remaining > 0:
        await redis.set(f"auth:blacklist:jti:{jti}", "1", ex=remaining)


async def is_token_blacklisted(redis: Redis, jti: str) -> bool:
    """Return True if the given jti has been blacklisted in Redis."""
    return await redis.exists(f"auth:blacklist:jti:{jti}") > 0


# ---------------------------------------------------------------------------
# Replay detection shadow key helpers
# ---------------------------------------------------------------------------


def _shadow_key(token: str) -> str:
    """Return the Redis key for the replay-detection shadow entry for a token."""
    return f"auth:replay:{hashlib.sha256(token.encode()).hexdigest()}"


async def _write_shadow_key(redis: Redis, token: str, user_id: str) -> None:
    """
    Store a shadow key mapping the SHA-256 of a consumed refresh token to the
    user_id. TTL equals the refresh token lifetime so the key auto-expires.
    """
    ttl = settings.REFRESH_TOKEN_TTL_DAYS * 86400
    await redis.set(_shadow_key(token), user_id, ex=ttl)


async def _write_shadow_keys_bulk(redis: Redis, tokens: list[str], user_id: str) -> None:
    """
    Store shadow keys for a batch of tokens using a Redis pipeline for
    efficiency.
    """
    pipe = redis.pipeline()
    ttl = settings.REFRESH_TOKEN_TTL_DAYS * 86400
    for t in tokens:
        pipe.set(_shadow_key(t), user_id, ex=ttl)
    await pipe.execute()


async def _check_replay_and_logout(
    db: AsyncSession, redis: Redis, token: str
) -> None:
    """
    Check whether a token is a replay of a previously consumed token.

    If the shadow key exists the token was legitimately consumed before —
    this is a replay attack. Perform full logout (delete ALL refresh tokens
    for the user) and raise ReplayDetectedError.

    If no shadow key exists the token was never valid (or the shadow key has
    already expired), so raise InvalidTokenError.
    """
    user_id = await redis.get(_shadow_key(token))
    if user_id is not None:
        # Replay detected — full logout
        uid = uuid.UUID(user_id if isinstance(user_id, str) else user_id.decode())
        await db.execute(delete(RefreshToken).where(RefreshToken.user_id == uid))
        raise ReplayDetectedError()

    # Shadow key not found — token was never valid
    raise InvalidTokenError()


# ---------------------------------------------------------------------------
# Login / refresh / logout service functions
# ---------------------------------------------------------------------------


async def login(
    db: AsyncSession, redis: Redis, body: LoginRequest
) -> TokenResponse:
    """
    Authenticate a user and issue a new access + refresh token pair.

    - Returns 401 if email not found, account inactive, or password wrong.
    - Returns 403 if email is not verified.
    - Enforces single-session policy: all previous refresh tokens for this
      user are revoked (shadow keys written for replay detection).
    """
    # Look up user by email
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentialsError()

    if not user.is_active:
        raise InvalidCredentialsError()

    # Verify password
    if not verify_password(body.password, user.password_hash):
        raise InvalidCredentialsError()

    # Require email verification
    if not user.email_verified:
        raise EmailNotVerifiedError(
            error_code="EMAIL_NOT_VERIFIED",
            message="Please verify your email before logging in",
        )

    # Single-session enforcement — revoke all existing refresh tokens
    existing_result = await db.execute(
        select(RefreshToken.token).where(RefreshToken.user_id == user.id)
    )
    old_tokens = [row[0] for row in existing_result.all()]
    if old_tokens:
        await _write_shadow_keys_bulk(redis, old_tokens, str(user.id))
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))

    # Issue new tokens
    access_token = create_access_token(str(user.id))
    refresh_token_str = secrets.token_urlsafe(32)
    db.add(
        RefreshToken(
            token=refresh_token_str,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
        )
    )

    logger.info(f"User logged in: {user.email} (id={user.id})")
    return TokenResponse(access_token=access_token, refresh_token=refresh_token_str)


async def refresh(
    db: AsyncSession, redis: Redis, body: RefreshRequest
) -> TokenResponse:
    """
    Rotate a refresh token: consume the old one and issue a new access +
    refresh token pair.

    - Replay detection: if the token was already consumed (shadow key exists),
      perform full logout and raise ReplayDetectedError.
    - Expiry check: delete the row and raise TokenExpiredError if expired.
    """
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == body.refresh_token)
    )
    row = result.scalar_one_or_none()

    if row is None:
        # Token not in DB — check if it was ever valid (shadow key lookup)
        await _check_replay_and_logout(db, redis, body.refresh_token)
        # _check_replay_and_logout always raises; this line is unreachable
        raise InvalidTokenError()

    # Check expiry
    if row.expires_at < datetime.now(timezone.utc):
        await db.delete(row)
        raise TokenExpiredError()

    # Write shadow key for the consumed token before deleting it
    await _write_shadow_key(redis, row.token, str(row.user_id))

    # Rotation: delete old row and create new one
    user_id = row.user_id
    await db.delete(row)
    new_token_str = secrets.token_urlsafe(32)
    db.add(
        RefreshToken(
            token=new_token_str,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
        )
    )

    # Issue new access token
    access_token = create_access_token(str(user_id))

    logger.info(f"Token refreshed for user_id={user_id}")
    return TokenResponse(access_token=access_token, refresh_token=new_token_str)


async def logout(
    db: AsyncSession, redis: Redis, refresh_token: str, access_token: str
) -> None:
    """
    Log out a user by:
    1. Deleting the refresh token row (idempotent — ignore if not found).
    2. Blacklisting the access token jti in Redis for its remaining lifetime.
    """
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await db.delete(row)

    if access_token:
        await blacklist_access_token(redis, access_token)

    logger.info("User logged out")


# ---------------------------------------------------------------------------
# Password reset token helpers
# ---------------------------------------------------------------------------


def generate_reset_token(email: str, pw_hash: str) -> str:
    """
    Generate a signed, time-limited password reset token.

    The user's current password_hash is used as the per-token salt so that
    changing the password automatically invalidates this token (single-use
    enforcement without storing token state).
    """
    return reset_serializer.dumps(email, salt=pw_hash)


def verify_reset_token(token: str, pw_hash: str) -> str:
    """
    Verify a password reset token and return the email address it encodes.

    - Validates HMAC signature using the user's current password_hash as salt.
    - Enforces 24-hour expiry (86400 seconds).
    - If the password has already been changed (different pw_hash), the HMAC
      will not match — this is how single-use is enforced.

    Raises:
        TokenExpiredError: token has passed its 24-hour expiry.
        InvalidTokenError: token is tampered, malformed, or already used.
    Returns:
        The email address encoded in the token.
    """
    try:
        return reset_serializer.loads(token, salt=pw_hash, max_age=86400)
    except SignatureExpired:
        raise TokenExpiredError()
    except BadSignature:
        raise InvalidTokenError()


# ---------------------------------------------------------------------------
# Password reset service functions
# ---------------------------------------------------------------------------


async def forgot_password(
    db: AsyncSession, redis: Redis, body: ForgotPasswordRequest
) -> None:
    """
    Initiate a password reset flow for the given email address.

    Enumeration prevention: always returns None regardless of whether the
    email exists. The arq job is only enqueued when the user is found.

    Steps:
    1. Look up user by email — return silently if not found.
    2. Generate a signed reset token (itsdangerous, pw_hash as salt).
    3. Build reset link from ALLOWED_ORIGINS[0] (placeholder — adjusted Phase 7).
    4. Enqueue send_reset_email arq job.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        # Return silently — do not reveal whether email exists
        return

    token = generate_reset_token(body.email, user.password_hash)
    reset_link = f"{settings.ALLOWED_ORIGINS[0]}/reset-password?token={token}"

    pool = await get_arq_pool()
    try:
        await pool.enqueue_job("send_reset_email", str(user.id), user.email, reset_link)
    finally:
        await pool.aclose()

    logger.info(f"Password reset requested for: {user.email} (id={user.id})")


async def reset_password(db: AsyncSession, body: ResetPasswordRequest) -> None:
    """
    Complete a password reset using a valid signed token.

    Steps:
    1. Extract email from token via loads_unsafe (needed to look up the user
       before we have their pw_hash for full verification).
    2. Find user by email — raise InvalidTokenError if not found.
    3. Fully verify the token with the user's current pw_hash as salt.
       This validates signature, expiry, and single-use (pw_hash changed => BadSignature).
    4. Update password hash.
    5. Delete ALL refresh tokens for the user (force re-login on all devices).
    """
    # Step 1: Extract email from token without full verification
    _, data = reset_serializer.loads_unsafe(body.token)
    if data is None:
        raise InvalidTokenError()
    email = data  # The payload is the email string

    # Step 2: Find user by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidTokenError()

    # Step 3: Full token verification with pw_hash as salt
    # (validates signature, expiry, and single-use enforcement)
    verify_reset_token(body.token, user.password_hash)

    # Step 4: Update password
    user.password_hash = hash_password(body.new_password)

    # Step 5: Revoke all sessions — force re-login on all devices
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))

    logger.info(f"Password reset completed for: {user.email} (id={user.id})")
