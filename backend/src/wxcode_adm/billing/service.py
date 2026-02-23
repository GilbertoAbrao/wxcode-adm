"""
Billing service functions for wxcode-adm.

Provides Plan CRUD operations with Stripe synchronization:
- create_plan: creates Plan + syncs Stripe Meter, Product, flat-fee Price, overage Price
- update_plan: applies changes + re-syncs Stripe Prices if fee amounts changed
- delete_plan: soft-deletes Plan (is_active=False) + archives Stripe Product
- list_plans: returns active or all plans ordered by price
- get_plan: loads a single plan by ID

Stripe calls are wrapped in try/except — Stripe failures log a warning but do NOT
block plan creation/update/deletion. The plan record is authoritative; Stripe IDs
are back-filled after successful API calls.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.billing.models import Plan
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
