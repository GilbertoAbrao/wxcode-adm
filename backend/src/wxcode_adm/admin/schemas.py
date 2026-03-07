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

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


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

    # Phase 20: Claude/wxcode integration fields
    status: str
    database_name: str | None
    default_target_stack: str
    neo4j_enabled: bool
    claude_default_model: str
    claude_max_concurrent_sessions: int
    claude_monthly_token_budget: int | None
    has_claude_token: bool  # True if claude_oauth_token is not None — token itself is never exposed

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
# Phase 22: Claude Provisioning schemas
# ---------------------------------------------------------------------------


class ClaudeTokenRequest(BaseModel):
    """Request body for PUT /admin/tenants/{id}/claude-token."""

    token: str = Field(min_length=1, max_length=4096)  # plaintext OAuth token
    reason: str = Field(min_length=1, max_length=500)  # audit trail reason


class ClaudeConfigUpdateRequest(BaseModel):
    """
    Request body for PATCH /admin/tenants/{id}/claude-config.

    All fields are optional so partial updates work. At least one must
    be provided — the model validator rejects all-None payloads.
    """

    claude_default_model: str | None = Field(default=None, max_length=50)
    claude_max_concurrent_sessions: int | None = Field(default=None, ge=1, le=100)
    # 0 means "set to unlimited" (stored as NULL in DB); None means "no change"
    claude_monthly_token_budget: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def at_least_one_field_set(self) -> "ClaudeConfigUpdateRequest":
        """Reject payloads where every field is None — nothing would be updated."""
        if (
            self.claude_default_model is None
            and self.claude_max_concurrent_sessions is None
            and self.claude_monthly_token_budget is None
        ):
            raise ValueError(
                "At least one of claude_default_model, claude_max_concurrent_sessions, "
                "or claude_monthly_token_budget must be provided"
            )
        return self


class ActivateTenantRequest(BaseModel):
    """Request body for POST /admin/tenants/{id}/activate."""

    reason: str = Field(min_length=1, max_length=500)  # audit trail reason


# ---------------------------------------------------------------------------
# MRR dashboard schemas (Plan 04)
# ---------------------------------------------------------------------------


class PlanDistributionItem(BaseModel):
    """One entry in the plan distribution breakdown of the MRR dashboard."""

    plan_slug: str
    plan_name: str
    count: int


class MRRTrendPoint(BaseModel):
    """A single day's MRR snapshot in the 30-day trend series."""

    date: str  # ISO date string, e.g., "2026-02-20"
    mrr_cents: int
    active_count: int


class MRRDashboardResponse(BaseModel):
    """
    MRR metrics dashboard for admin (Plan 04).

    Returned by GET /admin/dashboard/mrr. All data is computed from the local
    DB (no Stripe API calls). Trend data covers the last 30 days.
    """

    active_subscription_count: int
    mrr_cents: int
    plan_distribution: list[PlanDistributionItem]
    canceled_count_30d: int
    churn_rate: float  # 0.0-1.0, rounded to 4 decimal places
    trend: list[MRRTrendPoint]
    computed_at: datetime
