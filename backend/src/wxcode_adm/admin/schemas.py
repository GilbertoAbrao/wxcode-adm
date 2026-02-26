"""
Pydantic schemas for the wxcode-adm admin module.

Covers:
- AdminLoginRequest / AdminTokenResponse: admin auth endpoints (Plan 01)
- AdminActionRequest: shared required-reason body for destructive actions
- TenantListItem / TenantListResponse / TenantDetailResponse: tenant management (Plan 02)
- UserListItem / UserListResponse / UserDetailResponse: user management (Plan 03)
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
# User management schemas (Plan 03 will use these)
# ---------------------------------------------------------------------------


class UserListResponse(BaseModel):
    """Placeholder: list of users for admin user management (Plan 03)."""

    items: list[dict] = []
    total: int = 0


class UserDetailResponse(BaseModel):
    """Placeholder: detailed user view for admin (Plan 03)."""

    id: str = ""
    email: str = ""
    is_superuser: bool = False
    is_active: bool = True


# ---------------------------------------------------------------------------
# MRR dashboard placeholder schema (Plan 04 will extend this)
# ---------------------------------------------------------------------------


class MRRDashboardResponse(BaseModel):
    """Placeholder: MRR metrics dashboard for admin (Plan 04)."""

    mrr_cents: int = 0
    active_subscriptions: int = 0
    churned_this_month: int = 0
