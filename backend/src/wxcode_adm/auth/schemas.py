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
