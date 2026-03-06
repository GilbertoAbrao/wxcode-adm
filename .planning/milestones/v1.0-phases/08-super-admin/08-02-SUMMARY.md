---
phase: 08-super-admin
plan: "02"
subsystem: api
tags: [fastapi, sqlalchemy, admin, tenant-management, session-invalidation, audit]

# Dependency graph
requires:
  - phase: 08-super-admin/08-01
    provides: "require_admin dependency, admin router, admin schemas placeholders, write_audit"
  - phase: 07-user-account
    provides: "UserSession model with access_token_jti, blacklist_jti helper"
  - phase: 04-billing-core
    provides: "TenantSubscription and Plan models for plan info per tenant"
  - phase: 03-multi-tenancy-and-rbac
    provides: "Tenant, TenantMembership models"
provides:
  - "admin/service.py: list_tenants, get_tenant_detail, suspend_tenant, reactivate_tenant, soft_delete_tenant"
  - "admin/router.py: GET /admin/tenants, GET /admin/tenants/{id}, POST /admin/tenants/{id}/suspend, POST /admin/tenants/{id}/reactivate, DELETE /admin/tenants/{id}"
  - "admin/schemas.py: TenantListItem, TenantListResponse, TenantDetailResponse, AdminActionRequest (finalized with min/max_length)"
affects: ["08-03", "08-04", "deployment"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Correlated subquery for member_count: select(func.count(TenantMembership.id)).where(...).correlate(Tenant).scalar_subquery() avoids N+1"
    - "getattr() guards for is_suspended/is_deleted: safe attribute access before migration 007 adds the columns (Plan 08-04)"
    - "Outer join pattern: outerjoin(TenantSubscription).outerjoin(Plan) fetches plan info alongside tenants in one query"
    - "AdminActionRequest: reason field with Field(min_length=1, max_length=500) enforces reason requirement for all destructive admin actions"

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/admin/schemas.py
    - backend/src/wxcode_adm/admin/service.py
    - backend/src/wxcode_adm/admin/router.py

key-decisions:
  - "[08-02]: getattr() guards for is_suspended/is_deleted used in service — columns not on model until Plan 08-04 adds migration 007; attribute assignment works at Python level (SQLAlchemy persists once column exists)"
  - "[08-02]: list_tenants uses outer join to TenantSubscription+Plan — tenants without a subscription still appear in list with plan_name=None"
  - "[08-02]: suspend_tenant deletes RefreshTokens AND blacklists UserSession JTIs — covers both token types for immediate session invalidation"
  - "[08-02]: soft_delete_tenant does NOT invalidate sessions — get_tenant_context enforcement hook (hasattr guard from Plan 08-01) handles blocking on next request"

patterns-established:
  - "Admin destructive endpoints always require AdminActionRequest body (reason field) — audit trail requirement"
  - "Tenant suspension = JTI blacklist for active access tokens + RefreshToken delete for all members; reactivation just clears is_suspended flag (no auto re-issue)"

requirements-completed: [SADM-01, SADM-02]

# Metrics
duration: 3min
completed: 2026-02-26
---

# Phase 08 Plan 02: Tenant Management Summary

**Five admin tenant management endpoints: list/detail with plan info and member count, suspend (immediate session invalidation), reactivate, and soft-delete with audit logging**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T16:23:58Z
- **Completed:** 2026-02-26T16:27:04Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Implemented `list_tenants` with pagination, plan_slug/status filtering, correlated subquery for member count, and outer join for plan info — all in a single efficient query
- Implemented `suspend_tenant` with complete session invalidation: blacklists access token JTIs from UserSession table and deletes all RefreshToken rows for tenant members
- Added 5 tenant management endpoints under `/api/v1/admin/tenants` — all protected by `require_admin`, all destructive actions require reason string (AdminActionRequest)

## Task Commits

Each task was committed atomically:

1. **Task 1: Tenant management schemas and service functions** - `f3abd3a` (feat)
2. **Task 2: Tenant management router endpoints** - `57775fa` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `backend/src/wxcode_adm/admin/schemas.py` - Replaced placeholder schemas with full TenantListItem, TenantListResponse, TenantDetailResponse; finalized AdminActionRequest with min_length=1 validation
- `backend/src/wxcode_adm/admin/service.py` - Added list_tenants, get_tenant_detail, suspend_tenant, reactivate_tenant, soft_delete_tenant; retained auth functions from Plan 01
- `backend/src/wxcode_adm/admin/router.py` - Added 5 tenant management endpoints; retained auth endpoints from Plan 01

## Decisions Made
- `getattr()` guards for `is_suspended`/`is_deleted` used in service functions — the model columns are declared in Plan 08-04 (migration 007); Python attribute assignment works without the ORM column mapped, and SQLAlchemy will persist the value once the column is in the schema
- `list_tenants` uses outer joins for plan info rather than selectinload — avoids a second query and handles tenants without subscriptions cleanly (plan_name=None)
- `suspend_tenant` blacklists JTIs from UserSession AND deletes RefreshTokens — double invalidation ensures no path to re-authenticate without new login
- `soft_delete_tenant` deliberately does NOT invalidate sessions — the enforcement hook in `get_tenant_context` (Plan 08-01) handles this on next request; this avoids expensive session enumeration for a less urgent action

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Tenant management endpoints complete and all 129 existing tests pass
- Plan 08-03 can add user management endpoints to the same router
- Plan 08-04 adds migration 007 which activates the is_suspended/is_deleted columns; service functions already handle the attribute assignment

## Self-Check: PASSED

- FOUND: backend/src/wxcode_adm/admin/schemas.py
- FOUND: backend/src/wxcode_adm/admin/service.py
- FOUND: backend/src/wxcode_adm/admin/router.py
- FOUND commit: f3abd3a (Task 1)
- FOUND commit: 57775fa (Task 2)

---
*Phase: 08-super-admin*
*Completed: 2026-02-26*
