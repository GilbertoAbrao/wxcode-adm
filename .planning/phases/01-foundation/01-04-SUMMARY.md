---
phase: 01-foundation
plan: "04"
subsystem: database
tags: [sqlalchemy, tenant-isolation, pytest, aiosqlite, asyncio]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: TenantModel, TenantIsolationError exception class, install_tenant_guard function
provides:
  - Hard-enforcing tenant isolation guard that raises TenantIsolationError on unguarded ORM queries
  - Three-test suite proving guard behavior (raise on unguarded, pass on guarded, raw SQL unaffected)
  - Test infrastructure (backend/tests/ package, aiosqlite dev dependency)
affects:
  - 02-identity
  - all future phases using TenantModel subclasses

# Tech tracking
tech-stack:
  added: [aiosqlite, greenlet (transitive via sqlalchemy async)]
  patterns:
    - do_orm_execute event registered on sync_session_class (Session), not AsyncSession
    - pytest-asyncio async fixtures for SQLAlchemy async engine lifecycle

key-files:
  created:
    - backend/tests/__init__.py
    - backend/tests/test_tenant_guard.py
  modified:
    - backend/src/wxcode_adm/db/tenant.py
    - backend/pyproject.toml

key-decisions:
  - "Tenant guard event registered on Session (sync_session_class) not AsyncSession — do_orm_execute does not fire on AsyncSession"
  - "TenantIsolationError raised immediately on unguarded ORM SELECT, closing ROADMAP SC#2 gap"
  - "aiosqlite added to dev deps for in-memory SQLite testing of async SQLAlchemy sessions"

patterns-established:
  - "Tenant guard pattern: install_tenant_guard(session_maker) at app startup registers do_orm_execute on sync_session_class"
  - "Test isolation: in-memory SQLite (sqlite+aiosqlite://) for SQLAlchemy async tests without Docker"

requirements-completed: []

# Metrics
duration: 2min
completed: 2026-02-22
---

# Phase 1 Plan 04: Tenant Guard Enforcement Summary

**Upgraded tenant isolation guard from advisory WARNING to hard TenantIsolationError raise, with three passing tests proving enforcement via in-memory SQLite async session**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-22T23:01:55Z
- **Completed:** 2026-02-22T23:04:33Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Replaced `logger.warning(...)` with `raise TenantIsolationError(...)` in `install_tenant_guard`
- Closed ROADMAP SC#2 gap: unguarded TenantModel ORM queries are now runtime errors, not silent warnings
- Established test infrastructure (`backend/tests/` package, aiosqlite dev dependency)
- Three passing tests prove guard behavior across all expected scenarios

## Task Commits

Each task was committed atomically:

1. **Task 1: Upgrade tenant guard from WARNING to TenantIsolationError raise** - `3f164e4` (fix)
2. **Task 2: Add test proving tenant guard raises on unguarded queries** - `bb831d3` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `backend/src/wxcode_adm/db/tenant.py` - Import and raise TenantIsolationError; fix event registration to use sync_session_class; update docstrings
- `backend/tests/__init__.py` - Empty package init for test discovery
- `backend/tests/test_tenant_guard.py` - Three async tests using in-memory SQLite via aiosqlite
- `backend/pyproject.toml` - Added aiosqlite to dev dependencies

## Decisions Made
- Registered `do_orm_execute` on `Session` (via `session_factory.class_.sync_session_class`) instead of `AsyncSession`. SQLAlchemy's `do_orm_execute` event is a sync-Session event; it fires synchronously during ORM execution even in async context. AsyncSession does not support this event.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed do_orm_execute event registered on wrong class**
- **Found during:** Task 2 (running tests)
- **Issue:** Original `install_tenant_guard` used `session_factory.class_` which resolves to `AsyncSession`. SQLAlchemy raises `InvalidRequestError: No such event 'do_orm_execute' for target '<class AsyncSession>'`. The guard was silently non-functional in production.
- **Fix:** Changed to `session_factory.class_.sync_session_class` which resolves to the underlying sync `Session` class that actually supports `do_orm_execute`.
- **Files modified:** `backend/src/wxcode_adm/db/tenant.py` (line 65)
- **Verification:** All 3 tests pass; guard raises correctly.
- **Committed in:** `bb831d3` (Task 2 commit)

**2. [Rule 3 - Blocking] Installed missing greenlet dependency**
- **Found during:** Task 2 (initial test run)
- **Issue:** `greenlet` library not installed on local dev machine — required by SQLAlchemy async internals. Tests failed with `ValueError: the greenlet library is required`.
- **Fix:** `python3.11 -m pip install greenlet`. Note: in the Docker container, greenlet is already present as a transitive dependency of sqlalchemy. No pyproject.toml change needed (it's an OS-level transitive dep, not a direct dependency).
- **Files modified:** None (system-level install)
- **Verification:** Tests passed after install.
- **Committed in:** N/A (no code change)

---

**Total deviations:** 2 auto-fixed (1 bug fix, 1 blocking dependency)
**Impact on plan:** The bug fix (Rule 1) was critical — without it, the tenant guard was registered on the wrong class and was completely non-functional in production despite appearing to work. The greenlet fix was a local dev environment gap only.

## Issues Encountered
- The `do_orm_execute` event registration bug existed in the original code (before this plan). The guard has been non-functional since Plan 01. This plan's test coverage exposed the bug and fixed it.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ROADMAP SC#2 is fully closed: unguarded TenantModel queries now raise TenantIsolationError at runtime
- Test infrastructure is established; future phases can add async SQLAlchemy tests using the same pattern
- Phase 2 (Identity) can build TenantModel subclasses confident the guard enforces isolation

## Self-Check: PASSED

- FOUND: backend/src/wxcode_adm/db/tenant.py
- FOUND: backend/tests/test_tenant_guard.py
- FOUND: .planning/phases/01-foundation/01-04-SUMMARY.md
- FOUND: commit 3f164e4
- FOUND: commit bb831d3
