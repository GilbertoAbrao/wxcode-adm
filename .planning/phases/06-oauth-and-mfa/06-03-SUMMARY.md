---
phase: 06-oauth-and-mfa
plan: 03
subsystem: auth
tags: [mfa, totp, trusted-device, redis, fastapi, httponly-cookie]

# Dependency graph
requires:
  - phase: 06-02
    provides: MFA enrollment endpoints, MfaBackupCode model, mfa_enabled/mfa_secret on User
  - phase: 06-01
    provides: TrustedDevice model, LoginResponse schema, MfaVerifyRequest schema, _issue_tokens helper

provides:
  - Two-stage MFA login flow: login returns mfa_required=True + mfa_token when MFA enabled
  - POST /auth/mfa/verify endpoint completing second-factor authentication
  - TOTP replay prevention via Redis auth:mfa:used:{user_id} key (60s TTL)
  - Trusted device cookie management (create, verify, revoke)
  - TrustedDevice DB record creation with SHA-256 hashed token and expiry

affects:
  - 06-04 (tenant MFA enforcement will check mfa_required flow)
  - 06-05 (integration tests will test the two-stage login)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Two-stage auth: login() returns opaque mfa_token stored in Redis (300s TTL); mfa_verify() consumes it
    - TOTP replay prevention: Redis key auth:mfa:used:{user_id} = code with 60s TTL
    - Trusted device: SHA-256 hash stored in DB, plaintext only in HttpOnly cookie
    - login() return type is dict interpreted by router into LoginResponse

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/auth/service.py
    - backend/src/wxcode_adm/auth/router.py

key-decisions:
  - "login() return type changed to dict (not TokenResponse or LoginResponse) — router does final shaping; enables router to handle both MFA-required and direct-token cases without service knowing about HTTP"
  - "TOTP replay check uses exact code equality against Redis stored value — only applies to 6-digit numeric codes (is_totp_code check); backup codes skip replay detection since they are single-use by DB constraint"
  - "is_device_trusted() accepts str user_id (not UUID) — caller passes str(user.id); avoids UUID/str conversion mismatch in login() where user.id is a UUID object"
  - "mfa/verify returns JSONResponse (not Pydantic model) — required to call response.set_cookie(); same pattern as FastAPI docs recommend for cookie-setting endpoints"
  - "login() audit: login_mfa_pending logged when MFA required (not 'login') — differentiates full logins from MFA-gated sessions in audit trail"

patterns-established:
  - "Redis pending token pattern: store user_id as string at auth:{context}:{token} with short TTL; consume (delete) on use — reused by oauth_link and now mfa_pending"
  - "Trusted device cookie attributes: httponly=True, secure=(APP_ENV != 'development'), samesite='lax', max_age=TRUSTED_DEVICE_TTL_DAYS*86400"

requirements-completed:
  - AUTH-11
  - AUTH-13

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 06 Plan 03: Two-Stage MFA Login Summary

**Two-stage MFA login: password auth returns mfa_token (Redis 300s TTL), second factor via POST /auth/mfa/verify with TOTP replay prevention and 30-day trusted device cookie**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-24T18:07:00Z
- **Completed:** 2026-02-24T18:10:05Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Login flow now branches on MFA: returns `mfa_required=True + mfa_token` (stored in Redis for 300s) instead of JWT tokens when user has MFA enabled and device is not trusted
- POST /auth/mfa/verify validates TOTP or unused backup code against mfa_pending token, prevents TOTP replay (60s Redis key), and issues JWT tokens on success
- Trusted device helpers: `create_trusted_device` stores SHA-256 hash in DB, `is_device_trusted` checks expiry and hash, `revoke_trusted_devices` clears all records; cookie set HttpOnly with correct Secure/SameSite attributes

## Task Commits

Each task was committed atomically:

1. **Task 1: Two-stage login, MFA verify service, TOTP replay prevention, trusted device helpers** - `8cb0854` (feat)
2. **Task 2: MFA verify route, modified login route, trusted device cookie handling** - `32714e9` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified
- `backend/src/wxcode_adm/auth/service.py` - Modified login() with MFA branch and device_token param; added mfa_verify(), create_trusted_device(), is_device_trusted(), revoke_trusted_devices()
- `backend/src/wxcode_adm/auth/router.py` - POST /login now returns LoginResponse and handles both MFA-required and direct-token paths; new POST /auth/mfa/verify endpoint with JSONResponse + cookie setting

## Decisions Made
- `login()` return type changed to `dict` (not Pydantic model) — router shapes the final `LoginResponse`; keeps service layer HTTP-agnostic
- TOTP replay check only applies to 6-digit numeric codes (`is_totp_code` guard) — backup codes have DB-level single-use enforcement via `used_at` timestamp
- `is_device_trusted()` accepts `str` user_id to avoid UUID/str conversion friction at the call site in `login()`
- `POST /auth/mfa/verify` returns `JSONResponse` instead of Pydantic model — required to call `response.set_cookie()` on the response object
- Login audit: `login_mfa_pending` action logged when MFA required (separate from `login`) — differentiates partial auth attempts in audit log

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- Two-stage MFA login complete; plan 04 can add tenant-level MFA enforcement (check if tenant requires MFA and deny trusted device bypass when enforcement is on)
- `revoke_trusted_devices` ready for use when password reset or full session revocation is needed
- All 90 existing tests pass; login tests pass because mfa_enabled=False on test users (default)

## Self-Check: PASSED

All files confirmed present. All task commits confirmed in git history.

---
*Phase: 06-oauth-and-mfa*
*Completed: 2026-02-24*
