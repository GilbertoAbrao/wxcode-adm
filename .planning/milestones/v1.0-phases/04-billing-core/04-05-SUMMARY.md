---
phase: 04-billing-core
plan: 05
subsystem: testing
tags: [alembic, stripe, pytest, billing, migration, webhook, quota, member-cap]

# Dependency graph
requires:
  - phase: 04-billing-core
    provides: Plans CRUD, checkout, webhook processor, portal, enforcement dependencies (Plans 01-04)
provides:
  - Alembic migration 003 creating plans, tenant_subscriptions, webhook_events tables
  - Test infrastructure with Stripe mocks and billing DB setup
  - 19 integration tests covering all 5 Phase 4 success criteria
affects: [05-api-gateway, future-phases-using-billing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Stripe client mock via monkeypatch on both stripe_client_module and service module (module-level binding requires both)
    - Free plan seeded in test_db fixture so all workspace-creating tests work without explicit setup
    - redis_client mock at common.redis_client module level for payment_failed token revocation
    - tasks.worker.get_arq_pool mock covers lazy imports in service functions

key-files:
  created:
    - backend/alembic/versions/003_add_billing_tables.py
    - backend/tests/test_billing.py
  modified:
    - backend/alembic/env.py
    - backend/tests/conftest.py

key-decisions:
  - "Stripe client must be mocked in both stripe_client_module and billing_service_module — service.py copies the reference at import time via `from wxcode_adm.billing.stripe_client import stripe_client`"
  - "redis_client in _handle_payment_failed is lazily imported; patch at wxcode_adm.common.redis_client source module"
  - "tasks.worker.get_arq_pool patched at source so billing service lazy import picks up mock"
  - "Free plan seeded in test_db fixture (not per-test) — all workspace creation calls bootstrap_free_subscription which requires a free plan"
  - "Member cap test uses DB direct update to set member_cap=1 (owner-only) then verifies invitation returns 402"
  - "Admin plan CRUD endpoints use trailing slash (/api/v1/admin/billing/plans/) — FastAPI prefix+route combines to /plans/ path"

patterns-established:
  - "Billing test pattern: seed data via test_db direct session, assert via both HTTP response and DB query"
  - "Webhook job tests: call process_stripe_event(ctx, event_id, event_type, data_object) directly with ctx={session_maker: test_db}"
  - "Enforcement tests: call _enforce_token_quota and _enforce_active_subscription directly inside pytest.raises() to verify enforcement fires"

requirements-completed: [BILL-01, BILL-02, BILL-03, BILL-04, BILL-05]

# Metrics
duration: 7min
completed: 2026-02-23
---

# Phase 4 Plan 5: Migration 003 + Integration Tests Summary

**Alembic migration 003 for billing tables (plans, tenant_subscriptions, webhook_events) with 19 pytest integration tests proving all 5 Phase 4 billing success criteria**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-23T19:54:18Z
- **Completed:** 2026-02-23T20:01:18Z
- **Tasks:** 2 of 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- Migration 003 manually written following migration 002 patterns, creating plans, tenant_subscriptions, and webhook_events tables with correct FK constraints, indexes, and pk/uq naming via op.f()
- Test infrastructure updated: Stripe client fully mocked in conftest (both stripe_client_module and service module), redis_client mocked for payment_failed token revocation, free plan auto-seeded per test
- 19 integration tests passing: 5 plan CRUD (SC1), 3 checkout flow (SC2), 5 webhook state machine (SC3), 1 portal (SC4), 5 enforcement (SC5) — all 73 tests in suite pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic migration 003 + env.py billing import + conftest billing setup** - `05fdfbf` (feat)
2. **Task 2: Integration tests for all 5 Phase 4 success criteria** - `db6d3e9` (feat)

**Plan metadata:** TBD (docs commit)

## Files Created/Modified

- `backend/alembic/versions/003_add_billing_tables.py` - Migration creating plans, tenant_subscriptions, webhook_events tables with correct column definitions, FK constraints (CASCADE on tenant_id), and named indexes
- `backend/alembic/env.py` - Uncommented billing model import for autogenerate support
- `backend/tests/conftest.py` - Added billing model imports to test_db fixture, Stripe client mock (_FakeStripeClient with all needed async methods), redis_client mock for payment_failed, free plan auto-seed
- `backend/tests/test_billing.py` - 19 integration tests covering all BILL-01 through BILL-05 requirements

## Decisions Made

- Stripe client mock applied to both the source module and service module: `service.py` does `from wxcode_adm.billing.stripe_client import stripe_client` which creates a module-level copy — patching only the source module leaves the service's copy unchanged.
- `redis_client` in `_handle_payment_failed` is lazily imported (`from wxcode_adm.common.redis_client import redis_client`) — Python's module cache returns the patched value if we patch the source module attribute.
- `get_arq_pool` in billing service is also lazily imported inside `_handle_payment_failed` from `wxcode_adm.tasks.worker` — patching at source covers it without needing a service-module attribute.
- Free plan seeded in `test_db` fixture rather than per-test: `create_workspace` always calls `bootstrap_free_subscription` which requires a free plan; seeding once per test avoids repetition in all workspace-creating tests.
- Member cap test sets `member_cap=1` via direct DB update to make the already-present owner (count=1) equal the cap, then asserts the next invitation returns 402.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Stripe client mock must patch service module binding too**
- **Found during:** Task 1 (conftest.py Stripe mock setup)
- **Issue:** Plan's conftest instructions only patched `stripe_client_module.stripe_client`. The service module imports `from wxcode_adm.billing.stripe_client import stripe_client` creating a separate module-level binding. Patching only the source module left the service using the real Stripe client, causing `Invalid API Key` errors.
- **Fix:** Added `monkeypatch.setattr(billing_service_module, "stripe_client", fake_stripe)` alongside the source module patch.
- **Files modified:** `backend/tests/conftest.py`
- **Committed in:** 05fdfbf (Task 1 commit)

**2. [Rule 2 - Missing Critical] redis_client mock needed for payment_failed test**
- **Found during:** Task 1/2 (webhook payment_failed test)
- **Issue:** `_handle_payment_failed` uses `redis_client.setex()` to blacklist JWT JTIs. Without mocking, it attempted a real Redis connection and failed with `ConnectionError`.
- **Fix:** Added `monkeypatch.setattr(redis_client_module, "redis_client", test_redis)` to conftest client fixture.
- **Files modified:** `backend/tests/conftest.py`
- **Committed in:** db6d3e9 (Task 2 commit)

**3. [Rule 2 - Missing Critical] Free plan seed required in test_db fixture**
- **Found during:** Task 1 (running existing tenant tests after billing integration)
- **Issue:** Previously passing tenant tests (test_create_workspace_returns_slug etc.) now failed with `RuntimeError: No active free plan found`. Adding billing model imports to conftest created billing tables in test DB, and `create_workspace` calls `bootstrap_free_subscription` which requires a free plan to exist.
- **Fix:** Added free plan seed inside `test_db` fixture after creating tables, before yielding the session_maker.
- **Files modified:** `backend/tests/conftest.py`
- **Committed in:** 05fdfbf (Task 1 commit)

**4. [Rule 1 - Bug] Member cap test logic corrected**
- **Found during:** Task 2 (test_member_cap_blocks_invitation)
- **Issue:** Plan's test sketch counted invitations for cap checking. The actual `enforce_member_cap` counts `TenantMembership` rows (actual members, not pending invitations). Creating invitations without accepting them doesn't add members, so the cap was never hit.
- **Fix:** Changed test to directly update `plan.member_cap=1` via DB session (matching the owner's count of 1), then assert the next invitation returns 402.
- **Files modified:** `backend/tests/test_billing.py`
- **Committed in:** db6d3e9 (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (2 missing critical, 1 missing critical regression, 1 bug)
**Impact on plan:** All auto-fixes necessary for test infrastructure correctness. No scope creep — all changes kept within Task 1 and 2 boundaries.

## Issues Encountered

- Plan 05 Task 2 notes called `_seed_free_plan(test_db)` as a helper in tests. Since the free plan is now auto-seeded in `test_db` fixture, individual tests that need the free plan ID query it from DB rather than calling the helper. Cleaner and avoids duplicate slug conflicts.

## Next Phase Readiness

- Phase 4 (Billing Core) is now fully complete: all 5 plans done, all 5 BILL-* requirements verified by tests
- Migration 003 is ready to run against PostgreSQL via `alembic upgrade head`
- 73 tests pass (no regressions across auth, tenant, and billing domains)
- Phase 5 (API Gateway) can use billing enforcement dependencies directly

---
*Phase: 04-billing-core*
*Completed: 2026-02-23*
