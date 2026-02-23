"""
Billing service functions for wxcode-adm.

Provides Plan CRUD operations with Stripe synchronization:
- create_plan: creates Plan + syncs Stripe Meter, Product, flat-fee Price, overage Price
- update_plan: applies changes + re-syncs Stripe Prices if fee amounts changed
- delete_plan: soft-deletes Plan (is_active=False) + archives Stripe Product
- list_plans: returns active or all plans ordered by price
- get_plan: loads a single plan by ID

Checkout / subscription bootstrap:
- create_stripe_customer: creates a Stripe Customer for a tenant (best-effort)
- get_free_plan: returns the lowest-cost active plan (monthly_fee_cents=0)
- bootstrap_free_subscription: creates TenantSubscription(status=FREE) at onboarding
- create_checkout_session: generates a Stripe Checkout session URL for plan upgrade

Stripe calls are wrapped in try/except — Stripe failures log a warning but do NOT
block plan creation/update/deletion. The plan record is authoritative; Stripe IDs
are back-filled after successful API calls.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.billing.exceptions import PaymentRequiredError
from wxcode_adm.billing.models import Plan, SubscriptionStatus, TenantSubscription
from wxcode_adm.billing.schemas import CreatePlanRequest, UpdatePlanRequest
from wxcode_adm.billing.stripe_client import stripe_client
from wxcode_adm.common.exceptions import ConflictError, NotFoundError

logger = logging.getLogger(__name__)


async def create_plan(db: AsyncSession, body: CreatePlanRequest) -> Plan:
    """
    Create a new billing plan and sync it to Stripe.

    1. Check slug uniqueness — raise ConflictError if taken.
    2. Create Plan ORM instance, flush to get ID.
    3. Sync to Stripe: Billing Meter, Product, flat-fee Price, overage Price.
       Stripe failure is non-blocking — logged as warning, plan still created.
    4. Return plan.
    """
    # 1. Check slug uniqueness
    existing = await db.scalar(select(Plan).where(Plan.slug == body.slug))
    if existing is not None:
        raise ConflictError(
            error_code="PLAN_SLUG_EXISTS",
            message=f"A plan with slug '{body.slug}' already exists",
        )

    # 2. Create Plan ORM instance
    plan = Plan(
        name=body.name,
        slug=body.slug,
        monthly_fee_cents=body.monthly_fee_cents,
        token_quota=body.token_quota,
        overage_rate_cents_per_token=body.overage_rate_cents_per_token,
        member_cap=body.member_cap,
    )
    db.add(plan)
    await db.flush()  # Get the plan.id assigned

    # 3. Sync to Stripe (non-blocking)
    try:
        # a. Create Billing Meter
        meter = await stripe_client.billing.meters.create_async(
            params={
                "display_name": f"WXCODE Tokens — {body.name}",
                "event_name": f"wxcode_tokens_{body.slug}",
                "default_aggregation": {"formula": "sum"},
                "customer_mapping": {
                    "event_payload_key": "stripe_customer_id",
                    "type": "by_id",
                },
                "value_settings": {
                    "event_payload_key": "value",
                },
            }
        )

        # b. Create Product
        product = await stripe_client.products.create_async(
            params={
                "name": body.name,
                "metadata": {"plan_id": str(plan.id)},
            }
        )

        # c. Create flat-fee Price (licensed monthly)
        flat_price = await stripe_client.prices.create_async(
            params={
                "product": product.id,
                "currency": "usd",
                "unit_amount": body.monthly_fee_cents,
                "recurring": {
                    "interval": "month",
                    "usage_type": "licensed",
                },
            }
        )

        # d. Create overage Price (metered, linked to Billing Meter)
        overage_price = await stripe_client.prices.create_async(
            params={
                "product": product.id,
                "currency": "usd",
                "unit_amount_decimal": str(body.overage_rate_cents_per_token),
                "billing_scheme": "per_unit",
                "recurring": {
                    "interval": "month",
                    "usage_type": "metered",
                    "meter": meter.id,
                },
            }
        )

        # e. Back-fill Stripe IDs on plan
        plan.stripe_meter_id = meter.id
        plan.stripe_product_id = product.id
        plan.stripe_price_id = flat_price.id
        plan.stripe_overage_price_id = overage_price.id

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Stripe sync failed for plan '%s' (id=%s): %s",
            body.slug,
            plan.id,
            exc,
        )

    return plan


async def update_plan(
    db: AsyncSession, plan_id: uuid.UUID, body: UpdatePlanRequest
) -> Plan:
    """
    Update a billing plan and re-sync Stripe Prices if fee amounts changed.

    1. Load Plan by ID — raise NotFoundError if missing.
    2. Apply non-None fields from body.
    3. If monthly_fee_cents or overage changed AND plan has Stripe IDs, re-sync Prices.
    4. Return plan.
    """
    # 1. Load plan
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError(
            error_code="PLAN_NOT_FOUND",
            message=f"Plan with id '{plan_id}' not found",
        )

    # Track whether price sync is needed
    price_changed = False
    overage_changed = False

    # 2. Apply non-None fields
    if body.name is not None:
        plan.name = body.name
    if body.monthly_fee_cents is not None:
        if body.monthly_fee_cents != plan.monthly_fee_cents:
            price_changed = True
        plan.monthly_fee_cents = body.monthly_fee_cents
    if body.token_quota is not None:
        plan.token_quota = body.token_quota
    if body.overage_rate_cents_per_token is not None:
        if body.overage_rate_cents_per_token != plan.overage_rate_cents_per_token:
            overage_changed = True
        plan.overage_rate_cents_per_token = body.overage_rate_cents_per_token
    if body.member_cap is not None:
        plan.member_cap = body.member_cap
    if body.is_active is not None:
        plan.is_active = body.is_active

    # 3. Re-sync Stripe Prices if fee amounts changed and plan has Stripe data
    if plan.stripe_product_id and (price_changed or overage_changed):
        try:
            if price_changed and plan.stripe_price_id:
                # Archive old flat-fee Price
                await stripe_client.prices.update_async(
                    plan.stripe_price_id,
                    params={"active": False},
                )
                # Create new flat-fee Price
                new_flat_price = await stripe_client.prices.create_async(
                    params={
                        "product": plan.stripe_product_id,
                        "currency": "usd",
                        "unit_amount": plan.monthly_fee_cents,
                        "recurring": {
                            "interval": "month",
                            "usage_type": "licensed",
                        },
                    }
                )
                plan.stripe_price_id = new_flat_price.id

            if overage_changed and plan.stripe_overage_price_id:
                # Archive old overage Price
                await stripe_client.prices.update_async(
                    plan.stripe_overage_price_id,
                    params={"active": False},
                )
                # Create new overage Price
                new_overage_price = await stripe_client.prices.create_async(
                    params={
                        "product": plan.stripe_product_id,
                        "currency": "usd",
                        "unit_amount_decimal": str(plan.overage_rate_cents_per_token),
                        "billing_scheme": "per_unit",
                        "recurring": {
                            "interval": "month",
                            "usage_type": "metered",
                            "meter": plan.stripe_meter_id,
                        },
                    }
                )
                plan.stripe_overage_price_id = new_overage_price.id

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Stripe price re-sync failed for plan '%s' (id=%s): %s",
                plan.slug,
                plan_id,
                exc,
            )

    return plan


async def delete_plan(db: AsyncSession, plan_id: uuid.UUID) -> Plan:
    """
    Soft-delete a billing plan by setting is_active=False.

    Cannot hard-delete because TenantSubscription records may reference the plan.
    Also archives the Stripe Product (non-blocking).
    """
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError(
            error_code="PLAN_NOT_FOUND",
            message=f"Plan with id '{plan_id}' not found",
        )

    plan.is_active = False

    if plan.stripe_product_id:
        try:
            await stripe_client.products.update_async(
                plan.stripe_product_id,
                params={"active": False},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Stripe product archive failed for plan '%s' (id=%s): %s",
                plan.slug,
                plan_id,
                exc,
            )

    return plan


async def list_plans(
    db: AsyncSession,
    include_inactive: bool = False,
) -> list[Plan]:
    """
    List billing plans ordered by monthly_fee_cents ASC (free tier first).

    Args:
        include_inactive: if False (default), only returns is_active=True plans.
    """
    stmt = select(Plan)
    if not include_inactive:
        stmt = stmt.where(Plan.is_active.is_(True))
    stmt = stmt.order_by(Plan.monthly_fee_cents.asc())
    result = await db.scalars(stmt)
    return list(result.all())


async def get_plan(db: AsyncSession, plan_id: uuid.UUID) -> Plan:
    """
    Load a single plan by ID.

    Raises:
        NotFoundError: if plan does not exist.
    """
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError(
            error_code="PLAN_NOT_FOUND",
            message=f"Plan with id '{plan_id}' not found",
        )
    return plan


# ---------------------------------------------------------------------------
# Stripe Customer + subscription bootstrap (called from tenants/service.py)
# ---------------------------------------------------------------------------


async def create_stripe_customer(
    tenant_name: str,
    owner_email: str,
    tenant_id: uuid.UUID,
) -> str | None:
    """
    Create a Stripe Customer for a new tenant (best-effort).

    Called during workspace onboarding in tenants/service.py. If Stripe is
    unavailable or returns an error, logs a WARNING and returns None — the
    checkout flow will create the customer lazily when needed.

    Args:
        tenant_name: Display name of the workspace/tenant.
        owner_email: Email address of the workspace owner.
        tenant_id: UUID of the tenant (stored in Stripe Customer metadata).

    Returns:
        The Stripe Customer ID string (cus_...) on success, or None on failure.
    """
    try:
        customer = await stripe_client.customers.create_async(
            params={
                "email": owner_email,
                "name": tenant_name,
                "metadata": {"tenant_id": str(tenant_id)},
            }
        )
        return customer.id
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Stripe Customer creation failed for tenant '%s' (id=%s): %s",
            tenant_name,
            tenant_id,
            exc,
        )
        return None


async def get_free_plan(db: AsyncSession) -> Plan | None:
    """
    Return the active free plan (monthly_fee_cents=0), ordered by created_at ASC.

    Args:
        db: Async database session.

    Returns:
        The oldest active free Plan, or None if none exists.
    """
    result = await db.scalar(
        select(Plan)
        .where(Plan.monthly_fee_cents == 0, Plan.is_active.is_(True))
        .order_by(Plan.created_at.asc())
        .limit(1)
    )
    return result


async def bootstrap_free_subscription(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    stripe_customer_id: str | None,
) -> TenantSubscription:
    """
    Create a TenantSubscription(status=FREE) for a new tenant at onboarding.

    Must be called inside the same DB session/transaction as create_workspace.
    Caller manages session lifecycle (commit/rollback) — this function only
    flushes to obtain the subscription.id without committing.

    Args:
        db: Async database session (caller manages commit).
        tenant_id: UUID of the newly-created tenant.
        stripe_customer_id: Stripe Customer ID (may be None if creation failed).

    Returns:
        The created TenantSubscription ORM instance.

    Raises:
        RuntimeError: if no active free plan exists in the database.
    """
    free_plan = await get_free_plan(db)
    if free_plan is None:
        raise RuntimeError(
            "No active free plan found — seed one via admin API"
        )

    subscription = TenantSubscription(
        tenant_id=tenant_id,
        plan_id=free_plan.id,
        stripe_customer_id=stripe_customer_id,
        status=SubscriptionStatus.FREE,
        tokens_used_this_period=0,
    )
    db.add(subscription)
    await db.flush()

    return subscription


# ---------------------------------------------------------------------------
# Checkout session
# ---------------------------------------------------------------------------


async def create_checkout_session(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> tuple[str, str]:
    """
    Create a Stripe Checkout session for a tenant to subscribe to a paid plan.

    Steps:
    1. Load the TenantSubscription for this tenant — raise PaymentRequiredError if missing.
    2. Load the target Plan — raise NotFoundError if missing or inactive.
    3. Guard: free plan checkout rejected with ConflictError.
    4. Guard: already-active subscription rejected with ConflictError.
    5. If stripe_customer_id is None (Stripe Customer failed during onboarding),
       create one lazily now.
    6. Build line_items (flat fee + optional metered overage).
    7. Create Checkout Session via Stripe API.
    8. Return (session.url, session.id).

    Args:
        db: Async database session.
        tenant_id: UUID of the tenant checking out.
        plan_id: UUID of the target billing plan.

    Returns:
        (checkout_url, session_id) tuple.

    Raises:
        PaymentRequiredError: Subscription record not found (NO_SUBSCRIPTION).
        NotFoundError: Target plan not found or inactive (PLAN_NOT_FOUND).
        ConflictError: Attempting to checkout to free plan (CANNOT_CHECKOUT_FREE).
        ConflictError: Already actively subscribed (ALREADY_SUBSCRIBED).
    """
    from wxcode_adm.tenants.models import Tenant  # noqa: PLC0415 — lazy import avoids circular

    from wxcode_adm.config import settings as _settings  # noqa: PLC0415

    # 1. Load TenantSubscription
    subscription_result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )
    subscription = subscription_result.scalar_one_or_none()
    if subscription is None:
        raise PaymentRequiredError(
            error_code="NO_SUBSCRIPTION",
            message="No subscription record found for this tenant",
        )

    # 2. Load target Plan
    plan = await db.get(Plan, plan_id)
    if plan is None or not plan.is_active:
        raise NotFoundError(
            error_code="PLAN_NOT_FOUND",
            message=f"Plan with id '{plan_id}' not found or is not active",
        )

    # 3. Guard: reject checkout for free plan
    if plan.monthly_fee_cents == 0:
        raise ConflictError(
            error_code="CANNOT_CHECKOUT_FREE",
            message="Cannot checkout for the free plan — use upgrade instead",
        )

    # 4. Guard: already actively subscribed
    if subscription.stripe_subscription_id and subscription.status == SubscriptionStatus.ACTIVE:
        raise ConflictError(
            error_code="ALREADY_SUBSCRIBED",
            message="Already subscribed — use Customer Portal to manage",
        )

    # 5. Lazy Stripe Customer creation if onboarding failed
    if subscription.stripe_customer_id is None:
        # Load tenant + owner email
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        tenant_name = tenant.name if tenant else str(tenant_id)

        # Create customer without email (we don't have easy access to owner email here)
        # The checkout form will collect it if needed
        new_customer_id = await create_stripe_customer(
            tenant_name=tenant_name,
            owner_email="",  # Stripe allows empty email; user provides it at checkout
            tenant_id=tenant_id,
        )
        subscription.stripe_customer_id = new_customer_id

    # 6. Build line_items
    line_items = [
        {"price": plan.stripe_price_id, "quantity": 1},  # flat fee
    ]
    if plan.stripe_overage_price_id is not None:
        line_items.append({"price": plan.stripe_overage_price_id})  # metered overage

    # 7. Create Checkout Session
    session = await stripe_client.checkout.sessions.create_async(
        params={
            "customer": subscription.stripe_customer_id,
            "mode": "subscription",
            "line_items": line_items,
            "success_url": (
                f"{_settings.FRONTEND_URL}/billing?session_id={{CHECKOUT_SESSION_ID}}"
            ),
            "cancel_url": f"{_settings.FRONTEND_URL}/billing?canceled=true",
            "metadata": {
                "tenant_id": str(tenant_id),
                "plan_id": str(plan_id),
            },
            "subscription_data": {
                "metadata": {
                    "tenant_id": str(tenant_id),
                    "plan_id": str(plan_id),
                },
            },
        }
    )

    # 8. Return (checkout_url, session_id)
    return session.url, session.id
