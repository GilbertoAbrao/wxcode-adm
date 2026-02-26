---
phase: 08-super-admin
plan: 04
subsystem: api
tags: [mrr, dashboard, migration, alembic, sqlalchemy, pytest, integration-tests, jwt, admin]

# Dependency graph
requires:
  - phase: 08-02
    provides: suspend_tenant, soft_delete_tenant service functions (using getattr guards)
  - phase: 08-03
    provides: block_user, force_password_reset service functions (using hasattr guards)

provides:
  - MRR dashboard endpoint GET /admin/dashboard/mrr with 30-day trend
  - Alembic migration 007 adding 4 Boolean columns to tenants, tenant_memberships, users
  - is_suspended, is_deleted on Tenant model (direct column declarations)
  - is_blocked on TenantMembership model (direct column declaration)
  - password_reset_required on User model (direct column declaration)
  - 18 integration tests covering all 5 Phase 8 success criteria (SC1-SC5)

affects:
  - production deployment (migration 007 must run before app startup)
  - all tenant-context requests (is_suspended, is_deleted, is_blocked enforcement now direct)
  - all user requests (password_reset_required enforcement now direct)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Python-side 30-day trend grouping (no PostgreSQL date_trunc) for dashboard computation
    - Direct attribute access replaces hasattr() guards once migration columns exist
    - server_default=false on Boolean columns so existing rows never default to None

key-files:
  created:
    - backend/alembic/versions/007_add_super_admin_columns.py
    - backend/tests/test_super_admin.py
  modified:
    - backend/src/wxcode_adm/admin/schemas.py
    - backend/src/wxcode_adm/admin/service.py
    - backend/src/wxcode_adm/admin/router.py
    - backend/src/wxcode_adm/tenants/models.py
    - backend/src/wxcode_adm/tenants/dependencies.py
    - backend/src/wxcode_adm/auth/models.py
    - backend/src/wxcode_adm/auth/dependencies.py

key-decisions:
  - "Python-side 30-day trend grouping: load all relevant subscriptions in one query, iterate days in Python — avoids PostgreSQL date_trunc anti-pattern identified in research"
  - "MRR trend uses updated_at as proxy for cancellation date (TenantSubscription has no canceled_at column) — acceptable approximation for dashboard purposes"
  - "server_default=sa.text('false') on all 4 new Boolean columns — existing rows get False immediately, no data migration needed"
  - "hasattr() guards replaced with direct attribute access after migration 007 declares columns on models — cleaner code, migration 007 must run before deployment"
  - "httpx DELETE doesn't support json= kwarg — use client.request('DELETE', ..., content=json.dumps(...)) pattern in tests"

patterns-established:
  - "MRR dashboard: pure Python aggregation, no Stripe API calls, all data from local DB"
  - "Integration test helper _create_workspace() normalizes WorkspaceCreatedResponse to {id, name} dict for test convenience"
  - "Super-admin seeded directly via test_db fixture (_seed_super_admin helper) — no lifespan call needed in tests"

requirements-completed: [SADM-05, SADM-01, SADM-02, SADM-03, SADM-04]

# Metrics
duration: 7min
completed: 2026-02-26
---

# Phase 8 Plan 04: MRR Dashboard, Migration 007, and Integration Tests Summary

**MRR dashboard endpoint with 30-day trend/churn, migration 007 adding 4 Boolean columns, and 18 integration tests covering all 5 Phase 8 super-admin success criteria**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-26T00:16:41Z
- **Completed:** 2026-02-26T00:23:21Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- MRR dashboard computes active_subscription_count, mrr_cents, plan_distribution, churn_rate, and 30-day trend from local DB without Stripe API calls
- Migration 007 safely adds 4 Boolean columns (is_suspended, is_deleted, is_blocked, password_reset_required) with server_default=false to 3 tables
- 18 integration tests covering all 5 SADM success criteria — all 147 tests (129 existing + 18 new) pass

## Task Commits

Each task was committed atomically:

1. **Task 1: MRR dashboard + migration 007 + model columns** - `77f1c6c` (feat)
2. **Task 2: Integration tests for all 5 Phase 8 success criteria** - `c0b3ff3` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `backend/alembic/versions/007_add_super_admin_columns.py` - Migration adding is_suspended, is_deleted (tenants), is_blocked (tenant_memberships), password_reset_required (users)
- `backend/tests/test_super_admin.py` - 18 integration tests: SC1 pagination/filter, SC2 suspend/reactivate/soft-delete, SC3 user search/detail, SC4 block/force-reset, SC5 JWT isolation, MRR dashboard
- `backend/src/wxcode_adm/admin/schemas.py` - PlanDistributionItem, MRRTrendPoint, MRRDashboardResponse schemas replacing placeholder
- `backend/src/wxcode_adm/admin/service.py` - compute_mrr_dashboard() with Python-side 30-day trend aggregation
- `backend/src/wxcode_adm/admin/router.py` - GET /admin/dashboard/mrr endpoint
- `backend/src/wxcode_adm/tenants/models.py` - is_suspended, is_deleted on Tenant; is_blocked on TenantMembership
- `backend/src/wxcode_adm/tenants/dependencies.py` - hasattr() guards replaced with direct attribute access
- `backend/src/wxcode_adm/auth/models.py` - password_reset_required on User model
- `backend/src/wxcode_adm/auth/dependencies.py` - hasattr() guard replaced with direct attribute access

## Decisions Made

- Python-side 30-day trend grouping over PostgreSQL date_trunc — avoids research-identified anti-pattern, simpler for small subscription counts
- updated_at used as proxy for cancellation date since TenantSubscription has no canceled_at column — acceptable for dashboard trend approximation
- server_default=sa.text('false') on all new Boolean columns — existing rows immediately get False, no data migration needed
- hasattr() guards removed now that migration 007 declares columns directly on models
- httpx.AsyncClient.delete() doesn't accept json= kwarg — use client.request('DELETE', ..., content=json.dumps(...)) pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] httpx DELETE request format**
- **Found during:** Task 2 (integration tests)
- **Issue:** httpx AsyncClient.delete() doesn't accept json= kwarg, causing TypeError
- **Fix:** Used client.request("DELETE", url, content=json.dumps(...)) pattern for the soft-delete test
- **Files modified:** backend/tests/test_super_admin.py
- **Verification:** test_soft_delete_tenant passes
- **Committed in:** c0b3ff3 (Task 2 commit)

**2. [Rule 1 - Bug] Workspace response structure**
- **Found during:** Task 2 (integration tests)
- **Issue:** _create_workspace helper used wrong request body key (workspace_name instead of name) and wrong response access (ws["id"] instead of ws["tenant"]["id"])
- **Fix:** Fixed request body to {"name": name}, added normalization to extract tenant.id from WorkspaceCreatedResponse
- **Files modified:** backend/tests/test_super_admin.py
- **Verification:** All 18 tests pass
- **Committed in:** c0b3ff3 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both auto-fixes discovered during Task 2 test execution. No scope creep.

## Issues Encountered

None — both deviations were minor HTTP client API details discovered during test execution and fixed immediately.

## User Setup Required

None — migration 007 runs automatically via alembic upgrade head in the API container entrypoint. No external service configuration required.

## Next Phase Readiness

- Phase 8 is complete. All 4 plans done (01-04).
- All 5 SADM success criteria verified by integration tests.
- Production deployment requires running alembic upgrade head (migration 007 adds 4 Boolean columns).
- No blockers.

---
*Phase: 08-super-admin*
*Completed: 2026-02-26*
