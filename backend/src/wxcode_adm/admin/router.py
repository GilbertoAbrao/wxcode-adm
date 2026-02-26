"""
FastAPI router for the wxcode-adm admin module.

Provides super-admin authentication endpoints:
- POST /admin/login    — authenticate super-admin, issue admin-audience JWT
- POST /admin/refresh  — rotate admin refresh token
- POST /admin/logout   — invalidate admin session

Tenant management endpoints (Plan 02):
- GET  /admin/tenants                       — list tenants (paginated, filterable)
- GET  /admin/tenants/{tenant_id}           — get tenant detail
- POST /admin/tenants/{tenant_id}/suspend   — suspend tenant (invalidates sessions)
- POST /admin/tenants/{tenant_id}/reactivate — reactivate suspended tenant
- DELETE /admin/tenants/{tenant_id}          — soft-delete tenant

IP allowlist enforcement:
    If ADMIN_ALLOWED_IPS is set (non-empty), only requests from listed IPs
    are allowed to reach the login endpoint. Empty string = no restriction
    (dev-friendly default per Phase 8 plan decision).

Rate limiting:
    Login endpoint is limited to 10/minute (stricter than global 60/min,
    but less aggressive than regular auth 5/min since admin accounts are
    not publicly exposed and the IP allowlist provides additional protection).

CRITICAL: @router.post() must come BEFORE @limiter.limit() per Phase 5
decision [05-01] — reverse order silently breaks rate limiting.

CRITICAL: request: Request must be the first parameter on rate-limited
endpoints — slowapi uses it for IP extraction.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.admin import service as admin_service
from wxcode_adm.admin.dependencies import require_admin
from wxcode_adm.admin.jwt import decode_admin_access_token
from wxcode_adm.admin.schemas import (
    AdminActionRequest,
    AdminLoginRequest,
    AdminTokenResponse,
    TenantDetailResponse,
    TenantListResponse,
)
from wxcode_adm.auth.models import User
from wxcode_adm.common.exceptions import ForbiddenError
from wxcode_adm.common.rate_limit import limiter
from wxcode_adm.config import settings
from wxcode_adm.dependencies import get_redis, get_session

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Request/response bodies for refresh and logout
# ---------------------------------------------------------------------------


class RefreshBody(BaseModel):
    refresh_token: str


class LogoutBody(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Authentication endpoints (Plan 01)
# ---------------------------------------------------------------------------


@admin_router.post("/login", response_model=AdminTokenResponse)
@limiter.limit("10/minute")
async def admin_login(
    request: Request,
    body: AdminLoginRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> AdminTokenResponse:
    """
    Authenticate a super-admin user and issue admin-audience JWT tokens.

    IP allowlist: if ADMIN_ALLOWED_IPS is set, the client IP must be in
    the comma-separated list or the request is rejected with 403.

    Rate limited: 10 requests per minute per IP (brute-force protection).
    """
    # IP allowlist enforcement (skipped when ADMIN_ALLOWED_IPS is empty)
    if settings.ADMIN_ALLOWED_IPS:
        allowed = [ip.strip() for ip in settings.ADMIN_ALLOWED_IPS.split(",") if ip.strip()]
        client_ip = request.client.host if request.client else None
        if client_ip not in allowed:
            raise ForbiddenError(
                error_code="IP_NOT_ALLOWED",
                message="Access denied from this IP address",
            )

    client_ip = request.client.host if request.client else None
    tokens = await admin_service.admin_login(
        db=db,
        redis=redis,
        email=body.email,
        password=body.password,
        client_ip=client_ip,
    )
    return AdminTokenResponse(**tokens)


@admin_router.post("/refresh", response_model=AdminTokenResponse)
async def admin_refresh(
    body: RefreshBody,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> AdminTokenResponse:
    """
    Rotate an admin refresh token and issue a new admin-audience JWT pair.
    """
    tokens = await admin_service.admin_refresh(
        db=db,
        redis=redis,
        refresh_token_str=body.refresh_token,
    )
    return AdminTokenResponse(**tokens)


@admin_router.post("/logout")
async def admin_logout(
    body: LogoutBody,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """
    Invalidate an admin session by revoking the refresh token and
    blacklisting the access token JTI in Redis.
    """
    # Extract the JTI from the current admin access token
    # The token is in the Authorization header; re-extract for JTI
    auth_header = request.headers.get("authorization", "") if request else ""
    access_token = auth_header.removeprefix("Bearer ").removeprefix("bearer ")

    # Decode to get JTI (already validated by require_admin, so decode is safe)
    payload = decode_admin_access_token(access_token)
    jti = payload.get("jti", "")

    await admin_service.admin_logout(
        db=db,
        redis=redis,
        refresh_token_str=body.refresh_token,
        access_token_jti=jti,
    )
    return {"message": "Logged out"}


# ---------------------------------------------------------------------------
# Tenant management endpoints (Plan 02)
# ---------------------------------------------------------------------------


@admin_router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    plan_slug: str | None = Query(default=None),
    status: str | None = Query(default=None, description="active | suspended | deleted"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> TenantListResponse:
    """
    List all tenants with pagination and optional filtering.

    Filters:
    - plan_slug: filter by billing plan slug
    - status: 'active', 'suspended', 'deleted', or None for all
    """
    items, total = await admin_service.list_tenants(
        db=db,
        limit=limit,
        offset=offset,
        plan_slug=plan_slug,
        status=status,
    )
    return TenantListResponse(items=items, total=total)


@admin_router.get("/tenants/{tenant_id}", response_model=TenantDetailResponse)
async def get_tenant_detail(
    request: Request,
    tenant_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> TenantDetailResponse:
    """
    Get full detail for a specific tenant including subscription and member count.
    """
    detail = await admin_service.get_tenant_detail(db=db, tenant_id=tenant_id)
    return TenantDetailResponse(**detail)


@admin_router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(
    request: Request,
    tenant_id: uuid.UUID,
    body: AdminActionRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """
    Suspend a tenant. All member sessions are invalidated immediately.

    Requires a reason string for audit trail.
    """
    await admin_service.suspend_tenant(
        db=db,
        redis=redis,
        tenant_id=tenant_id,
        reason=body.reason,
        actor_id=admin.id,
    )
    return {"message": "Tenant suspended", "tenant_id": str(tenant_id)}


@admin_router.post("/tenants/{tenant_id}/reactivate")
async def reactivate_tenant(
    request: Request,
    tenant_id: uuid.UUID,
    body: AdminActionRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    Reactivate a previously suspended tenant.

    Requires a reason string for audit trail.
    """
    await admin_service.reactivate_tenant(
        db=db,
        tenant_id=tenant_id,
        reason=body.reason,
        actor_id=admin.id,
    )
    return {"message": "Tenant reactivated", "tenant_id": str(tenant_id)}


@admin_router.delete("/tenants/{tenant_id}")
async def soft_delete_tenant(
    request: Request,
    tenant_id: uuid.UUID,
    body: AdminActionRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    Soft-delete a tenant. Data is retained indefinitely (is_deleted=True).

    Requires a reason string for audit trail.
    """
    await admin_service.soft_delete_tenant(
        db=db,
        tenant_id=tenant_id,
        reason=body.reason,
        actor_id=admin.id,
    )
    return {"message": "Tenant soft-deleted", "tenant_id": str(tenant_id)}
