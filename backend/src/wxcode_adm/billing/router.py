"""
FastAPI routers for wxcode-adm billing domain.

Two routers:

billing_admin_router (prefix: /admin/billing/plans):
  Super-admin only. Full plan CRUD: create, update, soft-delete, list (all), get.
  All endpoints require require_admin (admin-audience JWT, aud="wxcode-adm-admin").
  Regular-audience JWTs are rejected with 401 even for is_superuser users.

billing_router (prefix: /billing):
  Any authenticated user. Public plan catalog endpoint returns active plans only.
  Used by tenants to browse available plans before subscribing.
  POST /billing/checkout: create Stripe Checkout session (billing_access or Owner required).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.admin.dependencies import require_admin
from wxcode_adm.audit.service import write_audit
from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.auth.models import User
from wxcode_adm.billing import service
from wxcode_adm.billing.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    CreatePlanRequest,
    PlanResponse,
    SubscriptionResponse,
    UpdatePlanRequest,
)
from wxcode_adm.common.exceptions import ForbiddenError
from wxcode_adm.dependencies import get_session
from wxcode_adm.tenants.dependencies import get_tenant_context
from wxcode_adm.tenants.models import MemberRole, Tenant, TenantMembership

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
    request: Request,
    body: CreatePlanRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_admin)],
) -> PlanResponse:
    """Create a new billing plan and sync to Stripe."""
    plan = await service.create_plan(db, body)
    await write_audit(
        db,
        actor_id=user.id,
        action="create_plan",
        resource_type="plan",
        resource_id=str(plan.id),
        ip_address=request.client.host if request.client else None,
        details={"slug": body.slug},
    )
    return PlanResponse.model_validate(plan)


@billing_admin_router.patch(
    "/{plan_id}",
    response_model=PlanResponse,
)
async def update_plan(
    request: Request,
    plan_id: uuid.UUID,
    body: UpdatePlanRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_admin)],
) -> PlanResponse:
    """Update an existing billing plan. Re-syncs Stripe Prices if fee amounts changed."""
    plan = await service.update_plan(db, plan_id, body)
    await write_audit(
        db,
        actor_id=user.id,
        action="update_plan",
        resource_type="plan",
        resource_id=str(plan_id),
        ip_address=request.client.host if request.client else None,
    )
    return PlanResponse.model_validate(plan)


@billing_admin_router.delete(
    "/{plan_id}",
    response_model=PlanResponse,
)
async def delete_plan(
    request: Request,
    plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_admin)],
) -> PlanResponse:
    """Soft-delete a billing plan (sets is_active=False). Archives Stripe Product."""
    plan = await service.delete_plan(db, plan_id)
    await write_audit(
        db,
        actor_id=user.id,
        action="delete_plan",
        resource_type="plan",
        resource_id=str(plan_id),
        ip_address=request.client.host if request.client else None,
    )
    return PlanResponse.model_validate(plan)


@billing_admin_router.get(
    "/",
    response_model=list[PlanResponse],
)
async def list_plans_admin(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_admin)],
) -> list[PlanResponse]:
    """List all billing plans (including inactive) for admin management."""
    plans = await service.list_plans(db, include_inactive=True)
    return [PlanResponse.model_validate(p) for p in plans]


@billing_admin_router.get(
    "/{plan_id}",
    response_model=PlanResponse,
)
async def get_plan(
    request: Request,
    plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_admin)],
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


# ---------------------------------------------------------------------------
# Billing access dependency
# ---------------------------------------------------------------------------


async def require_billing_access(
    ctx: Annotated[tuple[Tenant, TenantMembership], Depends(get_tenant_context)],
) -> tuple[Tenant, TenantMembership]:
    """
    Enforce that the requesting member has billing_access=True OR is the Owner.

    Owners always have implicit billing access. Other roles (Admin, Viewer)
    require the billing_access toggle to be explicitly set on their membership.

    Returns:
        (Tenant, TenantMembership) — the resolved tenant context.

    Raises:
        ForbiddenError: BILLING_ACCESS_REQUIRED — member lacks billing access.
    """
    tenant, membership = ctx
    if not membership.billing_access and membership.role != MemberRole.OWNER:
        raise ForbiddenError(
            error_code="BILLING_ACCESS_REQUIRED",
            message="Billing access required",
        )
    return tenant, membership


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@billing_router.get(
    "/plans",
    response_model=list[PlanResponse],
)
async def list_active_plans(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_verified)],
) -> list[PlanResponse]:
    """List active billing plans (public catalog for authenticated users)."""
    plans = await service.list_plans(db, include_inactive=False)
    return [PlanResponse.model_validate(p) for p in plans]


@billing_router.post(
    "/checkout",
    response_model=CheckoutResponse,
)
async def create_checkout_session(
    request: Request,
    body: CheckoutRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    ctx: Annotated[tuple[Tenant, TenantMembership], Depends(require_billing_access)],
) -> CheckoutResponse:
    """
    Create a Stripe Checkout session for a tenant to subscribe to a paid plan.

    Returns a Stripe-hosted checkout URL for client-side redirect.
    Includes both the flat monthly fee and metered overage line items.

    Requires: billing_access=True on membership OR Owner role.
    Rejects: free plan checkout, already-subscribed tenants.
    """
    tenant, membership = ctx
    checkout_url, session_id = await service.create_checkout_session(
        db=db,
        tenant_id=tenant.id,
        plan_id=body.plan_id,
    )
    await write_audit(
        db,
        actor_id=membership.user_id,
        action="create_checkout",
        resource_type="subscription",
        tenant_id=tenant.id,
        ip_address=request.client.host if request.client else None,
        details={"plan_id": str(body.plan_id)},
    )
    return CheckoutResponse(checkout_url=checkout_url, session_id=session_id)


@billing_router.post(
    "/portal",
    status_code=status.HTTP_200_OK,
)
async def create_portal_session(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    ctx: Annotated[tuple[Tenant, TenantMembership], Depends(require_billing_access)],
) -> dict:
    """
    Create a Stripe Customer Portal session for the current tenant.

    Returns a portal URL for client-side redirect. The portal allows members with
    billing access to manage their subscription, update payment methods, and view invoices.

    Requires: billing_access=True on membership OR Owner role.
    """
    tenant, membership = ctx
    portal_url = await service.create_portal_session(db=db, tenant_id=tenant.id)
    await write_audit(
        db,
        actor_id=membership.user_id,
        action="create_portal_session",
        resource_type="subscription",
        tenant_id=tenant.id,
        ip_address=request.client.host if request.client else None,
    )
    return {"portal_url": portal_url}


@billing_router.get(
    "/subscription",
    response_model=SubscriptionResponse,
)
async def get_subscription_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    ctx: Annotated[tuple[Tenant, TenantMembership], Depends(get_tenant_context)],
) -> SubscriptionResponse:
    """
    Get the current subscription status for the tenant.

    Returns subscription details including plan information.
    Any authenticated tenant member can view subscription status.

    Requires: any tenant membership (no billing_access needed).
    """
    tenant, _ = ctx
    subscription = await service.get_subscription_status(db=db, tenant_id=tenant.id)
    return SubscriptionResponse.model_validate(subscription)
