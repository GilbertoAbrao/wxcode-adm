---
phase: 07-user-account
plan: "03"
subsystem: auth
tags: [session-management, wxcode-redirect, one-time-code, user-agents, redis, sqlalchemy]

# Dependency graph
requires:
  - phase: 07-user-account
    plan: "01"
    provides: "UserSession model, get_current_jti dependency, Redis last_active pattern"
  - phase: 07-user-account
    plan: "02"
    provides: "users_router, users/schemas.py, users/service.py foundation"
  - phase: 05-platform-security
    provides: "write_audit, rate limiting, require_verified dependency"
  - phase: 02-auth-core
    provides: "blacklist_access_token, RefreshToken, _issue_tokens"
provides:
  - "GET /api/v1/users/me/sessions — list active sessions with device/browser/IP/city metadata"
  - "DELETE /api/v1/users/me/sessions/{id} — revoke individual session (JTI blacklisted immediately)"
  - "DELETE /api/v1/users/me/sessions — revoke all other sessions (keep current)"
  - "POST /api/v1/auth/wxcode/exchange — server-to-server one-time code exchange for JWT tokens"
  - "LoginResponse.wxcode_redirect_url and wxcode_code fields for frontend redirect"
  - "blacklist_jti() helper for direct JTI blacklisting without full JWT decode"
  - "create_wxcode_code, exchange_wxcode_code, get_redirect_url in auth/service.py"
  - "Session metadata (user_agent, ip_address) wired into ALL auth flows"
affects: ["07-04"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "blacklist_jti: direct Redis SET for JTI blacklisting (no JWT decode needed when JTI known)"
    - "wxcode one-time code: Redis GETDEL for atomic single-use code consumption"
    - "Session listing: inner join UserSession + RefreshToken ensures only active sessions returned"
    - "last_used_tenant_id updated on login after wxcode redirect resolution"
    - "refresh() updates UserSession.refresh_token_id + access_token_jti in-place (no new session row)"

key-files:
  created: []
  modified:
    - "backend/src/wxcode_adm/users/schemas.py"
    - "backend/src/wxcode_adm/users/service.py"
    - "backend/src/wxcode_adm/users/router.py"
    - "backend/src/wxcode_adm/auth/service.py"
    - "backend/src/wxcode_adm/auth/router.py"
    - "backend/src/wxcode_adm/auth/schemas.py"

key-decisions:
  - "[07-03]: blacklist_jti() added as separate helper — direct JTI write to Redis without full JWT decode; cleaner than modifying blacklist_access_token which parses JWT"
  - "[07-03]: wxcode GETDEL for atomic code consumption — code cannot be replayed even under concurrent requests"
  - "[07-03]: Session listing inner joins UserSession + RefreshToken — only sessions with active RefreshToken appear (orphaned sessions excluded automatically)"
  - "[07-03]: refresh() updates UserSession in-place rather than creating new row — single-session policy means there is at most one session per user; updating preserves session history"
  - "[07-03]: get_redirect_url returns (url, tenant_id) tuple — caller updates last_used_tenant_id at router layer to keep service HTTP-agnostic"

patterns-established:
  - "Session metadata wiring: extract user_agent + client_ip at router layer, pass as kwargs to service"
  - "wxcode redirect pattern: create_wxcode_code -> return URL + code in LoginResponse -> frontend redirects"

requirements-completed: [USER-03, USER-04]

# Metrics
duration: 8min
completed: 2026-02-25
---

# Phase 7 Plan 03: Session Management and wxcode Redirect Summary

**Session listing/revocation endpoints, one-time wxcode authorization code exchange, and session metadata wired into all auth flows from HTTP request headers**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-25T20:54:16Z
- **Completed:** 2026-02-25T21:02:15Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Session management: GET /users/me/sessions returns all active sessions with device_type, browser_name, browser_version, ip_address, city, and Redis-fresh last_active_at; current session tagged with is_current=True; sorted by most recent first
- Individual session revocation: DELETE /users/me/sessions/{id} blacklists the access token JTI immediately via new `blacklist_jti()` helper; deletes RefreshToken (CASCADE removes UserSession); prevents self-revocation with CANNOT_REVOKE_CURRENT error
- Bulk session revocation: DELETE /users/me/sessions revokes all other sessions, preserves current session, returns revoked_count
- wxcode one-time code: create_wxcode_code stores tokens in Redis (TTL=30s); exchange_wxcode_code uses GETDEL for atomic single-use consumption; POST /auth/wxcode/exchange is server-to-server (no JWT auth), rate-limited, returns 401 for invalid/expired/replayed codes
- Session metadata wired at router layer for ALL auth flows: login, MFA verify, OAuth callback, OAuth link confirm, and token refresh all extract user_agent from request.headers and ip_address from request.client.host and pass to service
- LoginResponse extended with optional wxcode_redirect_url and wxcode_code fields; last_used_tenant_id updated on each successful login
- Token refresh updated: UserSession.refresh_token_id and access_token_jti updated in-place on rotation; pre-Phase-7 tokens without UserSession get a new session created
- All 114 existing tests continue to pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Session listing and revocation (service + schemas + router endpoints)** - `5e2da3a` (feat)
2. **Task 2: wxcode redirect, session metadata wiring in login/MFA/OAuth flows, exchange endpoint** - `4939876` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/users/schemas.py` - Added SessionResponse, SessionListResponse, RevokeSessionResponse, RevokeAllSessionsResponse
- `backend/src/wxcode_adm/users/service.py` - Added list_sessions(), revoke_session(), revoke_all_other_sessions() with Redis last_active lookup and JTI blacklisting
- `backend/src/wxcode_adm/users/router.py` - Added GET/DELETE /me/sessions endpoints with audit logging
- `backend/src/wxcode_adm/auth/service.py` - Added blacklist_jti(), create_wxcode_code(), exchange_wxcode_code(), get_redirect_url(); updated login/mfa_verify/resolve_oauth_account/confirm_oauth_link/refresh to accept user_agent and ip_address; updated refresh to keep UserSession in sync
- `backend/src/wxcode_adm/auth/router.py` - Wired user_agent+ip_address extraction in login, mfa_verify, oauth_callback, oauth_link_confirm, refresh; added wxcode redirect logic to login; added POST /auth/wxcode/exchange endpoint
- `backend/src/wxcode_adm/auth/schemas.py` - Added WxcodeExchangeRequest/WxcodeExchangeResponse; added wxcode_redirect_url/wxcode_code to LoginResponse

## Decisions Made

- `blacklist_jti()` added as a new helper separate from `blacklist_access_token()` — when we have the JTI directly (e.g., from UserSession), we don't need to decode the full JWT; direct Redis SET is cleaner
- GETDEL for wxcode code exchange — atomic operation prevents race conditions on concurrent exchange attempts; code is single-use by design
- Session listing uses inner join with RefreshToken — only sessions with active RefreshToken appear; sessions orphaned by manual DB operations are excluded automatically
- `refresh()` updates UserSession in-place rather than creating a new session row on each token rotation — this preserves the session history and keeps session count at 1 per user (single-session policy)
- `get_redirect_url()` returns `(url, tenant_id)` tuple — the router updates `last_used_tenant_id` after calling the service, keeping the service layer HTTP-agnostic

## Deviations from Plan

### Auto-added Functionality

**1. [Rule 2 - Missing Functionality] Updated refresh() to maintain UserSession on token rotation**
- **Found during:** Task 2 (wiring session metadata)
- **Issue:** The token refresh flow manually created RefreshToken without calling `_issue_tokens`, so UserSession was not updated when tokens rotated. This would make session listing show stale/incorrect session data after token refresh.
- **Fix:** Updated `refresh()` to update `UserSession.refresh_token_id` and `access_token_jti` in-place after rotation; creates a new UserSession for pre-Phase-7 tokens that have no existing session row.
- **Files modified:** `backend/src/wxcode_adm/auth/service.py`
- **Commit:** 4939876

## Issues Encountered

None beyond the deviation above.

## User Setup Required

- `WXCODE_CODE_TTL` is already configured in settings (default: 30 seconds). No new environment variables required.
- `GET_REDIRECT_URL` resolves `Tenant.wxcode_url` — tenants must have `wxcode_url` configured for the redirect to trigger. No redirect occurs if wxcode_url is null.

## Self-Check: PASSED

- FOUND: users/schemas.py (SessionResponse, SessionListResponse, etc.)
- FOUND: users/service.py (list_sessions, revoke_session, revoke_all_other_sessions)
- FOUND: users/router.py (GET/DELETE /me/sessions endpoints)
- FOUND: auth/service.py (create_wxcode_code, exchange_wxcode_code, get_redirect_url, blacklist_jti)
- FOUND: auth/router.py (POST /wxcode/exchange, user_agent= wired in 5 places)
- FOUND: auth/schemas.py (WxcodeExchangeRequest, WxcodeExchangeResponse, LoginResponse wxcode fields)
- FOUND commit: 5e2da3a (feat: session listing and revocation endpoints)
- FOUND commit: 4939876 (feat: wxcode redirect, session metadata wiring, exchange endpoint)
- 114 tests passing

---
*Phase: 07-user-account*
*Completed: 2026-02-25*
