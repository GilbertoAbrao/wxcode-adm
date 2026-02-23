---
phase: 03-multi-tenancy-and-rbac
plan: 05
subsystem: testing
tags: [alembic, migration, pytest, pytest-asyncio, integration-tests, rbac, multi-tenancy, invitations, ownership-transfer]

# Dependency graph
requires:
  - phase: 03-multi-tenancy-and-rbac
    provides: Tenant models, membership service, invitation service, ownership transfer service, router endpoints
  - phase: 02-auth-core
    provides: User model, JWT auth, verify-email flow, conftest fixtures

provides:
  - Alembic migration 002 creating all 4 Phase 3 tables (tenants, tenant_memberships, invitations, ownership_transfers)
  - 33 integration tests covering all 6 Phase 3 success criteria
  - Verified auto-join flow: new user invitation auto-join triggers at verify-email with no separate accept step
  - Cross-tenant isolation confirmed: users cannot see other tenants' data

affects:
  - phase 04 (billing): tenant schema now deployable; tests confirm RBAC surface works correctly

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Track pre-signup OTP keys in Redis to identify new user's key without ambiguity
    - conftest.py patches both auth_service and tenant_service get_arq_pool for email mocking
    - Integration tests use _signup_verify_login helper with key-tracking to handle multiple concurrent users

key-files:
  created:
    - backend/alembic/versions/002_add_tenants_memberships_invitations_transfers.py
    - backend/tests/test_tenants.py
  modified:
    - backend/tests/conftest.py

key-decisions:
  - "conftest.py must patch tenant_service_module.get_arq_pool in addition to auth_service_module — invite_user calls get_arq_pool for email jobs"
  - "_signup_verify_login tracks pre-signup OTP keys in Redis to correctly identify new user's OTP key when multiple users exist in test DB"
  - "migration 002 uses String(20) for role columns (not native Enum) — consistent with native_enum=False decision from Plan 03-01"

patterns-established:
  - "Alembic migrations: create tables in FK dependency order, drop in reverse; use op.f() for all constraint names"
  - "Integration tests: each test is fully self-contained, creates its own users/workspaces/invitations"
  - "Helper _setup_member_with_role delegates to _signup_verify_login for correct OTP tracking"

requirements-completed:
  - TNNT-01
  - TNNT-02
  - TNNT-03
  - TNNT-04
  - TNNT-05
  - RBAC-01
  - RBAC-02
  - RBAC-03

# Metrics
duration: 6min
completed: 2026-02-23
---

# Phase 03 Plan 05: Migration + Integration Tests Summary

**Alembic migration 002 for 4 tenant tables and 33 integration tests proving all Phase 3 success criteria including dual invitation flows (existing-user accept + new-user auto-join at verify-email)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-23T15:52:06Z
- **Completed:** 2026-02-23T15:58:00Z
- **Tasks:** 2
- **Files modified:** 3 (migration created, test file created, conftest modified)

## Accomplishments

- Created deployable Alembic migration 002 with correct revision chain (down_revision="001"), creating tenants, tenant_memberships, invitations (with billing_access Boolean after role), and ownership_transfers tables
- All 33 integration tests pass covering every Phase 3 success criterion, including the critical locked decision: new users are auto-joined at email verification — no separate /invitations/accept step needed
- Phase 2 test suite (21 tests) still passes — zero regressions
- Cross-tenant isolation confirmed: user A cannot access tenant B's data, each user sees only their own members

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic migration 002 for tenant tables** - `eccca70` (feat)
2. **Task 2: Integration tests + conftest fix** - `c73c816` (feat)

## Files Created/Modified

- `backend/alembic/versions/002_add_tenants_memberships_invitations_transfers.py` — Migration creating all 4 Phase 3 tables with constraints, indexes, and FK relationships; billing_access Boolean column in invitations after role column
- `backend/tests/test_tenants.py` — 33 integration tests covering SC1-SC6; uses _signup_verify_login helper with pre-signup OTP key tracking; _setup_member_with_role helper for RBAC tests
- `backend/tests/conftest.py` — Added monkeypatch for tenant_service_module.get_arq_pool (was only patching auth service; invitation endpoint also calls get_arq_pool)

## Decisions Made

- conftest.py must patch `tenant_service_module.get_arq_pool` alongside `auth_service_module.get_arq_pool` — the invite_user service function calls get_arq_pool to enqueue invitation email jobs, which would fail without a mock
- `_signup_verify_login` now tracks Redis OTP keys existing BEFORE signup, then finds the newly created key after signup — this correctly identifies the right user's OTP when multiple users exist in the test database
- Alembic migration uses `String(20)` for role columns (matching `native_enum=False` from Plan 03-01) rather than native PostgreSQL ENUM type

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] conftest.py was only mocking auth service arq pool, not tenant service**
- **Found during:** Task 2 (test_invite_user_by_email test failure)
- **Issue:** The invitation endpoint calls `get_arq_pool()` from the tenant service module to send invitation emails. conftest.py was only monkeypatching `auth_service_module.get_arq_pool` but the tenant service imported its own reference. Test was attempting real Redis connection to localhost:6379 and failing with ConnectionError.
- **Fix:** Added `monkeypatch.setattr(tenant_service_module, "get_arq_pool", mock_get_arq_pool)` to conftest.py client fixture
- **Files modified:** `backend/tests/conftest.py`
- **Verification:** test_invite_user_by_email passes; all 33 tests pass
- **Committed in:** c73c816 (Task 2 commit)

**2. [Rule 1 - Bug] _signup_verify_login helper was ambiguous when multiple users exist in test DB**
- **Found during:** Task 2 (planning test execution, identifying potential issue)
- **Issue:** Original helper scanned all auth:otp:* keys and took the last one, but tests create multiple users sequentially in the same test — there would be multiple OTP keys and no guarantee of picking the right one (verify-email uses email+code, wrong code would return 400)
- **Fix:** Rewrote helper to record OTP keys existing BEFORE signup, then finds the NEW key created after signup — uniquely identifies this user's OTP key
- **Files modified:** `backend/tests/test_tenants.py`
- **Verification:** Tests with multiple users (e.g., test_new_user_auto_joins_multiple_invitations) pass correctly
- **Committed in:** c73c816 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 - Bug)
**Impact on plan:** Both fixes necessary for tests to function correctly. No scope creep.

## Issues Encountered

None beyond the two auto-fixed bugs above.

## Next Phase Readiness

- Phase 3 is complete. Migration 002 is deployable. All 7 requirements (TNNT-01 through TNNT-05, RBAC-01 through RBAC-03) are satisfied and tested.
- Phase 4 (Billing) can begin: multi-tenant membership surface is ready; billing_access toggle is implemented on TenantMembership and Invitation

---
*Phase: 03-multi-tenancy-and-rbac*
*Completed: 2026-02-23*
