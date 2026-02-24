---
phase: 06-oauth-and-mfa
plan: "05"
subsystem: auth
tags: [oauth, mfa, totp, alembic, integration-tests, trusted-devices, backup-codes]

# Dependency graph
requires:
  - phase: 06-04
    provides: tenant MFA enforcement, login enforcement integration, mfa_setup_required signal
  - phase: 06-03
    provides: two-stage MFA login, mfa_verify, trusted device cookie
  - phase: 06-01
    provides: OAuthAccount model, resolve_oauth_account, nullable password_hash
provides:
  - Alembic migration 005 persisting all Phase 6 schema changes
  - 24 integration tests covering all 6 Phase 6 success criteria (AUTH-08 through AUTH-13)
  - All 114 tests passing (90 existing + 24 new)
affects:
  - Phase 7 (frontend integration) — all OAuth/MFA routes tested and verified

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Mock authlib OAuth clients via unittest.mock.patch on router-level oauth object
    - Explicit UUID assignment in test DB setup (no flush() needed — avoids greenlet errors)
    - pyotp.TOTP(secret).now() for deterministic TOTP codes in tests

key-files:
  created:
    - backend/alembic/versions/005_add_oauth_mfa_tables.py
    - backend/tests/test_oauth_mfa.py
  modified:
    - backend/tests/conftest.py
    - backend/src/wxcode_adm/auth/service.py
    - backend/src/wxcode_adm/auth/schemas.py

key-decisions:
  - "resolve_oauth_account case 1 uses explicit TenantMembership count query instead of user.memberships lazy load — lazy loads raise MissingGreenlet on SQLAlchemy async sessions"
  - "generate_backup_codes hashes raw.replace('-','') not raw — token_urlsafe can generate dashes in the raw value, causing mismatch with verification that strips all dashes"
  - "MfaDisableRequest and MfaVerifyRequest code max_length increased 10→11 to accept formatted backup codes (XXXXX-XXXXX = 11 chars)"
  - "Test DB setup uses explicit UUID assignment instead of flush() to avoid MissingGreenlet when creating related models in one session block"

patterns-established:
  - "OAuth mocking pattern: patch wxcode_adm.auth.router.oauth; mock_client.authorize_access_token = AsyncMock"
  - "GitHub private email test pattern: mock_client.get as coroutine dispatching on URL string"
  - "MFA test shortcut: _create_user_with_mfa() creates DB user with mfa_enabled=True/mfa_secret set directly"

requirements-completed:
  - AUTH-08
  - AUTH-09
  - AUTH-10
  - AUTH-11
  - AUTH-12
  - AUTH-13

# Metrics
duration: 8min
completed: 2026-02-24
---

# Phase 06 Plan 05: OAuth and MFA Migration + Integration Tests Summary

**Alembic migration 005 persisting all Phase 6 schema changes, plus 24 integration tests covering OAuth (Google/GitHub), MFA enrollment/login, tenant enforcement, and trusted devices**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-24T18:22:00Z
- **Completed:** 2026-02-24T18:30:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Alembic migration 005: ALTER users (mfa_enabled, mfa_secret, nullable password_hash), ALTER tenants (mfa_enforced), CREATE oauth_accounts (2 unique constraints), CREATE mfa_backup_codes, CREATE trusted_devices — single head verified
- 24 integration tests across all 6 success criteria: Google OAuth (4 tests), GitHub OAuth (2), MFA enrollment (6), MFA login (5), tenant enforcement (4), trusted device (3)
- Auto-fixed 3 pre-existing bugs found during testing: lazy-load MissingGreenlet in OAuth service, backup code dash-hash mismatch, schema max_length too short for formatted backup codes

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic migration 005** - `aa4e64d` (feat)
2. **Task 2: Integration tests + bug fixes** - `35f6027` (feat)

**Plan metadata:** _committed with this summary_

## Files Created/Modified
- `backend/alembic/versions/005_add_oauth_mfa_tables.py` - Migration 005: ALTER users/tenants, CREATE oauth_accounts/mfa_backup_codes/trusted_devices with correct FKs, indexes, unique constraints; downgrade reverses all
- `backend/tests/test_oauth_mfa.py` - 24 integration tests covering AUTH-08 through AUTH-13 with mocked OAuth clients and pyotp TOTP codes
- `backend/tests/conftest.py` - Added explicit Phase 6 model imports (OAuthAccount, MfaBackupCode, TrustedDevice) for Base.metadata.create_all
- `backend/src/wxcode_adm/auth/service.py` - Fixed resolve_oauth_account lazy-load bug (case 1) and backup code hash consistency
- `backend/src/wxcode_adm/auth/schemas.py` - Fixed MfaDisableRequest and MfaVerifyRequest code max_length 10→11

## Decisions Made
- Migration follows exact pattern of migration 004 (op.f() naming convention, same column types, server defaults)
- Tests use `patch("wxcode_adm.auth.router.oauth")` to mock at the router level where the OAuth object is used
- GitHub private email test mocks `client.get` as a coroutine dispatching on URL string (matches actual service code)
- Test DB setup uses explicit `id=uuid.uuid4()` assignment instead of `await session.flush()` to avoid the SQLAlchemy async greenlet error on aiosqlite

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] resolve_oauth_account case 1 lazy-loads user.memberships**
- **Found during:** Task 2 (integration tests)
- **Issue:** `needs_onboarding = len(user.memberships) == 0` triggers lazy load on an async session, raising `MissingGreenlet` in SQLAlchemy 2.0 — cannot lazy-load relationships on async sessions
- **Fix:** Replaced with explicit `select(TenantMembership).where(TenantMembership.user_id == user.id)` async count query
- **Files modified:** `backend/src/wxcode_adm/auth/service.py`
- **Verification:** `test_google_oauth_existing_linked_user_logs_in` passes
- **Committed in:** `35f6027` (Task 2 commit)

**2. [Rule 1 - Bug] generate_backup_codes hashes raw value that may contain dashes**
- **Found during:** Task 2 (integration tests — test_mfa_disable_with_backup_code failed intermittently)
- **Issue:** `secrets.token_urlsafe` can include `-` characters in the raw 10-char value; hashing `raw` instead of `raw.replace('-','')` causes mismatch with verification which strips all dashes via `code.replace('-','')`
- **Fix:** Changed to `hash_password(raw.replace("-", ""))` in `generate_backup_codes`
- **Files modified:** `backend/src/wxcode_adm/auth/service.py`
- **Verification:** `test_mfa_disable_with_backup_code` and `test_mfa_verify_with_backup_code` pass consistently
- **Committed in:** `35f6027` (Task 2 commit)

**3. [Rule 1 - Bug] MfaDisableRequest and MfaVerifyRequest code max_length too short**
- **Found during:** Task 2 (integration tests — 422 Unprocessable Entity on formatted backup code)
- **Issue:** Schema had `max_length=10` but backup codes formatted as "XXXXX-XXXXX" are 11 characters; Pydantic rejected valid codes before they reached the service
- **Fix:** Changed `max_length` to 11 in both `MfaDisableRequest` and `MfaVerifyRequest` schemas
- **Files modified:** `backend/src/wxcode_adm/auth/schemas.py`
- **Verification:** `test_mfa_disable_with_backup_code` and `test_mfa_verify_with_backup_code` pass with formatted codes
- **Committed in:** `35f6027` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1 - Bug)
**Impact on plan:** All three fixes corrected pre-existing bugs in Phase 6 service code that were uncovered by the integration tests. No scope creep — all changes strictly limited to the bugs that blocked correct test execution.

## Issues Encountered
- `await session.flush()` inside `async with test_db() as session:` blocks triggers MissingGreenlet because aiosqlite needs explicit greenlet context for async ops. Fixed by using explicit UUID assignment (`id=uuid.uuid4()`) before creating related models in a single `await session.commit()` call.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Phase 6 OAuth and MFA is now fully complete: models, services, routes, migration, and all 114 tests passing
- Ready for Phase 7 (User Account Management / Frontend Integration)
- All 6 Phase 6 success criteria verified by integration tests (AUTH-08 through AUTH-13)

---
*Phase: 06-oauth-and-mfa*
*Completed: 2026-02-24*
