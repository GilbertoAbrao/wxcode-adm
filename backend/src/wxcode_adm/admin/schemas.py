"""
Pydantic schemas for the wxcode-adm admin module.

Covers:
- AdminLoginRequest / AdminTokenResponse: admin auth endpoints (Plan 01)
- Placeholder schemas for Plans 02-04: tenant management, user management,
  MRR dashboard, and generic admin action request. These are defined now so
  that router imports do not break as Plans 02-04 extend this file.

All models use Pydantic v2 semantics.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


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

    reason: str


# ---------------------------------------------------------------------------
# Tenant management placeholder schemas (Plans 02-03 will extend these)
# ---------------------------------------------------------------------------


class TenantListResponse(BaseModel):
    """Placeholder: list of tenants for admin tenant management (Plan 02)."""

    items: list[dict] = []
    total: int = 0


class TenantDetailResponse(BaseModel):
    """Placeholder: detailed tenant view for admin (Plan 02)."""

    id: str = ""
    slug: str = ""
    name: str = ""
    is_suspended: bool = False


# ---------------------------------------------------------------------------
# User management placeholder schemas (Plans 02-03 will extend these)
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
