"""
Auth service module for wxcode-adm.

Contains business logic for:
- signup: create user account and send verification email
- verify_email: verify OTP code and mark email as verified
- resend_verification: resend OTP with cooldown enforcement

Redis OTP key pattern:
  auth:otp:{user_id}          — the 6-digit code (TTL 600s)
  auth:otp:attempts:{user_id} — failed attempt counter (TTL 600s)
  auth:otp:cooldown:{user_id} — cooldown flag (TTL 60s)
"""

import logging
import secrets

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth.exceptions import EmailAlreadyExistsError, InvalidCredentialsError
from wxcode_adm.auth.models import User
from wxcode_adm.auth.password import hash_password
from wxcode_adm.auth.schemas import (
    ResendVerificationRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from wxcode_adm.common.exceptions import AppError
from wxcode_adm.tasks.worker import get_arq_pool

logger = logging.getLogger(__name__)


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
