---
phase: 04-billing-core
plan: 01
subsystem: payments
tags: [stripe, billing, fastapi, sqlalchemy, pydantic]

# Dependency graph
requires:
  - phase: 02-auth-core
    provides: User model with is_superuser field, require_verified dependency, auth exception classes
  - phase: 03-multi-tenancy-and-rbac
    provides: Tenant model (tenants.id FK target), TimestampMixin pattern, native_enum=False enum convention

provides:
  - stripe[async]==14.3.0 SDK integrated via modern StripeClient pattern
  - Plan model (platform-level billing tiers with Stripe sync IDs)
  - TenantSubscription model (per-tenant subscription state)
  - WebhookEvent model (Stripe webhook idempotency log)
  - SubscriptionStatus enum with native_enum=False
  - PaymentRequiredError, QuotaExceededError, MemberLimitError (HTTP 402)
  - billing/service.py: create_plan (Stripe Meter+Product+Price sync), update_plan, delete_plan, list_plans, get_plan
  - billing_admin_router: 5 super-admin CRUD endpoints at /api/v1/admin/billing/plans
  - billing_router: public plan catalog at /api/v1/billing/plans

affects:
  - 04-02 (tenant subscription endpoints will use TenantSubscription model and billing service)
  - 04-03 (webhook handler uses WebhookEvent for idempotency)
  - 04-04 (quota enforcement uses QuotaExceededError, MemberLimitError, PaymentRequiredError)
  - 04-05 (alembic migration 003 creates plans, tenant_subscriptions, webhook_events tables)

# Tech tracking
tech-stack:
  added:
    - "stripe[async]==14.3.0 — modern StripeClient async pattern"
  patterns:
    - "StripeClient singleton at module level (not per-request) — matches redis_client pattern"
    - "Stripe sync non-blocking — failures log warning, plan record remains authoritative"
    - "Soft-delete via is_active=False — hard delete blocked by FK constraint from TenantSubscription"
    - "native_enum=False on SubscriptionStatus — consistent with MemberRole pattern from Phase 3"
    - "from __future__ import annotations in models.py and service.py — Python 3.9 compat"

key-files:
  created:
    - backend/src/wxcode_adm/billing/exceptions.py
    - backend/src/wxcode_adm/billing/stripe_client.py
    - backend/src/wxcode_adm/billing/models.py
    - backend/src/wxcode_adm/billing/schemas.py
    - backend/src/wxcode_adm/billing/service.py
    - backend/src/wxcode_adm/billing/router.py
  modified:
    - backend/pyproject.toml
    - backend/src/wxcode_adm/config.py
    - backend/src/wxcode_adm/main.py

key-decisions:
  - "stripe[async]==14.3.0 uses modern StripeClient (not legacy stripe.api_key global) — supports async calls via _async suffix on methods"
  - "Stripe failures are non-blocking — wrapped in try/except with logger.warning; plan DB record is authoritative"
  - "Plan soft-deleted via is_active=False — hard delete intentionally blocked by TenantSubscription FK constraint"
  - "overage_rate_cents_per_token stored as integer hundredths of a cent (e.g., 4 = $0.00004/token) — avoids float precision issues"
  - "member_cap=-1 convention means unlimited members"
  - "Stripe IDs excluded from PlanResponse — internal implementation detail, not exposed to API consumers"
  - "require_superuser dependency wraps require_verified and adds is_superuser guard — 403 ForbiddenError for non-superusers"

patterns-established:
  - "Billing router pattern: billing_admin_router (super-admin) + billing_router (authenticated) — mirrors auth/tenant router split"
  - "Stripe sync pattern: flush ORM first to get ID, then sync, then back-fill Stripe IDs"

requirements-completed:
  - BILL-01

# Metrics
duration: 3min
completed: 2026-02-23
---

# Phase 4 Plan 01: Billing Foundation Summary

**Stripe SDK integration with Plan CRUD API: StripeClient singleton, billing models (Plan/TenantSubscription/WebhookEvent), and super-admin plan management with Stripe Meter+Product+Price synchronization**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-23T19:34:56Z
- **Completed:** 2026-02-23T19:38:07Z
- **Tasks:** 2
- **Files modified:** 9 (6 created, 3 modified)

## Accomplishments

- Billing foundation with Plan, TenantSubscription, WebhookEvent SQLAlchemy models and SubscriptionStatus enum (native_enum=False)
- stripe[async]==14.3.0 integrated via modern StripeClient singleton pattern with full async support
- Super-admin plan CRUD API at /api/v1/admin/billing/plans with Stripe synchronization (creates Billing Meter, Product, flat-fee Price, overage Price on plan creation)

## Task Commits

Each task was committed atomically:

1. **Task 1: Stripe SDK, config, billing models, exceptions, stripe_client** - `424ce72` (feat)
2. **Task 2: Plan CRUD service, schemas, router, and main.py wiring** - `6116a39` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified

- `backend/pyproject.toml` - Added stripe[async]==14.3.0 dependency
- `backend/src/wxcode_adm/config.py` - Added STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET, FRONTEND_URL settings
- `backend/src/wxcode_adm/billing/exceptions.py` - PaymentRequiredError, QuotaExceededError, MemberLimitError (all HTTP 402, accept optional kwargs)
- `backend/src/wxcode_adm/billing/stripe_client.py` - StripeClient singleton using modern pattern
- `backend/src/wxcode_adm/billing/models.py` - Plan, TenantSubscription (SubscriptionStatus enum, native_enum=False), WebhookEvent
- `backend/src/wxcode_adm/billing/schemas.py` - CreatePlanRequest, UpdatePlanRequest, PlanResponse (Stripe IDs excluded)
- `backend/src/wxcode_adm/billing/service.py` - create_plan (Stripe Meter+Product+Price sync), update_plan (price re-sync), delete_plan (soft), list_plans, get_plan
- `backend/src/wxcode_adm/billing/router.py` - billing_admin_router (5 super-admin routes) + billing_router (1 public catalog route)
- `backend/src/wxcode_adm/main.py` - Wired billing_admin_router and billing_router under /api/v1

## Decisions Made

- **StripeClient pattern**: Using modern `StripeClient(api_key)` constructor (not legacy `stripe.api_key = ...` global). All async calls use `_async` suffix: `stripe_client.products.create_async(params={...})`.
- **Non-blocking Stripe sync**: All Stripe API calls wrapped in try/except. Stripe failure logs a warning but the plan DB record is created/updated regardless. The plan is the source of truth; Stripe IDs are back-filled.
- **Soft-delete only**: `delete_plan` sets `is_active=False`, no hard delete. Hard delete would violate FK constraint from `TenantSubscription.plan_id` if any tenant is subscribed.
- **overage_rate_cents_per_token**: Integer hundredths of a cent (4 = $0.00004/token) for precision without floating-point arithmetic.
- **member_cap=-1**: Sentinel value for unlimited members on premium plans.
- **Stripe IDs hidden**: `PlanResponse` schema excludes all `stripe_*` fields — internal implementation details not needed by API consumers.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

Real Stripe API keys needed for actual billing functionality. Current `.env` has placeholder values (`sk_test_placeholder`, etc.) that allow app startup but will fail at Stripe API call time.

For Phase 4 testing with real Stripe:
1. Create a Stripe test account at https://dashboard.stripe.com/test/apikeys
2. Replace `.env` placeholder values with real test keys
3. Set `STRIPE_WEBHOOK_SECRET` from Stripe CLI: `stripe listen --print-secret`

## Next Phase Readiness

- Plan CRUD and Stripe sync infrastructure complete — ready for Plan 04-02 (tenant subscription endpoints)
- TenantSubscription model ready for subscription management service
- WebhookEvent model ready for Plan 04-03 (webhook handler with idempotency)
- All 3 billing exceptions ready for Plan 04-04 (quota enforcement middleware)
- Alembic migration 003 in Plan 04-05 will create `plans`, `tenant_subscriptions`, `webhook_events` tables

---
*Phase: 04-billing-core*
*Completed: 2026-02-23*
