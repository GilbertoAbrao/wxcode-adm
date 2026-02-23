# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-22)

**Core value:** Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.
**Current focus:** Phase 2 — Identity (next phase)

## Current Position

Phase: 2 of 8 (Auth Core) — IN PROGRESS
Plan: 1 of 5 in current phase (02-01 complete)
Status: Plan 02-01 complete — RSA/JWT/JWKS/User model/auth exceptions/password hashing ready
Last activity: 2026-02-23 — Plan 02-01 complete: RS256 JWT, JWKS endpoint, User model, Argon2 password hashing

Progress: [████░░░░░░] 16%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 5 min
- Total execution time: 0.37 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 4/4 | 23 min | 6 min |

**Recent Trend:**
- Last 5 plans: 4 min, 2 min, 15 min, 2 min
- Trend: Stable

*Updated after each plan completion*
| Phase 02-auth-core P01 | 4 | 2 tasks | 9 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Research]: PyJWT over python-jose (CVEs, unmaintained), pwdlib/argon2 over passlib (Python 3.13 incompatible)
- [Research]: arq over Celery for async tasks (async-native, uses existing Redis)
- [Research]: authlib for OAuth2 social login (native Starlette integration, PKCE support)
- [Research]: slowapi over fastapi-limiter (fastapi-limiter unmaintained since 2023)
- [Research]: TenantDocument base class must be Phase 1 — retrofitting cross-tenant isolation under live traffic is a migration risk
- [01-01]: redis==5.3.1 not 7.2.0 — redis-py client library is at 5.x; 7.x is the Redis server version; arq 0.27.0 requires redis<6
- [01-01]: TenantModel guard uses logged WARNING in Phase 1 (not hard raise) — avoids breaking health checks and seed functions; upgrades to RuntimeError in Phase 3
- [01-01]: Domain exceptions are NOT HTTPException subclasses — caught by FastAPI handler in Plan 02
- [01-02]: arq worker NOT started from lifespan — separate process for independent scaling; use arq wxcode_adm.tasks.worker.WorkerSettings
- [01-02]: redis_client is module-level singleton (not per-request) — pool managed by redis.asyncio, closed via aclose() in lifespan shutdown
- [01-02]: get_session uses explicit try/yield/commit/except/rollback pattern for precise commit timing relative to response
- [01-03]: python:3.11-slim (not alpine) — asyncpg requires gcc for compiling C extensions; alpine adds too much build complexity
- [01-03]: alembic upgrade head runs in api container entrypoint — simpler for dev; healthchecks serialize postgres readiness
- [01-03]: DATABASE_URL and REDIS_URL overridden in environment block (not env_file) — Docker hostnames take precedence over .env localhost values with no .env modification needed
- [01-03]: Worker uses same Dockerfile as api (build: context: ./backend) — command override runs arq instead of uvicorn; avoids second Dockerfile
- [01-04]: do_orm_execute event registered on Session (sync_session_class) not AsyncSession — AsyncSession does not support that event; guard was non-functional before this fix
- [01-04]: TenantIsolationError raised on unguarded ORM SELECT immediately (ROADMAP SC#2 gap closed) — no Phase 3 deferral needed
- [01-04]: aiosqlite used for in-memory SQLite async testing — no Docker/PostgreSQL needed in test suite
- [Phase 02-auth-core]: JWT kid set in JOSE header via jwt.encode headers param (not payload) — enables correct JWKS kid matching per RFC 7517
- [Phase 02-auth-core]: User model inherits Base+TimestampMixin (not TenantModel) — auth is platform-level, users span multiple tenants
- [Phase 02-auth-core]: JWKS endpoint root-mounted without API prefix — RFC 5785 requires /.well-known/ at domain root

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: MongoDB CVE-2025-14847 (MongoBleed) — must verify patched version (8.0.17+, 7.0.28+, or 6.0.27+) before any data is stored. Address in Phase 1.
- [Research]: Stripe Billing Meters API (post-2025-03-31 deprecation of legacy usage records) — verify exact event format and idempotency requirements during Phase 4 planning.
- [Research]: qrcode version 8.2 is MEDIUM confidence (search result, not direct PyPI fetch) — verify with pip install "qrcode[pil]" during Phase 6.

## Session Continuity

Last session: 2026-02-23
Stopped at: Completed 02-01-PLAN.md — RS256 JWT/JWKS/User model/auth exceptions/password hashing; 2 tasks, 9 files
Resume file: None
