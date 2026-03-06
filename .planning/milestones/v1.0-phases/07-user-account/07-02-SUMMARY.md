---
phase: 07-user-account
plan: "02"
subsystem: auth
tags: [user-profile, avatar-upload, pillow, password-change, fastapi, redis, sqlalchemy]

# Dependency graph
requires:
  - phase: 07-user-account
    plan: "01"
    provides: "User.display_name, User.avatar_url, UserSession model, get_current_jti dependency"
  - phase: 05-platform-security
    provides: "write_audit, rate limiting (limiter, RATE_LIMIT_AUTH), require_verified dependency"
  - phase: 02-auth-core
    provides: "hash_password, verify_password, blacklist_access_token, create_verification_code"
provides:
  - "GET /api/v1/users/me — full UserProfileResponse with display_name, avatar_url, mfa_enabled"
  - "PATCH /api/v1/users/me — partial update of display_name and/or email with OTP re-verification"
  - "POST /api/v1/users/me/avatar — JPEG/PNG upload, Pillow 256x256 resize, saved as JPEG"
  - "POST /api/v1/users/me/change-password — current password verification, other session invalidation"
  - "users/schemas.py: UserProfileResponse, UpdateProfileRequest/Response, AvatarUploadResponse, ChangePassword schemas"
  - "users/service.py: get_profile, update_profile, upload_avatar, change_password business logic"
  - "users/router.py: users_router wired into main.py"
affects: ["07-03", "07-04"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "users module: schemas.py + service.py + router.py separation following auth module pattern"
    - "Avatar upload: Pillow resize to 256x256 LANCZOS, convert RGB, save JPEG to AVATAR_UPLOAD_DIR"
    - "change_password: query UserSession by user_id+jti to blacklist access tokens, then delete RefreshTokens"
    - "current_jti preservation: skip blacklisting + RefreshToken deletion for current session FK match"

key-files:
  created:
    - "backend/src/wxcode_adm/users/schemas.py"
    - "backend/src/wxcode_adm/users/service.py"
    - "backend/src/wxcode_adm/users/router.py"
  modified:
    - "backend/src/wxcode_adm/auth/router.py"
    - "backend/src/wxcode_adm/main.py"
    - "backend/tests/test_auth.py"

key-decisions:
  - "[07-02]: change_password queries UserSession by user_id to get access_token_jti for blacklisting — avoids reconstructing tokens; direct Redis SET with ACCESS_TOKEN_TTL_HOURS TTL"
  - "[07-02]: current_jti preservation matches UserSession.access_token_jti == current_jti, then skips corresponding RefreshToken FK for deletion — keeps current session alive"
  - "[07-02]: GET /auth/me removed from auth/router.py — fully replaced by GET /users/me with richer profile response"
  - "[07-02]: Avatar stored at AVATAR_UPLOAD_DIR/{user.id}.jpg, served via relative path /avatars/{user.id}.jpg"

patterns-established:
  - "Users module pattern: schemas.py for Pydantic models, service.py for business logic, router.py for HTTP layer"
  - "Profile update pattern: check uniqueness before mutation, reset email_verified, enqueue OTP via arq"

requirements-completed: [USER-01, USER-02]

# Metrics
duration: 4min
completed: 2026-02-25
---

# Phase 7 Plan 02: User Account Profile Management Summary

**GET/PATCH /users/me, POST /users/me/avatar, POST /users/me/change-password with Pillow avatar resizing, current session preservation, and audit logging**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T20:45:41Z
- **Completed:** 2026-02-25T20:49:42Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- New `users` module with schemas.py (6 Pydantic models), service.py (4 async functions), and router.py (4 endpoints)
- GET /users/me replaces old GET /auth/me with richer response (display_name, avatar_url, mfa_enabled added)
- PATCH /users/me supports partial update of display_name and/or email; email change resets email_verified and enqueues OTP via arq
- POST /users/me/avatar validates JPEG/PNG (2MB limit), Pillow resizes to 256x256 LANCZOS JPEG; stored at AVATAR_UPLOAD_DIR
- POST /users/me/change-password verifies current password, blacklists other access tokens via Redis, deletes other RefreshToken rows while preserving the current session using current_jti
- All 114 existing tests pass; test_auth.py updated to use /users/me instead of /auth/me

## Task Commits

Each task was committed atomically:

1. **Task 1: Users module schemas and service layer** - `a297794` (feat)
2. **Task 2: Users router, wire into main.py, update tests** - `070afb6` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/users/schemas.py` - UserProfileResponse, UpdateProfileRequest/Response, AvatarUploadResponse, ChangePasswordRequest/Response schemas
- `backend/src/wxcode_adm/users/service.py` - get_profile, update_profile (email re-verification), upload_avatar (Pillow), change_password (session invalidation)
- `backend/src/wxcode_adm/users/router.py` - users_router with GET/PATCH /me, POST /me/avatar, POST /me/change-password; rate limiting on password change; audit logging
- `backend/src/wxcode_adm/auth/router.py` - Removed GET /auth/me (replaced by /users/me)
- `backend/src/wxcode_adm/main.py` - include_router(users_router) added after audit_router
- `backend/tests/test_auth.py` - Updated /auth/me references to /users/me; added display_name/avatar_url/mfa_enabled assertions

## Decisions Made

- `change_password` queries `UserSession` rows by `user_id` to get `access_token_jti` values, then blacklists each JTI in Redis with `ACCESS_TOKEN_TTL_HOURS` TTL — avoids having to reconstruct or decode tokens
- `current_jti` preservation: `UserSession` lookup by `user_id + access_token_jti == current_jti` finds the matching `RefreshToken.id`, which is then excluded from the bulk DELETE
- GET /auth/me removed entirely from `auth/router.py` — fully superseded by GET /users/me which returns the same base fields plus Phase 7 profile fields
- Avatar URL stored as relative path `/avatars/{user.id}.jpg` (research recommendation) — absolute URLs would break on domain changes

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all tasks completed without issues. The import-level lazy imports for `create_verification_code` and `get_arq_pool` in `users/service.py` follow the established codebase pattern (lazy imports to avoid circular dependencies).

## User Setup Required

None - no external service configuration required. Avatar uploads use `AVATAR_UPLOAD_DIR` which is already configured in settings.

## Next Phase Readiness

- Plan 02 complete: user profile CRUD, avatar upload, and password change all functional
- Plan 03 (session management listing/revocation) can build on the `UserSession` model and `users_router` prefix established here
- Plan 04 if applicable can extend the users module pattern
- All 114 tests passing, no blockers

## Self-Check: PASSED

- FOUND: users/schemas.py
- FOUND: users/service.py
- FOUND: users/router.py
- FOUND commit: a297794 (feat: users module schemas and service)
- FOUND commit: 070afb6 (feat: users router, main wiring, test updates)
- 114 tests passing

---
*Phase: 07-user-account*
*Completed: 2026-02-25*
