---
phase: 07-user-account
plan: "01"
subsystem: auth
tags: [user-agents, geoip2, pillow, sqlalchemy, redis, session-tracking]

# Dependency graph
requires:
  - phase: 06-oauth-and-mfa
    provides: "TrustedDevice model, _issue_tokens helper, RefreshToken model, auth dependencies infrastructure"
  - phase: 05-platform-security
    provides: "SQLite compat pattern (no JSONB), audit log, rate limiting"
provides:
  - "UserSession model with 10 rich metadata fields linked 1:1 to RefreshToken"
  - "User.display_name, User.avatar_url, User.last_used_tenant_id columns"
  - "Tenant.wxcode_url column for per-tenant custom domains"
  - "parse_session_metadata() helper: UA parsing + IP geolocation"
  - "_issue_tokens() creates UserSession with access_token_jti on every token issuance"
  - "get_current_user writes per-request last_active to Redis (auth:session:last_active:{jti})"
  - "get_current_jti dependency for downstream session tracking"
  - "Phase 7 config settings: GEOLITE2_DB_PATH, WXCODE_CODE_TTL, AVATAR_UPLOAD_DIR"
affects: ["07-02", "07-03", "07-04", "session-management", "profile-management"]

# Tech tracking
tech-stack:
  added: ["user-agents==2.2.0", "geoip2==5.2.0", "Pillow==11.2.1"]
  patterns:
    - "UserSession linked 1:1 to RefreshToken via FK with CASCADE delete"
    - "Simple String columns (no JSONB) for SQLite test compatibility per [05-04]"
    - "parse_session_metadata lazy-imports user_agents and geoip2 to avoid top-level import overhead"
    - "per-request last_active written to Redis with TTL = ACCESS_TOKEN_TTL_HOURS so keys auto-expire"
    - "GEOLITE2_DB_PATH empty string = geolocation disabled (no crash if MMDB missing)"

key-files:
  created: []
  modified:
    - "backend/pyproject.toml"
    - "backend/src/wxcode_adm/config.py"
    - "backend/src/wxcode_adm/auth/models.py"
    - "backend/src/wxcode_adm/tenants/models.py"
    - "backend/src/wxcode_adm/auth/service.py"
    - "backend/src/wxcode_adm/auth/dependencies.py"

key-decisions:
  - "[07-01]: UserSession uses simple String columns (no JSONB) — SQLite test compatibility per Phase 5 decision [05-04]"
  - "[07-01]: GEOLITE2_DB_PATH empty string disables geolocation gracefully — no crash if MMDB file not present in dev"
  - "[07-01]: per-request last_active uses Redis SETEX with ACCESS_TOKEN_TTL_HOURS TTL — stale keys auto-expire, no separate cleanup needed"
  - "[07-01]: _issue_tokens flushes RefreshToken before creating UserSession — flush assigns rt.id for FK without committing the transaction"
  - "[07-01]: user-agents and geoip2 lazy-imported inside parse_session_metadata — avoids import-time overhead, consistent with existing lazy-import pattern in codebase"

patterns-established:
  - "Session metadata pattern: parse_session_metadata(user_agent, ip_address) -> dict used by _issue_tokens"
  - "Redis last_active key: auth:session:last_active:{jti} written on every authenticated request via get_current_user"

requirements-completed: [USER-01, USER-03, USER-04]

# Metrics
duration: 12min
completed: 2026-02-25
---

# Phase 7 Plan 01: User Account Foundation Summary

**UserSession model with rich device/browser/IP metadata, per-request Redis last_active tracking, and User/Tenant profile columns for Phase 7 session management**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-25T20:38:16Z
- **Completed:** 2026-02-25T20:50:30Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- UserSession SQLAlchemy model with 10 metadata fields (refresh_token_id, user_id, access_token_jti, user_agent, device_type, browser_name, browser_version, ip_address, city, last_active_at) linked 1:1 to RefreshToken via FK with CASCADE delete
- User model extended with display_name, avatar_url, last_used_tenant_id columns; Tenant model extended with wxcode_url
- parse_session_metadata() helper parses User-Agent strings (Mobile/Tablet/Desktop/Other, browser name+version) and optionally geolocates IP via GeoLite2; _issue_tokens now creates UserSession alongside each RefreshToken
- get_current_user writes per-request last_active ISO timestamp to Redis (auth:session:last_active:{jti}) with ACCESS_TOKEN_TTL_HOURS TTL; get_current_jti dependency added for downstream use
- All 114 existing tests continue to pass with no modifications required

## Task Commits

Each task was committed atomically:

1. **Task 1: UserSession model, new User/Tenant columns, new dependencies and config settings** - `a2aea0a` (feat)
2. **Task 2: Update _issue_tokens with session metadata persistence, add per-request last_active to get_current_user, add session helpers** - `227a010` (feat)

## Files Created/Modified

- `backend/pyproject.toml` - Added user-agents==2.2.0, geoip2==5.2.0, Pillow==11.2.1 under Phase 7 section
- `backend/src/wxcode_adm/config.py` - Added GEOLITE2_DB_PATH, WXCODE_CODE_TTL, AVATAR_UPLOAD_DIR to Settings
- `backend/src/wxcode_adm/auth/models.py` - Added display_name/avatar_url/last_used_tenant_id to User; added UserSession model after TrustedDevice
- `backend/src/wxcode_adm/tenants/models.py` - Added wxcode_url column to Tenant model after mfa_enforced
- `backend/src/wxcode_adm/auth/service.py` - Added parse_session_metadata(), updated _issue_tokens signature and body to create UserSession, imported UserSession and decode_access_token
- `backend/src/wxcode_adm/auth/dependencies.py` - Added get_current_jti dependency, added per-request last_active Redis SETEX in get_current_user, added datetime/timezone imports and settings import

## Decisions Made

- UserSession uses simple String columns (no JSONB) for SQLite test compatibility per Phase 5 decision [05-04]
- GEOLITE2_DB_PATH empty string disables geolocation gracefully — no crash if MMDB file not present in dev/test environments
- Per-request last_active uses Redis SETEX with TTL = ACCESS_TOKEN_TTL_HOURS — stale keys auto-expire without separate cleanup
- _issue_tokens flushes RefreshToken row before creating UserSession so rt.id FK is available within the same transaction
- user-agents and geoip2 are lazy-imported inside parse_session_metadata — consistent with existing lazy-import pattern in codebase (auto_join_pending_invitations, billing bootstrap, etc.)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all tasks completed without issues. The existing test suite passed without modification because _issue_tokens backwards-compatible keyword-only defaults (user_agent=None, ip_address=None) ensure all callers continue to work.

## User Setup Required

None - no external service configuration required. GeoIP database (GEOLITE2_DB_PATH) is optional; geolocation is silently skipped when the path is empty or invalid.

## Next Phase Readiness

- Plan 01 foundation complete: UserSession model, profile columns, session metadata infrastructure all in place
- Plans 02-04 can now build on UserSession: Plan 02 (session listing/revocation UI), Plan 03 (router-level UA/IP extraction), Plan 04 (profile management with display_name/avatar_url)
- No blockers — all 114 tests passing, new models importable, libraries installed

---
*Phase: 07-user-account*
*Completed: 2026-02-25*
