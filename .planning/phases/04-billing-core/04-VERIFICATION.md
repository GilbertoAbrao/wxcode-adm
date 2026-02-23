---
phase: 04-billing-core
verified: 2026-02-23T20:30:00Z
status: passed
score: 19/19 must-haves verified
re_verification: false
---

# Phase 4: Billing Core Verification Report

**Phase Goal:** Tenants can subscribe to a paid plan, manage their billing, and the system enforces plan limits before any wxcode engine operation is allowed
**Verified:** 2026-02-23T20:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

All truths are verified across the five plan must_haves sections.

#### Plan 04-01 Truths (BILL-01)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Super-admin can create a billing plan with name, slug, fees, token quota, overage rate, and member cap | VERIFIED | `billing/router.py` POST `/admin/billing/plans/`, `billing/service.py create_plan`, test `test_superadmin_create_plan` passes |
| 2 | Super-admin can update plan details (name, fees, limits, is_active toggle) | VERIFIED | `billing/router.py` PATCH `/{plan_id}`, `billing/service.py update_plan`, test `test_superadmin_update_plan` passes |
| 3 | Super-admin can soft-delete a plan (set is_active=False) | VERIFIED | `billing/router.py` DELETE `/{plan_id}`, `billing/service.py delete_plan` sets `is_active=False`, test `test_superadmin_delete_plan` passes |
| 4 | Plan creation syncs to Stripe: creates a Billing Meter, Product, flat-fee Price, and overage Price | VERIFIED | `billing/service.py create_plan` lines 77-132: calls `stripe_client.billing.meters.create_async`, `stripe_client.products.create_async`, `stripe_client.prices.create_async` (twice), back-fills IDs |
| 5 | Plan update syncs price changes to Stripe (archives old Price, creates new one) | VERIFIED | `billing/service.py update_plan` lines 188-229: `stripe_client.prices.update_async(active=False)` then `create_async` for changed prices |
| 6 | Non-super-admin users cannot access plan CRUD endpoints (403) | VERIFIED | `require_superuser` dependency in `billing/router.py` raises `ForbiddenError`, test `test_nonsuperadmin_cannot_create_plan` passes with 403 |
| 7 | Any authenticated user can list active plans (public catalog) | VERIFIED | `GET /billing/plans` requires only `require_verified`, test `test_list_active_plans` passes |

#### Plan 04-02 Truths (BILL-02)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 8 | When a workspace is created, a Stripe Customer is created and a TenantSubscription record is inserted with status=free on the free plan | VERIFIED | `tenants/service.py create_workspace` lazy-imports and calls `create_stripe_customer` + `bootstrap_free_subscription`; test `test_workspace_creates_free_subscription` passes |
| 9 | Tenant member with billing_access can create a Stripe Checkout session for a plan | VERIFIED | `billing/router.py POST /billing/checkout` with `require_billing_access` dep; test `test_checkout_creates_session` passes |
| 10 | Checkout session URL is returned for client-side redirect to Stripe-hosted payment page | VERIFIED | `create_checkout_session` returns `(session.url, session.id)`; test asserts `checkout_url == "https://checkout.stripe.com/test"` |
| 11 | Checkout session includes both flat-fee and metered overage line items | VERIFIED | `billing/service.py create_checkout_session` lines 508-512: flat-fee always added; overage added if `stripe_overage_price_id is not None` |
| 12 | Free plan tenants cannot check out to the free plan again (no double-subscribe) | VERIFIED | Guard at line 476-480 raises `ConflictError(CANNOT_CHECKOUT_FREE)`; test `test_checkout_rejects_free_plan` passes with 409 |

#### Plan 04-03 Truths (BILL-03)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 13 | Stripe webhook POST with valid signature returns 200 and event is enqueued to arq | VERIFIED | `billing/webhook_router.py` enqueues via `pool.enqueue_job("process_stripe_event", ..., _job_id=event["id"])`, returns `{"received": True}` |
| 14 | Stripe webhook POST with invalid signature returns 400 | VERIFIED | `webhook_router.py` lines 66-68: catches `stripe.SignatureVerificationError`, raises `HTTPException(400)` |
| 15 | checkout.session.completed sets stripe_subscription_id and status=active | VERIFIED | `_handle_checkout_completed` sets `subscription.stripe_subscription_id`, `subscription.plan_id`, `status=ACTIVE`; test `test_webhook_checkout_completed` passes |
| 16 | customer.subscription.updated syncs status, current_period_start/end, resets tokens on period change | VERIFIED | `_handle_subscription_updated` lines 716-772: maps Stripe status, syncs timestamps, resets `tokens_used_this_period` when period changes |
| 17 | customer.subscription.deleted sets status=canceled | VERIFIED | `_handle_subscription_deleted` sets `status=CANCELED`; test `test_webhook_subscription_deleted` passes |
| 18 | invoice.paid restores status to active if it was past_due | VERIFIED | `_handle_invoice_paid` checks `status == PAST_DUE` then sets `ACTIVE`; test `test_webhook_invoice_paid_restores` passes |
| 19 | invoice.payment_failed sets status=past_due, revokes tenant JWT tokens, and enqueues payment_failed email | VERIFIED | `_handle_payment_failed` lines 824-918: sets `PAST_DUE`, deletes `RefreshToken` rows, blacklists JTIs in Redis, enqueues `send_payment_failed_email`; test `test_webhook_payment_failed` passes |
| 20 | Duplicate webhook events are processed at most once (arq _job_id + DB WebhookEvent idempotency) | VERIFIED | `process_stripe_event` checks `WebhookEvent` table first; webhook enqueued with `_job_id=event["id"]`; test `test_webhook_idempotency` confirms count=1 |

#### Plan 04-04 Truths (BILL-04 + BILL-05)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 21 | Tenant member with billing_access can open Stripe Customer Portal | VERIFIED | `billing/router.py POST /billing/portal` with `require_billing_access`; `create_portal_session` calls `stripe_client.billing_portal.sessions.create_async`; test `test_portal_returns_url` passes |
| 22 | Any tenant member can view their current subscription status | VERIFIED | `GET /billing/subscription` uses `get_tenant_context` (no billing_access required); test `test_subscription_status_endpoint` passes |
| 23 | Portal session URL is returned for client-side redirect | VERIFIED | `create_portal_session` returns `portal.url`; router returns `{"portal_url": url}` |
| 24 | When tenant subscription is past_due or canceled, wxcode engine requests get HTTP 402 | VERIFIED | `_enforce_active_subscription` raises `PaymentRequiredError(402)`; `require_active_subscription` calls it; tests `test_past_due_tenant_blocked_by_require_active_subscription` and `test_canceled_tenant_blocked_by_require_active_subscription` pass |
| 25 | Free tier tenants are hard-blocked at token quota with HTTP 402 and upgrade prompt | VERIFIED | `_enforce_token_quota` raises `QuotaExceededError(402)` for free tier at quota; test `test_free_tier_blocked_at_quota` passes via `pytest.raises(QuotaExceededError)` |
| 26 | Paid tier tenants are allowed to exceed quota (overage billing, never blocked) | VERIFIED | `_enforce_token_quota` only enforces when `monthly_fee_cents == 0`; paid tier falls through without exception |
| 27 | Member invitations are blocked when tenant hits member_cap with HTTP 402 | VERIFIED | `enforce_member_cap` called in `tenants/router.py create_invitation`; test `test_member_cap_blocks_invitation` passes with 402 |
| 28 | Warning headers appear at 80% and 100% of token quota in API responses | VERIFIED | `check_token_quota` sets `X-Quota-Warning: QUOTA_WARNING_80PCT` at >=80% and `QUOTA_REACHED` at >=100%, with `X-Quota-Usage` header |

#### Plan 04-05 Truths (migration + tests)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 29 | Alembic migration 003 creates plans, tenant_subscriptions, and webhook_events tables | VERIFIED | `003_add_billing_tables.py` exists with `op.create_table` for all 3 tables, correct columns and FK constraints |
| 30 | conftest.py imports billing models so SQLite test DB includes billing tables | VERIFIED | `conftest.py` lines 86, 114: `import wxcode_adm.billing.models` in both `_build_sqlite_metadata` and `test_db` fixture |
| 31 | Integration tests verify all 5 Phase 4 success criteria | VERIFIED | 19 tests collected and passed; all SC1-SC5 covered |
| 32 | Tests use mocked Stripe calls (no real Stripe API in CI) | VERIFIED | `conftest.py` lines 243-317: `_FakeStripeClient` patched at both `stripe_client_module` and `billing_service_module` |
| 33 | All existing tests still pass (no regressions) | VERIFIED | Full suite: 73 passed |

**Score:** 33/33 truths verified (condensed to 19/19 plan must_haves)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/src/wxcode_adm/billing/models.py` | Plan, TenantSubscription, WebhookEvent SQLAlchemy models | VERIFIED | All 3 models present; SubscriptionStatus enum with native_enum=False; correct columns |
| `backend/src/wxcode_adm/billing/exceptions.py` | PaymentRequiredError, QuotaExceededError, MemberLimitError | VERIFIED | All 3 classes extend AppError, status_code=402, accept optional kwargs |
| `backend/src/wxcode_adm/billing/stripe_client.py` | StripeClient singleton | VERIFIED | `stripe_client: StripeClient = StripeClient(...)` exported at module level |
| `backend/src/wxcode_adm/billing/service.py` | Plan CRUD + checkout + portal + webhook processor functions | VERIFIED | All functions present: create_plan, update_plan, delete_plan, list_plans, get_plan, create_stripe_customer, get_free_plan, bootstrap_free_subscription, create_checkout_session, create_portal_session, get_subscription_status, process_stripe_event + 5 handlers |
| `backend/src/wxcode_adm/billing/router.py` | billing_admin_router + billing_router with all endpoints | VERIFIED | billing_admin_router (5 routes), billing_router (4 routes: /plans, /checkout, /portal, /subscription) |
| `backend/src/wxcode_adm/billing/schemas.py` | CreatePlanRequest, UpdatePlanRequest, PlanResponse, CheckoutRequest, CheckoutResponse, SubscriptionResponse | VERIFIED | All 6 schemas present with correct field definitions |
| `backend/src/wxcode_adm/billing/webhook_router.py` | POST /webhooks/stripe endpoint | VERIFIED | `webhook_router` router with `stripe_webhook` handler; raw body + signature verification |
| `backend/src/wxcode_adm/billing/dependencies.py` | require_active_subscription, check_token_quota, check_member_cap, enforce_member_cap, _enforce_active_subscription, _enforce_token_quota | VERIFIED | All 6 functions present; private helpers are pure sync |
| `backend/src/wxcode_adm/billing/email.py` | send_payment_failed_email arq job | VERIFIED | Function present; follows auth/email.py pattern (logs + SMTP wrapped in try/except) |
| `backend/alembic/versions/003_add_billing_tables.py` | Migration creating 3 billing tables | VERIFIED | upgrade() creates plans, tenant_subscriptions, webhook_events; downgrade() reverses; correct FK/index constraints |
| `backend/tests/test_billing.py` | 19 integration tests covering all SC1-SC5 | VERIFIED | 19 tests; all pass in 2.96s |
| `backend/tests/conftest.py` | Updated with billing model imports and Stripe mocks | VERIFIED | Billing models imported in both fixture locations; Stripe client fully mocked; free plan auto-seeded |
| `backend/alembic/env.py` | billing model import for autogenerate | VERIFIED | `from wxcode_adm.billing import models as _billing_models  # noqa: F401` at line 19 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `billing/router.py` | `billing/service.py` | service function calls in route handlers | WIRED | All 5 admin routes call `service.create_plan/update_plan/delete_plan/list_plans/get_plan`; billing_router calls `service.create_checkout_session/create_portal_session/get_subscription_status/list_plans` |
| `billing/service.py` | `billing/stripe_client.py` | stripe_client async API calls | WIRED | `stripe_client` imported at module top; calls `stripe_client.billing.meters.create_async`, `stripe_client.products.create_async`, `stripe_client.prices.create_async`, etc. |
| `main.py` | `billing/router.py` | app.include_router | WIRED | Lines 160-162: `from wxcode_adm.billing.router import billing_admin_router, billing_router`; both included under `settings.API_V1_PREFIX` |
| `main.py` | `billing/webhook_router.py` | app.include_router for webhook | WIRED | Lines 165-166: `from wxcode_adm.billing.webhook_router import webhook_router as billing_webhook_router`; included under `API_V1_PREFIX` |
| `tenants/service.py` | `billing/service.py` | create_stripe_customer + bootstrap_free_subscription in create_workspace | WIRED | Lazy import at lines 178-181 inside `create_workspace`; both functions called after workspace flush |
| `billing/router.py` | `billing/service.py` | create_checkout_session call | WIRED | `POST /billing/checkout` calls `service.create_checkout_session(db, tenant.id, body.plan_id)` |
| `billing/service.py` | `billing/stripe_client.py` | customers.create_async and checkout.sessions.create_async | WIRED | `create_stripe_customer` calls `stripe_client.customers.create_async`; `create_checkout_session` calls `stripe_client.checkout.sessions.create_async` |
| `billing/webhook_router.py` | arq queue | pool.enqueue_job with _job_id=stripe_event_id | WIRED | Line 75-82: `pool.enqueue_job("process_stripe_event", event["id"], event["type"], event["data"]["object"], _job_id=event["id"])` |
| `billing/service.py` | `billing/models.py` | TenantSubscription and WebhookEvent queries | WIRED | `process_stripe_event` queries `WebhookEvent` for idempotency; all handlers query `TenantSubscription` |
| `billing/service.py` | `auth/models.py` | RefreshToken queries for JWT revocation | WIRED | `_handle_payment_failed` lazy-imports `RefreshToken`, queries all tokens for user_ids, deletes them, blacklists JTIs |
| `billing/router.py` | `billing/service.py` | create_portal_session and get_subscription_status calls | WIRED | `POST /billing/portal` calls `service.create_portal_session`; `GET /billing/subscription` calls `service.get_subscription_status` |
| `billing/dependencies.py` | `billing/models.py` | TenantSubscription and Plan queries for enforcement | WIRED | `require_active_subscription`, `check_token_quota`, `check_member_cap`, `enforce_member_cap` all query TenantSubscription and Plan |
| `tenants/router.py` | `billing/dependencies.py` | check_member_cap on invitation endpoint | WIRED | `create_invitation` handler lazy-imports `enforce_member_cap` (line 426) and calls it before `service.invite_user` |
| `billing/dependencies.py` | `_enforce_token_quota / _enforce_active_subscription` | private helpers called by public dependencies | WIRED | `require_active_subscription` calls `_enforce_active_subscription(subscription)`; `check_token_quota` calls `_enforce_token_quota(plan, subscription)` |
| `tests/conftest.py` | `billing/models.py` | model import for SQLite table creation | WIRED | `import wxcode_adm.billing.models` in both `_build_sqlite_metadata` and `test_db` fixture |
| `tests/conftest.py` | `billing/webhook_router.py` | get_arq_pool mock | WIRED | `monkeypatch.setattr(webhook_router_module, "get_arq_pool", mock_get_arq_pool)` at line 228 |
| `tests/test_billing.py` | `billing/router.py` | HTTP endpoint tests | WIRED | Tests call `/api/v1/admin/billing/plans/`, `/api/v1/billing/checkout`, `/api/v1/billing/portal`, `/api/v1/billing/subscription` |
| `tests/test_billing.py` | `billing/dependencies.py` | direct call to _enforce_token_quota and _enforce_active_subscription | WIRED | Tests import and call private helpers inside `pytest.raises(QuotaExceededError)` and `pytest.raises(PaymentRequiredError)` |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| BILL-01 | 04-01, 04-05 | Super-admin can CRUD billing plans (synced with Stripe) | SATISFIED | `billing_admin_router` with 5 CRUD endpoints; `create_plan` syncs Meter+Product+flat-fee+overage Price; 5 passing tests (SC1) |
| BILL-02 | 04-02, 04-05 | User can subscribe to a plan via Stripe Checkout | SATISFIED | `POST /billing/checkout` creates Stripe Checkout session with flat-fee + overage line items; workspace onboarding bootstraps free TenantSubscription; 3 passing tests (SC2) |
| BILL-03 | 04-03, 04-05 | Stripe webhooks sync subscription state (paid, updated, deleted, failed) | SATISFIED | `process_stripe_event` handles 5 event types; payment_failed revokes JWT tokens + sends email; two-layer idempotency; 5 passing tests (SC3) |
| BILL-04 | 04-04, 04-05 | User can manage billing via Stripe Customer Portal | SATISFIED | `POST /billing/portal` returns Stripe portal URL; `GET /billing/subscription` returns subscription details; 1 passing test (SC4) + subscription status test |
| BILL-05 | 04-04, 04-05 | Plan limits enforced before wxcode engine operations | SATISFIED | `require_active_subscription` blocks past_due/canceled; `check_token_quota` hard-blocks free tier at quota + sets warning headers; `enforce_member_cap` blocks invitations at cap; 5 passing tests (SC5) |

All 5 BILL-* requirements satisfied. No orphaned requirements.

---

### Anti-Patterns Found

None detected. Scanned all 11 billing source files and 2 test/infra files for:
- TODO/FIXME/placeholder comments: none
- Empty implementations (return null/[]/{}): none — all service functions have substantive implementations
- Console.log-only handlers: not applicable (Python)
- Stub API routes: none — all endpoints delegate to real service functions that query DB and call Stripe

Notable: `send_payment_failed_email` in `billing/email.py` always logs first (DEV pattern) but the actual SMTP send is wrapped in try/except — this is intentional design matching `auth/email.py` pattern, not a stub.

---

### Human Verification Required

The following items cannot be verified programmatically and require manual testing with real Stripe test keys:

#### 1. Stripe Checkout Session End-to-End

**Test:** Replace `.env` placeholder keys with real Stripe test keys (`sk_test_...`, `whsec_...`), create a plan via admin API, create a workspace, POST to `/billing/checkout`, open the returned `checkout_url` in a browser.
**Expected:** Stripe-hosted checkout page loads for the correct plan with flat monthly fee and metered overage line items visible.
**Why human:** Requires real Stripe API; fake client returns a static URL that cannot validate actual checkout page content.

#### 2. Stripe Webhook Pipeline End-to-End

**Test:** Using `stripe listen --forward-to localhost:8060/api/v1/webhooks/stripe`, complete a Stripe Checkout in a browser. Observe that the TenantSubscription row in the DB transitions from `status=free` to `status=active`.
**Expected:** `process_stripe_event` arq job runs and updates subscription status.
**Why human:** Requires real Stripe event delivery + running arq worker process; unit tests mock the arq queue and call `process_stripe_event` directly.

#### 3. Stripe Customer Portal End-to-End

**Test:** With a real Stripe Customer ID in `TenantSubscription.stripe_customer_id`, POST to `/billing/portal`. Open the returned `portal_url` in a browser.
**Expected:** Stripe Customer Portal loads, shows subscription management options.
**Why human:** Requires real Stripe Customer ID and live portal session; fake client returns a static URL.

#### 4. Payment Failure Email Delivery

**Test:** Trigger a payment failure in Stripe test dashboard (use a card that always fails). Observe that the payment failure email arrives at the owner's inbox.
**Expected:** Email received with subject "[WXCODE] Payment failed for {workspace_name}".
**Why human:** Requires real SMTP configuration and Stripe test event delivery.

---

## Summary

Phase 4 goal is fully achieved. All five BILL requirements are satisfied:

- **BILL-01 (Plan CRUD):** Super-admin can create, update, and soft-delete billing plans. Each plan creation triggers Stripe Meter + Product + flat-fee Price + overage Price creation (non-blocking). Non-super-admin gets HTTP 403.

- **BILL-02 (Checkout):** Every workspace creation bootstraps a free `TenantSubscription`. Members with `billing_access` or Owner role can create a Stripe Checkout session for paid plans. Free plan checkout is rejected with 409.

- **BILL-03 (Webhooks):** `POST /api/v1/webhooks/stripe` verifies Stripe-Signature and returns 200 in the fast path; processing is async via arq. Five event types handled: checkout activation, subscription updates with period rollover detection, deletion/cancellation, invoice payment restoration, and payment failure with JWT revocation + email notification. Two-layer idempotency prevents duplicate processing.

- **BILL-04 (Portal):** `POST /billing/portal` generates a Stripe Customer Portal URL for billing-access members. `GET /billing/subscription` returns current subscription status with plan details to any tenant member.

- **BILL-05 (Enforcement):** `require_active_subscription` blocks HTTP 402 for past_due/canceled subscriptions. `check_token_quota` hard-blocks free-tier tenants at quota (never blocks paid). `enforce_member_cap` integrated into invitation creation. Warning headers at 80%/100% quota. Private sync helpers `_enforce_active_subscription` and `_enforce_token_quota` are directly testable without FastAPI Depends.

All 73 tests pass (19 billing + 54 existing auth/tenant). No regressions. Migration 003 creates the three billing tables with correct constraints. Alembic env.py imports billing models for autogenerate support.

---

_Verified: 2026-02-23T20:30:00Z_
_Verifier: Claude (gsd-verifier)_
