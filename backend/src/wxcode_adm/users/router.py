"""
Users router for wxcode-adm.

Provides user profile management endpoints:
- GET  /users/me                  — Return current user's profile
- PATCH /users/me                 — Update display_name and/or email
- POST /users/me/avatar           — Upload and replace avatar image
- POST /users/me/change-password  — Change password with current password verification

All endpoints require email verification (require_verified dependency).
Password change endpoint is rate-limited to prevent brute-force attacks.

Decision (from 05-01): All endpoint functions accept request: Request as first
parameter — slowapi uses it for IP extraction; missing it silently skips limit.
Decision (from 05-01): Route decorator order — @router.post() FIRST, @limiter.limit() SECOND.
"""

from fastapi import APIRouter, Depends, Request, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.audit.service import write_audit
from wxcode_adm.auth.dependencies import get_current_jti, require_verified
from wxcode_adm.auth.models import User
from wxcode_adm.common.exceptions import AppError
from wxcode_adm.common.rate_limit import limiter
from wxcode_adm.config import settings
from wxcode_adm.dependencies import get_redis, get_session
from wxcode_adm.users import service
from wxcode_adm.users.schemas import (
    AvatarUploadResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    UpdateProfileRequest,
    UpdateProfileResponse,
    UserProfileResponse,
)

users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.get("/me", response_model=UserProfileResponse)
async def get_me(
    request: Request,
    user: User = Depends(require_verified),
) -> UserProfileResponse:
    """
    Return the current authenticated and verified user's full profile.

    Returns display_name, avatar_url, mfa_enabled in addition to the
    basic id/email/email_verified fields.

    - Returns 401 if no/invalid Bearer token.
    - Returns 403 if email is not verified.
    """
    profile_data = service.get_profile(user)
    return UserProfileResponse(**profile_data)


@users_router.patch("/me", response_model=UpdateProfileResponse)
async def patch_me(
    request: Request,
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    user: User = Depends(require_verified),
) -> UpdateProfileResponse:
    """
    Update the current user's display_name and/or email.

    - If both display_name and email are None in the request body,
      returns 400 "No fields to update".
    - Email change resets email_verified to False and sends a new OTP.
    - Returns 409 if the new email is already taken.
    - Writes audit entry: action="profile_update".

    - Returns 401 if not authenticated.
    - Returns 403 if email is not verified.
    """
    # Validate at least one field is provided
    if body.display_name is None and body.email is None:
        raise AppError(
            error_code="NO_FIELDS_TO_UPDATE",
            message="No fields to update",
            status_code=400,
        )

    updated_user = await service.update_profile(db, redis, user, body)

    await write_audit(
        db,
        actor_id=user.id,
        action="profile_update",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )

    profile_data = service.get_profile(updated_user)
    return UpdateProfileResponse(
        message="Profile updated successfully",
        profile=UserProfileResponse(**profile_data),
    )


@users_router.post("/me/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    request: Request,
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_verified),
) -> AvatarUploadResponse:
    """
    Upload a new avatar image for the current user.

    Accepts JPEG or PNG images up to 2MB. The image is resized to 256x256
    pixels and saved as JPEG. The relative path is stored on the user profile.

    - Returns 400 if content type is not image/jpeg or image/png.
    - Returns 400 if the file exceeds 2MB.
    - Writes audit entry: action="avatar_upload".

    - Returns 401 if not authenticated.
    - Returns 403 if email is not verified.
    """
    avatar_url = await service.upload_avatar(user, file, db)

    await write_audit(
        db,
        actor_id=user.id,
        action="avatar_upload",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )

    return AvatarUploadResponse(
        avatar_url=avatar_url,
        message="Avatar uploaded successfully",
    )


@users_router.post("/me/change-password", response_model=ChangePasswordResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    user: User = Depends(require_verified),
    jti: str = Depends(get_current_jti),
) -> ChangePasswordResponse:
    """
    Change the current user's password with current password verification.

    Verifies the current password, hashes the new password, and invalidates
    all OTHER active sessions. The current session remains valid so the user
    does not need to log in again immediately.

    Rate-limited: same limit as auth endpoints (brute-force protection).

    - Returns 400 if account uses OAuth only (no password to verify).
    - Returns 401 if current_password is incorrect.
    - Returns 429 if rate limit exceeded.
    - Writes audit entry: action="password_change".

    - Returns 401 if not authenticated.
    - Returns 403 if email is not verified.
    """
    await service.change_password(
        db, redis, user, body.current_password, body.new_password, current_jti=jti
    )

    await write_audit(
        db,
        actor_id=user.id,
        action="password_change",
        resource_type="user",
        ip_address=request.client.host if request.client else None,
    )

    return ChangePasswordResponse(message="Password changed successfully")
