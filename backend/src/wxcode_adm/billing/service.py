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

Portal / subscription status:
- create_portal_session: creates a Stripe Customer Portal session URL for billing management
- get_subscription_status: returns the current TenantSubscription with plan details

Stripe calls are wrapped in try/except — Stripe failures log a warning but do NOT
block plan creation/update/deletion. The plan record is authoritative; Stripe IDs
are back-filled after successful API calls.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.billing.exceptions import PaymentRequiredError
from wxcode_adm.billing.models import Plan, SubscriptionStatus, TenantSubscription, WebhookEvent
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
        token_quota_5h=body.token_quota_5h,
        token_quota_weekly=body.token_quota_weekly,
        overage_rate_cents_per_token=body.overage_rate_cents_per_token,
        member_cap=body.member_cap,
        max_projects=body.max_projects,
        max_output_projects=body.max_output_projects,
        max_storage_gb=body.max_storage_gb,
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
    if body.token_quota_5h is not None:
        plan.token_quota_5h = body.token_quota_5h
    if body.token_quota_weekly is not None:
        plan.token_quota_weekly = body.token_quota_weekly
    if body.overage_rate_cents_per_token is not None:
        if body.overage_rate_cents_per_token != plan.overage_rate_cents_per_token:
            overage_changed = True
        plan.overage_rate_cents_per_token = body.overage_rate_cents_per_token
    if body.member_cap is not None:
        plan.member_cap = body.member_cap
    if body.max_projects is not None:
        plan.max_projects = body.max_projects
    if body.max_output_projects is not None:
        plan.max_output_projects = body.max_output_projects
    if body.max_storage_gb is not None:
        plan.max_storage_gb = body.max_storage_gb
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

    # Check if any tenant is using this plan
    in_use_result = await db.execute(
        select(func.count(TenantSubscription.id)).where(
            TenantSubscription.plan_id == plan_id
        )
    )
    in_use_count = in_use_result.scalar_one()
    if in_use_count > 0:
        raise ConflictError(
            error_code="PLAN_IN_USE",
            message=f"Cannot delete plan — {in_use_count} tenant(s) are currently using it",
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


# ---------------------------------------------------------------------------
# Customer Portal + subscription status
# ---------------------------------------------------------------------------


async def create_portal_session(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> str:
    """
    Create a Stripe Customer Portal session URL for a tenant.

    The portal allows billing_access members to manage their subscription,
    update payment methods, download invoices, and cancel/upgrade.

    Args:
        db: Async database session.
        tenant_id: UUID of the tenant requesting portal access.

    Returns:
        The Stripe Customer Portal session URL (for client-side redirect).

    Raises:
        PaymentRequiredError: Subscription record not found, or stripe_customer_id is None.
    """
    from wxcode_adm.config import settings as _settings  # noqa: PLC0415

    subscription_result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )
    subscription = subscription_result.scalar_one_or_none()
    if subscription is None:
        raise PaymentRequiredError(
            error_code="NO_SUBSCRIPTION",
            message="No subscription found",
        )

    if subscription.stripe_customer_id is None:
        raise PaymentRequiredError(
            error_code="NO_STRIPE_CUSTOMER",
            message="Stripe customer not configured",
        )

    portal = await stripe_client.billing_portal.sessions.create_async(
        params={
            "customer": subscription.stripe_customer_id,
            "return_url": f"{_settings.FRONTEND_URL}/billing",
        }
    )

    return portal.url


async def get_subscription_status(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> TenantSubscription:
    """
    Return the current TenantSubscription for a tenant, including plan details.

    The plan relationship is loaded eagerly (lazy="joined" on the model),
    so no extra selectinload is needed.

    Args:
        db: Async database session.
        tenant_id: UUID of the tenant.

    Returns:
        TenantSubscription ORM instance with .plan populated.

    Raises:
        NotFoundError: if no subscription record exists for this tenant.
    """
    subscription_result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )
    subscription = subscription_result.scalar_one_or_none()
    if subscription is None:
        raise NotFoundError(
            error_code="SUBSCRIPTION_NOT_FOUND",
            message="No subscription found for this tenant",
        )
    return subscription


# ---------------------------------------------------------------------------
# Webhook event processors (arq jobs)
# ---------------------------------------------------------------------------


async def process_stripe_event(ctx: dict, event_id: str, event_type: str, data_object: dict):
    """
    arq job: process one Stripe webhook event. Idempotent via DB check.

    Two-layer deduplication:
    - arq _job_id = Stripe event ID (prevents re-enqueue while job is running/queued)
    - WebhookEvent table (permanent DB record — outlasts arq result TTL)

    Raises on unhandled exception so arq will retry the job.
    """
    session_maker = ctx["session_maker"]

    async with session_maker() as db:
        try:
            # DB-level idempotency check (outlasts arq result TTL)
            existing = await db.execute(
                select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
            )
            if existing.scalar_one_or_none():
                logger.info(f"Webhook {event_id} already processed, skipping")
                return

            # Route to handler
            if event_type == "checkout.session.completed":
                await _handle_checkout_completed(db, data_object)
            elif event_type == "customer.subscription.updated":
                await _handle_subscription_updated(db, data_object)
            elif event_type == "customer.subscription.deleted":
                await _handle_subscription_deleted(db, data_object)
            elif event_type == "invoice.paid":
                await _handle_invoice_paid(db, data_object)
            elif event_type == "invoice.payment_failed":
                await _handle_payment_failed(db, data_object)
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")

            # Record processed event
            db.add(WebhookEvent(
                stripe_event_id=event_id,
                event_type=event_type,
                processed_at=datetime.now(timezone.utc),
            ))
            await db.commit()

        except Exception:
            await db.rollback()
            logger.exception(f"Failed to process webhook {event_id} ({event_type})")
            raise  # Let arq retry


async def _handle_checkout_completed(db: AsyncSession, data_object: dict) -> None:
    """
    Handle checkout.session.completed: activate the TenantSubscription.

    Extracts tenant_id and plan_id from metadata, sets stripe_subscription_id
    and status=ACTIVE.
    """
    metadata = data_object.get("metadata", {})
    tenant_id_str = metadata.get("tenant_id")
    plan_id_str = metadata.get("plan_id")

    if not tenant_id_str or not plan_id_str:
        logger.warning(
            "checkout.session.completed missing metadata tenant_id/plan_id — skipping"
        )
        return

    tenant_id = uuid.UUID(tenant_id_str)
    plan_id = uuid.UUID(plan_id_str)

    result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        logger.warning(f"checkout.session.completed: no subscription for tenant {tenant_id}")
        return

    subscription.stripe_subscription_id = data_object.get("subscription")
    subscription.plan_id = plan_id
    subscription.status = SubscriptionStatus.ACTIVE

    logger.info(f"Checkout completed for tenant {tenant_id}, plan {plan_id}")


async def _handle_subscription_updated(db: AsyncSession, data_object: dict) -> None:
    """
    Handle customer.subscription.updated: sync status and billing period.

    Maps Stripe status to SubscriptionStatus. Resets tokens_used_this_period
    on period rollover (new period_start differs from existing).
    """
    stripe_subscription_id = data_object.get("id")
    if not stripe_subscription_id:
        return

    result = await db.execute(
        select(TenantSubscription).where(
            TenantSubscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        logger.warning(
            f"customer.subscription.updated: no subscription found for {stripe_subscription_id}"
        )
        return

    # Map Stripe status to SubscriptionStatus
    stripe_status = data_object.get("status", "")
    if stripe_status in ("active", "trialing"):
        subscription.status = SubscriptionStatus.ACTIVE
    elif stripe_status == "past_due":
        subscription.status = SubscriptionStatus.PAST_DUE
    elif stripe_status in ("canceled", "incomplete_expired"):
        subscription.status = SubscriptionStatus.CANCELED
    else:
        logger.info(
            f"customer.subscription.updated: unhandled Stripe status '{stripe_status}' "
            f"for subscription {stripe_subscription_id} — keeping current status"
        )

    # Sync billing period from Unix timestamps
    new_period_start_ts = data_object.get("current_period_start")
    new_period_end_ts = data_object.get("current_period_end")

    if new_period_start_ts is not None:
        new_period_start = datetime.fromtimestamp(new_period_start_ts, tz=timezone.utc)

        # Reset token counter if period rolled over
        if (
            subscription.current_period_start is None
            or subscription.current_period_start != new_period_start
        ):
            subscription.tokens_used_this_period = 0

        subscription.current_period_start = new_period_start

    if new_period_end_ts is not None:
        subscription.current_period_end = datetime.fromtimestamp(
            new_period_end_ts, tz=timezone.utc
        )


async def _handle_subscription_deleted(db: AsyncSession, data_object: dict) -> None:
    """
    Handle customer.subscription.deleted: cancel the TenantSubscription.
    """
    stripe_subscription_id = data_object.get("id")
    if not stripe_subscription_id:
        return

    result = await db.execute(
        select(TenantSubscription).where(
            TenantSubscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        logger.warning(
            f"customer.subscription.deleted: no subscription found for {stripe_subscription_id}"
        )
        return

    subscription.status = SubscriptionStatus.CANCELED
    logger.info(f"Subscription deleted for tenant {subscription.tenant_id}")


async def _handle_invoice_paid(db: AsyncSession, data_object: dict) -> None:
    """
    Handle invoice.paid: restore subscription to ACTIVE if it was PAST_DUE.

    Per CONTEXT: automatic restoration on invoice.paid, no manual intervention.
    """
    stripe_subscription_id = data_object.get("subscription")
    if stripe_subscription_id is None:
        # One-off invoice (not subscription-related)
        return

    result = await db.execute(
        select(TenantSubscription).where(
            TenantSubscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return

    if subscription.status == SubscriptionStatus.PAST_DUE:
        subscription.status = SubscriptionStatus.ACTIVE
        logger.info(f"Subscription restored for tenant {subscription.tenant_id}")


async def _handle_payment_failed(db: AsyncSession, data_object: dict) -> None:
    """
    Handle invoice.payment_failed: set past_due, revoke JWT tokens, enqueue email.

    Per CONTEXT locked decision: JWT tokens are revoked on payment failure.
    All refresh tokens for all tenant members are deleted and their JTIs are
    blacklisted in Redis with ACCESS_TOKEN_TTL_HOURS TTL.
    """
    # Lazy imports to avoid circular dependencies at module load
    from wxcode_adm.auth.models import RefreshToken  # noqa: PLC0415
    from wxcode_adm.tenants.models import TenantMembership, MemberRole  # noqa: PLC0415
    from wxcode_adm.common.redis_client import redis_client  # noqa: PLC0415
    from wxcode_adm.tasks.worker import get_arq_pool  # noqa: PLC0415
    from wxcode_adm.auth.models import User  # noqa: PLC0415

    stripe_subscription_id = data_object.get("subscription")
    if stripe_subscription_id is None:
        return

    result = await db.execute(
        select(TenantSubscription).where(
            TenantSubscription.stripe_subscription_id == stripe_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return

    subscription.status = SubscriptionStatus.PAST_DUE

    tenant_id = subscription.tenant_id

    # --- Revoke JWT tokens for all tenant members ---

    # a. Get all user_ids for this tenant
    membership_result = await db.execute(
        select(TenantMembership.user_id).where(TenantMembership.tenant_id == tenant_id)
    )
    user_ids = [row[0] for row in membership_result.fetchall()]

    if user_ids:
        from wxcode_adm.auth.models import UserSession  # noqa: PLC0415
        from wxcode_adm.auth.service import blacklist_jti  # noqa: PLC0415

        # b. Blacklist access token JTIs for all affected users via UserSession
        session_result = await db.execute(
            select(UserSession.access_token_jti).where(
                UserSession.user_id.in_(user_ids)
            )
        )
        jtis = [row[0] for row in session_result.fetchall()]
        for jti in jtis:
            await blacklist_jti(redis_client, jti)

        # c. Get all refresh tokens for these users
        tokens_result = await db.execute(
            select(RefreshToken).where(RefreshToken.user_id.in_(user_ids))
        )
        refresh_tokens = list(tokens_result.scalars().all())

        # d. Delete all refresh tokens for these users
        for token in refresh_tokens:
            await db.delete(token)

        logger.info(
            f"Revoked tokens for {len(user_ids)} members of tenant {tenant_id}"
        )

    # --- Enqueue payment failure email to owner + admins with billing_access ---

    # Get tenant name from the loaded relationship
    tenant_name = str(tenant_id)  # fallback
    if subscription.tenant is not None:
        tenant_name = subscription.tenant.name

    # Query memberships for owner or billing_access members, join with User for email
    billing_members_result = await db.execute(
        select(TenantMembership, User)
        .join(User, TenantMembership.user_id == User.id)
        .where(TenantMembership.tenant_id == tenant_id)
        .where(
            (TenantMembership.role == MemberRole.OWNER)
            | (TenantMembership.billing_access.is_(True))
        )
    )
    billing_members = billing_members_result.fetchall()

    if billing_members:
        pool = await get_arq_pool()
        try:
            for membership, user in billing_members:
                await pool.enqueue_job(
                    "send_payment_failed_email",
                    user.email,
                    tenant_name,
                )
        finally:
            await pool.aclose()
