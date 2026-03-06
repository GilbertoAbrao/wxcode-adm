---
phase: 05-platform-security
plan: 01
subsystem: api
tags: [slowapi, rate-limiting, redis, brute-force-protection, fastapi]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Redis connection (REDIS_URL), app factory pattern
  - phase: 02-auth-core
    provides: Auth endpoints (login, signup, forgot_password, reset_password, resend_verification, jwks)
provides:
  - slowapi Limiter singleton with Redis backend at common/rate_limit.py
  - SlowAPIASGIMiddleware wired into app factory before routers
  - 5/minute strict rate limit on all auth endpoints (brute-force protection)
  - JWKS and health endpoints exempt from rate limiting
  - 60/minute global default on all non-exempt endpoints via middleware
affects: [06-api-gateway, testing]

# Tech tracking
tech-stack:
  added: [slowapi==0.1.9]
  patterns:
    - Route decorator BEFORE @limiter.limit (reverse order from intuition)
    - All rate-limited endpoints must accept request: Request as first parameter
    - SlowAPIASGIMiddleware (not SlowAPIMiddleware) for async FastAPI compatibility

key-files:
  created:
    - backend/src/wxcode_adm/common/rate_limit.py
  modified:
    - backend/src/wxcode_adm/config.py
    - backend/src/wxcode_adm/main.py
    - backend/src/wxcode_adm/auth/router.py
    - backend/src/wxcode_adm/common/router.py
    - backend/src/wxcode_adm/billing/router.py
    - backend/src/wxcode_adm/billing/webhook_router.py
    - backend/src/wxcode_adm/tenants/router.py

key-decisions:
  - "SlowAPIASGIMiddleware (not SlowAPIMiddleware) required for async FastAPI — non-ASGI variant does not work correctly with async handlers"
  - "Route decorator MUST come first, @limiter.limit() SECOND — reversed order silently breaks rate limiting"
  - "All endpoint functions must accept request: Request as parameter — slowapi silently skips limit if missing"
  - "JWKS and health endpoints exempt via @limiter.exempt — public key retrieval and infrastructure checks must never be rate-limited"
  - "Redis backend via storage_uri=settings.REDIS_URL ensures limits persist across application restarts"

patterns-established:
  - "Rate limit decorator order: @router.post() first, @limiter.limit() second (below route)"
  - "Exempt pattern: @limiter.exempt on public/infrastructure endpoints that must never count against limits"

requirements-completed: [PLAT-03]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 5 Plan 01: Rate Limiting Summary

**slowapi Redis-backed rate limiter wired into FastAPI: 5/min brute-force protection on 5 auth endpoints, 60/min global default on all others, JWKS and health exempt**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T14:11:20Z
- **Completed:** 2026-02-24T14:15:35Z
- **Tasks:** 2
- **Files modified:** 7 (+ 1 created)

## Accomplishments

- Created `common/rate_limit.py` Limiter singleton backed by Redis with configurable limits via env vars
- Wired SlowAPIASGIMiddleware + RateLimitExceeded handler into `create_app()` before all routers
- Applied 5/minute strict limit to login, signup, forgot_password, reset_password, and resend_verification
- Exempted JWKS (`/.well-known/jwks.json`) and health endpoints from all rate limiting
- Added `request: Request` parameter to all endpoint functions in billing, tenants, auth, and webhook routers for slowapi compatibility

## Task Commits

Each task was committed atomically:

1. **Task 1: Create rate_limit module, add settings, integrate middleware in app factory** - `d4bc621` (feat)
2. **Task 2: Apply strict auth limits and exempt health/JWKS endpoints** - `a3c74ee` (feat, included in 05-02 commit)

## Files Created/Modified

- `backend/src/wxcode_adm/common/rate_limit.py` - Limiter singleton with Redis backend, re-exports for main.py
- `backend/src/wxcode_adm/config.py` - Added RATE_LIMIT_AUTH (5/minute) and RATE_LIMIT_GLOBAL (60/minute) settings
- `backend/src/wxcode_adm/main.py` - SlowAPIASGIMiddleware, app.state.limiter, RateLimitExceeded handler wired in create_app()
- `backend/src/wxcode_adm/auth/router.py` - 5x @limiter.limit(RATE_LIMIT_AUTH), 1x @limiter.exempt (jwks), request: Request on all rate-limited endpoints
- `backend/src/wxcode_adm/common/router.py` - @limiter.exempt on health_check
- `backend/src/wxcode_adm/billing/router.py` - request: Request added to all 9 endpoints
- `backend/src/wxcode_adm/billing/webhook_router.py` - request: Request added to stripe_webhook
- `backend/src/wxcode_adm/tenants/router.py` - request: Request added to all 14 endpoints

## Decisions Made

- SlowAPIASGIMiddleware (not SlowAPIMiddleware) — the non-ASGI variant silently fails with async FastAPI
- Route decorator order is counterintuitive: `@router.post()` FIRST, `@limiter.limit()` SECOND; reverse order breaks rate limiting silently
- All endpoint functions must have `request: Request` as first parameter — slowapi uses it to extract client IP; missing it silently skips the limit
- `storage_uri=settings.REDIS_URL` ensures rate limit counters persist across restarts (brute-force protection survives pod restarts)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Uses existing Redis from Phase 1 (REDIS_URL env var already set).

## Next Phase Readiness

- Rate limiting fully operational; auth endpoints protected from brute-force at 5/minute per IP
- Global 60/minute default applies to all non-exempt, non-decorated endpoints via middleware
- RATE_LIMIT_AUTH and RATE_LIMIT_GLOBAL configurable via environment variables for production tuning
- Ready for Phase 5 Plan 02 (audit logging) and remaining platform security plans

---
*Phase: 05-platform-security*
*Completed: 2026-02-24*
