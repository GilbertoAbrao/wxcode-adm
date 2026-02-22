---
phase: 01-foundation
plan: "01"
subsystem: database
tags: [python, fastapi, sqlalchemy, asyncpg, alembic, pydantic-settings, postgresql, multi-tenancy, arq, redis]

requires: []

provides:
  - Installable Python package wxcode-adm with all Phase 1 dependencies pinned
  - pydantic-settings Settings singleton with startup validation (fails fast on missing env vars)
  - SQLAlchemy 2.0 async engine with asyncpg, expire_on_commit=False, pool_pre_ping
  - DeclarativeBase with constraint naming conventions and TimestampMixin (id/created_at/updated_at)
  - TenantModel abstract base class with tenant_id column and do_orm_execute guard (Phase 1 warning, Phase 3 hard raise)
  - SoftDeleteMixin for tenant/user models
  - Domain module scaffolding (auth/, tenants/, billing/, users/, common/, db/, tasks/)
  - Alembic async migration runner initialized with env.py reading DATABASE_URL from settings
  - Shared domain exceptions (AppError, NotFoundError, ForbiddenError, ConflictError, TenantIsolationError)

affects:
  - 01-02 (FastAPI app factory, health endpoint, Redis, arq worker builds on this foundation)
  - 01-03 (Docker Compose uses engine, alembic, Redis)
  - All subsequent phases (every model inherits from TenantModel or Base + TimestampMixin)

tech-stack:
  added:
    - fastapi==0.131.0
    - uvicorn[standard]==0.41.0
    - sqlalchemy==2.0.46
    - asyncpg==0.31.0
    - alembic==1.18.4
    - pydantic-settings==2.13.1
    - redis==5.3.1 (fixed from plan's incorrect 7.2.0 - see deviations)
    - arq==0.27.0
    - pytest, pytest-asyncio, httpx (dev)
  patterns:
    - AsyncAttrs + DeclarativeBase with MetaData naming_convention for Alembic autogenerate reliability
    - async_sessionmaker with expire_on_commit=False (mandatory for async FastAPI)
    - do_orm_execute event for tenant isolation guard
    - Module-level settings singleton for startup validation
    - NullPool in Alembic env.py only (not in production API engine)

key-files:
  created:
    - backend/pyproject.toml
    - backend/src/wxcode_adm/__init__.py
    - backend/src/wxcode_adm/config.py
    - backend/src/wxcode_adm/db/__init__.py
    - backend/src/wxcode_adm/db/base.py
    - backend/src/wxcode_adm/db/engine.py
    - backend/src/wxcode_adm/db/tenant.py
    - backend/src/wxcode_adm/common/__init__.py
    - backend/src/wxcode_adm/common/exceptions.py
    - backend/src/wxcode_adm/auth/__init__.py
    - backend/src/wxcode_adm/tenants/__init__.py
    - backend/src/wxcode_adm/billing/__init__.py
    - backend/src/wxcode_adm/users/__init__.py
    - backend/src/wxcode_adm/tasks/__init__.py
    - backend/alembic.ini
    - backend/alembic/env.py
    - backend/alembic/script.py.mako
    - backend/alembic/versions/.gitkeep
    - backend/.env.example
    - frontend/.gitkeep
  modified: []

key-decisions:
  - "redis==5.3.1 not 7.2.0 — redis-py client library is at 5.x; 7.x is the Redis server version; arq 0.27.0 requires redis<6"
  - "TenantModel guard uses logged WARNING in Phase 1 (not hard raise) — avoids breaking health checks and seed functions that legitimately query without tenant context; upgrades to RuntimeError in Phase 3"
  - "NullPool in alembic/env.py only — production API engine uses AsyncAdaptedQueuePool with pool_size=10/max_overflow=20"
  - "Domain exceptions are NOT HTTPException subclasses — caught by FastAPI handler in Plan 02"

patterns-established:
  - "Pattern: All domain models inherit from TenantModel (tenant-scoped) or Base+TimestampMixin (platform-wide)"
  - "Pattern: str(settings.DATABASE_URL) required — pydantic v2 PostgresDsn returns Url object not string"
  - "Pattern: install_tenant_guard(async_session_maker) called once in lifespan startup"
  - "Pattern: Alembic env.py imports all model modules to populate Base.metadata for autogenerate"

requirements-completed: []

duration: 4min
completed: 2026-02-22
---

# Phase 1 Plan 01: Monorepo Skeleton and Foundation Summary

**SQLAlchemy 2.0 async engine with asyncpg, TenantModel isolation guard, pydantic-settings startup validation, and Alembic async migration runner installed in monorepo structure**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-22T21:38:14Z
- **Completed:** 2026-02-22T21:41:36Z
- **Tasks:** 2
- **Files modified:** 20

## Accomplishments

- Monorepo structure established with backend/src/wxcode_adm/ package and all domain module directories
- pydantic-settings Settings singleton with PostgresDsn, SecretStr fields and module-level singleton that raises ValidationError on startup if env vars missing
- SQLAlchemy 2.0 async engine (asyncpg driver) with AsyncAttrs DeclarativeBase, naming conventions, TimestampMixin, and correct async configuration (expire_on_commit=False, pool_pre_ping, NullPool only in Alembic)
- TenantModel abstract base class with tenant_id column and do_orm_execute guard scaffold (Phase 1: warning; Phase 3: hard raise)
- Alembic initialized with async template, env.py reading DATABASE_URL from pydantic-settings

## Task Commits

Each task was committed atomically:

1. **Task 1: Monorepo structure and Python package** - `1f5781d` (feat)
2. **Task 2: Config, database layer, TenantModel, Alembic, shared exceptions** - `bfac3a2` (feat)

**Plan metadata:** (committed after summary creation)

## Files Created/Modified

- `backend/pyproject.toml` - Project metadata with all Phase 1 dependencies pinned; redis corrected to 5.3.1
- `backend/src/wxcode_adm/config.py` - pydantic-settings Settings singleton with startup validation
- `backend/src/wxcode_adm/db/base.py` - DeclarativeBase with naming conventions and TimestampMixin
- `backend/src/wxcode_adm/db/engine.py` - Async engine and async_session_maker with correct pool settings
- `backend/src/wxcode_adm/db/tenant.py` - TenantModel with tenant_id, SoftDeleteMixin, and do_orm_execute guard
- `backend/src/wxcode_adm/common/exceptions.py` - Domain exceptions hierarchy (AppError, NotFoundError, ForbiddenError, ConflictError, TenantIsolationError)
- `backend/alembic/env.py` - Async migration runner reading DATABASE_URL from settings, targeting Base.metadata
- `backend/alembic.ini` - Alembic configuration (sqlalchemy.url placeholder overridden in env.py)
- `backend/.env.example` - Environment variable template for all required settings

## Decisions Made

- Used `redis==5.3.1` (arq 0.27.0 requires redis<6; plan incorrectly specified redis==7.2.0 which is the Redis server version not the Python client)
- TenantModel guard logs WARNING in Phase 1 instead of raising RuntimeError — avoids blocking health checks and seed functions that legitimately need cross-tenant queries before request middleware exists
- Domain exceptions are pure Python exceptions (not HTTPException subclasses) to keep domain layer decoupled from HTTP transport

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed incorrect redis-py version in pyproject.toml**
- **Found during:** Task 1 (pip install -e ".[dev]")
- **Issue:** Plan specified `redis==7.2.0` but the redis-py Python client library is at version 5.x (7.x is the Redis server version). arq 0.27.0 requires `redis<6,>=4.2.0`, so 7.2.0 caused a ResolutionImpossible error.
- **Fix:** Changed to `redis==5.3.1` (latest compatible version that satisfies arq's constraint)
- **Files modified:** `backend/pyproject.toml`
- **Verification:** `pip install -e ".[dev]"` succeeded; all packages installed cleanly
- **Committed in:** `1f5781d` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 dependency version bug)
**Impact on plan:** Essential fix for package installation. No scope creep. All other pinned versions from research are correct.

## Issues Encountered

None beyond the redis version conflict resolved via Rule 1.

## User Setup Required

None - no external service configuration required for this plan. The `.env` file (from `.env.example`) requires real JWT RSA keys and database credentials for running the application, but those are documented in `.env.example`.

## Next Phase Readiness

- Python package installed and importable
- Database layer, config, and exception hierarchy in place
- Alembic ready for first migration when domain models are created in Phase 2
- Plan 02 can now build FastAPI app factory, health endpoint, Redis client, and arq worker on top of this foundation

---
*Phase: 01-foundation*
*Completed: 2026-02-22*
