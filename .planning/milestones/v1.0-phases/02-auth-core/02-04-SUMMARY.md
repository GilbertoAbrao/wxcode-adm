---
phase: 02-auth-core
plan: "04"
subsystem: auth
tags: [itsdangerous, password-reset, signed-tokens, single-use, session-revocation, arq, fastapi-mail]

# Dependency graph
requires:
  - phase: 02-auth-core/02-01
    provides: User model, exceptions, password hashing, JWT infrastructure
  - phase: 02-auth-core/02-02
    provides: send_reset_email arq job stub, get_arq_pool, email job pattern
  - phase: 02-auth-core/02-03
    provides: RefreshToken model, blacklist helpers, delete pattern for session revocation
provides:
  - POST /api/v1/auth/forgot-password endpoint (enumeration-safe password reset initiation)
  - POST /api/v1/auth/reset-password endpoint (token verification, password update, session revocation)
  - generate_reset_token / verify_reset_token helpers using itsdangerous URLSafeTimedSerializer
  - ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordRequest, ResetPasswordResponse schemas
  - Password reset flow: 24-hour expiry, single-use via pw_hash salt, all sessions revoked on reset
affects:
  - 02-05 (require_verified dependency may gate reset endpoints)
  - 07-frontend (reset-password URL pattern for reset link)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "itsdangerous URLSafeTimedSerializer with pw_hash as per-token salt for stateless single-use reset tokens"
    - "loads_unsafe() to extract payload before full verification (resolves circular dependency: need email to get pw_hash to verify)"
    - "Enumeration prevention: forgot-password always returns same message regardless of email existence"
    - "Session revocation on password reset: DELETE all RefreshToken rows for user"

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/auth/schemas.py
    - backend/src/wxcode_adm/auth/service.py
    - backend/src/wxcode_adm/auth/router.py
    - backend/src/wxcode_adm/auth/email.py

key-decisions:
  - "pw_hash as itsdangerous salt: changing password automatically invalidates token without any DB token storage"
  - "loads_unsafe() for two-step verification: extract email first (unsigned), find user for pw_hash, then full verify — breaks circular dependency"
  - "reset_serializer uses JWT_PRIVATE_KEY as secret — strong random secret already in settings, salt='password-reset' namespaces from JWT usage"
  - "Reset link uses ALLOWED_ORIGINS[0] as base URL placeholder — adjusted in Phase 7 frontend integration"
  - "Access token NOT blacklisted on password reset — no current token in scope; 24h TTL handles natural expiry; Plan 05 is_active check adds defense"

patterns-established:
  - "itsdangerous signed reset tokens: stateless single-use via pw_hash salt rotation"
  - "Enumeration-safe forgot-password: always 200, only enqueue job when user found"
  - "Two-step itsdangerous loads: loads_unsafe for payload extraction, then loads with salt for full verification"

requirements-completed: [AUTH-04]

# Metrics
duration: 2min
completed: 2026-02-23
---

# Phase 2 Plan 4: Password Reset Flow Summary

**Stateless single-use password reset via itsdangerous URLSafeTimedSerializer with pw_hash as per-token salt, 24-hour expiry, and full session revocation on reset**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-23T13:28:42Z
- **Completed:** 2026-02-23T13:30:44Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Password reset token generation and verification using itsdangerous with pw_hash as salt for stateless single-use enforcement
- POST /api/v1/auth/forgot-password (enumeration-safe, always 200, arq job enqueued only when user exists)
- POST /api/v1/auth/reset-password (two-step verification, password update, delete all RefreshToken rows for full session revocation)

## Task Commits

Each task was committed atomically:

1. **Task 1: Password reset service logic with itsdangerous and session revocation** - `991ce24` (feat)
2. **Task 2: Forgot-password and reset-password router endpoints, and reset email job update** - `e7c7314` (feat)

**Plan metadata:** `[pending]` (docs: complete plan)

## Files Created/Modified

- `backend/src/wxcode_adm/auth/schemas.py` - Added ForgotPasswordRequest/Response, ResetPasswordRequest/Response schemas
- `backend/src/wxcode_adm/auth/service.py` - Added reset_serializer, generate_reset_token, verify_reset_token helpers, forgot_password and reset_password service functions
- `backend/src/wxcode_adm/auth/router.py` - Added POST /auth/forgot-password and POST /auth/reset-password endpoints, updated module docstring
- `backend/src/wxcode_adm/auth/email.py` - Fixed reset email body: updated expiry text from "1 hour" to "24 hours and can only be used once"

## Decisions Made

- **pw_hash as salt**: Using the user's current password_hash as the itsdangerous `salt` parameter makes the token single-use without any DB state. When the password changes, the hash changes, the salt changes, the HMAC fails — BadSignature on second use.
- **loads_unsafe for two-step verification**: To verify the token we need the user's pw_hash, but to find the user we need the email from the token. `loads_unsafe()` breaks this circular dependency by extracting the payload without HMAC verification; full verification follows after user lookup.
- **reset_serializer secret**: JWT_PRIVATE_KEY is used as the HMAC secret (already a strong secret in settings). `salt="password-reset"` at the serializer level namespaces it from JWT key usage.
- **Access token not blacklisted on reset**: No access token is in scope during password reset. The 24h TTL handles natural expiry. Plan 05's `require_verified` / `is_active` dependency will add defense in depth.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed reset email expiry text mismatch**
- **Found during:** Task 2 (reset email job review)
- **Issue:** email.py stub said "This link expires in 1 hour" but the token has a 24-hour max_age (86400 seconds) per the plan spec
- **Fix:** Updated body text to "This link expires in 24 hours and can only be used once"
- **Files modified:** backend/src/wxcode_adm/auth/email.py
- **Verification:** `assert '24 hours' in inspect.getsource(send_reset_email)` passes
- **Committed in:** e7c7314 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug)
**Impact on plan:** Fix necessary for email body to accurately reflect token expiry. No scope creep.

## Issues Encountered

- Plan verification script checked for `/forgot-password` but router uses `/auth/forgot-password` prefix (router has `prefix="/auth"`). Routes are correct — verification logic adjusted to match actual path structure.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Password reset flow is complete and testable (logs reset link at INFO level without SMTP configured)
- Plan 05 (require_verified dependency) can optionally gate reset endpoints or add is_active checks
- Phase 7 frontend will need to update the reset link base URL from ALLOWED_ORIGINS[0] placeholder to actual frontend URL

## Self-Check: PASSED

- schemas.py: FOUND
- service.py: FOUND
- router.py: FOUND
- email.py: FOUND
- 02-04-SUMMARY.md: FOUND
- Commit 991ce24 (Task 1): FOUND
- Commit e7c7314 (Task 2): FOUND

---
*Phase: 02-auth-core*
*Completed: 2026-02-23*
