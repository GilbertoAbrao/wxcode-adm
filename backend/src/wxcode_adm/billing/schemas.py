"""
Pydantic v2 request/response schemas for wxcode-adm billing domain.

Stripe IDs are intentionally excluded from PlanResponse — they are internal
implementation details and should not be exposed to API consumers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CreatePlanRequest(BaseModel):
    """Request body for POST /admin/billing/plans."""

    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    monthly_fee_cents: int = Field(ge=0)
    token_quota_5h: int = Field(ge=0)
    token_quota_weekly: int = Field(ge=0)
    overage_rate_cents_per_token: int = Field(ge=0, default=0)
    member_cap: int = Field(default=1)  # -1 = unlimited
    max_projects: int = Field(ge=1, default=5)
    max_output_projects: int = Field(ge=1, default=20)
    max_storage_gb: int = Field(ge=1, default=10)


class UpdatePlanRequest(BaseModel):
    """Request body for PATCH /admin/billing/plans/{plan_id}."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    monthly_fee_cents: Optional[int] = Field(default=None, ge=0)
    token_quota_5h: Optional[int] = Field(default=None, ge=0)
    token_quota_weekly: Optional[int] = Field(default=None, ge=0)
    overage_rate_cents_per_token: Optional[int] = Field(default=None, ge=0)
    member_cap: Optional[int] = None
    max_projects: Optional[int] = Field(default=None, ge=1)
    max_output_projects: Optional[int] = Field(default=None, ge=1)
    max_storage_gb: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None


class PlanResponse(BaseModel):
    """Response schema for plan objects. Stripe IDs are excluded (internal)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    monthly_fee_cents: int
    token_quota_5h: int
    token_quota_weekly: int
    overage_rate_cents_per_token: int
    member_cap: int
    max_projects: int
    max_output_projects: int
    max_storage_gb: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Checkout schemas
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    """Request body for POST /billing/checkout."""

    plan_id: uuid.UUID


class CheckoutResponse(BaseModel):
    """Response for POST /billing/checkout — Stripe Checkout session details."""

    checkout_url: str
    session_id: str


# ---------------------------------------------------------------------------
# Subscription response (used in Plan 04-04 quota endpoints)
# ---------------------------------------------------------------------------


class SubscriptionResponse(BaseModel):
    """Response schema for TenantSubscription objects."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    plan: PlanResponse
    status: str
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    tokens_used_this_period: int
    created_at: datetime
    updated_at: datetime
