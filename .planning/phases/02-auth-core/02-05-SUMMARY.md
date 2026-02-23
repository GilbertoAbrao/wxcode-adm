---
phase: 02-auth-core
plan: 05
subsystem: auth
tags: [fastapi, jwt, rsa256, sqlalchemy, alembic, pytest, fakeredis, httpx, sqlite, integration-tests]

# Dependency graph
requires:
  - phase: 02-auth-core-01
    provides: JWT sign/decode utilities (jwt.py), JWKS endpoint, User/RefreshToken models
  - phase: 02-auth-core-02
    provides: signup, verify-email, resend-verification service functions and OTP Redis patterns
  - phase: 02-auth-core-03
    provides: login, refresh, logout, blacklist/replay detection service functions
  - phase: 02-auth-core-04
    provides: forgot-password, reset-password endpoints with itsdangerous tokens
provides:
  - FastAPI OAuth2PasswordBearer scheme configured for /api/v1/auth/login
  - get_current_user dependency (JWT decode + Redis blacklist + User lookup)
  - require_verified dependency (email verification enforcement, HTTP 403)
  - GET /api/v1/auth/me protected endpoint for current user info
  - Alembic migration 001 creating users and refresh_tokens tables
  - 18 integration tests covering all 7 Phase 2 success criteria (all passing)
  - conftest.py with test fixtures (rsa_keys, test_db, test_redis, client)
affects: [03-rbac, 05-api, 07-user-account]

# Tech tracking
tech-stack:
  added:
    - fakeredis==2.26.2 (FakeRedis for async Redis in tests)
    - httpx (AsyncClient + ASGITransport for ASGI integration tests)
    - aiosqlite (in-memory SQLite for test DB)
    - cryptography (RSA key generation in test fixtures)
  patterns:
    - FastAPI dependency injection chain: oauth2_scheme -> get_current_user -> require_verified
    - app.dependency_overrides for test isolation (get_session, get_redis)
    - monkeypatch.setattr for settings JWT keys and reset_serializer per test
    - Arq pool mocked in tests via monkeypatch to avoid real Redis connections
    - _signup_verify_login helper for multi-step auth flow tests

key-files:
  created:
    - backend/src/wxcode_adm/auth/dependencies.py
    - backend/alembic/versions/001_add_users_and_refresh_tokens_tables.py
    - backend/tests/conftest.py
    - backend/tests/test_auth.py
  modified:
    - backend/src/wxcode_adm/auth/router.py (added /me endpoint)
    - backend/alembic/env.py (auth models import for autogenerate)
    - backend/src/wxcode_adm/db/base.py (Python-level defaults for SQLite compat)
    - backend/src/wxcode_adm/auth/service.py (timezone-naive datetime fix in refresh)
    - backend/pyproject.toml (fakeredis dev dependency)

key-decisions:
  - "conftest yields (client, redis, app, test_db) 4-tuple so tests can access app.dependency_overrides and test_db session factory directly"
  - "Alembic migration written manually (no live PostgreSQL available) — matches model definitions exactly"
  - "db/base.py TimestampMixin gets Python-level defaults for created_at/updated_at — server_defaults remain for production, Python defaults serve SQLite test compat"
  - "refresh service uses tzinfo-aware comparison: naive datetimes from SQLite get utc tzinfo attached before comparison"
  - "Reset password test uses generate_reset_token() directly (plan spec option b) — simpler than mocking arq job delivery"

patterns-established:
  - "Auth dependency chain: Depends(oauth2_scheme) -> decode_access_token -> blacklist check -> db.get(User) — all in get_current_user"
  - "Integration test fixture yields 4-tuple (client, redis, app, db) for full access to test infrastructure"
  - "Test helpers (e.g., _signup_verify_login, _get_user_from_db) reduce repetition across lifecycle tests"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07]

# Metrics
duration: 6min
completed: 2026-02-23
---

# Phase 2 Plan 05: Auth Dependencies, Alembic Migration, and Integration Tests Summary

**FastAPI auth dependency chain (get_current_user + require_verified), Alembic migration for users/refresh_tokens, and 18 integration tests proving all 7 Phase 2 auth success criteria**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-23T13:34:13Z
- **Completed:** 2026-02-23T13:40:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- `get_current_user` FastAPI dependency: validates Bearer JWT, checks Redis blacklist, loads User from DB
- `require_verified` dependency: wraps `get_current_user` and enforces `email_verified=True` (HTTP 403 otherwise)
- `GET /api/v1/auth/me` protected endpoint using full dependency chain (`require_verified`)
- Alembic migration `001` creating `users` and `refresh_tokens` tables with all indexes and FK constraints
- 18 integration tests covering the full auth lifecycle — all 21 tests in the suite pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Auth dependencies, /me endpoint, and Alembic migration** - `a8ba1f4` (feat)
2. **Task 2: Integration tests and auto-fixes** - `f03ac08` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/auth/dependencies.py` — oauth2_scheme, get_current_user, require_verified
- `backend/src/wxcode_adm/auth/router.py` — added GET /me endpoint with require_verified
- `backend/alembic/env.py` — auth models import for autogenerate
- `backend/alembic/versions/001_add_users_and_refresh_tokens_tables.py` — Alembic migration
- `backend/tests/conftest.py` — rsa_keys, test_db, test_redis, client fixtures
- `backend/tests/test_auth.py` — 18 integration tests covering all Phase 2 success criteria
- `backend/src/wxcode_adm/db/base.py` — Python-level defaults for created_at/updated_at (SQLite compat)
- `backend/src/wxcode_adm/auth/service.py` — timezone-naive datetime handling in refresh
- `backend/pyproject.toml` — fakeredis==2.26.2 added to dev dependencies

## Decisions Made

- Alembic migration written manually (no live PostgreSQL available for autogenerate) — migration is functionally identical to what autogenerate would produce from the models
- `conftest.py` client fixture yields `(client, redis, app, test_db)` 4-tuple so tests can access `app.dependency_overrides` and the `test_db` session factory for direct DB queries without hitting HTTP endpoints
- Reset password test uses `generate_reset_token()` directly (plan spec option b) — avoids mocking arq job delivery while still testing the full reset flow end-to-end
- `get_current_user` raises `InvalidTokenError` (not HTTPException) so the AppError exception handler converts it to the correct JSON 401 response

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SQLite-incompatible server defaults in TimestampMixin**
- **Found during:** Task 2 (first test run)
- **Issue:** `created_at` and `updated_at` columns only had `server_default=text("now()")`. SQLite doesn't have `now()`, causing INSERT failures in test DB.
- **Fix:** Added Python-level `default=lambda: datetime.now(timezone.utc)` to both columns in `db/base.py`. PostgreSQL still uses `server_default` in production; SQLite uses the Python default.
- **Files modified:** `backend/src/wxcode_adm/db/base.py`
- **Verification:** All 18 auth tests pass; 3 existing tenant guard tests still pass
- **Committed in:** `f03ac08` (Task 2 commit)

**2. [Rule 1 - Bug] Timezone-naive datetime comparison in refresh service**
- **Found during:** Task 2 (refresh token tests)
- **Issue:** SQLite returns `expires_at` as timezone-naive `datetime`, while the service compares with `datetime.now(timezone.utc)` (timezone-aware), causing `TypeError: can't compare offset-naive and offset-aware datetimes`.
- **Fix:** Added tzinfo check in `service.refresh`: if `expires_at.tzinfo is None`, attach `utc` before comparison.
- **Files modified:** `backend/src/wxcode_adm/auth/service.py`
- **Verification:** `test_refresh_returns_new_tokens` and `test_refresh_rejects_consumed_token` pass
- **Committed in:** `f03ac08` (Task 2 commit)

**3. [Rule 3 - Blocking] Alembic autogenerate requires live PostgreSQL**
- **Found during:** Task 1 (alembic revision command)
- **Issue:** `alembic revision --autogenerate` connects to PostgreSQL to introspect current schema. No PostgreSQL available in local dev environment.
- **Fix:** Wrote the migration file manually, deriving CREATE TABLE statements directly from model definitions. Result is equivalent to what autogenerate would produce.
- **Files modified:** `backend/alembic/versions/001_add_users_and_refresh_tokens_tables.py`
- **Verification:** Migration file exists with correct CreateTable for both tables; alembic env.py correctly imports auth models
- **Committed in:** `a8ba1f4` (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All auto-fixes essential for test suite operation. No scope creep.

## Issues Encountered

- `fakeredis[aiocompat]` extra does not exist in fakeredis 2.26.2 — changed pyproject.toml to `fakeredis==2.26.2` (no extras needed; `fakeredis.aioredis` module is always included)
- Each `create_app()` call creates a fresh app instance, so tests accessing `app.dependency_overrides` must use the specific `app` instance returned by the `client` fixture — fixed by extending fixture yield to 4-tuple

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 2 (Auth Core) complete: all 7 success criteria proven by passing tests
- `require_verified` dependency ready for protected endpoints in Phase 3+ (RBAC, user account)
- Alembic migration ready to run against PostgreSQL: `alembic upgrade head`
- No blockers for Phase 3 (RBAC/Tenant Membership)

---
*Phase: 02-auth-core*
*Completed: 2026-02-23*
