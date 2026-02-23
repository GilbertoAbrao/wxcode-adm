"""
Pydantic v2 request/response schemas for wxcode-adm billing domain.

Stripe IDs are intentionally excluded from PlanResponse — they are internal
implementation details and should not be exposed to API consumers.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreatePlanRequest(BaseModel):
    """Request body for POST /admin/billing/plans."""

    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    monthly_fee_cents: int = Field(ge=0)
    token_quota: int = Field(ge=0)
    overage_rate_cents_per_token: int = Field(ge=0, default=0)
    member_cap: int = Field(default=1)  # -1 = unlimited


class UpdatePlanRequest(BaseModel):
    """Request body for PATCH /admin/billing/plans/{plan_id}."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    monthly_fee_cents: int | None = Field(default=None, ge=0)
    token_quota: int | None = Field(default=None, ge=0)
    overage_rate_cents_per_token: int | None = Field(default=None, ge=0)
    member_cap: int | None = None
    is_active: bool | None = None


class PlanResponse(BaseModel):
    """Response schema for plan objects. Stripe IDs are excluded (internal)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    monthly_fee_cents: int
    token_quota: int
    overage_rate_cents_per_token: int
    member_cap: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
