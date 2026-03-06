---
phase: 03-multi-tenancy-and-rbac
plan: 02
subsystem: tenants
tags: [fastapi, sqlalchemy, rbac, tenants, dependencies, router, itsdangerous]

# Dependency graph
requires:
  - phase: 03-01
    provides: "Tenant, TenantMembership, MemberRole models; tenant exceptions; Pydantic schemas"
  - phase: 02-auth-core
    provides: "require_verified dependency, User model, get_session, common exceptions"
provides:
  - "get_tenant_context dependency: resolves (Tenant, TenantMembership) from X-Tenant-ID header"
  - "require_role factory: enforces minimum MemberRole level via integer comparison"
  - "require_tenant_member alias: semantic passthrough for any-member-required endpoints"
  - "create_workspace service: creates Tenant + OWNER membership with billing_access=True"
  - "generate_unique_slug: python-slugify with 10-iteration uniqueness loop"
  - "get_user_tenants: returns user tenant memberships via selectinload"
  - "invitation_serializer: module-level itsdangerous serializer (monkeypatched in tests)"
  - "POST /api/v1/onboarding/workspace (201): workspace creation endpoint"
  - "GET /api/v1/tenants/me: list user's tenants (no X-Tenant-ID required)"
  - "GET /api/v1/tenants/current: current tenant info"
  - "PATCH /api/v1/tenants/current: update display name (ADMIN required)"
  - "GET /api/v1/tenants/current/members: list members with email and role"
  - "conftest: tenant tables created in test SQLite DB"
  - "alembic env.py: tenant models registered for autogenerate"
affects: [03-03, 03-04, 03-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dependency factory pattern: require_role(MemberRole.ADMIN) returns FastAPI async dependency closure"
    - "selectinload for TenantMembership.tenant in get_user_tenants (avoids N+1 queries)"
    - "selectinload for TenantMembership.user in list_members (eager-load email)"
    - "db.flush() (not db.commit()) in create_workspace — caller session lifecycle controls commit"
    - "Module-level itsdangerous serializer monkeypatched in tests (same as auth/service.py pattern)"
    - "X-Tenant-ID: UUID parsed first, then falls back to slug lookup (try/except ValueError)"

key-files:
  created:
    - "backend/src/wxcode_adm/tenants/dependencies.py"
    - "backend/src/wxcode_adm/tenants/service.py"
    - "backend/src/wxcode_adm/tenants/router.py"
  modified:
    - "backend/src/wxcode_adm/main.py (added tenant_router and onboarding_router)"
    - "backend/tests/conftest.py (tenant model imports, invitation_serializer monkeypatch)"
    - "backend/alembic/env.py (uncommented tenants models import)"

key-decisions:
  - "UpdateTenantRequest defined in router.py (not schemas.py) — keeps schemas.py clean for Plan 03-03 which adds invitation/transfer schemas"
  - "list_members returns list[dict] (not list[MembershipResponse]) — MembershipResponse has email field that is not on TenantMembership ORM directly; dict avoids from_attributes mismatch"
  - "generate_unique_slug cap at 10 iterations — UNIQUE constraint on tenants.slug is authoritative guard; pre-check handles common case without race condition"
  - "invitation_serializer added to service.py now (pre-wired for Plan 03-03) — avoids touching service.py again when invitation sending is implemented"

# Metrics
duration: 4min
completed: 2026-02-23
---

# Phase 3 Plan 02: Tenant Operations and RBAC Enforcement Summary

**Tenant context dependency chain (get_tenant_context -> require_role), workspace creation onboarding endpoint, and tenant info/member endpoints wired into FastAPI app with conftest and alembic updated**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-23T15:36:24Z
- **Completed:** 2026-02-23T15:39:57Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Created `tenants/dependencies.py` with `get_tenant_context` (UUID+slug header resolution, non-member returns 404 to prevent enumeration), `require_role` factory (integer level comparison), and `require_tenant_member` semantic alias
- Created `tenants/service.py` with `create_workspace` (Tenant+OWNER membership, billing_access=True, db.flush pattern), `generate_unique_slug` (python-slugify, 10-iteration uniqueness loop), `get_user_tenants` (selectinload for N+1 avoidance), and `invitation_serializer` module-level attribute (pre-wired for Plan 03-03 monkeypatching)
- Created `tenants/router.py` with 5 endpoints across two routers: `onboarding_router` (POST /onboarding/workspace → 201) and `router` (GET /tenants/me, GET/PATCH /tenants/current, GET /tenants/current/members)
- Updated `main.py` to mount both routers under `/api/v1` prefix
- Updated `conftest.py` to import `wxcode_adm.tenants.models` in both `_build_sqlite_metadata()` and `test_db` fixtures, and to monkeypatch `invitation_serializer` in the `client` fixture
- Updated `alembic/env.py` to import tenant models for autogenerate support
- All 21 existing Phase 2 tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Tenant context dependencies and RBAC enforcement** - `27e6a7b` (feat)
2. **Task 2: Tenant router, main.py wiring, conftest and alembic updates** - `1c305cc` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/tenants/dependencies.py` - get_tenant_context, require_role, require_tenant_member
- `backend/src/wxcode_adm/tenants/service.py` - create_workspace, generate_unique_slug, get_user_tenants, invitation_serializer
- `backend/src/wxcode_adm/tenants/router.py` - 5 tenant/onboarding endpoints, UpdateTenantRequest schema
- `backend/src/wxcode_adm/main.py` - tenant_router and onboarding_router mounted
- `backend/tests/conftest.py` - tenant model imports and invitation_serializer monkeypatch
- `backend/alembic/env.py` - tenant models import for autogenerate

## Decisions Made

- `UpdateTenantRequest` defined in `router.py` (not `schemas.py`) to keep schemas.py clean for Plan 03-03 additions
- `list_members` returns `list[dict]` instead of `list[MembershipResponse]` — the `email` field in `MembershipResponse` is not a direct attribute of `TenantMembership`, requiring explicit dict construction from the loaded `user` relationship
- `invitation_serializer` pre-wired in `service.py` now (Plan 03-02) — avoids touching `service.py` again in Plan 03-03 when invitation sending is implemented; tests monkeypatch it in the `client` fixture

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all 21 existing tests pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `get_tenant_context` and `require_role` are fully operational — Plans 03-03 through 03-05 can use them directly
- Workspace creation endpoint is live at `POST /api/v1/onboarding/workspace`
- Conftest creates tenant/membership tables — invitation tests in Plan 03-03 will work without changes
- `invitation_serializer` is monkeypatched in tests — invitation acceptance tests can be added immediately

---
*Phase: 03-multi-tenancy-and-rbac*
*Completed: 2026-02-23*
