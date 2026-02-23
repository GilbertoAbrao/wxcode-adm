# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-22)

**Core value:** Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.
**Current focus:** Phase 3 — Multi-Tenancy and RBAC

## Current Position

Phase: 3 of 8 (Multi-Tenancy and RBAC) — COMPLETE
Plan: 5 of 5 in current phase (03-05 complete — migration 002, 33 integration tests covering all 6 Phase 3 success criteria)
Status: Plan 03-05 complete — Alembic migration 002 (4 tables), 33 integration tests, 54 total tests passing (auth + tenants), Phase 3 COMPLETE
Last activity: 2026-02-23 — Plan 03-05 complete: migration 002 and full integration test suite for all Phase 3 success criteria

Progress: [██████████] 62%

## Performance Metrics

**Velocity:**
- Total plans completed: 11
- Average duration: 5 min
- Total execution time: 0.87 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 4/4 | 23 min | 6 min |
| 02-auth-core | 5/5 | 20 min | 4 min |
| 03-multi-tenancy-and-rbac | 5/5 | 22 min | 4 min |

**Recent Trend:**
- Last 5 plans: 3 min, 2 min, 6 min, 4 min, 6 min
- Trend: Stable

*Updated after each plan completion*
| Phase 02-auth-core P01 | 4 | 2 tasks | 9 files |
| Phase 02-auth-core P02 | 3 | 2 tasks | 7 files |
| Phase 02-auth-core P03 | 3 | 2 tasks | 5 files |
| Phase 02-auth-core P04 | 2 | 2 tasks | 4 files |
| Phase 02-auth-core P05 | 6 | 2 tasks | 9 files |
| Phase 03-multi-tenancy-and-rbac P01 | 4 | 3 tasks | 6 files |
| Phase 03 P02 | 4 | 2 tasks | 6 files |
| Phase 03 P03 | 7 | 2 tasks | 6 files |
| Phase 03 P04 | 4 | 2 tasks | 2 files |
| Phase 03-multi-tenancy-and-rbac P05 | 6 | 2 tasks | 3 files |

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
- [02-02]: arq pool created per enqueue call (not singleton) — avoids connection leaks in service layer
- [02-02]: verify_otp_code checks code BEFORE incrementing counter — correct code on 3rd attempt still succeeds
- [02-02]: resend_verification returns silently on unknown email — prevents user enumeration
- [02-02]: send_reset_email stub defined in Plan 02 to avoid touching worker.py again in Plan 04
- [02-02]: seed_super_admin uses local import in lifespan to avoid circular import at module load
- [02-03]: EmailNotVerifiedError updated to accept optional error_code/message kwargs — backward-compatible with existing no-arg callers
- [02-03]: ReplayDetectedError error_code changed to REPLAY_DETECTED (from AUTH_REPLAY_DETECTED) per plan spec; triggers full session revocation
- [02-03]: blacklist_access_token uses jwt.decode with verify_exp=False — allows blacklisting nearly-expired tokens on logout
- [02-03]: Shadow key pattern auth:replay:{sha256} maps consumed refresh token hash to user_id for replay detection across DB row deletion
- [02-04]: pw_hash as itsdangerous salt — changing password automatically invalidates reset token without any DB token storage
- [02-04]: loads_unsafe() for two-step verification — extract email first (unsigned) to find user for pw_hash, then full verify (breaks circular dependency)
- [02-04]: reset_serializer uses JWT_PRIVATE_KEY as secret, salt="password-reset" namespaces from JWT usage
- [02-04]: Reset link uses ALLOWED_ORIGINS[0] as base URL placeholder — adjusted in Phase 7 frontend integration
- [Phase 02-auth-core]: conftest yields (client, redis, app, test_db) 4-tuple so tests can access app.dependency_overrides and test_db session factory directly
- [Phase 02-auth-core]: db/base.py TimestampMixin gets Python-level defaults for created_at/updated_at — server_defaults remain for production, Python defaults serve SQLite test compat
- [Phase 02-auth-core]: refresh service uses tzinfo-aware comparison: naive datetimes from SQLite get utc tzinfo attached before comparison
- [Phase 03-multi-tenancy-and-rbac]: native_enum=False on MemberRole Enum columns — avoids PostgreSQL CREATE TYPE and Alembic migration pitfalls
- [Phase 03-multi-tenancy-and-rbac]: from __future__ import annotations in tenants/models.py — Python 3.9.6 runtime requires Optional[X] instead of X | None
- [Phase 03-multi-tenancy-and-rbac]: billing_access is Boolean toggle on TenantMembership (not a role) — propagated from Invitation on acceptance
- [Phase 03]: UpdateTenantRequest defined in router.py (not schemas.py) — keeps schemas.py clean for Plan 03-03 invitation/transfer additions
- [Phase 03]: list_members returns list[dict] (not list[MembershipResponse]) — email comes from User relationship, not TenantMembership ORM column; dict avoids from_attributes mismatch
- [Phase 03]: invitation_serializer pre-wired in service.py in Plan 03-02 — avoids touching service.py again in Plan 03-03; tests monkeypatch via client fixture
- [03-03]: auto_join_pending_invitations uses lazy import inside verify_email to avoid circular import (auth.service -> tenants.service -> auth.models)
- [03-03]: invitation_router mounted separately (not under /tenants/current) — accepting user may have no existing tenant membership
- [03-03]: auto_join_pending_invitations is fault-tolerant — individual failures wrapped in try/except, logged as warnings, skipped; email verification always succeeds
- [03-04]: from __future__ import annotations added to service.py — Python 3.9.6 runtime does not support bool | None union syntax; matches pattern in models.py
- [03-04]: change_role guard order: owner self-demotion check FIRST before privilege-level guard — avoids false InsufficientRoleError when Owner acts on own membership
- [03-04]: TokenExpiredError reused for expired ownership transfers — semantically matches token expiry; no new exception class needed
- [03-04]: Router queries User email separately after change_role — service returns pure membership; router handles response shaping with User join
- [Phase 03]: conftest.py must patch tenant_service_module.get_arq_pool alongside auth_service — invite_user calls get_arq_pool for email jobs
- [Phase 03]: _signup_verify_login tracks pre-signup OTP keys in Redis to correctly identify new user's OTP key when multiple users exist in test DB
- [Phase 03]: Alembic migration 002 uses String(20) for role columns (not native ENUM) matching native_enum=False decision from Plan 03-01

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: MongoDB CVE-2025-14847 (MongoBleed) — must verify patched version (8.0.17+, 7.0.28+, or 6.0.27+) before any data is stored. Address in Phase 1.
- [Research]: Stripe Billing Meters API (post-2025-03-31 deprecation of legacy usage records) — verify exact event format and idempotency requirements during Phase 4 planning.
- [Research]: qrcode version 8.2 is MEDIUM confidence (search result, not direct PyPI fetch) — verify with pip install "qrcode[pil]" during Phase 6.

## Session Continuity

Last session: 2026-02-23
Stopped at: Completed 03-05-PLAN.md — Migration 002 (4 tenant tables) and 33 integration tests covering all 6 Phase 3 success criteria. Phase 3 COMPLETE.
Resume file: .planning/phases/04-billing/04-01-PLAN.md (next phase)
