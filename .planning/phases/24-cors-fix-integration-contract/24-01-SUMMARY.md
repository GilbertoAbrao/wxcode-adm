---
phase: 24-cors-fix-integration-contract
plan: 01
subsystem: infra
tags: [cors, starlette, fastapi, security, middleware, tenant]

# Dependency graph
requires:
  - phase: 20-crypto-service
    provides: Tenant model with wxcode_url field
  - phase: 23-admin-ui-claude-management
    provides: Production app with wildcard CORS that needed hardening
provides:
  - "Production-safe CORS middleware replacing allow_origin_regex wildcard"
  - "DynamicCORSMiddleware with static ALLOWED_ORIGINS + dynamic tenant wxcode_url origins"
  - "CORS behavior test suite with 5 tests covering allowed/disallowed origins and preflight"
affects: [24-02, integration-testing, security-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Subclass CORSMiddleware.is_allowed_origin() for dynamic origin checking"
    - "Module-level set cache populated at lifespan startup for runtime lookup"
    - "CORS test fixture that overrides ALLOWED_ORIGINS to explicit list (overrides .env wildcard)"

key-files:
  created:
    - backend/tests/test_cors.py
  modified:
    - backend/src/wxcode_adm/main.py

key-decisions:
  - "DynamicCORSMiddleware subclasses CORSMiddleware and overrides is_allowed_origin() — minimal intrusion, single override point"
  - "_tenant_origin_cache as module-level set populated at lifespan startup — simple and fast for origin lookups"
  - "cors_client test fixture patches ALLOWED_ORIGINS to explicit list — .env has wildcard that breaks CORS test assertions"
  - "Direct cache manipulation in test 5 (not DB+lifespan) — unit under test is middleware origin checking, not DB loading"

patterns-established:
  - "CORS fixture pattern: monkeypatch ALLOWED_ORIGINS + _tenant_origin_cache before create_app() for deterministic tests"

requirements-completed: [CORS-FIX, CORS-DYNAMIC]

# Metrics
duration: 5min
completed: 2026-03-09
---

# Phase 24 Plan 01: CORS Fix Summary

**Production-safe CORS via DynamicCORSMiddleware subclass: static ALLOWED_ORIGINS from settings + dynamic tenant wxcode_url origins loaded at startup into module-level cache**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-09T12:19:34Z
- **Completed:** 2026-03-09T12:24:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Removed `allow_origin_regex=r".*"` security hole from CORS middleware
- Implemented `DynamicCORSMiddleware` subclass that checks both static `ALLOWED_ORIGINS` and tenant `wxcode_url` values from a module-level cache
- Added lifespan step to populate `_tenant_origin_cache` at startup from DB
- Created 5-test CORS suite covering allowed/disallowed origins, OPTIONS preflight, and tenant custom domain origins

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace wildcard CORS with ALLOWED_ORIGINS + dynamic tenant wxcode_urls** - `24e388b` (feat)
2. **Task 2: Add CORS behavior tests** - `3b6f413` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/main.py` - Replaced CORSMiddleware wildcard with DynamicCORSMiddleware; added _tenant_origin_cache, _build_cors_origins(), DynamicCORSMiddleware class; added lifespan step to load tenant wxcode_urls
- `backend/tests/test_cors.py` - 5 CORS behavior tests with local cors_client fixture that patches ALLOWED_ORIGINS to explicit list

## Decisions Made

- **DynamicCORSMiddleware subclasses CORSMiddleware:** Overrides `is_allowed_origin()` only — minimal intrusion, no duplication of Starlette internals. The parent's logic handles static origins; the override adds tenant origins as a second pass.
- **Module-level `_tenant_origin_cache` set:** Simple, fast, thread-compatible for read access. Populated once at startup; could be refreshed in future if needed.
- **Test fixture patches ALLOWED_ORIGINS:** The `.env` file has `ALLOWED_ORIGINS=["*"]` for dev convenience. Tests must override this to test CORS origin rejection deterministically. The `cors_client` fixture patches the settings singleton before `create_app()` is called.
- **Direct cache manipulation in tenant test:** Test 5 uses `tenant_cache.add(origin)` rather than creating a real DB tenant and running lifespan. The unit being tested is the middleware's origin checking path, not the DB query.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CORS test fixture required explicit ALLOWED_ORIGINS patch**
- **Found during:** Task 2 (Add CORS behavior tests)
- **Issue:** The `.env` file has `ALLOWED_ORIGINS=["*"]`, which causes `allow_all_origins=True` in the middleware. Tests 1 and 4 failed because all origins were allowed (including evil ones) and responses returned `*` rather than echoing the specific allowed origin.
- **Fix:** Created a local `cors_client` fixture (instead of using the global `client` fixture) that patches `config_module.settings.ALLOWED_ORIGINS = ["http://localhost:3060"]` and `_tenant_origin_cache = set()` before calling `create_app()`. This ensures deterministic CORS behavior in tests regardless of `.env` settings.
- **Files modified:** `backend/tests/test_cors.py`
- **Verification:** All 5 CORS tests pass
- **Committed in:** `3b6f413` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test setup due to .env wildcard)
**Impact on plan:** Fix was necessary for correct test assertions. No scope creep.

## Issues Encountered

None beyond the ALLOWED_ORIGINS test fixture issue documented above.

## User Setup Required

None — no external service configuration required. For production deployment, set `ALLOWED_ORIGINS` in `.env` to the actual frontend domain(s) instead of `["*"]`.

## Next Phase Readiness

- CORS is production-safe: requests from non-allowed origins are rejected
- Tenant custom domains supported via `_tenant_origin_cache` at startup
- Plan 24-02 (integration health endpoint) was already executed (SUMMARY exists)
- Phase 24 complete after this plan

## Self-Check: PASSED

- FOUND: `backend/tests/test_cors.py`
- FOUND: `backend/src/wxcode_adm/main.py`
- FOUND: `.planning/phases/24-cors-fix-integration-contract/24-01-SUMMARY.md`
- FOUND commit: `24e388b` (Task 1)
- FOUND commit: `3b6f413` (Task 2)

---
*Phase: 24-cors-fix-integration-contract*
*Completed: 2026-03-09*
