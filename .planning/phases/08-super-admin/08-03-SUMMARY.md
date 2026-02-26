---
phase: 08-super-admin
plan: "03"
subsystem: admin
tags: [fastapi, super-admin, user-management, search, block, force-reset, audit]

# Dependency graph
requires:
  - phase: 08-01
    provides: "require_admin, admin JWT, password_reset_required enforcement hook in get_current_user"
  - phase: 03-multi-tenancy-and-rbac
    provides: "TenantMembership model, is_blocked column (added in migration 007)"
  - phase: 07-user-account
    provides: "UserSession model with access_token_jti for session invalidation"
  - phase: 05-platform-security
    provides: "write_audit, blacklist_jti"
provides:
  - "admin/schemas.py: UserMembershipItem, UserSessionItem, UserListItem, UserListResponse, UserDetailResponse, UserBlockRequest, UserUnblockRequest, UserForceResetRequest"
  - "admin/service.py: search_users, get_user_detail, block_user, unblock_user, force_password_reset"
  - "admin/router.py: GET /admin/users, GET /admin/users/{id}, POST /admin/users/{id}/block, POST /admin/users/{id}/unblock, POST /admin/users/{id}/force-reset"
  - "auth/service.py: reset_password clears password_reset_required flag (hasattr guard)"
affects: ["08-04"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-tenant user block: TenantMembership.is_blocked=True with hasattr guard; enforcement in get_tenant_context from Plan 01"
    - "force_password_reset: flag + session invalidation (blacklist JTI + delete RefreshToken) + arq reset email enqueue, all in one transaction"
    - "Non-blocking email: reset email enqueue in try/except with WARNING log; forced-reset flag is still set even if arq is unavailable"
    - "reset_password clears password_reset_required with hasattr() guard — safe before migration 007 adds the column"

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/admin/schemas.py
    - backend/src/wxcode_adm/admin/service.py
    - backend/src/wxcode_adm/admin/router.py
    - backend/src/wxcode_adm/auth/service.py

key-decisions:
  - "[08-03]: block_user uses hasattr() guard for is_blocked on TenantMembership — column added by migration 007 (Plan 08-04); enforcement in get_tenant_context already has hasattr guard from Plan 01"
  - "[08-03]: force_password_reset wraps arq enqueue in try/except — email failure is non-blocking; forced-reset flag is the authoritative state, email is best-effort"
  - "[08-03]: search_users uses or_() for ilike search across email+display_name with tenant_id join filter — counts using same filter conditions"
  - "[08-03]: get_user_detail loads memberships via explicit join on Tenant (not lazy-load) — SQLAlchemy 2.0 async sessions cannot lazy-load relationships"
  - "[08-03]: force_password_reset flushes before generating reset token — ensures password_reset_required flag is visible; db.refresh() picks up any concurrent changes"

patterns-established:
  - "User management action pattern: load resource, validate membership, set flag, write_audit, return — same for block and unblock"
  - "Admin search endpoint pattern: base_q + count_q built in parallel, same filters applied to both, paginated main query"

requirements-completed:
  - SADM-03
  - SADM-04

# Metrics
duration: 7min
completed: 2026-02-26
---

# Phase 08 Plan 03: User Management Endpoints Summary

**Super-admin user search, per-tenant block/unblock, and force-password-reset with session invalidation and audit logging**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-26T16:29:14Z
- **Completed:** 2026-02-26T16:36:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Replaced placeholder user schemas (`UserListResponse`, `UserDetailResponse`) with fully-typed Pydantic v2 models: `UserMembershipItem`, `UserSessionItem`, `UserListItem`, `UserListResponse`, `UserDetailResponse`, `UserBlockRequest`, `UserUnblockRequest`, `UserForceResetRequest`
- Implemented `search_users` with case-insensitive `ilike` search on email and display_name, optional `tenant_id` membership filter, paginated with count query using the same filters
- Implemented `get_user_detail` returning full profile with all tenant memberships (including `is_blocked` via `hasattr` guard) and active UserSessions
- Implemented `block_user` and `unblock_user` as per-tenant operations on `TenantMembership.is_blocked` with audit logging; enforcement via existing `get_tenant_context` hook (Plan 01)
- Implemented `force_password_reset`: sets `password_reset_required=True`, blacklists all session JTIs, deletes all RefreshToken rows, and enqueues arq `send_reset_email` job (non-blocking)
- Updated `auth/service.py:reset_password()` to clear `password_reset_required = False` via `hasattr` guard — completing the forced-reset lifecycle
- Added 5 router endpoints: GET /admin/users, GET /admin/users/{id}, POST /admin/users/{id}/block, POST /admin/users/{id}/unblock, POST /admin/users/{id}/force-reset

## Task Commits

Each task was committed atomically:

1. **Task 1: User management schemas and service functions** - `58210bd` (feat)
2. **Task 2: User management router endpoints** - `70aa9ae` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `backend/src/wxcode_adm/admin/schemas.py` — Added UserMembershipItem, UserSessionItem, UserListItem, UserListResponse, UserDetailResponse, UserBlockRequest, UserUnblockRequest, UserForceResetRequest
- `backend/src/wxcode_adm/admin/service.py` — Added search_users, get_user_detail, block_user, unblock_user, force_password_reset
- `backend/src/wxcode_adm/admin/router.py` — Added 5 user management endpoints under /admin/users
- `backend/src/wxcode_adm/auth/service.py` — reset_password now clears password_reset_required with hasattr guard

## Decisions Made
- `block_user` uses `hasattr()` guard for `TenantMembership.is_blocked` — column added by migration 007 (Plan 08-04); the enforcement hook in `get_tenant_context` already has a hasattr guard from Plan 01, so the block is safe to set before the migration
- `force_password_reset` wraps the arq email enqueue in `try/except` — email failure is logged as WARNING but does not roll back the forced-reset flag; the flag is the authoritative enforcement mechanism
- `search_users` builds `count_q` and `base_q` in parallel with identical filters to avoid double-querying the DB with different filter logic
- `get_user_detail` uses explicit join on Tenant (not lazy-load) because SQLAlchemy 2.0 async sessions cannot lazy-load relationships (established pattern from [06-05])
- `reset_password` clears `password_reset_required` via `hasattr()` guard — backward-compatible with existing tests before migration 007 adds the column

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- None

## User Setup Required
None — all functionality works with existing infrastructure.

## Next Phase Readiness
- Plans SADM-03 and SADM-04 requirements are now fulfilled
- All 5 user management endpoints are live under /api/v1/admin/users
- Plan 08-04 (migration 007 + deployment) will add the actual DB columns for is_suspended, is_deleted, is_blocked, password_reset_required; hasattr guards ensure safe operation before migration

## Self-Check: PASSED

- FOUND: backend/src/wxcode_adm/admin/schemas.py (contains UserMembershipItem, UserListResponse, UserDetailResponse, UserBlockRequest, UserForceResetRequest)
- FOUND: backend/src/wxcode_adm/admin/service.py (contains search_users, get_user_detail, block_user, unblock_user, force_password_reset)
- FOUND: backend/src/wxcode_adm/admin/router.py (contains /admin/users endpoints)
- FOUND: backend/src/wxcode_adm/auth/service.py (contains password_reset_required clearance)
- FOUND commit: 58210bd (Task 1)
- FOUND commit: 70aa9ae (Task 2)

---
*Phase: 08-super-admin*
*Completed: 2026-02-26*
