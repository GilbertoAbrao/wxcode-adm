"""
FastAPI routers for wxcode-adm billing domain.

Two routers:

billing_admin_router (prefix: /admin/billing/plans):
  Super-admin only. Full plan CRUD: create, update, soft-delete, list (all), get.
  All endpoints require require_verified + is_superuser check.

billing_router (prefix: /billing):
  Any authenticated user. Public plan catalog endpoint returns active plans only.
  Used by tenants to browse available plans before subscribing.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.auth.models import User
from wxcode_adm.billing import service
from wxcode_adm.billing.schemas import CreatePlanRequest, PlanResponse, UpdatePlanRequest
from wxcode_adm.common.exceptions import ForbiddenError
from wxcode_adm.dependencies import get_session

# ---------------------------------------------------------------------------
# Superuser dependency
# ---------------------------------------------------------------------------


async def require_superuser(
    user: Annotated[User, Depends(require_verified)],
) -> User:
    """
    Extend require_verified to also enforce super-admin access.

    Raises:
        ForbiddenError: if the authenticated user is not a super-admin.
    """
    if not user.is_superuser:
        raise ForbiddenError(
            error_code="SUPERUSER_REQUIRED",
            message="Super-admin access required",
        )
    return user


# ---------------------------------------------------------------------------
# Admin router — super-admin plan CRUD
# ---------------------------------------------------------------------------

billing_admin_router = APIRouter(
    prefix="/admin/billing/plans",
    tags=["Billing Admin"],
)


@billing_admin_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=PlanResponse,
)
async def create_plan(
    body: CreatePlanRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_superuser)],
) -> PlanResponse:
    """Create a new billing plan and sync to Stripe."""
    plan = await service.create_plan(db, body)
    return PlanResponse.model_validate(plan)


@billing_admin_router.patch(
    "/{plan_id}",
    response_model=PlanResponse,
)
async def update_plan(
    plan_id: uuid.UUID,
    body: UpdatePlanRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_superuser)],
) -> PlanResponse:
    """Update an existing billing plan. Re-syncs Stripe Prices if fee amounts changed."""
    plan = await service.update_plan(db, plan_id, body)
    return PlanResponse.model_validate(plan)


@billing_admin_router.delete(
    "/{plan_id}",
    response_model=PlanResponse,
)
async def delete_plan(
    plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_superuser)],
) -> PlanResponse:
    """Soft-delete a billing plan (sets is_active=False). Archives Stripe Product."""
    plan = await service.delete_plan(db, plan_id)
    return PlanResponse.model_validate(plan)


@billing_admin_router.get(
    "/",
    response_model=list[PlanResponse],
)
async def list_plans_admin(
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_superuser)],
) -> list[PlanResponse]:
    """List all billing plans (including inactive) for admin management."""
    plans = await service.list_plans(db, include_inactive=True)
    return [PlanResponse.model_validate(p) for p in plans]


@billing_admin_router.get(
    "/{plan_id}",
    response_model=PlanResponse,
)
async def get_plan(
    plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_superuser)],
) -> PlanResponse:
    """Get a single billing plan by ID."""
    plan = await service.get_plan(db, plan_id)
    return PlanResponse.model_validate(plan)


# ---------------------------------------------------------------------------
# Public catalog router — any authenticated user
# ---------------------------------------------------------------------------

billing_router = APIRouter(
    prefix="/billing",
    tags=["Billing"],
)


@billing_router.get(
    "/plans",
    response_model=list[PlanResponse],
)
async def list_active_plans(
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_verified)],
) -> list[PlanResponse]:
    """List active billing plans (public catalog for authenticated users)."""
    plans = await service.list_plans(db, include_inactive=False)
    return [PlanResponse.model_validate(p) for p in plans]
