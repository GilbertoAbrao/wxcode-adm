"""
Pydantic v2 request/response schemas for auth endpoints.

These schemas are used by auth router endpoints for request validation
and response serialization. They are intentionally thin — no business
logic lives here, only data shape and validation constraints.
"""

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    """Request body for POST /api/v1/auth/signup."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class SignupResponse(BaseModel):
    """Response body for POST /api/v1/auth/signup."""

    message: str


class VerifyEmailRequest(BaseModel):
    """Request body for POST /api/v1/auth/verify-email."""

    email: str
    code: str = Field(min_length=6, max_length=6)


class VerifyEmailResponse(BaseModel):
    """Response body for POST /api/v1/auth/verify-email."""

    message: str


class ResendVerificationRequest(BaseModel):
    """Request body for POST /api/v1/auth/resend-verification."""

    email: str


class ResendVerificationResponse(BaseModel):
    """Response body for POST /api/v1/auth/resend-verification."""

    message: str


class MessageResponse(BaseModel):
    """Generic reusable message response."""

    message: str


class LoginRequest(BaseModel):
    """Request body for POST /api/v1/auth/login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response body for POST /api/v1/auth/login and POST /api/v1/auth/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Request body for POST /api/v1/auth/refresh."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Request body for POST /api/v1/auth/logout."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Request body for POST /api/v1/auth/forgot-password."""

    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Response body for POST /api/v1/auth/forgot-password.

    Always returns the same message regardless of whether the email exists
    to prevent user enumeration attacks.
    """

    message: str


class ResetPasswordRequest(BaseModel):
    """Request body for POST /api/v1/auth/reset-password."""

    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    """Response body for POST /api/v1/auth/reset-password."""

    message: str


# ---------------------------------------------------------------------------
# Phase 6: OAuth and MFA schemas
# ---------------------------------------------------------------------------


class OAuthCallbackResponse(BaseModel):
    """
    Response returned after a successful OAuth login or account link confirm.

    is_new_user: True if this is the first time this user has signed in.
    needs_onboarding: True if the user has no tenant memberships and was not
        invited — they should be directed to the workspace creation flow.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_new_user: bool
    needs_onboarding: bool


class OAuthLinkResponse(BaseModel):
    """
    Response returned when an OAuth email matches an existing password account.

    Per locked decision: the frontend must prompt the user to enter their
    password to confirm ownership and link the provider.

    link_token: short-lived Redis token (TTL = MFA_PENDING_TTL_SECONDS) that
        encodes {user_id, provider, provider_user_id} for the link confirm step.
    """

    link_required: bool = True
    link_token: str
    email: str
    provider: str


class OAuthLinkConfirmRequest(BaseModel):
    """Request body for POST /api/v1/auth/oauth/link/confirm."""

    link_token: str
    password: str


class MfaEnrollBeginResponse(BaseModel):
    """
    Response for GET /api/v1/auth/mfa/enroll — begins TOTP enrollment.

    secret: base32 TOTP secret to store in the authenticator app.
    qr_code: base64-encoded PNG of the QR code for scanning.
    provisioning_uri: otpauth:// URI for manual entry in authenticator apps.
    """

    secret: str
    qr_code: str
    provisioning_uri: str


class MfaEnrollConfirmRequest(BaseModel):
    """Request body for POST /api/v1/auth/mfa/enroll/confirm."""

    code: str = Field(min_length=6, max_length=6)


class MfaEnrollConfirmResponse(BaseModel):
    """
    Response for POST /api/v1/auth/mfa/enroll/confirm — completes enrollment.

    backup_codes: plain-text codes shown ONCE at enrollment.
        The user must save these — they are not stored in plain text.
    """

    backup_codes: list[str]


class MfaVerifyRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/mfa/verify — second-factor challenge.

    mfa_token: the pending token issued by login() when MFA is required.
    code: 6-digit TOTP code or up to 10-char backup code.
    trust_device: if True, a TrustedDevice token is issued so MFA is
        skipped on this device for TRUSTED_DEVICE_TTL_DAYS days.
    """

    mfa_token: str
    # Allow 6 (TOTP) to 11 (backup code formatted as "XXXXX-XXXXX") characters.
    # Service strips dashes before hash comparison.
    code: str = Field(min_length=6, max_length=11)
    trust_device: bool = False


class MfaStatusResponse(BaseModel):
    """Response for GET /api/v1/auth/mfa/status."""

    mfa_enabled: bool


class MfaDisableRequest(BaseModel):
    """Request body for POST /api/v1/auth/mfa/disable."""

    # Allow 6 (TOTP) to 11 (backup code formatted as "XXXXX-XXXXX") characters.
    # Service strips dashes before hash comparison.
    code: str = Field(min_length=6, max_length=11)


class LoginResponse(BaseModel):
    """
    Response body for POST /api/v1/auth/login — supports two-stage MFA flow.

    When MFA is NOT required:
        access_token and refresh_token are populated; mfa_required=False.

    When MFA IS required (user has mfa_enabled=True):
        mfa_required=True; mfa_token is a short-lived Redis pending token;
        access_token and refresh_token are None — issued after MFA verify.

    When the user is in a tenant that enforces MFA but has not enrolled:
        mfa_required=True; mfa_setup_required=True; mfa_token is set.
        The frontend should redirect to MFA enrollment (/auth/mfa/enroll).
        After enrollment the user must log in again to complete authentication.

    Phase 7: wxcode_redirect_url and wxcode_code are set when the user's tenant
        has a wxcode_url configured. The frontend uses these to redirect:
        window.location.href = `${wxcode_redirect_url}?code=${wxcode_code}`

    Note: TokenResponse remains for the /refresh endpoint (always returns tokens).
    """

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_token: str | None = None
    mfa_setup_required: bool = False
    # Phase 7: wxcode redirect — set when tenant has wxcode_url configured
    wxcode_redirect_url: str | None = None
    wxcode_code: str | None = None


# ---------------------------------------------------------------------------
# Phase 7 Plan 03: wxcode exchange schemas
# ---------------------------------------------------------------------------


class WxcodeExchangeRequest(BaseModel):
    """Request body for POST /api/v1/auth/wxcode/exchange.

    Called server-to-server by the wxcode backend to exchange a one-time
    authorization code for JWT access and refresh tokens.
    """

    code: str


class WxcodeExchangeResponse(BaseModel):
    """Response body for POST /api/v1/auth/wxcode/exchange."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
