---
phase: 08-super-admin
plan: "01"
subsystem: auth
tags: [jwt, fastapi, super-admin, audience-isolation, ip-allowlist, enforcement-hooks]

# Dependency graph
requires:
  - phase: 02-auth-core
    provides: "create_access_token, decode_access_token, RefreshToken model, is_token_blacklisted, blacklist_jti"
  - phase: 05-platform-security
    provides: "write_audit, slowapi limiter, ForbiddenError"
  - phase: 07-user-account
    provides: "User model with is_superuser flag, blacklist_jti helper"
provides:
  - "admin/jwt.py: create_admin_access_token and decode_admin_access_token with aud=wxcode-adm-admin"
  - "admin/dependencies.py: require_admin FastAPI dependency (admin-audience JWT + is_superuser verification)"
  - "admin/schemas.py: AdminLoginRequest, AdminTokenResponse, placeholder schemas for Plans 02-04"
  - "admin/service.py: admin_login, admin_refresh, admin_logout"
  - "admin/router.py: POST /api/v1/admin/login (IP allowlist), POST /api/v1/admin/refresh, POST /api/v1/admin/logout"
  - "config.py: ADMIN_ALLOWED_IPS setting"
  - "Enforcement hooks: is_suspended/is_deleted/is_blocked in get_tenant_context (hasattr guards)"
  - "Enforcement hook: password_reset_required in get_current_user (hasattr guard)"
affects: ["08-02", "08-03", "08-04", "deployment"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Admin-audience JWT isolation: aud=wxcode-adm-admin creates bidirectional rejection (PyJWT 2.11.0)"
    - "hasattr() guards for enforcement hooks: columns added in migration 007 (Plan 08-04), hooks safe to run before migration"
    - "Separate admin_oauth2_scheme tokenUrl from regular oauth2_scheme — distinct OpenAPI security schemes"
    - "IP allowlist: comma-separated ADMIN_ALLOWED_IPS env var, empty = no restriction (dev-friendly)"

key-files:
  created:
    - backend/src/wxcode_adm/admin/__init__.py
    - backend/src/wxcode_adm/admin/jwt.py
    - backend/src/wxcode_adm/admin/dependencies.py
    - backend/src/wxcode_adm/admin/schemas.py
    - backend/src/wxcode_adm/admin/service.py
    - backend/src/wxcode_adm/admin/router.py
  modified:
    - backend/src/wxcode_adm/config.py
    - backend/src/wxcode_adm/main.py
    - backend/src/wxcode_adm/tenants/dependencies.py
    - backend/src/wxcode_adm/auth/dependencies.py

key-decisions:
  - "[08-01]: Admin refresh does NOT use shadow key replay detection — IP allowlist provides additional protection at login gate; admin sessions are short-lived"
  - "[08-01]: hasattr() guards in enforcement hooks ensure existing tests pass before migration 007 adds columns to Tenant/TenantMembership/User"
  - "[08-01]: Admin router uses RefreshToken model (no separate AdminRefreshToken table) — reuses existing model, admin tokens identified by aud claim"
  - "[08-01]: Logout endpoint re-decodes the admin token from Authorization header to extract JTI — require_admin already validated it, so re-decode is safe"

patterns-established:
  - "Admin isolation: separate oauth2_scheme + decode_*_access_token per audience; plans 02-04 import require_admin from admin/dependencies.py"
  - "Enforcement hook pattern: hasattr() guard + check + raise ForbiddenError; safe before migration adds the column"

requirements-completed: []

# Metrics
duration: 5min
completed: 2026-02-26
---

# Phase 08 Plan 01: Super-Admin Foundation Summary

**Admin-audience JWT isolation (aud=wxcode-adm-admin) with login/refresh/logout endpoints, IP allowlist, and enforcement hooks for tenant suspension, user blocking, and forced password reset**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-26T20:55:12Z
- **Completed:** 2026-02-26T21:00:47Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Created the isolated admin authentication layer: admin-audience JWT creation (wraps create_access_token with aud claim) and decoding (enforces audience claim via PyJWT 2.11.0)
- Implemented POST /api/v1/admin/login (rate-limited 10/min, IP allowlist from ADMIN_ALLOWED_IPS), POST /api/v1/admin/refresh (token rotation), POST /api/v1/admin/logout (JTI blacklist + audit)
- Added enforcement hooks in existing dependencies with hasattr() guards so Plans 02-04 can set is_suspended/is_blocked/password_reset_required columns without breaking existing tests before migration 007 runs

## Task Commits

Each task was committed atomically:

1. **Task 1: Admin JWT + dependencies + config + enforcement hooks** - `05715c0` (feat)
2. **Task 2: Admin login/refresh/logout endpoints with IP guard** - `2774097` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `backend/src/wxcode_adm/admin/__init__.py` - Admin module package (empty)
- `backend/src/wxcode_adm/admin/jwt.py` - create_admin_access_token + decode_admin_access_token with aud enforcement
- `backend/src/wxcode_adm/admin/dependencies.py` - require_admin dependency (admin JWT + is_superuser + blacklist)
- `backend/src/wxcode_adm/admin/schemas.py` - AdminLoginRequest, AdminTokenResponse, placeholder schemas for Plans 02-04
- `backend/src/wxcode_adm/admin/service.py` - admin_login, admin_refresh, admin_logout with audit logging
- `backend/src/wxcode_adm/admin/router.py` - POST /admin/login (rate limited, IP guard), /admin/refresh, /admin/logout
- `backend/src/wxcode_adm/config.py` - Added ADMIN_ALLOWED_IPS setting (empty = no restriction)
- `backend/src/wxcode_adm/main.py` - Mounted admin_router at /api/v1/admin
- `backend/src/wxcode_adm/tenants/dependencies.py` - is_suspended, is_deleted, is_blocked enforcement hooks with hasattr guards
- `backend/src/wxcode_adm/auth/dependencies.py` - password_reset_required enforcement hook with hasattr guard

## Decisions Made
- Admin refresh does NOT use shadow key replay detection — IP allowlist at login provides additional protection; admin sessions are short-lived and the complexity is not warranted
- hasattr() guards in all enforcement hooks ensure zero breakage of existing 129 tests before migration 007 (Plan 08-04) adds the actual columns to the DB models
- Admin router reuses the RefreshToken model (no separate AdminRefreshToken table) — admin tokens are distinguished by aud claim, not by a different table
- Logout endpoint re-decodes the Authorization header token to extract JTI (require_admin already validated it, making re-decode safe and avoiding passing the raw token through additional function signatures)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Missing python-multipart and user-agents packages in test environment (not in project venv) — installed via pip for test runner; not a code change, no impact on project dependencies.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Admin foundation complete: admin JWT, require_admin, IP allowlist, admin endpoints all working
- Plans 02-04 can import require_admin from admin/dependencies.py immediately
- Enforcement hooks in tenants/dependencies.py and auth/dependencies.py are activated once migration 007 adds the columns (Plan 08-04)
- All 129 existing tests pass unchanged

## Self-Check: PASSED

- FOUND: backend/src/wxcode_adm/admin/__init__.py
- FOUND: backend/src/wxcode_adm/admin/jwt.py
- FOUND: backend/src/wxcode_adm/admin/dependencies.py
- FOUND: backend/src/wxcode_adm/admin/schemas.py
- FOUND: backend/src/wxcode_adm/admin/service.py
- FOUND: backend/src/wxcode_adm/admin/router.py
- FOUND commit: 05715c0 (Task 1)
- FOUND commit: 2774097 (Task 2)

---
*Phase: 08-super-admin*
*Completed: 2026-02-26*
