"""
Pydantic schemas for the wxcode-adm admin module.

Covers:
- AdminLoginRequest / AdminTokenResponse: admin auth endpoints (Plan 01)
- AdminActionRequest: shared required-reason body for destructive actions
- TenantListItem / TenantListResponse / TenantDetailResponse: tenant management (Plan 02)
- UserMembershipItem / UserSessionItem / UserListItem / UserListResponse
  / UserDetailResponse / UserBlockRequest / UserUnblockRequest
  / UserForceResetRequest: user management endpoints (Plan 03)
- MRRDashboardResponse: MRR metrics dashboard (Plan 04)

All models use Pydantic v2 semantics.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Admin auth schemas (Plan 01)
# ---------------------------------------------------------------------------


class AdminLoginRequest(BaseModel):
    """Request body for POST /api/v1/admin/login."""

    email: EmailStr
    password: str = ""

    model_config = {"str_min_length": 0}


class AdminTokenResponse(BaseModel):
    """Response body for admin login and refresh endpoints."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Admin action schema (shared across Plans 02-04)
# ---------------------------------------------------------------------------


class AdminActionRequest(BaseModel):
    """Generic admin action body — reason is required for audit trail."""

    reason: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Tenant management schemas (Plan 02)
# ---------------------------------------------------------------------------


class TenantListItem(BaseModel):
    """One tenant row in the admin tenant list."""

    id: uuid.UUID
    name: str
    slug: str
    is_suspended: bool
    is_deleted: bool
    plan_name: str | None
    plan_slug: str | None
    member_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantListResponse(BaseModel):
    """Paginated list of tenants for the admin tenant management view."""

    items: list[TenantListItem]
    total: int


class TenantDetailResponse(BaseModel):
    """Detailed tenant information for the admin view."""

    id: uuid.UUID
    name: str
    slug: str
    is_suspended: bool
    is_deleted: bool
    mfa_enforced: bool
    wxcode_url: str | None
    plan_name: str | None
    plan_slug: str | None
    subscription_status: str | None
    member_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# User management schemas (Plan 03)
# ---------------------------------------------------------------------------


class UserMembershipItem(BaseModel):
    """
    A single tenant membership for a user, returned in UserDetailResponse.

    Includes tenant identity, the user's role, billing access flag, and
    whether the user is blocked in this specific tenant.
    """

    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    role: str
    billing_access: bool
    is_blocked: bool


class UserSessionItem(BaseModel):
    """
    A single active session for a user, returned in UserDetailResponse.

    Fields come from UserSession model (Phase 7). last_active_at may be
    None if not yet synced from Redis.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_type: str | None
    browser_name: str | None
    ip_address: str | None
    city: str | None
    last_active_at: datetime | None


class UserListItem(BaseModel):
    """
    Summary representation of a user, returned in paginated UserListResponse.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    email_verified: bool
    is_active: bool
    mfa_enabled: bool
    created_at: datetime


class UserListResponse(BaseModel):
    """Paginated list of users for admin user search."""

    items: list[UserListItem]
    total: int


class UserDetailResponse(BaseModel):
    """
    Full profile of a user including memberships and sessions.

    Returned by GET /admin/users/{id}.
    """

    id: uuid.UUID
    email: str
    display_name: str | None
    avatar_url: str | None
    email_verified: bool
    is_active: bool
    is_superuser: bool
    mfa_enabled: bool
    created_at: datetime
    updated_at: datetime
    memberships: list[UserMembershipItem]
    sessions: list[UserSessionItem]


class UserBlockRequest(BaseModel):
    """
    Request body for POST /admin/users/{id}/block.

    Per-tenant scope: only the user's membership in the given tenant is
    blocked; their access to other tenants is not affected.
    """

    tenant_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=500)


class UserUnblockRequest(BaseModel):
    """
    Request body for POST /admin/users/{id}/unblock.

    Restores access to the specific tenant only.
    """

    tenant_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=500)


class UserForceResetRequest(BaseModel):
    """
    Request body for POST /admin/users/{id}/force-reset.

    Sets password_reset_required flag on the user, invalidates all active
    sessions, and triggers a password reset email.
    """

    reason: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# MRR dashboard placeholder schema (Plan 04 will extend this)
# ---------------------------------------------------------------------------


class MRRDashboardResponse(BaseModel):
    """Placeholder: MRR metrics dashboard for admin (Plan 04)."""

    mrr_cents: int = 0
    active_subscriptions: int = 0
    churned_this_month: int = 0
