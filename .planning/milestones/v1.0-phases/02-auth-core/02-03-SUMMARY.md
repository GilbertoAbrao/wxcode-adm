---
phase: 02-auth-core
plan: 03
subsystem: auth
tags: [jwt, refresh-token, redis, sqlalchemy, single-session, replay-detection, blacklist]

# Dependency graph
requires:
  - phase: 02-auth-core plan 01
    provides: JWT creation (create_access_token), User model, exceptions (InvalidCredentialsError, TokenExpiredError, InvalidTokenError)
  - phase: 02-auth-core plan 02
    provides: EmailNotVerifiedError, auth router structure, get_session/get_redis dependencies
provides:
  - POST /api/v1/auth/login — authenticate user, issue access+refresh tokens, enforce single-session
  - POST /api/v1/auth/refresh — rotate refresh token with replay detection
  - POST /api/v1/auth/logout — delete refresh token + blacklist access token jti in Redis
  - RefreshToken SQLAlchemy model (refresh_tokens table)
  - Access token blacklist helpers (blacklist_access_token, is_token_blacklisted)
  - Redis shadow key replay detection (_shadow_key, _write_shadow_key, _write_shadow_keys_bulk)
affects:
  - 02-04 (password reset will use login infrastructure)
  - 02-05 (get_current_user must call is_token_blacklisted on the jti claim)
  - 03-tenant-rbac (RBAC roles/claims injected into access tokens at login)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - shadow-key-replay-detection
    - single-session-enforcement
    - redis-jti-blacklist

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/auth/models.py
    - backend/src/wxcode_adm/auth/schemas.py
    - backend/src/wxcode_adm/auth/service.py
    - backend/src/wxcode_adm/auth/router.py
    - backend/src/wxcode_adm/auth/exceptions.py

key-decisions:
  - "EmailNotVerifiedError updated to accept optional error_code/message kwargs — login passes custom message per plan spec without breaking existing no-arg callers"
  - "ReplayDetectedError error_code changed from AUTH_REPLAY_DETECTED to REPLAY_DETECTED per plan spec; message updated to 'Session compromised — all sessions revoked. Please log in again.'"
  - "blacklist_access_token uses jwt.decode with verify_exp=False — allows blacklisting nearly-expired tokens on logout without raising TokenExpiredError during decode"
  - "Logout is idempotent — deletes refresh token if present but ignores missing row; blacklists access token silently if malformed"

patterns-established:
  - "Shadow key pattern: auth:replay:{sha256(token)} maps consumed refresh token hash to user_id for replay detection across DB row deletion"
  - "Single-session enforcement: all previous refresh token rows deleted + shadow keys written on each new login"
  - "Replay response: full logout (delete all user refresh tokens) + ReplayDetectedError 401"
  - "Blacklist pattern: auth:blacklist:jti:{jti} with TTL = remaining token lifetime"

requirements-completed: [AUTH-05, AUTH-06]

# Metrics
duration: 3min
completed: 2026-02-23
---

# Phase 02 Plan 03: Token Lifecycle Summary

**Login/refresh/logout endpoints with RS256 JWT issuance, refresh token rotation via PostgreSQL, Redis jti blacklist on logout, and replay-detection shadow keys triggering full session revocation**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-23T13:22:25Z
- **Completed:** 2026-02-23T13:26:15Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- RefreshToken model added (TimestampMixin+Base, refresh_tokens table with token/user_id/expires_at columns)
- Login endpoint authenticates users, enforces single-session (revokes previous tokens + writes shadow keys), issues RS256 access token + opaque refresh token
- Refresh endpoint rotates tokens with full replay detection via Redis shadow keys; replaying a consumed token triggers full logout (all sessions deleted)
- Logout deletes refresh token row and blacklists access token jti in Redis with TTL = remaining lifetime
- LoginRequest, TokenResponse, RefreshRequest, LogoutRequest schemas added

## Task Commits

Each task was committed atomically:

1. **Task 1: RefreshToken model, login/refresh/logout service logic, access token blacklist, replay detection** - `6ad7be1` (feat)
2. **Task 2: Login, refresh, and logout router endpoints** - `3db1d10` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `backend/src/wxcode_adm/auth/models.py` - Added RefreshToken model (TimestampMixin+Base, refresh_tokens table)
- `backend/src/wxcode_adm/auth/schemas.py` - Added LoginRequest, TokenResponse, RefreshRequest, LogoutRequest
- `backend/src/wxcode_adm/auth/service.py` - Added login, refresh, logout, blacklist_access_token, is_token_blacklisted, shadow key helpers
- `backend/src/wxcode_adm/auth/router.py` - Added POST /login, /refresh, /logout endpoints
- `backend/src/wxcode_adm/auth/exceptions.py` - Updated ReplayDetectedError (code/message); updated EmailNotVerifiedError to accept kwargs

## Decisions Made

- **EmailNotVerifiedError kwargs**: Updated to accept optional error_code/message/status_code kwargs while keeping backward-compatible no-arg constructor. Required because the login service passes custom message "Please verify your email before logging in".
- **ReplayDetectedError spec alignment**: Changed error_code from `AUTH_REPLAY_DETECTED` to `REPLAY_DETECTED` and updated message to match plan spec exactly.
- **blacklist_access_token decodes with verify_exp=False**: Avoids TokenExpiredError when blacklisting a token during logout if it is about to expire; we still extract jti and calculate remaining TTL, only setting the Redis key if TTL > 0.
- **Logout is idempotent**: Refresh token deletion ignores not-found rows; blacklist_access_token silently returns on malformed tokens. Safe to call multiple times.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] EmailNotVerifiedError did not accept custom kwargs**
- **Found during:** Task 1 (login service implementation)
- **Issue:** The plan specified `raise EmailNotVerifiedError(error_code="EMAIL_NOT_VERIFIED", message="Please verify your email before logging in")` but the existing `EmailNotVerifiedError.__init__` was no-arg only
- **Fix:** Updated `EmailNotVerifiedError.__init__` to accept optional `error_code`, `message`, `status_code` kwargs with backward-compatible defaults
- **Files modified:** `backend/src/wxcode_adm/auth/exceptions.py`
- **Verification:** Both `EmailNotVerifiedError()` and `EmailNotVerifiedError(error_code="X", message="Y")` work; status_code defaults to 403
- **Committed in:** `6ad7be1` (Task 1 commit)

**2. [Rule 1 - Bug] ReplayDetectedError error_code/message did not match plan spec**
- **Found during:** Task 1 (review of existing exceptions.py)
- **Issue:** Existing code had `AUTH_REPLAY_DETECTED` code and "Session invalidated" message; plan spec requires `REPLAY_DETECTED` and "Session compromised — all sessions revoked. Please log in again."
- **Fix:** Updated `ReplayDetectedError.__init__` to use the exact code and message from the plan
- **Files modified:** `backend/src/wxcode_adm/auth/exceptions.py`
- **Verification:** `ReplayDetectedError().error_code == 'REPLAY_DETECTED'` and message contains "all sessions revoked"
- **Committed in:** `6ad7be1` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs in existing exception classes)
**Impact on plan:** Both fixes required for correct behavior per plan spec. No scope creep.

## Issues Encountered

None — plan executed as specified with only minor corrections to pre-existing exception class signatures.

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- Token lifecycle complete: login/refresh/logout all functional
- Plan 02-04 (password reset) can use login infrastructure and email job patterns
- Plan 02-05 (get_current_user middleware) must call `is_token_blacklisted(redis, jti)` where jti is extracted from the decoded access token payload — this is the hook that makes logout effective for access tokens

---
*Phase: 02-auth-core*
*Completed: 2026-02-23*

## Self-Check: PASSED

- FOUND: backend/src/wxcode_adm/auth/models.py
- FOUND: backend/src/wxcode_adm/auth/schemas.py
- FOUND: backend/src/wxcode_adm/auth/service.py
- FOUND: backend/src/wxcode_adm/auth/router.py
- FOUND: backend/src/wxcode_adm/auth/exceptions.py
- FOUND: .planning/phases/02-auth-core/02-03-SUMMARY.md
- FOUND commit: 6ad7be1 (Task 1 — RefreshToken model + service logic)
- FOUND commit: 3db1d10 (Task 2 — router endpoints)
