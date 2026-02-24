---
phase: 05-platform-security
plan: 02
subsystem: audit
tags: [audit, sqlalchemy, jsonb, arq, cron, fastapi, postgresql]

# Dependency graph
requires:
  - phase: 02-auth-core
    provides: User model, require_verified dependency, JWT auth
  - phase: 03-multi-tenancy-and-rbac
    provides: Tenant model, TenantMembership, tenant router endpoints
  - phase: 04-billing-core
    provides: billing plan/subscription endpoints, webhook router
  - phase: 05-platform-security (plan 01)
    provides: rate limiting middleware, request: Request params on auth endpoints

provides:
  - Immutable audit_logs table (append-only, no updated_at, JSONB details)
  - write_audit() helper for atomic audit entries within caller's DB transaction
  - purge_old_audit_logs() arq cron job (daily 2 AM UTC, configurable retention)
  - GET /admin/audit-logs super-admin paginated query endpoint
  - All write operations (POST/PATCH/DELETE) across auth, tenants, billing instrumented

affects:
  - 05-platform-security (plans 03, 04)
  - Future phases that add new write endpoints (must call write_audit)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - write_audit called after service operation, within same DB transaction (atomic)
    - arq cron job pattern: receives ctx dict with session_maker, runs DELETE query
    - Append-only table: no TimestampMixin, no updated_at, manual created_at column
    - JSONB details column for flexible structured context per operation
    - Optional UUID FK columns use Mapped[Optional[uuid.UUID]] for Python 3.9 compat

key-files:
  created:
    - backend/src/wxcode_adm/audit/__init__.py
    - backend/src/wxcode_adm/audit/models.py
    - backend/src/wxcode_adm/audit/service.py
    - backend/src/wxcode_adm/audit/schemas.py
    - backend/src/wxcode_adm/audit/router.py
  modified:
    - backend/src/wxcode_adm/tasks/worker.py
    - backend/src/wxcode_adm/main.py
    - backend/alembic/env.py
    - backend/src/wxcode_adm/auth/router.py
    - backend/src/wxcode_adm/tenants/router.py
    - backend/src/wxcode_adm/billing/router.py

key-decisions:
  - "AuditLog has no TimestampMixin and no updated_at — append-only table semantics enforced at model level"
  - "write_audit does NOT commit — caller's session commit includes audit entry atomically with business data"
  - "purge_old_audit_logs is arq cron job at 2 AM UTC — uses own session from ctx[session_maker], commits immediately"
  - "login audit lookup queries User.id by email (indexed) after successful login — only runs on success, lightweight"
  - "billing cancel_invitation was using _ for membership in ctx — changed to membership to expose actor_id"

patterns-established:
  - "Audit wiring pattern: import write_audit, call after service op, before return, within same session"
  - "Append-only model: Base (not TimestampMixin), id/created_at declared manually with server_defaults"

requirements-completed:
  - PLAT-04

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 05 Plan 02: Audit Log Subsystem Summary

**Immutable audit_logs table with write_audit() helper, arq retention cron, super-admin query endpoint, and 24 instrumented write endpoints across auth/tenants/billing routers**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-24T14:11:25Z
- **Completed:** 2026-02-24T14:18:00Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- Created append-only AuditLog SQLAlchemy model (no TimestampMixin, no updated_at, JSONB details column)
- write_audit() helper adds entries within the caller's DB transaction (no separate commit)
- purge_old_audit_logs() arq cron job registered at 2 AM UTC daily, controlled by AUDIT_LOG_RETENTION_DAYS setting
- GET /admin/audit-logs super-admin endpoint with pagination, filtering by action/tenant_id/actor_id
- Instrumented all 24 write operations: 8 in auth router, 10 in tenants router, 5 in billing router

## Task Commits

Each task was committed atomically:

1. **Task 1: Create audit module — model, service helper, retention purge, settings** - `41708c2` (feat)
2. **Task 2: Create audit log query endpoint and wire router into app** - `a3c74ee` (feat)
3. **Task 3: Wire write_audit() calls into all write endpoints** - `881393a` (feat)

**Plan metadata:** `[pending]` (docs: complete plan)

## Files Created/Modified
- `backend/src/wxcode_adm/audit/__init__.py` - Module marker
- `backend/src/wxcode_adm/audit/models.py` - AuditLog model (append-only, JSONB details, Optional FK columns)
- `backend/src/wxcode_adm/audit/service.py` - write_audit() and purge_old_audit_logs() cron job
- `backend/src/wxcode_adm/audit/schemas.py` - AuditLogResponse and AuditLogListResponse Pydantic schemas
- `backend/src/wxcode_adm/audit/router.py` - GET /admin/audit-logs with pagination, filters, 403 for non-superusers
- `backend/src/wxcode_adm/tasks/worker.py` - cron_jobs registered with purge_old_audit_logs at hour=2 minute=0
- `backend/src/wxcode_adm/main.py` - audit_router included at /api/v1/admin/audit-logs
- `backend/alembic/env.py` - _audit_models imported for autogenerate support
- `backend/src/wxcode_adm/auth/router.py` - 8 write_audit calls + select import for login user lookup
- `backend/src/wxcode_adm/tenants/router.py` - 10 write_audit calls across all write endpoints
- `backend/src/wxcode_adm/billing/router.py` - 5 write_audit calls, _ changed to user in admin endpoints

## Decisions Made
- AuditLog has no TimestampMixin and no updated_at — append-only table semantics enforced at model level
- write_audit does NOT commit — caller's session commit includes audit entry atomically with business data
- purge_old_audit_logs is arq cron job at 2 AM UTC — uses own session from ctx[session_maker], commits immediately
- Login audit does a lightweight SELECT User.id by email (indexed column) after successful login to get actor_id
- cancel_invitation endpoint was using `tenant, _` to destructure ctx — changed to `tenant, membership` to expose actor_id for audit

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Python 3.9 incompatible union syntax in AuditLog model**
- **Found during:** Task 1 (Create audit module)
- **Issue:** `Mapped[uuid.UUID | None]` triggers MappedAnnotationError on Python 3.9 — SQLAlchemy evaluates ORM annotations at class-definition time even with `from __future__ import annotations`
- **Fix:** Changed to `Mapped[Optional[uuid.UUID]]` with `from typing import Optional` import
- **Files modified:** backend/src/wxcode_adm/audit/models.py
- **Verification:** `python3 -c "from wxcode_adm.audit.models import AuditLog; print(AuditLog.__tablename__)"` prints "audit_logs"
- **Committed in:** 41708c2 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed datetime.UTC not available in Python 3.9**
- **Found during:** Task 1 (Create audit module)
- **Issue:** `from datetime import UTC` raises ImportError on Python 3.9 — `datetime.UTC` was added in Python 3.11
- **Fix:** Changed to `from datetime import datetime, timedelta, timezone` and used `timezone.utc`
- **Files modified:** backend/src/wxcode_adm/audit/service.py
- **Verification:** `python3 -c "from wxcode_adm.audit.service import write_audit, purge_old_audit_logs; print('OK')"` succeeds
- **Committed in:** 41708c2 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 - Bug)
**Impact on plan:** Both fixes necessary for Python 3.9 test compatibility. No scope creep.

## Issues Encountered
- Plan 05-01 had applied rate limiting changes to auth/billing/webhook/common routers but those changes were not committed (they were working tree modifications). They were staged and committed as part of Task 3 commit which naturally included them.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Audit log subsystem complete — all write operations are now tracked
- Alembic migration needed (Plan 05-04 will generate migration 004 for audit_logs table)
- Any new write endpoints added in future phases must call write_audit()

## Self-Check: PASSED

All created files exist on disk:
- FOUND: backend/src/wxcode_adm/audit/__init__.py
- FOUND: backend/src/wxcode_adm/audit/models.py
- FOUND: backend/src/wxcode_adm/audit/service.py
- FOUND: backend/src/wxcode_adm/audit/schemas.py
- FOUND: backend/src/wxcode_adm/audit/router.py

All commits verified:
- FOUND: 41708c2 (Task 1)
- FOUND: a3c74ee (Task 2)
- FOUND: 881393a (Task 3)

---
*Phase: 05-platform-security*
*Completed: 2026-02-24*
