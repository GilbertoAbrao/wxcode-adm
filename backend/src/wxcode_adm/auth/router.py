"""
Auth router for wxcode-adm.

This module provides two routers:

1. `router` — Root-mounted (no prefix), provides:
   - GET /.well-known/jwks.json — RSA public key in JWKS format (RFC 5785)

2. `auth_api_router` — Mounted at /api/v1/auth, provides:
   - POST /signup      — Create account and send verification email
   - POST /verify-email — Verify email with OTP code
   - POST /resend-verification — Resend OTP with 60-second cooldown

The JWKS endpoint MUST remain at domain root per RFC 5785 — external services
(e.g., wxcode engine) fetch this URL to verify JWTs issued by wxcode-adm.
"""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth import service
from wxcode_adm.auth.jwks import build_jwks_response
from wxcode_adm.auth.schemas import (
    ResendVerificationRequest,
    ResendVerificationResponse,
    SignupRequest,
    SignupResponse,
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
