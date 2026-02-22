---
phase: 01-foundation
plan: "02"
subsystem: api
tags: [python, fastapi, redis, arq, asyncio, health-check, lifespan, cors, sqlalchemy]

requires:
  - phase: 01-01
    provides: SQLAlchemy async engine (engine, async_session_maker), pydantic-settings singleton, domain exceptions (AppError hierarchy), install_tenant_guard function, TenantModel base

provides:
  - FastAPI app factory (create_app) with asynccontextmanager lifespan verifying PostgreSQL and Redis on startup
  - Redis async client singleton (redis.asyncio.Redis) with get_redis FastAPI dependency
  - get_session AsyncGenerator dependency with commit-on-success/rollback-on-error lifecycle
  - GET /api/v1/health endpoint returning live PostgreSQL and Redis status (200 or 503)
  - AppError exception handler translating domain errors to JSON responses
  - CORS middleware configured with settings.ALLOWED_ORIGINS
  - arq WorkerSettings with test_job, startup/shutdown hooks, and get_arq_pool helper
  - Module-level app instance for uvicorn: wxcode_adm.main:app

affects:
  - 01-03 (Docker Compose will start uvicorn with wxcode_adm.main:app and arq with WorkerSettings)
  - All subsequent phases (every API endpoint uses get_session and get_redis dependencies)
  - All task definitions use WorkerSettings as base and get_arq_pool for enqueueing

tech-stack:
  added: []
  patterns:
    - asynccontextmanager lifespan (not deprecated @app.on_event) for startup/shutdown
    - get_session as async context manager with explicit commit/rollback (not autocommit)
    - AppError exception handler pattern for domain-to-HTTP error translation
    - arq worker as SEPARATE PROCESS (not spawned from lifespan) with own DB/Redis lifecycle
    - get_arq_pool helper for enqueueing from API code (not sharing worker pool)

key-files:
  created:
    - backend/src/wxcode_adm/common/redis_client.py
    - backend/src/wxcode_adm/dependencies.py
    - backend/src/wxcode_adm/main.py
    - backend/src/wxcode_adm/common/router.py
    - backend/src/wxcode_adm/tasks/worker.py
  modified: []

key-decisions:
  - "arq worker NOT started from lifespan — it must run as a separate process (arq wxcode_adm.tasks.worker.WorkerSettings); lifespan only verifies DB/Redis connectivity"
  - "redis_client is a module-level singleton (not per-request) — Redis connection pool is managed internally by redis.asyncio, closed in lifespan shutdown via aclose()"
  - "get_session uses explicit try/yield/commit/except/rollback pattern (not async with) — gives precise control over when commit happens relative to response"

patterns-established:
  - "Pattern: All endpoints that need DB access use get_session dependency (handles commit/rollback)"
  - "Pattern: Health endpoint uses real DB/Redis queries (not mocked) to detect infrastructure failures"
  - "Pattern: Domain errors raise AppError subclasses; HTTP translation happens in exception handler"
  - "Pattern: CORS and exception handlers registered in create_app() factory, not at module level"

requirements-completed: []

duration: 2min
completed: 2026-02-22
---

# Phase 1 Plan 02: FastAPI App Factory and arq Worker Summary

**FastAPI app factory with asynccontextmanager lifespan verifying PostgreSQL + Redis, live health endpoint at /api/v1/health, Redis singleton with async connection pool, session dependency with commit/rollback lifecycle, and arq WorkerSettings with test_job for separate-process job processing**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-22T21:44:11Z
- **Completed:** 2026-02-22T21:46:30Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- FastAPI app factory (create_app) with asynccontextmanager lifespan that verifies PostgreSQL via `SELECT 1` and Redis via `ping()` before accepting traffic
- Tenant isolation guard installed in lifespan using `install_tenant_guard(async_session_maker)` from Plan 01
- GET /api/v1/health endpoint returns 200 with live PostgreSQL + Redis status checks or 503 on failure
- arq WorkerSettings with test_job, startup (verifies PostgreSQL), shutdown (disposes engine), and get_arq_pool helper for enqueueing from API code

## Task Commits

Each task was committed atomically:

1. **Task 1: Redis client singleton, session dependency, FastAPI app factory with lifespan** - `c7150d0` (feat)
2. **Task 2: Health endpoint and arq worker with test job** - `700f917` (feat)

**Plan metadata:** (committed after summary creation)

## Files Created/Modified

- `backend/src/wxcode_adm/common/redis_client.py` - Redis.from_url singleton with decode_responses=True; get_redis dependency returning the shared client
- `backend/src/wxcode_adm/dependencies.py` - get_session AsyncGenerator with try/yield/commit/except rollback pattern; re-exports get_redis
- `backend/src/wxcode_adm/main.py` - create_app factory with lifespan (PostgreSQL+Redis verify, tenant guard, graceful shutdown), CORS middleware, AppError exception handler, module-level app instance
- `backend/src/wxcode_adm/common/router.py` - GET /health endpoint with live SELECT 1 and Redis ping checks; returns 200 or 503 with error details
- `backend/src/wxcode_adm/tasks/worker.py` - arq WorkerSettings (functions, on_startup, on_shutdown, redis_settings, max_jobs, job_timeout), test_job, get_arq_pool helper

## Decisions Made

- arq worker is NOT started from the FastAPI lifespan — it runs as a dedicated separate process via `arq wxcode_adm.tasks.worker.WorkerSettings`. Starting it inside lifespan would couple its lifecycle to the API process and prevent horizontal scaling of workers independently.
- `redis_client` is a module-level singleton shared across all request handlers. The connection pool is managed internally by redis.asyncio. Per-request Redis connections would be wasteful. `aclose()` is called in lifespan shutdown.
- `get_session` uses explicit try/yield/commit/except rollback pattern (not `async with session` context manager) to give precise control: commit happens after the endpoint body returns successfully, rollback on any exception including HTTPException.

## Deviations from Plan

None — plan executed exactly as written. All patterns from the plan's action section followed precisely. No bugs or missing functionality discovered.

## Issues Encountered

PostgreSQL and Redis were not running locally during execution (Plan 03 sets up Docker Compose). Structural verification was performed via Python import checks and static analysis confirming all must_have truths and key_links. Live infrastructure tests will be confirmed when Plan 03 Docker Compose is running.

## User Setup Required

None — no new external service configuration required. The application needs PostgreSQL and Redis running (configured in Plan 03 Docker Compose). Environment variables already documented in `backend/.env.example` from Plan 01.

## Next Phase Readiness

- `uvicorn wxcode_adm.main:app --host 0.0.0.0 --port 8060` starts the FastAPI app (requires running PostgreSQL and Redis)
- `arq wxcode_adm.tasks.worker.WorkerSettings` starts the arq job processor (requires running Redis)
- Plan 03 (Docker Compose) can now wire up the full stack: PostgreSQL + Redis + API + worker
- All subsequent phases can use `get_session`, `get_redis`, and `WorkerSettings.functions` directly

---
*Phase: 01-foundation*
*Completed: 2026-02-22*

## Self-Check: PASSED

- All 5 created files exist on disk
- Both task commits (c7150d0, 700f917) verified in git log
- Import verification: all modules import cleanly with Python 3.11
- Route verification: /api/v1/health route registered, CORS middleware active
- Must_have truths verified: SELECT 1 in lifespan, redis ping, tenant guard, session commit/rollback, WorkerSettings.functions
