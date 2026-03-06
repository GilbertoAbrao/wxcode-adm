---
phase: 11-billing-integration-fixes
plan: "01"
subsystem: payments
tags: [stripe, jwt, redis, blacklist, billing, admin-auth, integration-test]

# Dependency graph
requires:
  - phase: 07-session-management
    provides: blacklist_jti helper and UserSession.access_token_jti for session revocation
  - phase: 08-super-admin
    provides: require_admin dependency enforcing admin-audience JWT isolation
  - phase: 04-billing-core
    provides: _handle_payment_failed webhook handler and billing admin router
provides:
  - Correct access token blacklisting in _handle_payment_failed via UserSession.access_token_jti + blacklist_jti
  - Admin-audience JWT enforcement on all 5 billing admin endpoints via require_admin
  - E2E integration test proving payment failure -> PAST_DUE -> JTI blacklisted -> 401
affects: [v1.0-certification, gap-closure, INT-01, INT-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy import of UserSession + blacklist_jti inside _handle_payment_failed to avoid circular imports"
    - "Admin-audience JWT enforcement via require_admin (not local require_superuser) on billing admin routes"
    - "E2E webhook test pattern: seed paid plan, activate via checkout webhook, fire payment_failed, assert status + Redis key + HTTP 401"

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/billing/service.py
    - backend/src/wxcode_adm/billing/router.py
    - backend/tests/test_billing.py

key-decisions:
  - "[11-01]: _handle_payment_failed uses UserSession.access_token_jti (not RefreshToken.token) as the JTI source for Redis blacklisting — access JTIs live on UserSession, not RefreshToken"
  - "[11-01]: billing admin router uses require_admin (admin-audience JWT) not local require_superuser — audience isolation is enforced consistently across all admin domains"
  - "[11-01]: test_list_active_plans uses admin token for CRUD and separate regular-audience token for public GET /billing/plans — the two endpoints have different auth requirements"
  - "[11-01]: test_regular_jwt_rejected_on_billing_admin expects 401 (not 403) — require_admin rejects non-admin-audience tokens at decode level before reaching authorization"

patterns-established:
  - "Payment failure token revocation: query UserSession.access_token_jti by user_id, call blacklist_jti(redis, jti) for each — same pattern as suspend_tenant in admin/service.py"
  - "Billing admin endpoints must use require_admin for admin-audience JWT enforcement, never a local require_superuser wrapper"

requirements-completed: [BILL-01, BILL-03, BILL-05]

# Metrics
duration: 5min
completed: 2026-03-04
---

# Phase 11 Plan 01: Billing Integration Fixes Summary

**Fixed INT-01 (access token blacklisting uses UserSession.access_token_jti + blacklist_jti) and INT-02 (billing admin routes enforce admin-audience JWT via require_admin), closing the last two v1.0 integration gaps.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-04T19:44:07Z
- **Completed:** 2026-03-04T19:49:37Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Fixed `_handle_payment_failed` to query `UserSession.access_token_jti` and call `blacklist_jti(redis_client, jti)` instead of using broken `redis_client.setex(token.token, ...)` pattern
- Replaced local `require_superuser` function in billing/router.py with imported `require_admin` from admin.dependencies on all 5 billing admin endpoints
- Updated 4 SC1 tests to use `_seed_super_admin` + `_admin_login` (admin-audience JWT) instead of `_signup_verify_login` + `_make_superuser`
- Added `test_payment_failed_blacklists_access_token` proving E2E flow #8: payment failure -> PAST_DUE -> JTI in Redis blacklist -> original token returns 401
- Full test suite: 149 tests passing, 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix _handle_payment_failed blacklist bug and replace require_superuser with require_admin** - `f72ab35` (fix)
2. **Task 2: Update all broken SC1 tests to use admin-audience JWTs and add E2E flow #8 test** - `ac5f3c7` (feat)

## Files Created/Modified
- `backend/src/wxcode_adm/billing/service.py` - Fixed `_handle_payment_failed`: UserSession.access_token_jti + blacklist_jti; removed unused _settings import
- `backend/src/wxcode_adm/billing/router.py` - Added require_admin import; removed local require_superuser function; replaced all 5 Depends(require_superuser) with Depends(require_admin); updated module docstring
- `backend/tests/test_billing.py` - Added `_seed_super_admin` and `_admin_login` helpers; updated 4 SC1 superadmin tests; renamed test_nonsuperadmin_cannot_create_plan -> test_regular_jwt_rejected_on_billing_admin with 401 assertion; added test_payment_failed_blacklists_access_token E2E test

## Decisions Made
- `_handle_payment_failed` uses `UserSession.access_token_jti` as JTI source (not `RefreshToken.token`) because access token JTIs live on UserSession rows, matching the `blacklist_jti` function's expected input
- Removed unused `_settings` lazy import from `_handle_payment_failed` after removing the broken `ttl_seconds = _settings.ACCESS_TOKEN_TTL_HOURS * 3600` line — `blacklist_jti` handles TTL internally
- `test_list_active_plans` uses separate regular-audience token for public `GET /billing/plans` since that endpoint uses `require_verified`, not `require_admin`
- Kept `ForbiddenError` import in router.py — still used by `require_billing_access`
- Kept `require_verified` import in router.py — still used by `list_active_plans` endpoint

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — both code fixes applied cleanly. The E2E test for the `test_payment_failed_blacklists_access_token` used a simplified Redis scan approach (scanning for any `auth:blacklist:jti:*` key) rather than querying UserSession first, which is more robust for integration testing.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- INT-01 and INT-02 are closed — v1.0 billing integration gaps fully resolved
- All 149 tests pass with no regressions
- v1.0 certification criteria are now met for billing token revocation and admin JWT audience isolation

---
*Phase: 11-billing-integration-fixes*
*Completed: 2026-03-04*
