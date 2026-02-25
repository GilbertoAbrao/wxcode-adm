"""
Pydantic v2 request/response schemas for user profile endpoints.

These schemas are used by the users router for request validation and
response serialization. They cover:
- GET /users/me — UserProfileResponse
- PATCH /users/me — UpdateProfileRequest / UpdateProfileResponse
- POST /users/me/avatar — AvatarUploadResponse
- POST /users/me/change-password — ChangePasswordRequest / ChangePasswordResponse
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserProfileResponse(BaseModel):
    """GET /users/me response."""

    id: str
    email: str
    email_verified: bool
    display_name: str | None
    avatar_url: str | None
    mfa_enabled: bool

    model_config = ConfigDict(from_attributes=True)


class UpdateProfileRequest(BaseModel):
    """PATCH /users/me request — all fields optional (partial update)."""

    display_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None


class UpdateProfileResponse(BaseModel):
    """PATCH /users/me response."""

    message: str
    profile: UserProfileResponse


class AvatarUploadResponse(BaseModel):
    """POST /users/me/avatar response."""

    avatar_url: str
    message: str


class ChangePasswordRequest(BaseModel):
    """POST /users/me/change-password request."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordResponse(BaseModel):
    """POST /users/me/change-password response."""

    message: str
