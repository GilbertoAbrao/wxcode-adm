---
phase: 04-billing-core
plan: 02
subsystem: payments
tags: [stripe, billing, checkout, fastapi, sqlalchemy, pydantic]

# Dependency graph
requires:
  - phase: 04-01
    provides: Plan/TenantSubscription/WebhookEvent models, billing service, stripe_client singleton

provides:
  - billing/service.py: create_stripe_customer (best-effort Stripe Customer at workspace onboarding)
  - billing/service.py: get_free_plan (returns active plan with monthly_fee_cents=0)
  - billing/service.py: bootstrap_free_subscription (creates TenantSubscription status=FREE)
  - billing/service.py: create_checkout_session (Stripe Checkout with flat-fee + metered overage)
  - tenants/service.py: create_workspace now bootstraps Stripe Customer + TenantSubscription(FREE)
  - billing/schemas.py: CheckoutRequest, CheckoutResponse, SubscriptionResponse
  - billing/router.py: require_billing_access dependency (billing_access=True or Owner role)
  - billing/router.py: POST /billing/checkout endpoint returning checkout_url + session_id

affects:
  - 04-03 (webhook handler will activate subscriptions created via checkout)
  - 04-04 (quota enforcement uses the TenantSubscription bootstrapped here)
  - 04-05 (alembic migration creates tenant_subscriptions table for bootstrapped records)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy import inside create_workspace body for billing bootstrap — avoids circular import (same pattern as auto_join_pending_invitations for auth.service)"
    - "Best-effort Stripe Customer creation — RuntimeError raised only for missing free plan (hard requirement); Stripe failures log warning and set stripe_customer_id=None"
    - "Checkout line_items: flat fee always included; overage item included only if stripe_overage_price_id is not None"
    - "require_billing_access: billing_access=True OR Owner role — billing_access is a per-member toggle"

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/billing/service.py
    - backend/src/wxcode_adm/tenants/service.py
    - backend/src/wxcode_adm/billing/schemas.py
    - backend/src/wxcode_adm/billing/router.py

key-decisions:
  - "Lazy import inside create_workspace for billing service — avoids circular import billing.service -> tenants.models -> billing.service at module load"
  - "create_stripe_customer is best-effort: Stripe failure logs WARNING, returns None; checkout flow creates customer lazily if stripe_customer_id is None"
  - "bootstrap_free_subscription raises RuntimeError if no free plan exists — free plan is a hard system requirement (must be seeded); this is a programming error not a user error"
  - "POST /billing/checkout uses PaymentRequiredError (not NotFoundError) for missing subscription — aligns with billing exception hierarchy from Plan 04-01"
  - "require_billing_access: Owner bypasses billing_access toggle — Owner always has implicit full access"
  - "SubscriptionResponse schema defined now for Plan 04-04 use — avoids modifying schemas.py again later"
  - "schemas.py: UpdatePlanRequest uses Optional[str] instead of str | None — improves Python 3.9 dev env compatibility while from __future__ annotations handles runtime"

requirements-completed:
  - BILL-02

# Metrics
duration: 3min
completed: 2026-02-23
---

# Phase 4 Plan 02: Stripe Customer + Checkout Session Summary

**Workspace onboarding now bootstraps a Stripe Customer and free TenantSubscription; POST /billing/checkout generates a Stripe-hosted payment page URL with flat-fee and metered overage line items**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-23T19:40:46Z
- **Completed:** 2026-02-23T19:43:46Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Every new workspace creation now calls `create_stripe_customer` (best-effort) and `bootstrap_free_subscription`, giving each tenant a Stripe Customer ID and a `TenantSubscription(status=FREE)` record from day one
- `POST /billing/checkout` endpoint creates a Stripe Checkout session with both the flat monthly fee and metered overage line items; returns `checkout_url` and `session_id` for client-side redirect
- `require_billing_access` dependency enforces the billing_access toggle per CONTEXT.md: Owner always has access, other roles need explicit `billing_access=True` on their membership

## Task Commits

Each task was committed atomically:

1. **Task 1: Stripe Customer creation + free plan bootstrap** - `a5e8695` (feat)
2. **Task 2: Stripe Checkout session endpoint** - `ea8da17` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/billing/service.py` - Added `create_stripe_customer`, `get_free_plan`, `bootstrap_free_subscription`, `create_checkout_session`; imported `PaymentRequiredError`, `SubscriptionStatus`, `TenantSubscription`
- `backend/src/wxcode_adm/tenants/service.py` - Modified `create_workspace` to call Stripe Customer creation + free plan bootstrap via lazy import
- `backend/src/wxcode_adm/billing/schemas.py` - Added `CheckoutRequest`, `CheckoutResponse`, `SubscriptionResponse`; updated `UpdatePlanRequest` to use `Optional[X]` for wider compatibility
- `backend/src/wxcode_adm/billing/router.py` - Added `require_billing_access` dependency, `POST /billing/checkout` endpoint; added imports for `get_tenant_context`, `MemberRole`, `Tenant`, `TenantMembership`

## Decisions Made

- **Lazy import pattern**: `create_workspace` imports billing service functions inside the function body to avoid circular imports at module load time. This matches the established pattern from `auto_join_pending_invitations` in Plan 03-03.
- **Best-effort Stripe Customer**: `create_stripe_customer` returns `None` on any Stripe error. The `bootstrap_free_subscription` accepts `None` and stores it on the `TenantSubscription`. The checkout endpoint detects `None` and creates the Stripe Customer lazily.
- **PaymentRequiredError for missing subscription**: The plan spec explicitly requires `PaymentRequiredError` (not `NotFoundError`) when a tenant has no subscription record — semantically correct since this indicates a billing setup problem.
- **`SubscriptionResponse` defined now**: Even though it's primarily used in Plan 04-04, defining it in Plan 04-02 avoids a second schemas.py modification pass.
- **`require_billing_access` guards**: Owner bypasses the `billing_access` toggle entirely — this matches the established `billing_access` design from Phase 3 CONTEXT.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

Files verified:
- `backend/src/wxcode_adm/billing/service.py` — FOUND
- `backend/src/wxcode_adm/tenants/service.py` — FOUND
- `backend/src/wxcode_adm/billing/schemas.py` — FOUND
- `backend/src/wxcode_adm/billing/router.py` — FOUND

Commits verified:
- `a5e8695` — FOUND (Task 1)
- `ea8da17` — FOUND (Task 2)

---
*Phase: 04-billing-core*
*Completed: 2026-02-23*
