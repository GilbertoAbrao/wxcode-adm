---
phase: 07-user-account
plan: "04"
subsystem: testing
tags: [alembic, integration-tests, pytest, sqlalchemy, redis, user-sessions, wxcode-redirect]

# Dependency graph
requires:
  - phase: 07-user-account
    plan: "01"
    provides: "UserSession model, parse_session_metadata, _issue_tokens with session creation"
  - phase: 07-user-account
    plan: "02"
    provides: "GET/PATCH /users/me, POST /users/me/change-password, users module"
  - phase: 07-user-account
    plan: "03"
    provides: "GET/DELETE /users/me/sessions, POST /auth/wxcode/exchange, blacklist_jti, create_wxcode_code"
provides:
  - "Alembic migration 006 for production DB with user_sessions, profile columns, wxcode_url"
  - "15 integration tests covering all 4 USER success criteria end-to-end"
  - "Test coverage for SC1 (profile view/update), SC2 (password change), SC3 (session management), SC4 (wxcode redirect)"
affects: ["phase-08", "deployment"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alembic migration follows 005 style: op.f() for constraint names, explicit FKs and indexes"
    - "Test helpers: _signup_verify_login tracks pre-signup OTP Redis keys for multi-user isolation"
    - "wxcode test pattern: direct DB update via test_db() session to set tenant.wxcode_url before testing redirect"

key-files:
  created:
    - "backend/alembic/versions/006_add_user_sessions_and_profile_columns.py"
    - "backend/tests/test_user_account.py"
  modified: []

key-decisions:
  - "[07-04]: Migration 006 uses explicit op.f() constraint naming convention consistent with 005"
  - "[07-04]: wxcode test sets tenant.wxcode_url via direct DB update (test_db fixture) — avoids needing an API for tenant configuration"
  - "[07-04]: test_wxcode_code_exchange creates workspace first so user has a tenant with wxcode_url to resolve"

patterns-established:
  - "Integration test file per major feature area: test_user_account.py covers all 4 USER success criteria"
  - "Use update(Tenant).values() in test_db for direct tenant configuration without API overhead"

requirements-completed: [USER-01, USER-02, USER-03, USER-04]

# Metrics
duration: 3min
completed: 2026-02-25
---

# Phase 7 Plan 04: Alembic Migration 006 and User Account Integration Tests Summary

**Alembic migration 006 for user_sessions/profile columns, plus 15 integration tests proving all 4 USER success criteria end-to-end**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-25T21:06:13Z
- **Completed:** 2026-02-25T21:08:58Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Alembic migration 006 creates user_sessions table with 10 metadata columns, FK to refresh_tokens (CASCADE), FK to users (CASCADE), unique access_token_jti; adds display_name/avatar_url/last_used_tenant_id to users; adds wxcode_url to tenants; includes downgrade() that reverses all changes
- 15 integration tests covering all 4 USER success criteria: (1) profile view returns all 6 fields, update display_name reflects immediately, email change resets email_verified, empty patch returns 400; (2) change-password success, old password rejected after change, wrong current returns 401; (3) list sessions with is_current tag, cannot revoke current (400), revoke all others preserves current, nonexistent session returns 404; (4) invalid code returns 401, full code exchange returns tokens, single-use enforcement works, login without wxcode_url returns no code
- Full test suite passes: 129 tests (114 existing + 15 new), no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic migration 006** - `1bbde79` (feat)
2. **Task 2: Integration tests for all 4 USER success criteria** - `749568e` (feat)

## Files Created/Modified

- `backend/alembic/versions/006_add_user_sessions_and_profile_columns.py` - Migration 006: user_sessions table, display_name/avatar_url/last_used_tenant_id on users, wxcode_url on tenants; downgrade reverses all changes
- `backend/tests/test_user_account.py` - 15 integration tests: SC1 (5 tests), SC2 (3 tests), SC3 (4 tests), SC4 (3 tests)

## Decisions Made

- Migration 006 chains on down_revision="005" — correct position in migration chain verified by reading 005 header
- wxcode test sets tenant.wxcode_url via `update(Tenant).values(wxcode_url=...)` in test_db session — avoids needing an admin API, consistent with how test_oauth_mfa.py directly manipulates DB state for test setup
- test_wxcode_code_exchange creates a workspace first so the user has a TenantMembership with a Tenant that can have wxcode_url set; this exercises the full get_redirect_url code path including the TenantMembership query

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all tasks completed without issues. The 15 tests passed on first run without any debugging required. The existing implementation from Plans 01-03 was correct and complete.

## User Setup Required

None - no external service configuration required. Alembic migration 006 will be applied automatically at container startup via `alembic upgrade head` in the entrypoint.

## Next Phase Readiness

- Phase 7 is now complete: all 4 USER success criteria implemented and verified by integration tests
- Alembic migration 006 is production-ready and will apply cleanly on top of migration 005
- 129 tests passing, no known issues
- Phase 8 can build on UserSession, user profile, and wxcode redirect infrastructure

## Self-Check: PASSED

- FOUND: backend/alembic/versions/006_add_user_sessions_and_profile_columns.py
- FOUND: backend/tests/test_user_account.py
- FOUND commit: 1bbde79 (feat: Alembic migration 006)
- FOUND commit: 749568e (feat: integration tests)
- 129 tests passing (114 existing + 15 new)
- grep "user_sessions" migration confirms table name present
- grep "down_revision" confirms down_revision = "005"

---
*Phase: 07-user-account*
*Completed: 2026-02-25*
