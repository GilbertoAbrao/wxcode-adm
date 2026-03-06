# Phase 4: Billing Core - Research

**Researched:** 2026-02-23
**Domain:** Stripe Billing (Meters, Checkout, Webhooks, Customer Portal), FastAPI subscription enforcement, arq background processing
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Plan catalog design
- Hybrid billing: monthly subscription fee + usage-based token metering
- Plans define two limit types: **token quota** (included monthly allowance + overage rate) and **member cap** (hard limit)
- Plans are fully manageable by super-admin via CRUD API — tiers, limits, and pricing are not hardcoded
- Each plan syncs to a Stripe Price (subscription component) + Stripe Billing Meter (usage component)
- No trial periods — a permanent free tier with low limits serves as the entry point

#### Checkout & subscription flow
- No coupon/promo code support at launch
- Upgrades apply immediately with Stripe proration
- Downgrades take effect at end of current billing period (not immediate)
- Post-checkout redirect behavior: Claude's Discretion

#### Payment failure handling
- No grace period — tenant is immediately restricted on payment failure
- Restricted tenant: can access wxcode-adm (to fix payment) but cannot access wxcode engine
- JWT tokens are revoked on payment failure, forcing re-authentication with restricted state
- Notification: email sent to tenant owner + admins with billing_access
- Automatic restoration: when Stripe confirms payment resolved (invoice.paid webhook), tenant is automatically restored to their paid plan — no manual intervention

#### Enforcement behavior
- Warning headers at 80% and 100% of token quota in API responses
- Token usage: **overage billing** for paid plans — requests continue beyond quota, extra tokens billed at overage rate (never block a paying customer)
- Token usage on free tier: **hard block** at quota — HTTP 402 with upgrade prompt, no overage possible (no payment method)
- Member limit: **hard cap** on all plans — HTTP 402 when trying to invite beyond plan limit, must upgrade
- On payment failure: wxcode-adm accessible, wxcode engine blocked, JWT tokens revoked

### Claude's Discretion
- Post-checkout redirect destination (dashboard vs billing page)
- Stripe webhook retry/idempotency implementation details
- Token usage tracking granularity and storage approach
- Overage rate display and communication in warning headers

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BILL-01 | Super-admin can CRUD billing plans (synced with Stripe) | Plan model + Stripe Price/Meter create/update API; `stripe.billing.Meter.create()` + `stripe.Price.create(recurring.meter=...)` |
| BILL-02 | User can subscribe to a plan via Stripe Checkout | `stripe.checkout.Session.create(mode="subscription", line_items=[...], customer=stripe_customer_id)` pattern |
| BILL-03 | Stripe webhooks sync subscription state (paid, updated, deleted, failed) | Raw body preservation + `stripe.Webhook.construct_event()`; arq `_job_id` deduplication; subscription state machine |
| BILL-04 | User can manage billing via Stripe Customer Portal | `stripe.billing_portal.Session.create(customer=..., return_url=...)` pattern |
| BILL-05 | Plan limits enforced before wxcode engine operations | FastAPI dependency checking `TenantSubscription.status + quota` before forwarding; HTTP 402 with `QUOTA_EXCEEDED` / `PAYMENT_REQUIRED` error codes |
</phase_requirements>

---

## Summary

Phase 4 introduces Stripe as a third external dependency (alongside PostgreSQL and Redis). The core integration has three logical layers: (1) plan catalog that stays in sync with Stripe objects, (2) subscription lifecycle managed via Checkout + webhooks, and (3) enforcement at the API gateway layer before requests reach the wxcode engine.

The **Stripe Billing Meters API** (post-2025-03-31 deprecation) is the correct tool for the token overage component. Legacy `usage_type=metered` without a meter is removed in API version `2025-03-31.basil`. This phase must use the new `billing.Meter` + `billing.MeterEvent` path. The stripe-python library v14.x (latest: 14.3.0) provides `stripe.billing.Meter.create()` and `stripe.billing.meter_event.create()` — these are stable synchronous and async (`_async` suffix) methods.

The **hybrid billing model** (flat subscription fee + metered overage) requires two Stripe Price objects per plan: one `licensed` Price for the fixed monthly fee, and one `metered` Price linked to the Billing Meter for overages. Both appear as line items on a single Checkout Session. Stripe invoices them together at period end.

The **webhook processing path** is the trickiest correctness concern. Stripe may deliver the same event multiple times (retries on non-2xx responses). The pattern is: ingestion endpoint (fast, signature-verify, return 200, enqueue to arq) → arq worker (processes event idempotently using arq's `_job_id` deduplication). The arq `_job_id` is set to the Stripe event ID — arq's Redis transaction guarantees a job with a given ID cannot be enqueued twice while it is still queued or running.

**Primary recommendation:** Use `stripe[async]` with `StripeClient` for all Stripe API calls. Store `stripe_customer_id` and `stripe_subscription_id` on the `Tenant` model. Represent subscription state locally in a `TenantSubscription` table (not just querying Stripe on every request). Enforce via a reusable FastAPI dependency that reads local state.

---

## Standard Stack

### Core (new additions for Phase 4)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| stripe | 14.3.0 | Stripe Python SDK — Customer, Checkout, Portal, Meters, Webhooks | Official Stripe SDK; v14+ has stable async support via `_async` suffix; StripeClient is the modern pattern |
| httpx | (bundled via stripe[async]) | Async HTTP client for stripe-python async calls | stripe-python uses httpx for async requests; required when calling `*_async` methods |

### Existing Stack (no changes needed)

| Library | Already Used | Relevance |
|---------|-------------|-----------|
| FastAPI 0.131.0 | Yes | Router, Depends, Request (for raw body), Header |
| SQLAlchemy 2.0 async | Yes | Plan, TenantSubscription, WebhookEvent models |
| Alembic 1.18.4 | Yes | Migration 003 for billing tables |
| arq 0.27.0 | Yes | Webhook event processor jobs |
| redis 5.3.1 | Yes | arq queue backend + webhook idempotency |
| fastapi-mail | Yes | Payment failure notification emails |
| pydantic-settings | Yes | STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PUBLISHABLE_KEY env vars |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stripe-python (official) | async-stripe (community wrapper) | async-stripe is unofficial; stripe-python v13+ has native async support — no wrapper needed |
| Local subscription state table | Query Stripe API on every request | Stripe API call on each request adds latency and Stripe rate-limit risk; local state is fast and the webhook keeps it fresh |
| arq `_job_id` deduplication | Redis SET NX manual dedup | arq's `_job_id` uses an atomic Redis transaction — already available, no extra code; use it |

**Installation:**
```bash
pip install "stripe[async]==14.3.0"
```

---

## Architecture Patterns

### Recommended Project Structure

```
backend/src/wxcode_adm/
├── billing/
│   ├── __init__.py          # (exists, empty — extend it)
│   ├── models.py            # Plan, TenantSubscription, WebhookEvent
│   ├── schemas.py           # Pydantic request/response for billing endpoints
│   ├── service.py           # Business logic: create_plan, sync_to_stripe, create_checkout, etc.
│   ├── exceptions.py        # PaymentRequiredError, QuotaExceededError, MemberLimitError
│   ├── dependencies.py      # require_active_subscription, check_token_quota, check_member_quota
│   ├── router.py            # /api/v1/billing/* endpoints
│   ├── stripe_client.py     # StripeClient singleton, async wrappers
│   ├── webhook_router.py    # /api/v1/webhooks/stripe (raw body, no auth)
│   └── email.py             # send_payment_failed_email arq job
├── config.py                # Add STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PUBLISHABLE_KEY
└── alembic/versions/
    └── 003_add_billing_tables.py
```

### Data Model

```
Plan (platform-level, tenant_id=NULL)
  id: UUID
  name: str           — "Free", "Starter", "Pro"
  slug: str           — machine identifier
  stripe_price_id: str          — Stripe Price ID for subscription fee
  stripe_meter_id: str          — Stripe Billing Meter ID for token usage
  stripe_overage_price_id: str  — Stripe Price ID for metered overage
  monthly_fee_cents: int        — 0 for free tier
  token_quota: int              — included tokens per month (free gets e.g. 10_000)
  overage_rate_per_token: Decimal — e.g. 0.00004 (overage rate for paid; NULL for free)
  member_cap: int               — max members (-1 = unlimited)
  is_active: bool               — soft delete / hide from catalog
  created_at, updated_at

TenantSubscription (one per Tenant — platform-level, tenant_id IS the tenant)
  id: UUID
  tenant_id: UUID (FK tenants.id, UNIQUE — one subscription per tenant)
  plan_id: UUID (FK plans.id)
  stripe_subscription_id: str   — NULL until first checkout completes
  stripe_customer_id: str       — set at tenant creation
  status: str (Enum)            — "free" | "active" | "past_due" | "canceled"
  current_period_start: DateTime
  current_period_end: DateTime
  tokens_used_this_period: int  — local counter (incremented by engine proxy)
  created_at, updated_at

WebhookEvent (idempotency log)
  id: UUID
  stripe_event_id: str (UNIQUE) — e.g. "evt_1ABC..."
  event_type: str               — e.g. "invoice.paid"
  processed_at: DateTime
  created_at
```

**Design decision:** `TenantSubscription` is NOT a `TenantModel` subclass (no RLS concern — it is the tenant's own record, accessed by platform code). It inherits `Base + TimestampMixin` directly, like `Tenant` and `TenantMembership`.

**Free tier bootstrap:** On workspace creation (`POST /api/v1/onboarding/workspace`), create a Stripe Customer and insert a `TenantSubscription` with `status="free"` pointing to the free plan. This means every tenant always has a subscription record from day one.

### Pattern 1: Stripe StripeClient Singleton

Use `StripeClient` (not the legacy `stripe.api_key` global). Configure once at module level in `billing/stripe_client.py`.

```python
# Source: stripe-python GitHub README + PyPI page
# billing/stripe_client.py

import stripe
from stripe import StripeClient

from wxcode_adm.config import settings

# Module-level singleton — created once at import time.
# Uses httpx for async requests (requires stripe[async]).
stripe_client: StripeClient = StripeClient(
    settings.STRIPE_SECRET_KEY.get_secret_value(),
)
```

**Async usage pattern (append `_async` to method name):**

```python
# Creating a Stripe Customer (async)
customer = await stripe_client.customers.create_async(
    params={"email": tenant_owner_email, "name": tenant_name, "metadata": {"tenant_id": str(tenant.id)}}
)

# Creating a Checkout Session (async)
session = await stripe_client.checkout.sessions.create_async(
    params={
        "customer": tenant_subscription.stripe_customer_id,
        "mode": "subscription",
        "line_items": [
            {"price": plan.stripe_price_id, "quantity": 1},        # flat fee
            {"price": plan.stripe_overage_price_id, "quantity": 1}, # metered overage
        ],
        "success_url": f"{settings.FRONTEND_URL}/billing?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{settings.FRONTEND_URL}/billing",
    }
)

# Creating a Billing Portal Session (async)
portal = await stripe_client.billing_portal.sessions.create_async(
    params={
        "customer": tenant_subscription.stripe_customer_id,
        "return_url": f"{settings.FRONTEND_URL}/billing",
    }
)
```

### Pattern 2: Stripe Plan Sync

When super-admin creates or updates a Plan, sync to Stripe:

1. Create a Stripe Billing Meter (for token overage tracking)
2. Create a Stripe Product (for the plan)
3. Create a flat-fee Price (`recurring.usage_type="licensed"`, `unit_amount=monthly_fee_cents`)
4. Create an overage Price (`recurring.usage_type="metered"`, `recurring.meter=meter_id`, `unit_amount_decimal=overage_rate_per_100_tokens`)

```python
# Source: https://docs.stripe.com/billing/subscriptions/usage-based-v1/use-cases/flat-fee-and-overages

# Step 1: Create billing meter
meter = await stripe_client.billing.meters.create_async(params={
    "display_name": f"{plan.name} Token Meter",
    "event_name": f"wxcode_tokens_{plan.slug}",   # must be unique per plan
    "default_aggregation": {"formula": "sum"},
    "customer_mapping": {
        "event_payload_key": "stripe_customer_id",
        "type": "by_id",
    },
    "value_settings": {"event_payload_key": "value"},
})

# Step 2: Create product
product = await stripe_client.products.create_async(
    params={"name": plan.name, "metadata": {"plan_id": str(plan.id)}}
)

# Step 3: Flat fee price (licensed — charged every billing period)
flat_price = await stripe_client.prices.create_async(params={
    "product": product.id,
    "currency": "usd",
    "unit_amount": plan.monthly_fee_cents,   # 0 for free tier
    "recurring": {"interval": "month", "usage_type": "licensed"},
})

# Step 4: Overage price (metered — charged per token above quota)
overage_price = await stripe_client.prices.create_async(params={
    "product": product.id,
    "currency": "usd",
    "billing_scheme": "per_unit",
    # overage_rate is per-token; Stripe charges per unit so set unit_amount_decimal
    "unit_amount_decimal": str(int(plan.overage_rate_per_token * 100)),  # in cents * 100
    "recurring": {
        "interval": "month",
        "usage_type": "metered",
        "meter": meter.id,
    },
})
```

**IMPORTANT:** Billing Meter configuration is immutable after creation (except display_name). `event_name` cannot be changed. Design the `event_name` format carefully upfront.

### Pattern 3: Webhook Ingestion (Fast Path)

The webhook endpoint must:
1. Read raw bytes (NOT parse as JSON — signature verification requires raw bytes)
2. Verify Stripe signature synchronously
3. Return 200 immediately
4. Enqueue to arq with `_job_id=stripe_event_id` for deduplication

```python
# Source: FastAPI docs + Stripe webhook docs + blog.frank-mich.com pattern
# billing/webhook_router.py

from fastapi import APIRouter, Header, HTTPException, Request
from typing import Annotated
import stripe

from wxcode_adm.config import settings
from wxcode_adm.tasks.worker import get_arq_pool

webhook_router = APIRouter()


async def get_raw_body(request: Request) -> bytes:
    """Must return raw bytes — NOT parsed JSON. Stripe signature requires exact bytes."""
    return await request.body()


@webhook_router.post("/webhooks/stripe", status_code=200)
async def stripe_webhook(
    stripe_signature: Annotated[str, Header(alias="stripe-signature")],
    body: bytes = Depends(get_raw_body),
) -> dict:
    """
    Fast ingestion endpoint: verify signature, enqueue to arq, return 200.

    CRITICAL: body must be raw bytes. Any JSON parsing before this point
    will break signature verification (different byte representation).

    Returns 200 immediately — processing happens asynchronously in arq.
    Stripe retries on non-2xx, so quick 200 is essential.
    """
    try:
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET.get_secret_value(),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Enqueue with _job_id = stripe event ID for arq-level deduplication.
    # arq atomic Redis transaction guarantees no duplicate enqueue.
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job(
            "process_stripe_event",
            event["id"],
            event["type"],
            event["data"]["object"],
            _job_id=event["id"],   # arq deduplication key
        )
    finally:
        await pool.aclose()

    return {"received": True}
```

### Pattern 4: Webhook Processor (Subscription State Machine)

Each event type handler updates local `TenantSubscription` state:

```python
# billing/service.py — webhook processor jobs (registered in worker.py)

SUBSCRIPTION_ACTIVE_STATUSES = {"active", "trialing"}
SUBSCRIPTION_FAILED_STATUSES = {"past_due", "unpaid", "canceled", "incomplete_expired"}

async def process_stripe_event(ctx: dict, event_id: str, event_type: str, data_object: dict):
    """
    arq job: process one Stripe webhook event.
    Idempotent — arq _job_id prevents duplicate processing.
    """
    session_maker = ctx["session_maker"]

    async with session_maker() as db:
        # Double-check DB-level idempotency (arq result TTL can expire)
        existing = await db.execute(
            select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
        )
        if existing.scalar_one_or_none():
            return  # already processed

        if event_type == "customer.subscription.updated":
            await _handle_subscription_updated(db, data_object)
        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(db, data_object)
        elif event_type == "invoice.paid":
            await _handle_invoice_paid(db, data_object)
        elif event_type == "invoice.payment_failed":
            await _handle_payment_failed(db, data_object)
        elif event_type == "checkout.session.completed":
            await _handle_checkout_completed(db, data_object)

        # Record processed event for DB-level idempotency
        db.add(WebhookEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            processed_at=datetime.now(timezone.utc),
        ))
        await db.commit()
```

**State machine transitions:**

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Set `stripe_subscription_id` + `status=active` on `TenantSubscription` |
| `customer.subscription.updated` | Sync `status`, `current_period_start/end`; if downgrade, schedule plan change |
| `customer.subscription.deleted` | Set `status=canceled`; revoke access |
| `invoice.paid` | If `status != active`, restore to `active`; clear any JWT blacklisting signals |
| `invoice.payment_failed` | Set `status=past_due`; revoke JWT tokens for tenant; enqueue payment_failed email |

### Pattern 5: JWT Token Revocation on Payment Failure

The existing system uses a Redis blacklist via `jti` (JWT ID). On payment failure, revoke all active tokens for all tenant members:

```python
# billing/service.py

async def revoke_tenant_tokens(tenant_id: UUID, redis: Redis, db: AsyncSession):
    """
    Revoke all active JWT tokens for users who are members of this tenant.

    Steps:
    1. Load all TenantMembership rows for this tenant (all members)
    2. Load all RefreshToken rows for those users
    3. Blacklist the refresh token JTIs in Redis (with ACCESS_TOKEN_TTL_HOURS TTL)
    4. Delete the RefreshToken rows (forces re-login)

    After revocation, users who try to use existing tokens will get InvalidTokenError.
    On next login, the auth dependency will reflect the restricted subscription state
    (JWT claims can include a "billing_status" claim, OR the dependency checks DB state).
    """
    # Load members
    members_result = await db.execute(
        select(TenantMembership.user_id).where(TenantMembership.tenant_id == tenant_id)
    )
    user_ids = [row[0] for row in members_result.all()]

    if not user_ids:
        return

    # Load and delete their refresh tokens
    tokens_result = await db.execute(
        select(RefreshToken).where(RefreshToken.user_id.in_(user_ids))
    )
    tokens = tokens_result.scalars().all()

    for token in tokens:
        # Blacklist in Redis (TTL = access token lifetime so blacklist auto-expires)
        ttl_seconds = settings.ACCESS_TOKEN_TTL_HOURS * 3600
        await redis.setex(f"blacklist:{token.token}", ttl_seconds, "1")

    # Delete refresh tokens to force re-login
    for token in tokens:
        await db.delete(token)
```

**Important:** The JWT `sub` claim holds `user_id`. The billing status must be checked via DB (or a short-lived cached flag) on each request for the wxcode engine proxy endpoint. Embedding billing status in JWT claims is fragile (stale after revocation). The correct pattern: check `TenantSubscription.status` in the enforcement dependency.

### Pattern 6: Plan Enforcement Dependency

```python
# billing/dependencies.py

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.auth.models import User
from wxcode_adm.billing.models import TenantSubscription, Plan
from wxcode_adm.billing.exceptions import PaymentRequiredError, QuotaExceededError, MemberLimitError
from wxcode_adm.dependencies import get_session
from wxcode_adm.tenants.dependencies import get_tenant_context
from wxcode_adm.tenants.models import Tenant, TenantMembership


async def require_active_subscription(
    ctx: tuple[Tenant, TenantMembership] = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_session),
) -> tuple[Tenant, TenantMembership, TenantSubscription]:
    """
    Dependency that enforces subscription is active before wxcode engine operations.

    Raises:
        PaymentRequiredError (HTTP 402): subscription is past_due or canceled
    """
    tenant, membership = ctx
    sub_result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
    )
    subscription = sub_result.scalar_one_or_none()

    if subscription is None or subscription.status in ("past_due", "canceled", "unpaid"):
        raise PaymentRequiredError(
            error_code="PAYMENT_REQUIRED",
            message="Subscription payment required. Visit billing settings to resolve.",
        )

    return tenant, membership, subscription


async def check_token_quota(
    ctx: tuple[Tenant, TenantMembership, TenantSubscription] = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_session),
) -> tuple[Tenant, TenantMembership, TenantSubscription]:
    """
    Dependency that enforces token quota on the free plan.
    For paid plans, passes through (overage billing handles excess).

    Adds X-Quota-Warning header at 80%+ usage.

    Raises:
        QuotaExceededError (HTTP 402): free plan quota exhausted
    """
    tenant, membership, subscription = ctx

    plan_result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
    plan = plan_result.scalar_one()

    usage_pct = subscription.tokens_used_this_period / plan.token_quota if plan.token_quota > 0 else 0

    # Free tier: hard block
    if plan.monthly_fee_cents == 0 and subscription.tokens_used_this_period >= plan.token_quota:
        raise QuotaExceededError(
            error_code="TOKEN_QUOTA_EXCEEDED",
            message=f"Free plan token quota ({plan.token_quota}) exhausted. Upgrade to continue.",
        )

    return tenant, membership, subscription  # Warning headers added in response middleware


async def check_member_cap(
    ctx: tuple[Tenant, TenantMembership] = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_session),
) -> tuple[Tenant, TenantMembership]:
    """
    Dependency that enforces member cap before invitation creation.
    All plans enforce member cap (hard limit).

    Raises:
        MemberLimitError (HTTP 402): member count at or above cap
    """
    tenant, membership = ctx
    # Count current members
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count()).select_from(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id
        )
    )
    member_count = count_result.scalar_one()

    # Get plan cap
    sub_result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
    )
    subscription = sub_result.scalar_one_or_none()
    if subscription:
        plan_result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
        plan = plan_result.scalar_one()
        if plan.member_cap > 0 and member_count >= plan.member_cap:
            raise MemberLimitError(
                error_code="MEMBER_LIMIT_REACHED",
                message=f"Plan member limit ({plan.member_cap}) reached. Upgrade to invite more members.",
            )

    return tenant, membership
```

### Pattern 7: Warning Headers for Quota

Warning headers are added at 80% and 100% token usage. Implement via a response middleware or inline in the dependency. Since FastAPI dependencies can't easily modify response headers, use a `BackgroundTask` or inject via `Response` parameter:

```python
# In the router or service that proxies to wxcode engine:
from fastapi import Response

@router.post("/engine/proxy")
async def proxy_to_engine(
    response: Response,
    ctx = Depends(check_token_quota),
    ...
):
    tenant, membership, subscription = ctx
    plan = ...  # from DB

    usage_pct = subscription.tokens_used_this_period / plan.token_quota
    if usage_pct >= 1.0:
        response.headers["X-Quota-Warning"] = "QUOTA_REACHED"
        response.headers["X-Quota-Usage"] = f"{subscription.tokens_used_this_period}/{plan.token_quota}"
    elif usage_pct >= 0.8:
        response.headers["X-Quota-Warning"] = "QUOTA_WARNING_80PCT"
        response.headers["X-Quota-Usage"] = f"{subscription.tokens_used_this_period}/{plan.token_quota}"
    ...
```

### Anti-Patterns to Avoid

- **Never parse the webhook body as JSON before signature verification:** Any Python JSON parser produces different bytes than the raw wire format. Pass `request.body()` raw bytes directly to `stripe.Webhook.construct_event()`.
- **Never query Stripe API on every enforcement check:** The local `TenantSubscription` record is the source of truth for enforcement. Query Stripe only for admin/billing management operations.
- **Never use `billing_scheme=tiered` for the flat fee component:** The flat fee uses `usage_type=licensed` + `billing_scheme=per_unit`. Tiered pricing is for the usage component, not the base fee.
- **Never skip DB-level idempotency for webhook processing:** arq `_job_id` deduplication only works while the job exists in Redis (TTL-limited). Add a `WebhookEvent` table row as a permanent DB-level idempotency record.
- **Never create a Billing Meter then try to change its event_name:** Meter configuration is immutable. Plan the `event_name` scheme before creating meters (`wxcode_tokens_{plan_slug}` pattern).
- **Never use `native_enum=True` for status enums:** Follow the existing codebase pattern: `Enum(SubscriptionStatus, native_enum=False)`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Payment page UI | Custom payment form | Stripe Checkout (hosted) | PCI compliance; Stripe handles card validation, 3DS, Apple Pay |
| Subscription management UI | Custom portal | Stripe Customer Portal | Payment method updates, invoice history, cancellation — all handled by Stripe |
| Webhook signature verification | Manual HMAC | `stripe.Webhook.construct_event()` | Stripe SDK handles timing tolerance (5-min window), constant-time comparison, replay attack prevention |
| Overage billing calculations | Custom proration | Stripe Billing Meters | Stripe aggregates meter events and invoices at period end; no calculation code needed |
| Webhook deduplication (enqueue level) | Redis SET NX manual | arq `_job_id` (atomic Redis tx) | Already available; arq guarantees no duplicate enqueue via Redis transaction |
| Token usage aggregation (for Stripe billing) | Batch aggregation job | `stripe.billing.meter_event.create()` | Stripe aggregates events; just report each operation's token count |

**Key insight:** Stripe handles the entire money movement, invoicing, and payment retry lifecycle. The application's job is to keep local subscription state synchronized via webhooks and enforce locally.

---

## Common Pitfalls

### Pitfall 1: Webhook Signature Failure from Body Parsing

**What goes wrong:** FastAPI endpoint accepts `body: dict` or `body: str` — framework JSON-parses the body before the handler sees it. `stripe.Webhook.construct_event()` receives different bytes and fails with `SignatureVerificationError`.

**Why it happens:** FastAPI automatically parses JSON bodies when the parameter type is `dict`. The raw bytes differ from the serialized JSON string (key ordering, whitespace).

**How to avoid:** Declare the body parameter as `bytes = Depends(get_raw_body)` where `get_raw_body` calls `await request.body()`. Never use `body: dict` on webhook endpoints.

**Warning signs:** `stripe.error.SignatureVerificationError` in production logs but signature appears valid in Stripe Dashboard. Body is being parsed before verification.

### Pitfall 2: Billing Meter event_name Immutability

**What goes wrong:** A billing meter is created with `event_name="wxcode_tokens"`. Later, a plan is renamed and you try to update the meter's `event_name` to match. Stripe returns an error — `event_name` is immutable after creation.

**Why it happens:** Stripe's meter API only allows updating `display_name`. All other fields are set once.

**How to avoid:** Use stable, plan-slug-based event names: `wxcode_tokens_{plan_slug}`. Store the meter ID in the `Plan` table. If a plan's slug cannot change (it maps to a Stripe object), document this constraint.

**Warning signs:** Stripe API error `400: Cannot update event_name` when trying to edit a meter.

### Pitfall 3: Legacy Metered Pricing (Pre-Deprecation) Confusion

**What goes wrong:** Following old Stripe documentation or blog posts that show `recurring[usage_type]=metered` WITHOUT a `meter` parameter. This creates a legacy metered price. As of API version `2025-03-31.basil`, Stripe no longer allows creating metered prices without a meter.

**Why it happens:** Search results often return older content. Legacy examples show `aggregate_usage=sum` on prices — this is the deprecated pattern.

**How to avoid:** Always use the new path: create a `billing.Meter` first, then create a Price with `recurring[meter]=meter_id`. Verify the stripe-python version being used supports `billing.meters`.

**Warning signs:** Stripe API returning `400: aggregate_usage is not supported in this API version`.

### Pitfall 4: Double-Processing Webhooks (arq TTL Expiry)

**What goes wrong:** arq's `_job_id` prevents duplicate enqueue only while the job exists in Redis. Default arq result TTL is 1 second by default (configurable). Stripe retries webhooks for up to 72 hours. After the arq result expires, a retry of the same event creates a second job.

**Why it happens:** arq deletes job results from Redis after they expire. A new enqueue with the same `_job_id` succeeds once the old result is gone.

**How to avoid:** Add a `WebhookEvent` table with a `UNIQUE` constraint on `stripe_event_id`. The webhook processor checks this table at the start of each job. If the event ID already exists, return immediately (no-op). This provides permanent DB-level idempotency that outlasts Redis TTL.

**Warning signs:** Subscription restored from `past_due` → `active` twice, or duplicate emails sent for payment failure.

### Pitfall 5: Forgetting execution_options on TenantModel Queries

**What goes wrong:** `Plan` might inherit `TenantModel` if it has a `tenant_id` column. Any SELECT on it without `.execution_options(_tenant_enforced=True)` raises `TenantIsolationError`.

**Why it happens:** Phase 1 guard fires on all `TenantModel` subclasses.

**How to avoid:** `Plan` should NOT inherit `TenantModel` — it is platform-level data (managed by super-admin, applies to all tenants). Use `Base + TimestampMixin` with `tenant_id=NULL` convention (see `TenantModel` docstring: "Platform-wide data (plans, settings) uses tenant_id = NULL"). `TenantSubscription` similarly is NOT a `TenantModel` subclass — it's the tenant's record accessed by platform code.

**Warning signs:** `TenantIsolationError: Unguarded query on TenantModel subclass 'Plan'` — then `Plan` inherited wrong base class.

### Pitfall 6: Stripe Customer Not Created at Tenant Formation

**What goes wrong:** Tenant is created, but `stripe_customer_id` is added to `TenantSubscription` lazily (only when user tries to check out). Checkout session creation then fails because no customer exists.

**Why it happens:** Deferred Stripe Customer creation is a common optimization, but it creates a workflow gap.

**How to avoid:** Create a Stripe Customer synchronously during workspace creation (`POST /api/v1/onboarding/workspace`). Store `stripe_customer_id` in `TenantSubscription` immediately. The free plan subscription record is also inserted at this point.

**Warning signs:** `InvalidRequestError: No such customer: None` when creating checkout sessions for tenants that haven't previously subscribed.

### Pitfall 7: conftest Missing Billing Model Import

**What goes wrong:** `billing.models` not imported in `_build_sqlite_metadata()` in `conftest.py`. Billing tables don't exist in SQLite test DB.

**Why it happens:** Same pattern as Phase 3 pitfall 4.

**How to avoid:** Add `import wxcode_adm.billing.models  # noqa: F401` to `_build_sqlite_metadata()` and the `test_db` fixture alongside existing model imports.

**Warning signs:** `OperationalError: no such table: plans` in test output.

---

## Code Examples

Verified patterns from official sources:

### Stripe Billing Meter Creation

```python
# Source: https://docs.stripe.com/billing/subscriptions/usage-based-v1/use-cases/flat-fee-and-overages
# + https://docs.stripe.com/api/billing/meter/create

meter = await stripe_client.billing.meters.create_async(params={
    "display_name": "wxcode Tokens",
    "event_name": "wxcode_tokens_starter",   # unique, immutable after creation
    "default_aggregation": {"formula": "sum"},
    "customer_mapping": {
        "event_payload_key": "stripe_customer_id",
        "type": "by_id",
    },
    "value_settings": {"event_payload_key": "value"},
})
# → meter.id = "mtr_..."
```

### Recording Token Usage (Meter Event)

```python
# Source: https://docs.stripe.com/api/billing/meter-event/create
# Call this from the wxcode engine proxy after a request completes

event = stripe.billing.meter_event.create(
    event_name="wxcode_tokens_starter",
    payload={
        "value": tokens_consumed,           # integer, whole numbers only
        "stripe_customer_id": stripe_customer_id,
    },
    identifier=f"{request_id}_{tenant_id}",  # UUID for idempotency (24h rolling window)
)
```

### Webhook Signature Verification (FastAPI)

```python
# Source: https://blog.frank-mich.com/fastapi-stripe-webhook-template/
# + Stripe docs on webhook signature

async def get_raw_body(request: Request) -> bytes:
    """Raw bytes — must NOT be parsed JSON."""
    return await request.body()

@webhook_router.post("/webhooks/stripe")
async def stripe_webhook(
    stripe_signature: Annotated[str, Header(alias="stripe-signature")],
    body: bytes = Depends(get_raw_body),
) -> dict:
    try:
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET.get_secret_value(),
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400) from exc

    pool = await get_arq_pool()
    try:
        await pool.enqueue_job(
            "process_stripe_event",
            event["id"], event["type"], event["data"]["object"],
            _job_id=event["id"],
        )
    finally:
        await pool.aclose()
    return {"received": True}
```

### arq Job ID Deduplication

```python
# Source: https://arq-docs.helpmanual.io/ — _job_id parameter
# Returns None if job with this ID already exists (queued or running)

job = await pool.enqueue_job(
    "process_stripe_event",
    event_id, event_type, data_object,
    _job_id=event_id,   # Stripe event ID — atomic Redis tx prevents duplicate enqueue
)
# job is None if already queued → idempotent by design
```

### Checkout Session (Hybrid: Flat Fee + Metered)

```python
# Source: https://docs.stripe.com/billing/subscriptions/usage-based-v1/use-cases/flat-fee-and-overages

session = await stripe_client.checkout.sessions.create_async(params={
    "customer": tenant_subscription.stripe_customer_id,
    "mode": "subscription",
    "line_items": [
        # Fixed monthly fee
        {"price": plan.stripe_price_id, "quantity": 1},
        # Metered overage (quantity=1 required but Stripe ignores it for metered prices)
        {"price": plan.stripe_overage_price_id, "quantity": 1},
    ],
    "success_url": f"{settings.FRONTEND_URL}/billing?session_id={{CHECKOUT_SESSION_ID}}",
    "cancel_url": f"{settings.FRONTEND_URL}/billing?canceled=true",
    "metadata": {"tenant_id": str(tenant.id), "plan_id": str(plan.id)},
})
return session.url  # redirect user to this URL
```

### Customer Portal Session

```python
# Source: https://docs.stripe.com/customer-management/integrate-customer-portal

portal_session = await stripe_client.billing_portal.sessions.create_async(params={
    "customer": tenant_subscription.stripe_customer_id,
    "return_url": f"{settings.FRONTEND_URL}/billing",
})
return portal_session.url  # redirect user to this URL
```

### Error Classes for Billing

```python
# billing/exceptions.py — following existing AppError pattern

class PaymentRequiredError(AppError):
    """Subscription payment required — HTTP 402."""
    def __init__(self, error_code: str = "PAYMENT_REQUIRED", message: str = "Payment required"):
        super().__init__(error_code=error_code, message=message, status_code=402)

class QuotaExceededError(AppError):
    """Token quota exhausted (free tier hard block) — HTTP 402."""
    def __init__(self, error_code: str = "TOKEN_QUOTA_EXCEEDED", message: str = "Token quota exceeded"):
        super().__init__(error_code=error_code, message=message, status_code=402)

class MemberLimitError(AppError):
    """Plan member cap reached — HTTP 402."""
    def __init__(self, error_code: str = "MEMBER_LIMIT_REACHED", message: str = "Member limit reached"):
        super().__init__(error_code=error_code, message=message, status_code=402)
```

**Note:** The main.py `AppError` exception handler already handles all `AppError` subclasses. Add `PaymentRequiredError`, `QuotaExceededError`, and `MemberLimitError` to `billing/exceptions.py`. No changes to `main.py` are needed — the existing handler translates all `AppError` instances to `{"error_code": ..., "message": ...}` JSON.

### Alembic Migration Import

```python
# alembic/env.py — add after existing imports
from wxcode_adm.billing import models as _billing_models  # noqa: F401
# Un-comment the existing placeholder line:
# from wxcode_adm.billing import models as _  # noqa
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Legacy `usage_type=metered` without meter | Billing Meters API (`billing.Meter` + `billing.MeterEvent`) | 2025-03-31.basil | Must create meter first; event names are plan-specific |
| `stripe.api_key = "..."` (global) | `StripeClient("sk_...")` | stripe-python v8+ | No global state; async via `_async` suffix methods |
| `aggregate_usage` on Price | `recurring.meter` on Price | 2025-03-31.basil | Price creation now references a Meter ID |
| `UsageRecord.create()` | `billing.meter_event.create()` | 2025-03-31.basil | New API path; identifier replaces idempotency_key pattern |

**Deprecated/outdated:**
- `stripe.SubscriptionItem.create_usage_record()`: Removed in API v2025-03-31.basil
- `aggregate_usage` parameter on Price: Removed in API v2025-03-31.basil
- Legacy `usage_type=metered` without meter: No longer creatable in current API versions

---

## Codebase Integration Notes

These are facts specific to this codebase that the planner MUST know:

### TenantModel Guard Applies to Billing Models If Misused

`Plan` and `TenantSubscription` should NOT inherit `TenantModel`. They are platform-level. The TenantModel docstring says "Platform-wide data (plans, settings) uses tenant_id = NULL" — this refers to the nullable `tenant_id` column pattern. For `Plan` and `TenantSubscription`, use `Base + TimestampMixin` directly (no `tenant_id` column at all for `Plan`; `TenantSubscription.tenant_id` is a real FK to tenants, not the TenantModel isolation mechanism).

### Webhook Router Must Use Different Auth Pattern

The `/webhooks/stripe` endpoint must NOT use `require_verified` or any JWT auth dependency. Stripe does not send JWT tokens — it sends a `Stripe-Signature` header. The router must be registered WITHOUT the JWT auth middleware applied.

### conftest.py Needs Billing Model Import

Add `import wxcode_adm.billing.models  # noqa: F401` to BOTH `_build_sqlite_metadata()` and `test_db` in `conftest.py`. This is the same pattern used for Phase 3 tenants models.

### arq WorkerSettings Must Register Billing Jobs

`billing/service.py` or `billing/email.py` will define arq job functions (`process_stripe_event`, `send_payment_failed_email`). These must be added to `WorkerSettings.functions` in `tasks/worker.py`.

### config.py Needs Stripe Keys

Add to `Settings` in `config.py`:
```python
STRIPE_SECRET_KEY: SecretStr
STRIPE_PUBLISHABLE_KEY: str
STRIPE_WEBHOOK_SECRET: SecretStr
FRONTEND_URL: str = "http://localhost:3060"
```

### Tenant Subscription Created During Workspace Onboarding

The `POST /api/v1/onboarding/workspace` endpoint (Phase 3) creates a `Tenant`. Phase 4 must hook into this to also create a Stripe Customer + `TenantSubscription` record on the free plan. Options:
1. Modify the onboarding service to call Stripe Customer creation (coupling but simple)
2. Add a post-creation hook / separate init step

Recommendation: Modify the onboarding service to create the Stripe Customer and insert `TenantSubscription` in the same DB transaction (or immediately after, with Stripe as the external call).

### main.py Exception Handler Already Handles 402

The global `AppError` handler in `main.py` returns `status_code=exc.status_code` — so `PaymentRequiredError` (status_code=402) will be correctly returned as HTTP 402 without any main.py changes. This is the existing codebase pattern.

### billing/__init__.py Is Already Empty

Phase 1 created a placeholder `billing/__init__.py` (empty). Phase 4 fills in the module. No need to create the directory.

---

## Open Questions

1. **Token usage counter: Redis or PostgreSQL?**
   - What we know: `tokens_used_this_period` needs to be fast (checked on every engine request) and accurate (basis for enforcement). Redis INCR is O(1) and atomic. PostgreSQL UPDATE requires a row lock.
   - Recommendation: Store the canonical count in `TenantSubscription.tokens_used_this_period` (PostgreSQL) but use Redis as a fast read-ahead cache (`token_usage:{tenant_id}:{period_start_date}`). The wxcode engine proxy increments Redis atomically; a periodic flush (or webhook-triggered reset at period start) syncs back to PostgreSQL. This avoids PostgreSQL row contention on every request while keeping durable state. If simplicity is preferred, start with PostgreSQL-only (fast enough for the expected load at launch).

2. **Post-checkout redirect destination (Claude's Discretion)**
   - Recommendation: Redirect to `/billing?session_id={CHECKOUT_SESSION_ID}`. The billing page fetches the session status to confirm the subscription is active and shows the new plan. A dashboard redirect is simpler but doesn't confirm success to the user.

3. **How to handle downgrade scheduling**
   - What we know: Downgrades take effect at end of current billing period. Stripe `subscription_schedule` API handles deferred plan changes. Alternatively, set `proration_behavior=none` + `billing_cycle_anchor=unchanged` on `subscription.update()` with `trial_end="now"` for immediate effect.
   - Recommendation: For simplicity, use `stripe.Subscription.modify(sub_id, cancel_at_period_end=False, items=[{"id": item_id, "price": new_price_id}], proration_behavior="none")` at period end via webhook on `customer.subscription.updated`. Or simpler: use Stripe's built-in subscription update with `billing_cycle_anchor=unchanged` — Stripe handles the transition at period end automatically when you use their Customer Portal.

4. **Stripe Webhook Secret for local development**
   - The `stripe listen --forward-to localhost:8060/api/v1/webhooks/stripe` CLI provides a local webhook secret. Add to `.env` as `STRIPE_WEBHOOK_SECRET`.
   - For tests: mock `stripe.Webhook.construct_event()` to return a predefined event dict.

---

## Sources

### Primary (HIGH confidence)
- Official Stripe docs: https://docs.stripe.com/api/billing/meter/create — Billing Meter creation parameters
- Official Stripe docs: https://docs.stripe.com/api/billing/meter-event/create — Meter event creation
- Official Stripe docs: https://docs.stripe.com/billing/subscriptions/usage-based-v1/use-cases/flat-fee-and-overages — Flat fee + overage model (curl examples verified)
- Official Stripe docs: https://docs.stripe.com/customer-management/integrate-customer-portal — Portal session creation
- Official Stripe docs: https://docs.stripe.com/billing/subscriptions/webhooks — Subscription webhook events
- Official Stripe docs: https://docs.stripe.com/changelog/basil/2025-03-31/deprecate-legacy-usage-based-billing — Legacy deprecation confirmation
- stripe-python PyPI page: https://pypi.org/project/stripe/ — Latest version 14.3.0, async support
- stripe-python GitHub README: https://github.com/stripe/stripe-python — StripeClient API, `_async` suffix pattern
- arq official docs: https://arq-docs.helpmanual.io/ — `_job_id` deduplication, enqueue_job parameters
- wxcode_adm codebase (all source files read above) — existing patterns, session lifecycle, auth blacklist

### Secondary (MEDIUM confidence)
- Stripe webhook docs: https://docs.stripe.com/webhooks — Raw body requirement, signature verification, idempotency guidance
- FastAPI + Stripe webhook template: https://blog.frank-mich.com/fastapi-stripe-webhook-template/ — Raw body dependency pattern (cross-verified with Stripe docs)
- stripe-python DeepWiki: https://deepwiki.com/stripe/stripe-python/6.2-async-support — Async StripeClient usage

### Tertiary (LOW confidence — needs validation against final implementation)
- arq `_job_id` TTL behavior: Stated in arq GitHub issues — test in integration to confirm result TTL default
- `check_member_cap` enforcement point: Inferred from CONTEXT decisions; exact endpoint location (invitation router vs. dedicated dep) needs planning decision

---

## Metadata

**Confidence breakdown:**
- Standard stack (stripe-python 14.x): HIGH — Verified via PyPI page (v14.3.0, Jan 2026), GitHub README
- Billing Meters API: HIGH — Verified via official Stripe docs; deprecation timeline verified
- Webhook pattern (raw body, sig verify): HIGH — Official Stripe docs + cross-verified with community template
- arq deduplication (_job_id): HIGH — Official arq docs; existing worker.py confirms arq 0.27.0 in project
- Subscription state machine: HIGH — Official Stripe subscription webhook docs
- Architecture (Plan/TenantSubscription models): HIGH — Follows established codebase patterns
- Token quota enforcement: MEDIUM — Design is correct; Redis vs PostgreSQL counter tradeoff is Claude's Discretion
- Downgrade scheduling details: LOW — Stripe supports multiple approaches; exact implementation is planning-time decision

**Research date:** 2026-02-23
**Valid until:** 2026-03-23 (Stripe APIs are stable; stripe-python minor releases won't break patterns)
