"""
Auth service module for wxcode-adm.

Contains business logic for:
- signup: create user account and send verification email
- verify_email: verify OTP code and mark email as verified
- resend_verification: resend OTP with cooldown enforcement
- login: authenticate user and issue access + refresh tokens (or MFA challenge)
- refresh: rotate refresh token and issue new access token
- logout: invalidate refresh token and blacklist access token in Redis
- forgot_password: enqueue reset email (enumeration-safe, always succeeds)
- reset_password: verify token, update password, revoke all sessions
- _issue_tokens: reusable helper — revoke old sessions, issue new token pair
- get_github_email: extract email from GitHub OAuth token (handles private emails)
- get_google_userinfo: extract email/sub from Google OIDC token
- resolve_oauth_account: state machine for new-user / link-required / existing login
- confirm_oauth_link: confirm account link with password verification
- generate_backup_codes: generate 10 formatted backup codes with argon2 hashes
- generate_qr_code_base64: encode a provisioning URI as a base64 PNG QR code
- mfa_begin_enrollment: generate TOTP secret + QR code for enrollment start
- mfa_confirm_enrollment: verify TOTP code, set mfa_enabled, generate backup codes
- mfa_disable: disable MFA accepting TOTP or backup code
- mfa_verify: complete two-stage login with TOTP or backup code
- create_trusted_device: generate and store a trusted device token (DB + cookie value)
- is_device_trusted: check whether a device token matches a valid TrustedDevice row
- revoke_trusted_devices: delete all TrustedDevice rows for a user
- blacklist_jti: blacklist a JTI directly (without full JWT decode)
- create_wxcode_code: generate and store a one-time wxcode authorization code in Redis
- exchange_wxcode_code: atomically consume a wxcode code and return token data
- get_redirect_url: resolve the wxcode_url for the user's last-used tenant

Redis OTP key pattern:
  auth:otp:{user_id}          — the 6-digit code (TTL 600s)
  auth:otp:attempts:{user_id} — failed attempt counter (TTL 600s)
  auth:otp:cooldown:{user_id} — cooldown flag (TTL 60s)

Redis blacklist/replay key patterns:
  auth:blacklist:jti:{jti}    — blacklisted access token jti (TTL = remaining token lifetime)
  auth:replay:{sha256}        — shadow key mapping consumed refresh token hash to user_id

Redis OAuth link pattern:
  auth:oauth_link:{token}     — JSON {user_id, provider, provider_user_id} (TTL = MFA_PENDING_TTL_SECONDS)

Redis MFA pending key pattern:
  auth:mfa_pending:{token}    — user_id string (TTL = MFA_PENDING_TTL_SECONDS = 300s)

Redis MFA replay prevention pattern:
  auth:mfa:used:{user_id}     — TOTP code value (TTL = 60s; prevents same code reuse)

Redis wxcode one-time code pattern:
  auth:wxcode_code:{code}     — JSON {user_id, access_token, refresh_token} (TTL = WXCODE_CODE_TTL = 30s)
"""

import base64
import hashlib
import io
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pyotp
import qrcode
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
    MfaInvalidCodeError,
    OAuthEmailUnavailableError,
    OAuthProviderAlreadyLinkedError,
    ReplayDetectedError,
    TokenExpiredError,
)
from wxcode_adm.auth.jwt import create_access_token, decode_access_token
from wxcode_adm.auth.models import MfaBackupCode, OAuthAccount, RefreshToken, TrustedDevice, User, UserSession
from wxcode_adm.auth.password import hash_password, verify_password
from wxcode_adm.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    OAuthCallbackResponse,
    OAuthLinkResponse,
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

    # 5. Auto-join pending invitations (new user invitation flow)
    # Lazy import to avoid circular import (tenants.service -> auth.models)
    from wxcode_adm.tenants.service import auto_join_pending_invitations  # noqa: PLC0415
    joined = await auto_join_pending_invitations(db, user)
    if joined:
        logger.info(f"Auto-joined {user.email} to {len(joined)} tenant(s) from pending invitations")


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


async def blacklist_jti(redis: Redis, jti: str) -> None:
    """
    Blacklist an access token JTI directly in Redis.

    Used when we have the JTI from a UserSession row (e.g., session revocation)
    rather than a full JWT string. Writes the Redis blacklist key with TTL
    equal to ACCESS_TOKEN_TTL_HOURS * 3600 seconds so stale keys auto-expire.

    Args:
        redis: Redis client
        jti: the JTI string to blacklist
    """
    await redis.set(
        f"auth:blacklist:jti:{jti}",
        "1",
        ex=int(settings.ACCESS_TOKEN_TTL_HOURS * 3600),
    )


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
    db: AsyncSession,
    redis: Redis,
    body: LoginRequest,
    device_token: str | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict:
    """
    Authenticate a user and issue a new access + refresh token pair.

    When MFA is enabled on the user's account:
    - Checks if the request carries a trusted device cookie (device_token).
    - If the device is trusted, skips MFA and issues tokens immediately.
    - Otherwise, generates an opaque mfa_pending token stored in Redis
      (TTL = MFA_PENDING_TTL_SECONDS) and returns
      {"mfa_required": True, "mfa_token": token} without issuing JWT tokens.

    When MFA is not enabled, issues access + refresh tokens immediately and
    returns {"mfa_required": False, "access_token": ..., "refresh_token": ...}.

    The router interprets the returned dict and constructs the appropriate
    LoginResponse. device_token defaults to None for backward compatibility
    with all existing callers and tests.

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

    # Phase 6: Check if the user is in any tenant that enforces MFA.
    # Lazy import to avoid circular import (auth.service -> tenants.service -> auth.models).
    from wxcode_adm.tenants.service import get_enforcing_tenants_for_user  # noqa: PLC0415
    enforcing_tenants = await get_enforcing_tenants_for_user(db, user.id)

    # Enforcement branch: user is in an enforcing tenant but has NO MFA enrolled.
    # Must prompt them to set up MFA before issuing tokens.
    if enforcing_tenants and not user.mfa_enabled:
        mfa_token = secrets.token_urlsafe(32)
        import json as _json  # noqa: PLC0415
        await redis.set(
            f"auth:mfa_pending:{mfa_token}",
            _json.dumps({"user_id": str(user.id), "setup_required": True}),
            ex=settings.MFA_PENDING_TTL_SECONDS,
        )
        logger.info(
            f"MFA setup required for login: {user.email} (id={user.id}) "
            f"— in {len(enforcing_tenants)} enforcing tenant(s)"
        )
        return {
            "mfa_required": True,
            "mfa_token": mfa_token,
            "mfa_setup_required": True,
        }

    # MFA branch: check if MFA is enabled on this account
    if user.mfa_enabled:
        # Per locked decision: "No remember-device when tenant enforces MFA"
        # Only check trusted device if the user is NOT in any enforcing tenant.
        if not enforcing_tenants and device_token and await is_device_trusted(db, str(user.id), device_token):
            # Trusted device — skip MFA and issue tokens directly
            token_response = await _issue_tokens(
                db, redis, user, user_agent=user_agent, ip_address=ip_address
            )
            logger.info(
                f"User logged in via trusted device: {user.email} (id={user.id})"
            )
            return {
                "mfa_required": False,
                "access_token": token_response.access_token,
                "refresh_token": token_response.refresh_token,
            }

        # Device not trusted (or in enforcing tenant — always require TOTP)
        mfa_token = secrets.token_urlsafe(32)
        await redis.set(
            f"auth:mfa_pending:{mfa_token}",
            str(user.id),
            ex=settings.MFA_PENDING_TTL_SECONDS,
        )
        logger.info(
            f"MFA required for login: {user.email} (id={user.id})"
        )
        return {"mfa_required": True, "mfa_token": mfa_token}

    # MFA not enabled and no enforcing tenants — issue tokens directly
    token_response = await _issue_tokens(
        db, redis, user, user_agent=user_agent, ip_address=ip_address
    )

    logger.info(f"User logged in: {user.email} (id={user.id})")
    return {
        "mfa_required": False,
        "access_token": token_response.access_token,
        "refresh_token": token_response.refresh_token,
    }


async def refresh(
    db: AsyncSession,
    redis: Redis,
    body: RefreshRequest,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """
    Rotate a refresh token: consume the old one and issue a new access +
    refresh token pair.

    - Replay detection: if the token was already consumed (shadow key exists),
      perform full logout and raise ReplayDetectedError.
    - Expiry check: delete the row and raise TokenExpiredError if expired.

    Phase 7: updates the linked UserSession with new access_token_jti and
    optionally refreshes metadata (user_agent, ip_address) if provided.
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

    # Check expiry — handle both timezone-aware (PostgreSQL) and timezone-naive
    # (SQLite test DB) datetimes for cross-DB compatibility.
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.delete(row)
        raise TokenExpiredError()

    # Write shadow key for the consumed token before deleting it
    await _write_shadow_key(redis, row.token, str(row.user_id))

    # Capture the old RefreshToken.id for UserSession update before deleting
    old_rt_id = row.id
    user_id = row.user_id

    # Rotation: delete old RefreshToken and create new one
    await db.delete(row)
    await db.flush()  # Ensure delete is flushed before creating new row

    new_token_str = secrets.token_urlsafe(32)
    new_rt = RefreshToken(
        token=new_token_str,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(new_rt)
    await db.flush()  # Assigns new_rt.id for UserSession FK update

    # Issue new access token
    access_token = create_access_token(str(user_id))
    new_jti = decode_access_token(access_token)["jti"]

    # Update the UserSession: update refresh_token_id FK and access_token_jti
    # This keeps the session alive after token rotation (same logical session).
    session_result = await db.execute(
        select(UserSession).where(UserSession.refresh_token_id == old_rt_id)
    )
    session_record = session_result.scalar_one_or_none()
    if session_record is not None:
        session_record.refresh_token_id = new_rt.id
        session_record.access_token_jti = new_jti
        # Update metadata if provided (refreshed session may come from different device)
        if user_agent is not None:
            meta = parse_session_metadata(user_agent, ip_address)
            session_record.user_agent = meta["user_agent"]
            session_record.device_type = meta["device_type"]
            session_record.browser_name = meta["browser_name"]
            session_record.browser_version = meta["browser_version"]
            session_record.ip_address = meta["ip_address"]
            session_record.city = meta["city"]
    else:
        # No UserSession exists for this RefreshToken (pre-Phase-7 token).
        # Create a new UserSession so all active sessions have metadata.
        meta = parse_session_metadata(user_agent, ip_address)
        db.add(UserSession(
            refresh_token_id=new_rt.id,
            user_id=user_id,
            access_token_jti=new_jti,
            last_active_at=datetime.now(timezone.utc),
            **meta,
        ))

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


def _reset_salt(user: User) -> str:
    """
    Return the itsdangerous salt to use for this user's password reset token.

    For users with a password (password_hash is set), use the hash as salt so
    that changing the password automatically invalidates the reset token.

    For OAuth-only users (password_hash is None), use a stable fixed salt based
    on the user's ID. After they set a password via reset_password(), their
    new password_hash becomes the salt, so the old token is invalidated.

    Args:
        user: The User whose reset token salt to compute.

    Returns:
        A non-empty string to use as the itsdangerous salt.
    """
    return user.password_hash if user.password_hash else f"no-password-{user.id}"


def generate_reset_token(email: str, pw_hash: str) -> str:
    """
    Generate a signed, time-limited password reset token.

    The user's current password_hash (or fixed salt for OAuth-only users) is
    used as the per-token salt so that changing the password automatically
    invalidates this token (single-use enforcement without storing token state).
    """
    return reset_serializer.dumps(email, salt=pw_hash)


def verify_reset_token(token: str, pw_hash: str) -> str:
    """
    Verify a password reset token and return the email address it encodes.

    - Validates HMAC signature using the user's current password_hash (or
      fixed salt for OAuth-only users) as salt.
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

    # Use _reset_salt to handle OAuth-only users (nullable password_hash)
    token = generate_reset_token(body.email, _reset_salt(user))
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

    # Step 3: Full token verification with pw_hash (or OAuth-only salt) as salt
    # (validates signature, expiry, and single-use enforcement)
    verify_reset_token(body.token, _reset_salt(user))

    # Step 4: Update password
    user.password_hash = hash_password(body.new_password)

    # Step 4a: Clear forced-reset flag if it was set by an admin action (Plan 08-03).
    # hasattr guard ensures this is safe before migration 007 adds the column.
    if hasattr(user, "password_reset_required"):
        user.password_reset_required = False

    # Step 5: Revoke all sessions — force re-login on all devices
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))

    logger.info(f"Password reset completed for: {user.email} (id={user.id})")


# ---------------------------------------------------------------------------
# Phase 6: Token issuance helper (shared by login, OAuth, and MFA verify)
# ---------------------------------------------------------------------------


def parse_session_metadata(
    user_agent_str: str | None = None,
    ip_address: str | None = None,
) -> dict:
    """Parse User-Agent and geolocate IP into session metadata dict.

    Args:
        user_agent_str: raw User-Agent header string (optional)
        ip_address: client IP address (optional)

    Returns:
        Dict with keys: user_agent, device_type, browser_name, browser_version,
        ip_address, city. All values are strings or None.
    """
    meta: dict = {
        "user_agent": user_agent_str,
        "device_type": None,
        "browser_name": None,
        "browser_version": None,
        "ip_address": ip_address,
        "city": None,
    }
    if user_agent_str:
        from user_agents import parse as parse_ua  # noqa: PLC0415
        ua = parse_ua(user_agent_str)
        if ua.is_mobile:
            meta["device_type"] = "Mobile"
        elif ua.is_tablet:
            meta["device_type"] = "Tablet"
        elif ua.is_pc:
            meta["device_type"] = "Desktop"
        else:
            meta["device_type"] = "Other"
        meta["browser_name"] = ua.browser.family
        meta["browser_version"] = ua.browser.version_string
    if ip_address and settings.GEOLITE2_DB_PATH:
        try:
            import geoip2.database  # noqa: PLC0415
            with geoip2.database.Reader(settings.GEOLITE2_DB_PATH) as reader:
                response = reader.city(ip_address)
                meta["city"] = response.city.name
        except Exception:
            pass  # Private IPs, missing DB, etc.
    return meta


async def _issue_tokens(
    db: AsyncSession,
    redis: Redis,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """
    Issue a new access + refresh token pair for a user.

    Enforces single-session policy: all existing refresh tokens for the user
    are revoked and shadow keys are written for replay detection.

    Creates a UserSession row with parsed User-Agent and geolocated IP
    alongside the new RefreshToken for rich session metadata tracking.

    This helper is shared by login(), resolve_oauth_account(), and
    confirm_oauth_link() to avoid duplicating token issuance logic.

    Args:
        db: async database session
        redis: Redis client
        user: the User for whom to issue tokens
        user_agent: raw User-Agent header string (optional, keyword-only)
        ip_address: client IP address (optional, keyword-only)
    """
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
    rt = RefreshToken(
        token=refresh_token_str,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(rt)
    await db.flush()  # Assigns rt.id so we can use it for UserSession FK

    # Extract JTI from the access token for UserSession association
    payload = decode_access_token(access_token)
    jti = payload["jti"]

    # Parse session metadata (User-Agent, IP geolocation)
    meta = parse_session_metadata(user_agent, ip_address)

    # Create UserSession row linked 1:1 to the RefreshToken
    session_record = UserSession(
        refresh_token_id=rt.id,
        user_id=user.id,
        access_token_jti=jti,
        last_active_at=datetime.now(timezone.utc),
        **meta,
    )
    db.add(session_record)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token_str)


# ---------------------------------------------------------------------------
# Phase 7: wxcode one-time authorization code helpers
# ---------------------------------------------------------------------------


async def create_wxcode_code(
    redis: Redis,
    user_id: str,
    access_token: str,
    refresh_token: str,
) -> str:
    """
    Generate and store a one-time wxcode authorization code in Redis.

    The code is a random URL-safe string stored with a short TTL
    (settings.WXCODE_CODE_TTL, default 30s). The wxcode backend exchanges
    this code for the actual JWT tokens via POST /auth/wxcode/exchange.

    Token never appears in a URL — only the short-lived authorization code does.

    Args:
        redis: Redis client
        user_id: the user's ID string
        access_token: the issued JWT access token
        refresh_token: the issued refresh token string

    Returns:
        The one-time authorization code string.
    """
    code = secrets.token_urlsafe(32)
    payload = json.dumps({
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
    })
    await redis.set(
        f"auth:wxcode_code:{code}",
        payload,
        ex=settings.WXCODE_CODE_TTL,
    )
    return code


async def exchange_wxcode_code(redis: Redis, code: str) -> dict | None:
    """
    Atomically consume a one-time wxcode authorization code.

    Uses Redis GETDEL for atomic consumption — the key is deleted in the same
    operation, making the code single-use even under concurrent requests.

    Args:
        redis: Redis client
        code: the one-time authorization code from the redirect URL

    Returns:
        Dict with user_id, access_token, refresh_token — or None if the code
        is expired, already used, or never existed.
    """
    raw = await redis.getdel(f"auth:wxcode_code:{code}")
    if raw is None:
        return None
    data = json.loads(raw if isinstance(raw, str) else raw.decode())
    return data


async def get_redirect_url(
    db: AsyncSession, user: "User"
) -> tuple[str | None, "uuid.UUID | None"]:
    """
    Resolve the wxcode application URL for the user.

    Resolution order:
    1. If user.last_used_tenant_id is set, query that Tenant and return
       tenant.wxcode_url if not None.
    2. Otherwise, query the user's most recent TenantMembership
       (ORDER BY created_at DESC LIMIT 1), load the Tenant, and return
       tenant.wxcode_url.
    3. If no memberships or no wxcode_url configured, return (None, None).

    Returns:
        Tuple of (wxcode_url, tenant_id) where both may be None.
    """
    from wxcode_adm.tenants.models import Tenant, TenantMembership  # noqa: PLC0415

    if user.last_used_tenant_id is not None:
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.id == user.last_used_tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is not None and tenant.wxcode_url:
            return tenant.wxcode_url, tenant.id

    # Fall back to most recent membership
    membership_result = await db.execute(
        select(TenantMembership)
        .where(TenantMembership.user_id == user.id)
        .order_by(TenantMembership.created_at.desc())
        .limit(1)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        return None, None

    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == membership.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None or not tenant.wxcode_url:
        return None, None

    return tenant.wxcode_url, tenant.id


# ---------------------------------------------------------------------------
# Phase 6: OAuth service functions
# ---------------------------------------------------------------------------


async def get_github_email(client: object, token: dict) -> tuple[str, str]:
    """
    Extract email and provider_user_id from a GitHub OAuth token.

    GitHub users may have a private email, so we fall back to the
    /user/emails endpoint and select the primary email when the profile
    email field is None.

    Args:
        client: authlib OAuth client for GitHub
        token: token dict from authorize_access_token

    Returns:
        Tuple of (email, provider_user_id)

    Raises:
        OAuthEmailUnavailableError: if no email can be found
    """
    resp = await client.get("user", token=token)
    profile = resp.json()
    provider_user_id = str(profile["id"])
    email = profile.get("email")

    if not email:
        # GitHub user has private email — fetch /user/emails
        emails_resp = await client.get("user/emails", token=token)
        emails = emails_resp.json()
        # Select primary email from the list
        for entry in emails:
            if entry.get("primary"):
                email = entry.get("email")
                break

    if not email:
        raise OAuthEmailUnavailableError()

    return email, provider_user_id


async def get_google_userinfo(token: dict) -> tuple[str, str]:
    """
    Extract email and provider_user_id from a Google OIDC token.

    Google includes userinfo in the token dict when using the OIDC
    server_metadata_url flow. We verify email_verified before trusting the email.

    Args:
        token: token dict from authorize_access_token (includes userinfo)

    Returns:
        Tuple of (email, provider_user_id)

    Raises:
        OAuthEmailUnavailableError: if email is missing or not verified
    """
    userinfo = token.get("userinfo") or token
    email = userinfo.get("email")
    email_verified = userinfo.get("email_verified", False)
    sub = userinfo.get("sub")

    if not email or not email_verified:
        raise OAuthEmailUnavailableError()

    if not sub:
        raise OAuthEmailUnavailableError()

    return email, str(sub)


async def resolve_oauth_account(
    db: AsyncSession,
    redis: Redis,
    provider: str,
    email: str,
    provider_user_id: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> OAuthCallbackResponse | OAuthLinkResponse:
    """
    Account resolution state machine for OAuth sign-in.

    Three cases:
    1. OAuthAccount exists for (provider, provider_user_id) → login existing user.
    2. OAuthAccount not found; User exists by email with password_hash → link_required.
    3. OAuthAccount not found; User exists by email without password_hash → provider conflict.
    4. Neither found → create new User + OAuthAccount, enqueue verification email.

    Args:
        db: async database session
        redis: Redis client
        provider: 'google' or 'github'
        email: email address from OAuth provider
        provider_user_id: unique user ID from the OAuth provider

    Returns:
        OAuthCallbackResponse on successful login or new account creation.
        OAuthLinkResponse when password confirmation is required.

    Raises:
        OAuthProviderAlreadyLinkedError: if user has another OAuth provider already linked.
    """
    # Case 1: Existing OAuthAccount → login
    oauth_result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
    )
    oauth_account = oauth_result.scalar_one_or_none()
    if oauth_account is not None:
        user_result = await db.execute(
            select(User).where(User.id == oauth_account.user_id)
        )
        user = user_result.scalar_one()
        token_response = await _issue_tokens(
            db, redis, user, user_agent=user_agent, ip_address=ip_address
        )
        # Determine if user needs onboarding — use explicit async query to avoid
        # lazy-loading the memberships relationship on the async session
        # (lazy loads raise MissingGreenlet on async sessions in SQLAlchemy 2.0).
        from wxcode_adm.tenants.models import TenantMembership as _TM  # noqa: PLC0415
        membership_count_result = await db.execute(
            select(_TM).where(_TM.user_id == user.id)
        )
        needs_onboarding = len(membership_count_result.scalars().all()) == 0
        logger.info(f"OAuth login for existing user: {user.email} via {provider}")
        return OAuthCallbackResponse(
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            is_new_user=False,
            needs_onboarding=needs_onboarding,
        )

    # Case 2 / 3: Check for existing user by email
    user_result = await db.execute(select(User).where(User.email == email))
    existing_user = user_result.scalar_one_or_none()

    if existing_user is not None:
        if existing_user.password_hash is not None:
            # Case 2: Password account exists → require link confirmation
            link_token = secrets.token_urlsafe(32)
            link_data = json.dumps({
                "user_id": str(existing_user.id),
                "provider": provider,
                "provider_user_id": provider_user_id,
            })
            await redis.set(
                f"auth:oauth_link:{link_token}",
                link_data,
                ex=settings.MFA_PENDING_TTL_SECONDS,
            )
            logger.info(
                f"OAuth link required for {email} via {provider} "
                f"(existing password account)"
            )
            return OAuthLinkResponse(
                link_token=link_token,
                email=email,
                provider=provider,
            )
        else:
            # Case 3: OAuth-only user with a different provider → conflict
            raise OAuthProviderAlreadyLinkedError()

    # Case 4: New user — create account and OAuthAccount
    new_user = User(
        email=email,
        password_hash=None,
        email_verified=False,
        mfa_enabled=False,
    )
    db.add(new_user)
    await db.flush()  # Assigns new_user.id

    db.add(
        OAuthAccount(
            user_id=new_user.id,
            provider=provider,
            provider_user_id=provider_user_id,
        )
    )

    # Generate OTP and enqueue verification email (same as signup flow)
    code = await create_verification_code(redis, str(new_user.id))
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job(
            "send_verification_email", str(new_user.id), new_user.email, code
        )
    finally:
        await pool.aclose()

    # Per locked decision: "Skip workspace creation if already invited to a tenant"
    # Check whether there are pending invitations for this email — if yes, the
    # user will be auto-joined via auto_join_pending_invitations after email
    # verification, so needs_onboarding should be False to skip workspace creation.
    from wxcode_adm.tenants.models import Invitation  # noqa: PLC0415
    inv_result = await db.execute(
        select(Invitation).where(
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
        )
    )
    pending_invitations = inv_result.scalars().all()
    needs_onboarding = len(pending_invitations) == 0

    token_response = await _issue_tokens(
        db, redis, new_user, user_agent=user_agent, ip_address=ip_address
    )
    logger.info(f"New user created via OAuth: {email} (provider={provider})")
    return OAuthCallbackResponse(
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        is_new_user=True,
        needs_onboarding=needs_onboarding,
    )


async def confirm_oauth_link(
    db: AsyncSession,
    redis: Redis,
    link_token: str,
    password: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """
    Confirm an OAuth account link by verifying the user's password.

    Retrieves the pending link data from Redis, verifies the user's password,
    creates the OAuthAccount to link the provider, and issues new tokens.

    Args:
        db: async database session
        redis: Redis client
        link_token: the short-lived Redis token from OAuthLinkResponse
        password: the user's current password for ownership confirmation

    Returns:
        TokenResponse with new access + refresh tokens.

    Raises:
        InvalidTokenError: if the link_token is not found in Redis.
        InvalidCredentialsError: if the password does not match.
    """
    # Retrieve link data from Redis
    raw = await redis.get(f"auth:oauth_link:{link_token}")
    if raw is None:
        raise InvalidTokenError()

    link_data = json.loads(raw if isinstance(raw, str) else raw.decode())
    user_id = uuid.UUID(link_data["user_id"])
    provider = link_data["provider"]
    provider_user_id = link_data["provider_user_id"]

    # Load user and verify password
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise InvalidTokenError()

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    # Create the OAuthAccount link
    db.add(
        OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
        )
    )

    # Delete the Redis link token (single-use)
    await redis.delete(f"auth:oauth_link:{link_token}")

    logger.info(
        f"OAuth account linked: {user.email} -> {provider} "
        f"(provider_user_id={provider_user_id})"
    )

    return await _issue_tokens(db, redis, user, user_agent=user_agent, ip_address=ip_address)


# ---------------------------------------------------------------------------
# Phase 6: MFA enrollment service functions
# ---------------------------------------------------------------------------

# Number of backup codes generated at enrollment time.
BACKUP_CODE_COUNT = 10


def generate_backup_codes() -> tuple[list[str], list[str]]:
    """
    Generate BACKUP_CODE_COUNT one-time backup codes for MFA recovery.

    Each code is a random 10-character string formatted as "XXXXX-XXXXX"
    (5 chars, dash, 5 chars) for readability. The code is hashed with
    argon2id (via hash_password) without the dash for storage.

    Returns:
        Tuple of (plaintext_formatted, hashed) lists, each of length
        BACKUP_CODE_COUNT. The plaintext list is shown to the user ONCE
        and must never be stored in the database.
    """
    plaintext_formatted: list[str] = []
    hashed: list[str] = []

    for _ in range(BACKUP_CODE_COUNT):
        raw = secrets.token_urlsafe(8)[:10].upper()
        formatted = f"{raw[:5]}-{raw[5:]}"
        # Strip ALL dashes from raw before hashing so that token_urlsafe-generated
        # dashes in the raw value don't cause a mismatch with verify (which also
        # strips all dashes from the submitted code before comparing).
        code_hash = hash_password(raw.replace("-", ""))
        plaintext_formatted.append(formatted)
        hashed.append(code_hash)

    return plaintext_formatted, hashed


def generate_qr_code_base64(uri: str) -> str:
    """
    Generate a QR code image for a TOTP provisioning URI and return it as
    a base64-encoded PNG string.

    The base64 string can be embedded in an <img> src attribute directly:
        <img src="data:image/png;base64,{qr_code}" />

    Args:
        uri: otpauth:// provisioning URI from pyotp.TOTP.provisioning_uri()

    Returns:
        Base64-encoded PNG string (no data URI prefix).
    """
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


async def mfa_begin_enrollment(db: AsyncSession, user: User) -> dict:
    """
    Begin MFA enrollment for a user: generate a TOTP secret and QR code.

    Does NOT set mfa_enabled=True — that only happens when the user confirms
    enrollment with a valid TOTP code (mfa_confirm_enrollment).

    Steps:
    1. Reject if MFA is already enabled.
    2. Generate a new TOTP secret (pyotp.random_base32).
    3. Store the secret on user.mfa_secret (temporary, not yet confirmed).
    4. Generate the provisioning URI and QR code image.

    Args:
        db: async database session
        user: the authenticated User requesting enrollment

    Returns:
        Dict with keys: secret, qr_code (base64 PNG), provisioning_uri.

    Raises:
        AppError(MFA_ALREADY_ENABLED, 400): if user.mfa_enabled is True.
    """
    if user.mfa_enabled:
        raise AppError(
            error_code="MFA_ALREADY_ENABLED",
            message="MFA is already enabled",
            status_code=400,
        )

    secret = pyotp.random_base32()
    user.mfa_secret = secret

    provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name="WXCODE",
    )
    qr_code = generate_qr_code_base64(provisioning_uri)

    logger.info(f"MFA enrollment started for user: {user.email} (id={user.id})")

    return {
        "secret": secret,
        "qr_code": qr_code,
        "provisioning_uri": provisioning_uri,
    }


async def mfa_confirm_enrollment(
    db: AsyncSession, user: User, code: str
) -> list[str]:
    """
    Confirm MFA enrollment by verifying a TOTP code from the user's authenticator.

    On success:
    - Sets user.mfa_enabled = True.
    - Generates 10 argon2-hashed backup codes.
    - Cleans up any pre-existing MfaBackupCode rows (from previous failed enrollments).
    - Creates new MfaBackupCode rows (one per hashed code).
    - Returns the plaintext backup codes (shown to the user ONCE, never stored).

    Args:
        db: async database session
        user: the authenticated User completing enrollment
        code: 6-digit TOTP code from the user's authenticator app

    Returns:
        List of 10 plaintext backup codes formatted as "XXXXX-XXXXX".

    Raises:
        AppError(MFA_NOT_STARTED, 400): if user.mfa_secret is None.
        AppError(MFA_ALREADY_ENABLED, 400): if user.mfa_enabled is True.
        MfaInvalidCodeError: if the TOTP code is invalid.
    """
    if user.mfa_secret is None:
        raise AppError(
            error_code="MFA_NOT_STARTED",
            message="Begin enrollment first",
            status_code=400,
        )

    if user.mfa_enabled:
        raise AppError(
            error_code="MFA_ALREADY_ENABLED",
            message="MFA is already enabled",
            status_code=400,
        )

    # Verify the TOTP code (valid_window=1 allows ±30s clock skew)
    if not pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
        raise MfaInvalidCodeError()

    # Enable MFA
    user.mfa_enabled = True

    # Generate backup codes
    plaintext_codes, hashed_codes = generate_backup_codes()

    # Delete any pre-existing backup codes (cleanup from previous failed enrollments)
    await db.execute(
        delete(MfaBackupCode).where(MfaBackupCode.user_id == user.id)
    )

    # Create new backup code rows
    for code_hash in hashed_codes:
        db.add(
            MfaBackupCode(
                user_id=user.id,
                code_hash=code_hash,
                used_at=None,
            )
        )

    await db.flush()

    logger.info(f"MFA enrollment confirmed for user: {user.email} (id={user.id})")

    return plaintext_codes


async def mfa_disable(
    db: AsyncSession, redis: Redis, user: User, code: str
) -> None:
    """
    Disable MFA for a user by verifying a TOTP code or an unused backup code.

    Verification order:
    1. Try TOTP verification first.
    2. If TOTP fails, try backup code: strip dashes, query unused MfaBackupCode
       rows, iterate and call verify_password on each code_hash.
    3. If neither matches, raise MfaInvalidCodeError.

    On success:
    - Sets user.mfa_enabled = False and user.mfa_secret = None.
    - Deletes all MfaBackupCode rows for the user.

    Note (per locked decision): if tenant MFA enforcement is on, the user will
    be re-prompted to enroll on their next login.

    Args:
        db: async database session
        redis: Redis client (reserved for future session invalidation)
        user: the authenticated User requesting MFA disable
        code: a 6-digit TOTP code OR a formatted backup code ("XXXXX-XXXXX")

    Raises:
        AppError(MFA_NOT_ENABLED, 400): if user.mfa_enabled is False.
        MfaInvalidCodeError: if neither TOTP nor backup code matches.
    """
    if not user.mfa_enabled:
        raise AppError(
            error_code="MFA_NOT_ENABLED",
            message="MFA is not enabled",
            status_code=400,
        )

    # Try TOTP verification first
    totp_valid = pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1)

    if not totp_valid:
        # Try backup code — strip dashes before comparing
        code_stripped = code.replace("-", "")
        backup_result = await db.execute(
            select(MfaBackupCode).where(
                MfaBackupCode.user_id == user.id,
                MfaBackupCode.used_at.is_(None),
            )
        )
        backup_rows = backup_result.scalars().all()

        backup_valid = False
        for row in backup_rows:
            if verify_password(code_stripped, row.code_hash):
                row.used_at = datetime.now(timezone.utc)
                backup_valid = True
                break

        if not backup_valid:
            raise MfaInvalidCodeError()

    # Disable MFA
    user.mfa_enabled = False
    user.mfa_secret = None

    # Delete all backup codes for this user
    await db.execute(
        delete(MfaBackupCode).where(MfaBackupCode.user_id == user.id)
    )

    logger.info(f"MFA disabled for user: {user.email} (id={user.id})")


# ---------------------------------------------------------------------------
# Phase 6: MFA two-stage login verify + trusted device helpers
# ---------------------------------------------------------------------------


async def mfa_verify(
    db: AsyncSession,
    redis: Redis,
    mfa_token: str,
    code: str,
    trust_device: bool = False,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict:
    """
    Complete a two-stage MFA login by verifying a TOTP code or backup code.

    Flow:
    1. Look up auth:mfa_pending:{mfa_token} in Redis.
       If not found, raise InvalidTokenError (expired or invalid).
    2. Load the User by the stored user_id.
       If not found or not active, raise InvalidTokenError.
    3. TOTP replay check (6-digit codes only):
       If auth:mfa:used:{user_id} exists AND equals code, raise
       MfaInvalidCodeError (replay detected).
    4. Verify code — TOTP first, then backup code:
       a. TOTP: pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1).
          On success, write replay prevention key (TTL 60s).
       b. Backup: strip dashes, iterate unused MfaBackupCode rows, verify hash.
          On match, set row.used_at = now.
       c. If neither matches, raise MfaInvalidCodeError.
    5. Delete the mfa_pending Redis key (consumed).
    6. Issue tokens via _issue_tokens.
    7. If trust_device=True, create a TrustedDevice record and include
       the plaintext device_token in the returned dict for cookie-setting.

    Returns:
        dict with access_token, refresh_token, and optionally device_token.

    Raises:
        InvalidTokenError: mfa_token not found in Redis.
        MfaInvalidCodeError: TOTP or backup code verification failed.
    """
    # 1. Retrieve mfa_pending token from Redis
    raw_value = await redis.get(f"auth:mfa_pending:{mfa_token}")
    if raw_value is None:
        raise InvalidTokenError()

    raw_str = raw_value if isinstance(raw_value, str) else raw_value.decode()

    # Parse the Redis value — may be a plain user_id string (normal MFA flow)
    # or a JSON object {"user_id": "...", "setup_required": true} (enforcement flow).
    try:
        pending_data = json.loads(raw_str)
        user_id_str = pending_data["user_id"]
        if pending_data.get("setup_required"):
            # User needs to enroll in MFA first — cannot proceed with mfa_verify
            raise AppError(
                error_code="MFA_SETUP_REQUIRED",
                message="You must complete MFA enrollment before logging in",
                status_code=403,
            )
    except (json.JSONDecodeError, KeyError):
        # Plain string format — normal MFA flow (backward compat)
        user_id_str = raw_str

    # 2. Load user
    user_result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id_str))
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise InvalidTokenError()

    # 3. TOTP replay check — only applies to 6-digit numeric TOTP codes
    is_totp_code = len(code) == 6 and code.isdigit()
    if is_totp_code:
        used_code = await redis.get(f"auth:mfa:used:{user_id_str}")
        if used_code is not None:
            used_str = used_code if isinstance(used_code, str) else used_code.decode()
            if used_str == code:
                raise MfaInvalidCodeError()

    # 4. Verify code: TOTP first, then backup code
    totp_valid = pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1)

    if totp_valid:
        # Write replay prevention key for 60 seconds
        await redis.set(f"auth:mfa:used:{user_id_str}", code, ex=60)
    else:
        # Try backup code — strip dashes before comparing
        code_stripped = code.replace("-", "")
        backup_result = await db.execute(
            select(MfaBackupCode).where(
                MfaBackupCode.user_id == user.id,
                MfaBackupCode.used_at.is_(None),
            )
        )
        backup_rows = backup_result.scalars().all()

        backup_valid = False
        for row in backup_rows:
            if verify_password(code_stripped, row.code_hash):
                row.used_at = datetime.now(tz=timezone.utc)
                backup_valid = True
                break

        if not backup_valid:
            raise MfaInvalidCodeError()

    # 5. Consume the mfa_pending token
    await redis.delete(f"auth:mfa_pending:{mfa_token}")

    # 6. Issue tokens (Phase 7: pass session metadata from HTTP request)
    token_response = await _issue_tokens(
        db, redis, user, user_agent=user_agent, ip_address=ip_address
    )

    result: dict = {
        "access_token": token_response.access_token,
        "refresh_token": token_response.refresh_token,
    }

    # 7. Create trusted device record if requested
    if trust_device:
        device_token_value = await create_trusted_device(db, user.id)
        result["device_token"] = device_token_value

    logger.info(f"MFA verified for user: {user.email} (id={user.id})")
    return result


async def create_trusted_device(db: AsyncSession, user_id: uuid.UUID) -> str:
    """
    Create a TrustedDevice record for the given user and return the plaintext token.

    Generates a random opaque device_token, stores its SHA-256 hash in the DB
    with an expiry of TRUSTED_DEVICE_TTL_DAYS days, and returns the plaintext
    token for storing in an HttpOnly cookie.

    Args:
        db: async database session
        user_id: UUID of the user

    Returns:
        Plaintext device_token (for cookie; never stored in DB).
    """
    device_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(device_token.encode()).hexdigest()
    expires_at = datetime.now(tz=timezone.utc) + timedelta(
        days=settings.TRUSTED_DEVICE_TTL_DAYS
    )
    db.add(
        TrustedDevice(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    logger.info(f"Trusted device created for user_id={user_id}")
    return device_token


async def is_device_trusted(
    db: AsyncSession, user_id: str, device_token: str
) -> bool:
    """
    Check whether a device token corresponds to a valid, unexpired TrustedDevice.

    Args:
        db: async database session
        user_id: string UUID of the user
        device_token: plaintext device token (from cookie)

    Returns:
        True if the device is trusted and not expired; False otherwise.
    """
    if not device_token:
        return False

    token_hash = hashlib.sha256(device_token.encode()).hexdigest()
    result = await db.execute(
        select(TrustedDevice).where(
            TrustedDevice.user_id == uuid.UUID(user_id),
            TrustedDevice.token_hash == token_hash,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False

    # Check expiry
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(tz=timezone.utc):
        await db.delete(row)
        return False

    return True


async def revoke_trusted_devices(db: AsyncSession, user_id: uuid.UUID) -> None:
    """
    Delete all TrustedDevice records for the given user.

    Called when a user resets their password or explicitly revokes all sessions
    to ensure trusted devices are cleared along with refresh tokens.

    Args:
        db: async database session
        user_id: UUID of the user
    """
    await db.execute(
        delete(TrustedDevice).where(TrustedDevice.user_id == user_id)
    )
