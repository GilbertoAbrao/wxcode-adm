"""
Auth router for wxcode-adm.

This module provides two routers:

1. `router` — Root-mounted (no prefix), provides:
   - GET /.well-known/jwks.json — RSA public key in JWKS format (RFC 5785)

2. `auth_api_router` — Mounted at /api/v1/auth, provides:
   - POST /signup                      — Create account and send verification email
   - POST /verify-email                — Verify email with OTP code
   - POST /resend-verification         — Resend OTP with 60-second cooldown
   - POST /login                       — Authenticate and receive access+refresh tokens (or MFA challenge)
   - POST /mfa/verify                  — Complete two-stage MFA login (TOTP or backup code)
   - POST /refresh                     — Rotate refresh token and get new access token
   - POST /logout                      — Invalidate refresh token and blacklist access token
   - POST /forgot-password             — Initiate password reset (enumeration-safe)
   - POST /reset-password              — Complete password reset with signed token
   - GET  /oauth/{provider}/login      — OAuth redirect to Google or GitHub
   - GET  /oauth/{provider}/callback   — OAuth callback — exchange code, resolve account
   - POST /oauth/link/confirm          — Confirm account link with password
   - POST /mfa/enroll                  — Begin MFA enrollment (generate secret + QR code)
   - POST /mfa/confirm                 — Confirm enrollment with TOTP code + receive backup codes
   - DELETE /mfa                       — Disable MFA (TOTP or backup code required)
   - GET  /mfa/status                  — Check MFA enrollment status

The JWKS endpoint MUST remain at domain root per RFC 5785 — external services
(e.g., wxcode engine) fetch this URL to verify JWTs issued by wxcode-adm.
"""

from typing import Union

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.audit.service import write_audit
from wxcode_adm.auth import service
from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.auth.jwks import build_jwks_response
from wxcode_adm.auth.models import User
from wxcode_adm.auth.oauth import oauth
from wxcode_adm.auth.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MessageResponse,
    MfaDisableRequest,
    MfaEnrollBeginResponse,
    MfaEnrollConfirmRequest,
    MfaEnrollConfirmResponse,
    MfaStatusResponse,
    MfaVerifyRequest,
    OAuthCallbackResponse,
    OAuthLinkConfirmRequest,
    OAuthLinkResponse,
    RefreshRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from wxcode_adm.common.exceptions import AppError
from wxcode_adm.common.rate_limit import limiter
from wxcode_adm.config import settings
from wxcode_adm.dependencies import get_redis, get_session

# ---------------------------------------------------------------------------
# Root-mounted router (/.well-known/jwks.json — no API prefix)
# ---------------------------------------------------------------------------

router = APIRouter(tags=["auth"])


@router.get("/.well-known/jwks.json")
@limiter.exempt
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
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup(
    request: Request,
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
    await write_audit(
        db,
        action="signup",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
        details={"email": body.email},
    )
    return SignupResponse(message="Check your email for a verification code")


@auth_api_router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    request: Request,
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
    await write_audit(
        db,
        action="verify_email",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )
    return VerifyEmailResponse(message="Email verified successfully")


@auth_api_router.post("/resend-verification", response_model=ResendVerificationResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def resend_verification(
    request: Request,
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
    await write_audit(
        db,
        action="resend_verification",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )
    return ResendVerificationResponse(message="Check your email for a new verification code")


@auth_api_router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> LoginResponse:
    """
    Authenticate a user and issue JWT access + refresh tokens, or initiate MFA.

    When MFA is enabled on the user's account:
    - Returns LoginResponse(mfa_required=True, mfa_token=...) without JWT tokens.
    - Client must complete login via POST /mfa/verify with mfa_token + TOTP code.
    - A wxcode_trusted_device cookie (if present) is checked; trusted devices
      skip the MFA prompt.

    When MFA is not enabled:
    - Returns LoginResponse with access_token and refresh_token.

    - Returns 401 if email not found, password incorrect, or account inactive.
    - Returns 403 if email has not been verified.
    - Single-session policy: previous refresh tokens for the user are revoked.
    """
    # Extract trusted device cookie (may be None — backward compatible)
    device_token = request.cookies.get("wxcode_trusted_device")

    result = await service.login(db, redis, body, device_token=device_token)

    # Lightweight user lookup to capture actor_id in audit log.
    # Uses indexed email column — only runs on successful authentication.
    user_result = await db.execute(select(User.id).where(User.email == body.email))
    user_row = user_result.scalar_one_or_none()

    if result.get("mfa_required"):
        # MFA pending — log intermediate action (no tokens issued yet)
        if user_row:
            await write_audit(
                db,
                actor_id=user_row,
                action="login_mfa_pending",
                resource_type="session",
                ip_address=request.client.host if request.client else None,
            )
        return LoginResponse(mfa_required=True, mfa_token=result["mfa_token"])

    # Tokens issued — log full login
    if user_row:
        await write_audit(
            db,
            actor_id=user_row,
            action="login",
            resource_type="session",
            ip_address=request.client.host if request.client else None,
        )
    return LoginResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
    )


@auth_api_router.post("/mfa/verify")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def mfa_verify(
    request: Request,
    body: MfaVerifyRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> JSONResponse:
    """
    Complete a two-stage MFA login by verifying a TOTP code or backup code.

    Accepts the mfa_token returned by POST /login when MFA is required, plus
    the user's current TOTP code (or an unused backup code). On success,
    issues JWT access + refresh tokens and optionally sets a trusted device
    cookie (HttpOnly, SameSite=Lax, Secure in production).

    - Returns 200 with access_token, refresh_token, token_type on success.
    - Returns 401 (INVALID_TOKEN) if mfa_token is expired or not found.
    - Returns 401 (MFA_INVALID_CODE) if TOTP code is wrong or backup code is
      invalid/already used.
    - Returns 401 (MFA_INVALID_CODE) if the same TOTP code is submitted twice
      within 60 seconds (replay prevention).
    - Rate limited: same limit as other auth endpoints (brute-force protection).
    """
    result = await service.mfa_verify(
        db, redis, body.mfa_token, body.code, body.trust_device
    )

    # Write audit entry on successful MFA verification
    await write_audit(
        db,
        action="mfa_verify_success",
        resource_type="session",
        ip_address=request.client.host if request.client else None,
    )

    # Build JSON response with tokens
    response_data = {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "token_type": "bearer",
    }
    response = JSONResponse(content=response_data)

    # Set trusted device cookie if requested and device_token was returned
    if body.trust_device and "device_token" in result:
        response.set_cookie(
            key="wxcode_trusted_device",
            value=result["device_token"],
            httponly=True,
            secure=settings.APP_ENV != "development",
            samesite="lax",
            max_age=settings.TRUSTED_DEVICE_TTL_DAYS * 86400,
        )

    return response


@auth_api_router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
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
    result = await service.refresh(db, redis, body)
    await write_audit(
        db,
        action="refresh_token",
        resource_type="session",
        ip_address=request.client.host if request.client else None,
    )
    return result


@auth_api_router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
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
    await write_audit(
        db,
        action="logout",
        resource_type="session",
        ip_address=request.client.host if request.client else None,
    )
    return MessageResponse(message="Logged out successfully")


@auth_api_router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ForgotPasswordResponse:
    """
    Initiate a password reset flow for the given email address.

    - Returns 200 always with the same message regardless of whether the email
      exists — this prevents user enumeration attacks.
    - An arq job is enqueued to send the reset link only when the user exists.
    """
    await service.forgot_password(db, redis, body)
    # No details — enumeration-safe (do not expose whether email was found)
    await write_audit(
        db,
        action="forgot_password",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )
    return ForgotPasswordResponse(
        message="If an account exists, a reset link has been sent"
    )


@auth_api_router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_session),
) -> ResetPasswordResponse:
    """
    Complete a password reset using a signed token from the reset email.

    - Returns 200 on success with a confirmation message.
    - Returns 401 if the token is invalid, malformed, or already used.
    - Returns 401 if the token has expired (24-hour window).
    - On success, ALL refresh tokens for the user are deleted (force re-login).
    """
    await service.reset_password(db, body)
    await write_audit(
        db,
        action="reset_password",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )
    return ResetPasswordResponse(message="Password has been reset successfully")


@auth_api_router.get("/me")
async def me(
    user: User = Depends(require_verified),
) -> dict:
    """
    Return the current authenticated and verified user's basic information.

    This endpoint is protected by the full dependency chain:
    get_current_user (JWT validation + blacklist check) → require_verified
    (email verification enforcement).

    - Returns 401 if no/invalid Bearer token is provided.
    - Returns 401 if the access token has been blacklisted (logged out).
    - Returns 403 if the user's email is not verified.
    - Returns 200 with id, email, email_verified on success.

    Note: this endpoint will be refined in Phase 7 (User Account) to include
    additional profile fields.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "email_verified": user.email_verified,
    }


# ---------------------------------------------------------------------------
# Phase 6: OAuth routes
# ---------------------------------------------------------------------------


_VALID_PROVIDERS = {"google", "github"}


@auth_api_router.get("/oauth/{provider}/login")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def oauth_login(
    request: Request,
    provider: str,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    """
    Redirect the user to the OAuth provider's authorization page.

    Validates the provider name, retrieves the authlib OAuth client, and
    returns a redirect response to the provider's consent/auth screen.
    SessionMiddleware is required — authlib stores the OAuth state and
    PKCE code_verifier in the session.

    - Returns 302 redirect to Google or GitHub on success.
    - Returns 400 if provider is not 'google' or 'github'.
    """
    if provider not in _VALID_PROVIDERS:
        raise AppError(
            error_code="OAUTH_UNKNOWN_PROVIDER",
            message=f"Unknown OAuth provider: {provider}. Must be 'google' or 'github'.",
            status_code=400,
        )
    client = oauth.create_client(provider)
    if client is None:
        raise AppError(
            error_code="OAUTH_PROVIDER_NOT_CONFIGURED",
            message=f"OAuth provider '{provider}' is not configured.",
            status_code=400,
        )
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    return await client.authorize_redirect(request, redirect_uri)


@auth_api_router.get(
    "/oauth/{provider}/callback",
    response_model=Union[OAuthCallbackResponse, OAuthLinkResponse],
    name="oauth_callback",
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def oauth_callback(
    request: Request,
    provider: str,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Union[OAuthCallbackResponse, OAuthLinkResponse]:
    """
    Handle the OAuth provider callback after user authorization.

    Exchanges the authorization code for an access token, extracts user
    information, and resolves the account (new user / link required / login).

    - Returns OAuthCallbackResponse with JWT tokens on success (new or existing user).
    - Returns OAuthLinkResponse when the email matches an existing password account.
    - Returns 400 if provider is unknown or email is unavailable.
    - Returns 409 if user already has a different OAuth provider linked.
    """
    if provider not in _VALID_PROVIDERS:
        raise AppError(
            error_code="OAUTH_UNKNOWN_PROVIDER",
            message=f"Unknown OAuth provider: {provider}. Must be 'google' or 'github'.",
            status_code=400,
        )
    client = oauth.create_client(provider)
    if client is None:
        raise AppError(
            error_code="OAUTH_PROVIDER_NOT_CONFIGURED",
            message=f"OAuth provider '{provider}' is not configured.",
            status_code=400,
        )

    token = await client.authorize_access_token(request)

    if provider == "google":
        email, provider_user_id = await service.get_google_userinfo(token)
    else:
        email, provider_user_id = await service.get_github_email(client, token)

    result = await service.resolve_oauth_account(
        db, redis, provider, email, provider_user_id
    )

    await write_audit(
        db,
        action="oauth_login",
        resource_type="session",
        ip_address=request.client.host if request.client else None,
        details={"provider": provider, "email": email},
    )

    return result


@auth_api_router.post(
    "/oauth/link/confirm",
    response_model=OAuthCallbackResponse,
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def oauth_link_confirm(
    request: Request,
    body: OAuthLinkConfirmRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> OAuthCallbackResponse:
    """
    Confirm an OAuth account link by verifying the user's password.

    After receiving an OAuthLinkResponse, the frontend prompts the user to
    enter their password. This endpoint verifies the password, links the
    OAuth provider to the existing account, and issues new JWT tokens.

    - Returns OAuthCallbackResponse with JWT tokens on success.
    - Returns 401 if link_token is expired or invalid.
    - Returns 401 if password is incorrect.
    """
    token_response = await service.confirm_oauth_link(
        db, redis, body.link_token, body.password
    )

    await write_audit(
        db,
        action="oauth_link",
        resource_type="session",
        ip_address=request.client.host if request.client else None,
    )

    return OAuthCallbackResponse(
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        is_new_user=False,
        needs_onboarding=False,
    )


# ---------------------------------------------------------------------------
# Phase 6: MFA enrollment routes
# ---------------------------------------------------------------------------


@auth_api_router.post("/mfa/enroll", response_model=MfaEnrollBeginResponse)
async def mfa_enroll(
    request: Request,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    user: User = Depends(require_verified),
) -> MfaEnrollBeginResponse:
    """
    Begin MFA enrollment by generating a TOTP secret and QR code.

    The returned QR code should be scanned with an authenticator app (e.g.,
    Google Authenticator, Authy). The provisioning_uri can be used for manual
    entry. After scanning, call POST /mfa/confirm with a valid TOTP code.

    - Returns 200 with secret, qr_code (base64 PNG), provisioning_uri.
    - Returns 400 if MFA is already enabled.
    - Returns 401 if not authenticated.
    - Returns 403 if email is not verified.
    """
    result = await service.mfa_begin_enrollment(db, user)
    await write_audit(
        db,
        actor_id=user.id,
        action="mfa_enroll_begin",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )
    return MfaEnrollBeginResponse(**result)


@auth_api_router.post("/mfa/confirm", response_model=MfaEnrollConfirmResponse)
async def mfa_confirm(
    request: Request,
    body: MfaEnrollConfirmRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    user: User = Depends(require_verified),
) -> MfaEnrollConfirmResponse:
    """
    Confirm MFA enrollment by providing a valid TOTP code from the authenticator.

    On success, 10 backup codes are returned. These codes are shown ONCE and
    must be saved by the user — they are never stored in plain text.

    - Returns 200 with backup_codes list on success.
    - Returns 400 if mfa_begin_enrollment was not called first (no mfa_secret).
    - Returns 400 if MFA is already enabled.
    - Returns 401 if the TOTP code is invalid.
    - Returns 401 if not authenticated.
    - Returns 403 if email is not verified.
    """
    backup_codes = await service.mfa_confirm_enrollment(db, user, body.code)
    await write_audit(
        db,
        actor_id=user.id,
        action="mfa_enroll_confirm",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )
    return MfaEnrollConfirmResponse(backup_codes=backup_codes)


@auth_api_router.delete("/mfa", response_model=MessageResponse)
async def mfa_disable(
    request: Request,
    body: MfaDisableRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    user: User = Depends(require_verified),
) -> MessageResponse:
    """
    Disable MFA by providing a valid TOTP code or an unused backup code.

    Per locked decision: if the tenant enforces MFA, the user will be
    re-prompted to enroll on their next login.

    - Returns 200 on success.
    - Returns 400 if MFA is not enabled.
    - Returns 401 if the code is invalid (TOTP or backup).
    - Returns 401 if not authenticated.
    - Returns 403 if email is not verified.
    """
    await service.mfa_disable(db, redis, user, body.code)
    await write_audit(
        db,
        actor_id=user.id,
        action="mfa_disable",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )
    return MessageResponse(message="MFA has been disabled")


@auth_api_router.get("/mfa/status", response_model=MfaStatusResponse)
async def mfa_status(
    request: Request,
    user: User = Depends(require_verified),
) -> MfaStatusResponse:
    """
    Check the current user's MFA enrollment status.

    - Returns 200 with mfa_enabled boolean.
    - Returns 401 if not authenticated.
    - Returns 403 if email is not verified.
    """
    return MfaStatusResponse(mfa_enabled=user.mfa_enabled)
