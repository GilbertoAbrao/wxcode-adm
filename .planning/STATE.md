# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-22)

**Core value:** Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.
**Current focus:** Phase 1 — Foundation

## Current Position

Phase: 1 of 8 (Foundation)
Plan: 2 of 3 in current phase
Status: In progress
Last activity: 2026-02-22 — Plan 01-02 complete: FastAPI app factory, health endpoint, Redis client, arq worker

Progress: [██░░░░░░░░] 8%

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: 3 min
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 2/3 | 6 min | 3 min |

**Recent Trend:**
- Last 5 plans: 4 min, 2 min
- Trend: Faster

*Updated after each plan completion*

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

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: MongoDB CVE-2025-14847 (MongoBleed) — must verify patched version (8.0.17+, 7.0.28+, or 6.0.27+) before any data is stored. Address in Phase 1.
- [Research]: Stripe Billing Meters API (post-2025-03-31 deprecation of legacy usage records) — verify exact event format and idempotency requirements during Phase 4 planning.
- [Research]: qrcode version 8.2 is MEDIUM confidence (search result, not direct PyPI fetch) — verify with pip install "qrcode[pil]" during Phase 6.

## Session Continuity

Last session: 2026-02-22
Stopped at: Completed 01-02-PLAN.md — FastAPI app factory, health endpoint, Redis client, arq worker with WorkerSettings
Resume file: None
