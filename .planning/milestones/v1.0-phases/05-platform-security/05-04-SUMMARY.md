---
phase: 05-platform-security
plan: "04"
subsystem: testing
tags: [pytest, alembic, rate-limiting, audit-log, email-templates, sqlalchemy, slowapi, migration]

# Dependency graph
requires:
  - phase: 05-platform-security (plan 01)
    provides: slowapi limiter singleton, @limiter.exempt on health/JWKS, rate_limit module
  - phase: 05-platform-security (plan 02)
    provides: AuditLog model, write_audit helper, purge_old_audit_logs, audit router
  - phase: 05-platform-security (plan 03)
    provides: FastMail singleton, 4 email sender functions with html_template/plain_template
provides:
  - Alembic migration 004 creating audit_logs table (UUID PK, JSONB details, 4 indexes, 2 FK)
  - 17 integration tests in test_platform_security.py covering PLAT-03, PLAT-04, PLAT-05
  - SQLite JSONB compatibility fix in conftest and test_tenant_guard for all test fixtures
  - Rate limiter disabled by default in test fixtures for test isolation
affects: [future phases that add new tests, CI/CD pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Rate limit test pattern: swap limiter._storage to MemoryStorage + set limiter._limiter to FixedWindowRateLimiter(mem) to enable in-memory rate limiting without Redis"
    - "JSONB SQLite compat: patch JSONB columns to JSON + strip server_default before Base.metadata.create_all; restore after"
    - "Email mock pattern: patch wxcode_adm.common.mail.fast_mail (the singleton module) directly since lazy imports always use it"
    - "Rate limit isolation: app.state.limiter.enabled = False in client fixture; tests re-enable inline with try/finally cleanup"

key-files:
  created:
    - backend/alembic/versions/004_add_audit_logs_table.py
    - backend/tests/test_platform_security.py
  modified:
    - backend/tests/conftest.py
    - backend/tests/test_tenant_guard.py
    - backend/src/wxcode_adm/common/rate_limit.py

key-decisions:
  - "JSONB-to-JSON patch applied in-place on Base.metadata before create_all and restored after — safe per-test because each test_db gets a fresh engine"
  - "Original app.state.limiter must be used for rate limit tests (not a new Limiter) because @limiter.exempt adds routes to original limiter's _exempt_routes set"
  - "headers_enabled=True added to Limiter singleton so Retry-After header is included in 429 responses"
  - "Rate limit tests use MemoryStorage + FixedWindowRateLimiter swapped onto existing limiter._storage/_limiter fields"
  - "Email function tests patch wxcode_adm.common.mail.fast_mail directly (not auth.email.fast_mail) because lazy import always re-imports from common.mail"

patterns-established:
  - "Rate limit test isolation pattern: save original _storage/_limiter, swap to MemoryStorage, enable, try/finally restore and disable"
  - "Audit log test pattern: unique action names in filter tests to avoid collisions with API-generated audit entries"
  - "JSONB SQLite compat: patch+restore pattern is reusable for any new fixtures needing Base.metadata.create_all"

requirements-completed:
  - PLAT-03
  - PLAT-04
  - PLAT-05

# Metrics
duration: 8min
completed: 2026-02-24
---

# Phase 5 Plan 04: Migration 004 and Integration Tests Summary

**Alembic migration 004 for audit_logs table plus 17 integration tests verifying all Phase 5 success criteria: rate limiting 429+Retry-After, audit log CRUD + super-admin access, and HTML email template rendering**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-24T14:21:47Z
- **Completed:** 2026-02-24T14:29:34Z
- **Tasks:** 2
- **Files modified:** 5 (+ 2 created)

## Accomplishments

- Hand-wrote Alembic migration 004 creating `audit_logs` table with UUID PK, JSONB details column, 4 indexes (actor_id, tenant_id, action, created_at), and 2 FK constraints with ON DELETE SET NULL
- Created 17 integration tests in `test_platform_security.py` covering all 3 Phase 5 success criteria (4 rate limit + 7 audit + 6 email tests)
- Fixed SQLite incompatibility: JSONB columns patched to JSON + PostgreSQL server defaults stripped before `create_all`, restored after — applied to both `conftest.py` and `test_tenant_guard.py`
- Added `app.state.limiter.enabled = False` to client fixture for test isolation; rate limit tests re-enable inline using original limiter with in-memory storage swap

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Alembic migration 004 and update conftest for Phase 5 tests** - `4279979` (feat)
2. **Task 2: Write integration tests for PLAT-03, PLAT-04, and PLAT-05** - `9c4f75a` (feat)

**Plan metadata:** `[pending docs commit]` (docs: complete plan)

## Files Created/Modified

- `backend/alembic/versions/004_add_audit_logs_table.py` - Migration 004: audit_logs table with JSONB details, 4 indexes, actor_id + tenant_id FK constraints
- `backend/tests/test_platform_security.py` - 17 integration tests (4 rate limit, 7 audit, 6 email)
- `backend/tests/conftest.py` - Added audit model import; JSONB->JSON SQLite compat patch; limiter disabled by default
- `backend/tests/test_tenant_guard.py` - Applied same JSONB->JSON SQLite compat fix to guarded_session fixture
- `backend/src/wxcode_adm/common/rate_limit.py` - Added `headers_enabled=True` so Retry-After is included in 429 responses

## Decisions Made

- **JSONB-to-JSON patch pattern**: Applied in-place on `Base.metadata` before `create_all`, restored after. Safe per test because each `test_db` gets a fresh SQLite engine. No TypeDecorator needed.
- **Original limiter must be preserved for tests**: `app.state.limiter` must be the original limiter because `@limiter.exempt` adds routes to the original limiter's `_exempt_routes` set. Swapping to a new Limiter loses all exempt registrations (health/JWKS would get rate-limited).
- **Memory storage swap**: For rate limit tests, swap `limiter._storage` to `limits.storage.MemoryStorage()` and `limiter._limiter` to `FixedWindowRateLimiter(mem_storage)` to avoid needing a real Redis instance.
- **headers_enabled=True**: Added to the singleton Limiter so 429 responses include `Retry-After` header — this is correct behavior for brute-force protection (clients should back off).
- **Email singleton patching**: `wxcode_adm.common.mail.fast_mail` is the canonical target because all 4 email sender functions do lazy imports (`from wxcode_adm.common.mail import fast_mail` inside try/except) — patching at the auth/tenants/billing.email module level fails since those modules don't have `fast_mail` as a module attribute.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] JSONB type causes SQLite compilation error in test fixtures**
- **Found during:** Task 1 (running existing tests after audit model import was added to conftest)
- **Issue:** `sqlalchemy.exc.CompileError: Compiler can't render element of type JSONB` — SQLAlchemy's JSONB type does NOT automatically fall back to JSON for non-PostgreSQL dialects; it raises CompileError instead
- **Fix:** Added in-place JSONB->JSON patch + server_default strip before `Base.metadata.create_all` in `test_db` fixture; applied same pattern to `test_tenant_guard.py`'s `guarded_session` fixture
- **Files modified:** backend/tests/conftest.py, backend/tests/test_tenant_guard.py
- **Verification:** `python3 -m pytest tests/ -v` — 73 previously-passing tests continue to pass
- **Committed in:** 4279979 (Task 1 commit)

**2. [Rule 1 - Bug] Rate limit exemption lost when swapping to new Limiter instance**
- **Found during:** Task 2 (health/JWKS exemption tests failing with 429)
- **Issue:** `@limiter.exempt` registers routes in `limiter._exempt_routes` on the original limiter object. Swapping `app.state.limiter` to a new `Limiter()` instance creates an empty `_exempt_routes` set — health and JWKS endpoints lose their exemption.
- **Fix:** Changed test strategy to patch `_storage` and `_limiter` fields on the existing `app.state.limiter` instead of replacing it. Added helper `_enable_original_limiter_with_memory_storage()` / `_restore_original_limiter()`.
- **Files modified:** backend/tests/test_platform_security.py
- **Verification:** `pytest tests/test_platform_security.py::test_health_endpoint_exempt` passes (10 calls, never 429)
- **Committed in:** 9c4f75a (Task 2 commit)

**3. [Rule 2 - Missing Critical] headers_enabled=True needed for Retry-After in 429 responses**
- **Found during:** Task 2 (test_rate_limit_response_includes_retry_after failing)
- **Issue:** `headers_enabled` defaults to `False` in slowapi's Limiter. Without it, `_inject_headers` is a no-op and 429 responses have no Retry-After header.
- **Fix:** Added `headers_enabled=True` to the production Limiter singleton in `common/rate_limit.py` — this is the correct production behavior (clients should receive backoff instructions).
- **Files modified:** backend/src/wxcode_adm/common/rate_limit.py
- **Verification:** Retry-After header present in 429 responses; all rate limit tests pass
- **Committed in:** 9c4f75a (Task 2 commit)

**4. [Rule 1 - Bug] Filter test collides with API-generated audit entries**
- **Found during:** Task 2 (test_audit_log_query_filtering assertion failure: total=3 vs expected 2)
- **Issue:** The auth login endpoint creates its own audit entries (action="login"), so filtering by action=login returns both manually-created entries AND the superadmin login entry from the test setup.
- **Fix:** Changed filter test to use unique action names ("test_filter_event_a", "test_filter_event_b") that don't collide with any auth-generated audit actions.
- **Files modified:** backend/tests/test_platform_security.py
- **Verification:** `pytest tests/test_platform_security.py::test_audit_log_query_filtering` passes
- **Committed in:** 9c4f75a (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (1 Rule 3 blocking, 1 Rule 1 bug, 1 Rule 2 missing critical, 1 Rule 1 bug)
**Impact on plan:** All 4 auto-fixes were necessary for correctness. Plan under-specified SQLite JSONB compatibility and the details of slowapi's exempt mechanism. No scope creep.

## Issues Encountered

The plan stated: "The simplest approach: in the test_db fixture, after creating tables with `Base.metadata.create_all`, the column already works because SQLAlchemy's `JSONB` type falls back to `JSON` for non-PostgreSQL dialects automatically. Verify this works — if not, add a TypeDecorator."

Verification result: JSONB does NOT fall back — SQLAlchemy raises `CompileError`. A TypeDecorator was not used; instead a simpler in-place patch/restore approach was applied since modifying the column type temporarily is less invasive and doesn't affect production code paths.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Migration 004 is ready to apply to production PostgreSQL: `alembic upgrade head`
- All 90 tests pass (18 auth + 19 billing + 17 platform security + 3 tenant guard + 33 tenants)
- Phase 5 (Platform Security) is now complete — all 4 plans executed, all 3 success criteria (PLAT-03, PLAT-04, PLAT-05) verified by automated tests

## Self-Check: PASSED

All created files exist on disk:
- FOUND: backend/alembic/versions/004_add_audit_logs_table.py
- FOUND: backend/tests/test_platform_security.py

All commits verified:
- FOUND: 4279979 (Task 1 commit)
- FOUND: 9c4f75a (Task 2 commit)

---
*Phase: 05-platform-security*
*Completed: 2026-02-24*
