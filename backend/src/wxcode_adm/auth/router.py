"""
Auth router for wxcode-adm.

This module provides two routers:

1. `router` — Root-mounted (no prefix), provides:
   - GET /.well-known/jwks.json — RSA public key in JWKS format (RFC 5785)

2. `auth_api_router` — Mounted at /api/v1/auth, provides:
   - POST /signup                — Create account and send verification email
   - POST /verify-email          — Verify email with OTP code
   - POST /resend-verification   — Resend OTP with 60-second cooldown
   - POST /login                 — Authenticate and receive access+refresh tokens
   - POST /refresh               — Rotate refresh token and get new access token
   - POST /logout                — Invalidate refresh token and blacklist access token

The JWKS endpoint MUST remain at domain root per RFC 5785 — external services
(e.g., wxcode engine) fetch this URL to verify JWTs issued by wxcode-adm.
"""

from fastapi import APIRouter, Depends, Header
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth import service
from wxcode_adm.auth.jwks import build_jwks_response
from wxcode_adm.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from wxcode_adm.config import settings
from wxcode_adm.dependencies import get_redis, get_session

# ---------------------------------------------------------------------------
# Root-mounted router (/.well-known/jwks.json — no API prefix)
# ---------------------------------------------------------------------------

router = APIRouter(tags=["auth"])


@router.get("/.well-known/jwks.json")
async def jwks_endpoint() -> dict:
    """
    Return the RSA public key in JWKS (JSON Web Key Set) format.

    This endpoint is public — no authentication required. It allows any
    service to retrieve the public key needed to verify JWTs issued by
    wxcode-adm.
    """
    return build_jwks_response(
        settings.JWT_PUBLIC_KEY.get_secret_value(),
        kid=settings.JWT_KID,
    )


# ---------------------------------------------------------------------------
# API-prefixed auth router (/api/v1/auth)
# ---------------------------------------------------------------------------

auth_api_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_api_router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(
    body: SignupRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> SignupResponse:
    """
    Create a new user account and send an email verification code.

    - Returns 201 on success with a message to check email.
    - Returns 409 if the email is already registered.
    - Returns 422 if the request body is invalid.
    """
    await service.signup(db, redis, body)
    return SignupResponse(message="Check your email for a verification code")


@auth_api_router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> VerifyEmailResponse:
    """
    Verify a user's email address using the 6-digit OTP code.

    - Returns 200 on success.
    - Returns 400 if the code is invalid or expired.
    - Returns 401 if the email address is not found (prevents enumeration).
    - After 3 wrong attempts the code is invalidated — user must resend.
    """
    await service.verify_email(db, redis, body)
    return VerifyEmailResponse(message="Email verified successfully")


@auth_api_router.post("/resend-verification", response_model=ResendVerificationResponse)
async def resend_verification(
    body: ResendVerificationRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ResendVerificationResponse:
    """
    Resend a new verification code to the given email address.

    - Returns 200 always (even if email not found — prevents enumeration).
    - Returns 429 if the 60-second cooldown is still active.
    """
    await service.resend_verification(db, redis, body)
    return ResendVerificationResponse(message="Check your email for a new verification code")


@auth_api_router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    """
    Authenticate a user and issue JWT access + refresh tokens.

    - Returns 200 with access_token and refresh_token on success.
    - Returns 401 if email not found, password incorrect, or account inactive.
    - Returns 403 if email has not been verified.
    - Single-session policy: previous refresh tokens for the user are revoked.
    """
    return await service.login(db, redis, body)


@auth_api_router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    """
    Rotate a refresh token and issue a new access + refresh token pair.

    - Returns 200 with new access_token and refresh_token on success.
    - Returns 401 if the refresh token is invalid or has been consumed.
    - Returns 401 (REPLAY_DETECTED) if a previously consumed token is replayed;
      this triggers full logout (all sessions revoked).
    - Returns 401 if the refresh token has expired.
    """
    return await service.refresh(db, redis, body)


@auth_api_router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    authorization: str | None = Header(default=None),
) -> MessageResponse:
    """
    Log out a user by invalidating their refresh token and blacklisting the
    access token jti in Redis.

    - The refresh token is taken from the request body.
    - The access token is taken from the Authorization: Bearer <token> header.
    - Returns 200 always (idempotent — safe to call even if already logged out).
    """
    access_token = ""
    if authorization and authorization.startswith("Bearer "):
        access_token = authorization[7:]
    await service.logout(db, redis, body.refresh_token, access_token)
    return MessageResponse(message="Logged out successfully")
