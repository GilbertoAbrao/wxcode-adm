# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-22)

**Core value:** Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.
**Current focus:** Phase 4 — Billing Core

## Current Position

Phase: 4 of 8 (Billing Core) — IN PROGRESS
Plan: 4 of 5 in current phase (04-04 complete — Customer Portal access, subscription status API, and plan enforcement dependencies)
Status: Plan 04-04 complete — POST /billing/portal, GET /billing/subscription, billing/dependencies.py with require_active_subscription, check_token_quota, check_member_cap, enforce_member_cap, _enforce_active_subscription, _enforce_token_quota
Last activity: 2026-02-23 — Plan 04-04 complete: Stripe Customer Portal, subscription status, and plan enforcement dependencies

Progress: [████████████████] 75%

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
| 04-billing-core | 2/5 | 6 min | 3 min |

**Recent Trend:**
- Last 5 plans: 2 min, 6 min, 4 min, 6 min, 3 min
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
| Phase 04-billing-core P01 | 3 | 2 tasks | 9 files |
| Phase 04-billing-core P02 | 3 | 2 tasks | 4 files |
| Phase 04-billing-core P04 | 4 | 2 tasks | 3 files |
| Phase 04-billing-core P03 | 4 | 2 tasks | 5 files |

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
- [04-01]: stripe[async]==14.3.0 uses modern StripeClient constructor (not legacy stripe.api_key global) — all async calls use _async suffix on methods
- [04-01]: Stripe failures are non-blocking — wrapped in try/except with logger.warning; plan DB record is authoritative source of truth
- [04-01]: Plan soft-deleted via is_active=False — hard delete blocked by TenantSubscription FK constraint
- [04-01]: overage_rate_cents_per_token stored as integer hundredths of a cent (e.g., 4 = $0.00004/token) — avoids float precision issues
- [04-01]: member_cap=-1 convention means unlimited members on a plan
- [04-01]: Stripe IDs excluded from PlanResponse — internal implementation detail not needed by API consumers
- [04-02]: create_workspace uses lazy import for billing bootstrap — avoids circular import billing.service -> tenants.models at module load; matches auto_join_pending_invitations pattern
- [04-02]: create_stripe_customer is best-effort — Stripe failure logs WARNING, returns None; checkout creates customer lazily if needed
- [04-02]: bootstrap_free_subscription raises RuntimeError if no free plan exists — free plan is a hard system requirement (must be seeded)
- [04-02]: require_billing_access: Owner always has implicit billing access; other roles need explicit billing_access=True toggle
- [04-04]: _enforce_active_subscription and _enforce_token_quota are pure sync helpers — Plan 05 tests call them directly without FastAPI Depends wiring
- [04-04]: enforce_member_cap is a standalone async utility (not a FastAPI Depends) — avoids double tenant-context resolution since require_role already resolves it in create_invitation
- [04-04]: check_token_quota chains on require_active_subscription — quota check only runs if subscription is not past_due/canceled
- [04-04]: Overage billing rule: _enforce_token_quota only raises for monthly_fee_cents==0 plans — paid customers are never blocked regardless of token usage
- [Phase 04-billing-core]: Webhook router is a separate file from router.py — fundamentally different auth requirements (Stripe-Signature, not JWT)
- [Phase 04-billing-core]: Two-layer webhook idempotency: arq _job_id (Redis, in-flight dedup) + WebhookEvent table (permanent DB record, outlasts arq TTL)
- [Phase 04-billing-core]: payment_failed revokes JWT tokens via RefreshToken delete AND Redis blacklist with ACCESS_TOKEN_TTL_HOURS TTL

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: MongoDB CVE-2025-14847 (MongoBleed) — must verify patched version (8.0.17+, 7.0.28+, or 6.0.27+) before any data is stored. Address in Phase 1.
- [Research]: Stripe Billing Meters API (post-2025-03-31 deprecation of legacy usage records) — verify exact event format and idempotency requirements during Phase 4 planning.
- [Research]: qrcode version 8.2 is MEDIUM confidence (search result, not direct PyPI fetch) — verify with pip install "qrcode[pil]" during Phase 6.

## Session Continuity

Last session: 2026-02-23
Stopped at: Completed 04-04-PLAN.md — Customer Portal, subscription status API, plan enforcement dependencies, Plan 4 of 5 in Phase 4
Resume file: .planning/phases/04-billing-core/04-05-PLAN.md
