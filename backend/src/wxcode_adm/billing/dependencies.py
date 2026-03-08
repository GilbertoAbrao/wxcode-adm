"""
Plan enforcement dependencies for wxcode-adm.

These dependencies are wired into endpoints that proxy to the wxcode engine
or manage tenant resources with plan-enforced limits.

Enforcement rules (from CONTEXT.md locked decisions):
- Paid plans: overage billing (never block a paying customer on token quota)
- Free tier: hard block at token quota (HTTP 402 with upgrade prompt)
- Member cap: hard limit on ALL plans (HTTP 402 when at/above cap)
- Past_due/canceled: block wxcode engine access (HTTP 402)

Public FastAPI dependencies (use with Depends()):
- require_active_subscription: blocks past_due/canceled tenants
- check_token_quota: enforces free tier quota + sets X-Quota-Warning headers
- check_member_cap: blocks invitations when plan member_cap reached

Standalone utility (call directly from endpoint handlers):
- enforce_member_cap: same logic as check_member_cap but takes explicit args

Private helpers (pure sync, no Depends — called by dependencies and tests):
- _enforce_active_subscription: raises PaymentRequiredError for past_due/canceled
- _enforce_token_quota: raises QuotaExceededError for free tier at quota
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.billing.exceptions import MemberLimitError, PaymentRequiredError, QuotaExceededError
from wxcode_adm.billing.models import Plan, SubscriptionStatus, TenantSubscription
from wxcode_adm.dependencies import get_session
from wxcode_adm.tenants.dependencies import get_tenant_context
from wxcode_adm.tenants.models import Tenant, TenantMembership


# ---------------------------------------------------------------------------
# Private synchronous helpers — pure logic, no DB, no Depends
# Called by the FastAPI dependencies AND directly by integration tests.
# ---------------------------------------------------------------------------


def _enforce_active_subscription(subscription: TenantSubscription) -> None:
    """
    Raise PaymentRequiredError if the subscription is in a blocking state.

    Blocking states: PAST_DUE, CANCELED.
    FREE and ACTIVE are allowed.

    This is a pure synchronous function with no DB calls and no FastAPI Depends.
    Plan 05 integration tests call this directly to verify enforcement logic.

    Args:
        subscription: The tenant's current TenantSubscription ORM instance.

    Raises:
        PaymentRequiredError: if status is PAST_DUE or CANCELED.
    """
    if subscription.status in (SubscriptionStatus.PAST_DUE, SubscriptionStatus.CANCELED):
        raise PaymentRequiredError(
            error_code="PAYMENT_REQUIRED",
            message="Subscription payment required. Visit billing settings to resolve.",
        )


def _enforce_token_quota(plan: Plan, subscription: TenantSubscription) -> None:
    """
    Raise QuotaExceededError if a free-tier tenant has exhausted their token quota.

    Enforcement rule (locked decision from CONTEXT.md):
    - Free tier (monthly_fee_cents == 0): hard block at quota (never allow overage)
    - Paid tiers: never block (overage billing — paying customers are never interrupted)

    This is a pure synchronous function with no DB calls and no FastAPI Depends.
    Plan 05 integration tests call this directly to verify enforcement logic.

    Args:
        plan: The Plan ORM instance linked to this subscription.
        subscription: The tenant's current TenantSubscription ORM instance.

    Raises:
        QuotaExceededError: if free-tier tenant is at or over token quota.
    """
    # Only enforce on free tier (monthly_fee_cents == 0) with a defined quota
    # Use token_quota_5h as the enforcement field for the shorter time window
    if plan.monthly_fee_cents == 0 and plan.token_quota_5h > 0:
        if subscription.tokens_used_this_period >= plan.token_quota_5h:
            raise QuotaExceededError(
                error_code="TOKEN_QUOTA_EXCEEDED",
                message=(
                    f"Free plan token quota ({plan.token_quota_5h}) exhausted. "
                    "Upgrade to continue."
                ),
            )
    # Paid tier: do nothing — overage billing, never block a paying customer


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def require_active_subscription(
    ctx: Annotated[tuple[Tenant, TenantMembership], Depends(get_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[Tenant, TenantMembership, TenantSubscription]:
    """
    FastAPI dependency that enforces an active (non-blocking) subscription.

    Allows FREE and ACTIVE subscription statuses. Blocks PAST_DUE and CANCELED.
    Raises PaymentRequiredError (HTTP 402) if no subscription record exists.

    Usage:
        @router.get("/engine-proxy")
        async def proxy(ctx = Depends(require_active_subscription)):
            tenant, membership, subscription = ctx
            ...

    Returns:
        (Tenant, TenantMembership, TenantSubscription) tuple.

    Raises:
        PaymentRequiredError: No subscription found, or status is PAST_DUE/CANCELED.
    """
    tenant, membership = ctx

    subscription_result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
    )
    subscription = subscription_result.scalar_one_or_none()

    if subscription is None:
        raise PaymentRequiredError(
            error_code="PAYMENT_REQUIRED",
            message="Subscription payment required. Visit billing settings to resolve.",
        )

    _enforce_active_subscription(subscription)

    return tenant, membership, subscription


async def check_token_quota(
    response: Response,
    ctx: Annotated[
        tuple[Tenant, TenantMembership, TenantSubscription],
        Depends(require_active_subscription),
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[Tenant, TenantMembership, TenantSubscription]:
    """
    FastAPI dependency that enforces token quota and sets usage warning headers.

    Chains on require_active_subscription (inherits its checks).
    Loads the plan for this subscription, then:
    - Hard blocks free-tier tenants at their token quota (HTTP 402).
    - Never blocks paid-tier tenants (overage billing).
    - Sets X-Quota-Warning and X-Quota-Usage headers at 80% and 100% usage.

    The Response parameter is injected by FastAPI to allow setting response headers
    from within a dependency. This is the documented pattern for header injection.

    Usage:
        @router.post("/engine-proxy")
        async def proxy(ctx = Depends(check_token_quota)):
            tenant, membership, subscription = ctx
            # X-Quota-Warning header will be set if usage is >= 80%
            ...

    Returns:
        (Tenant, TenantMembership, TenantSubscription) tuple.

    Raises:
        QuotaExceededError: if free-tier tenant is at or over their token quota.
    """
    tenant, membership, subscription = ctx

    # Load the plan for this subscription
    plan = await db.get(Plan, subscription.plan_id)

    # Call private helper — raises QuotaExceededError for free tier at quota
    _enforce_token_quota(plan, subscription)

    # Calculate usage percentage for warning headers (using token_quota_5h)
    if plan.token_quota_5h > 0:
        usage_pct = subscription.tokens_used_this_period / plan.token_quota_5h
        if usage_pct >= 1.0:
            response.headers["X-Quota-Warning"] = "QUOTA_REACHED"
            response.headers["X-Quota-Usage"] = (
                f"{subscription.tokens_used_this_period}/{plan.token_quota_5h}"
            )
        elif usage_pct >= 0.8:
            response.headers["X-Quota-Warning"] = "QUOTA_WARNING_80PCT"
            response.headers["X-Quota-Usage"] = (
                f"{subscription.tokens_used_this_period}/{plan.token_quota_5h}"
            )

    return tenant, membership, subscription


async def check_member_cap(
    ctx: Annotated[tuple[Tenant, TenantMembership], Depends(get_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[Tenant, TenantMembership]:
    """
    FastAPI dependency that enforces the plan member cap.

    If the tenant has no subscription, returns without blocking (no enforcement
    without a plan on record). If member_cap <= 0 (unlimited, -1 convention),
    returns without blocking.

    Usage:
        @router.post("/tenant-action-with-cap")
        async def action(ctx = Depends(check_member_cap)):
            tenant, membership = ctx
            ...

    Returns:
        (Tenant, TenantMembership) tuple.

    Raises:
        MemberLimitError: if current member count >= plan.member_cap.
    """
    tenant, membership = ctx

    subscription_result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
    )
    subscription = subscription_result.scalar_one_or_none()

    if subscription is None:
        # No subscription — no enforcement without a plan on record
        return tenant, membership

    plan = await db.get(Plan, subscription.plan_id)

    if plan.member_cap <= 0:
        # Unlimited plan (member_cap=-1 convention)
        return tenant, membership

    # Count current active members
    member_count_result = await db.execute(
        select(func.count()).select_from(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id
        )
    )
    member_count = member_count_result.scalar_one()

    if member_count >= plan.member_cap:
        raise MemberLimitError(
            error_code="MEMBER_LIMIT_REACHED",
            message=(
                f"Plan member limit ({plan.member_cap}) reached. "
                "Upgrade to invite more members."
            ),
        )

    return tenant, membership


# ---------------------------------------------------------------------------
# Standalone utility (not a FastAPI dependency)
# Called directly from endpoint handlers to avoid double Depends resolution.
# ---------------------------------------------------------------------------


async def enforce_member_cap(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """
    Enforce the plan member cap for a tenant without FastAPI Depends wiring.

    Identical logic to check_member_cap but takes explicit arguments.
    Called directly from the invitation endpoint handler to avoid double
    tenant-context resolution (require_role already resolves context).

    Args:
        db: Async database session.
        tenant_id: UUID of the tenant to check.

    Raises:
        MemberLimitError: if current member count >= plan.member_cap.
    """
    subscription_result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )
    subscription = subscription_result.scalar_one_or_none()

    if subscription is None:
        return  # No subscription — no enforcement

    plan = await db.get(Plan, subscription.plan_id)

    if plan.member_cap <= 0:
        return  # Unlimited plan

    # Count current members
    member_count_result = await db.execute(
        select(func.count()).select_from(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id
        )
    )
    member_count = member_count_result.scalar_one()

    if member_count >= plan.member_cap:
        raise MemberLimitError(
            error_code="MEMBER_LIMIT_REACHED",
            message=(
                f"Plan member limit ({plan.member_cap}) reached. "
                "Upgrade to invite more members."
            ),
        )
