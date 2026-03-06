---
phase: 07-user-account
verified: 2026-02-25T21:30:00Z
status: passed
score: 22/22 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Upload a JPEG avatar via POST /api/v1/users/me/avatar"
    expected: "Image is resized to 256x256 JPEG and returned as /avatars/{user_id}.jpg"
    why_human: "File I/O to AVATAR_UPLOAD_DIR and Pillow image dimensions cannot be verified by grep; filesystem write behavior requires a live environment"
  - test: "Email change OTP delivery via PATCH /api/v1/users/me"
    expected: "Verification email is sent to the new address with a 6-digit OTP code"
    why_human: "arq job enqueue is tested but actual email delivery requires SMTP integration test in a live environment"
---

# Phase 7: User Account Verification Report

**Phase Goal:** Users can manage their own profile and sessions, and are seamlessly redirected to the wxcode application after login with their access token embedded in the redirect
**Verified:** 2026-02-25T21:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | UserSession model exists with all 10 session metadata fields | VERIFIED | `auth/models.py` lines 258–301: `class UserSession` with `refresh_token_id`, `user_id`, `access_token_jti`, `user_agent`, `device_type`, `browser_name`, `browser_version`, `ip_address`, `city`, `last_active_at` |
| 2 | User model has `display_name` and `avatar_url` columns | VERIFIED | `auth/models.py` lines 85–93: both mapped columns present |
| 3 | Tenant model has `wxcode_url` column | VERIFIED | `tenants/models.py` lines 92–96: `wxcode_url: Mapped[Optional[str]]` after `mfa_enforced` |
| 4 | User model has `last_used_tenant_id` column | VERIFIED | `auth/models.py` lines 96–100: FK to `tenants.id` ON DELETE SET NULL |
| 5 | `_issue_tokens` creates a UserSession row alongside each RefreshToken | VERIFIED | `auth/service.py` lines 915–932: flush → decode JTI → `parse_session_metadata` → `UserSession(...)` added to session |
| 6 | Per-request `last_active` written to Redis on every authenticated API call | VERIFIED | `auth/dependencies.py` lines 115–122: `redis.setex(f"auth:session:last_active:{jti}", ...)` in `get_current_user` |
| 7 | `user-agents`, `geoip2`, `Pillow` libraries installed | VERIFIED | `pyproject.toml` lines 29–31: all three packages declared at pinned versions |
| 8 | User can view profile via GET /api/v1/users/me | VERIFIED | `users/router.py` line 49: `@users_router.get("/me", response_model=UserProfileResponse)`; service.get_profile returns all 6 fields; test `test_get_profile` passes |
| 9 | User can update `display_name` via PATCH /api/v1/users/me; change reflected in GET | VERIFIED | `users/router.py` line 67 + `users/service.py` update_profile; test `test_update_display_name` verifies round-trip |
| 10 | User can change email via PATCH; `email_verified` resets to False | VERIFIED | `users/service.py` lines 75–86: email uniqueness check → `user.email_verified = False` → OTP enqueue; test `test_update_email_resets_verification` passes |
| 11 | User can change password via POST /api/v1/users/me/change-password | VERIFIED | `users/router.py` line 148; `users/service.py` change_password with OAuth-only guard, password verify, hash update; tests SC2 all pass |
| 12 | After password change, old password rejected; other sessions invalidated | VERIFIED | `users/service.py` lines 237–293: JTI blacklisting per UserSession row, RefreshToken delete with current_jti exclusion; test `test_change_password_old_rejected` passes |
| 13 | User can view list of active sessions with device/browser/IP/city/last_active | VERIFIED | `users/service.py` list_sessions: inner-join UserSession+RefreshToken, Redis last_active lookup, session_dicts with all metadata; test `test_list_sessions` passes |
| 14 | Current session tagged as `is_current` in the session list | VERIFIED | `users/service.py` line 368: `"is_current": jti == current_jti`; test asserts `len(current) == 1` |
| 15 | User can revoke any individual session; access token immediately rejected | VERIFIED | `users/service.py` revoke_session: `blacklist_jti(redis, ...)` then DELETE RefreshToken; self-revocation prevented with CANNOT_REVOKE_CURRENT error; tests pass |
| 16 | User can revoke all other sessions except current | VERIFIED | `users/service.py` revoke_all_other_sessions: bulk JTI blacklist, DELETE excluding current RT; test `test_revoke_all_other_sessions` passes |
| 17 | After login, wxcode redirect URL and one-time code returned in LoginResponse | VERIFIED | `auth/router.py` lines 259–280: `get_redirect_url` → `create_wxcode_code` → `LoginResponse(wxcode_redirect_url=..., wxcode_code=...)`; test `test_wxcode_code_exchange` asserts both fields |
| 18 | wxcode backend exchanges one-time code for JWT via POST /auth/wxcode/exchange | VERIFIED | `auth/router.py` lines 479–519: rate-limited endpoint with `exchange_wxcode_code` (GETDEL) → returns `WxcodeExchangeResponse` |
| 19 | Code is single-use; replayed code returns 401 | VERIFIED | `auth/service.py` line 995: `redis.getdel(...)` atomic consumption; test asserts second exchange returns 401 |
| 20 | Session metadata (user_agent, ip_address) wired into ALL auth flows | VERIFIED | `auth/router.py`: login (line 216–223), mfa_verify (line 309–315), OAuth callback (lines 380–381), OAuth link confirm (lines 659–660), refresh (lines 616–617) all extract and pass `user_agent=`/`ip_address=` |
| 21 | Alembic migration 006 creates user_sessions and adds profile columns | VERIFIED | `006_add_user_sessions_and_profile_columns.py`: full CREATE TABLE user_sessions (all 13 columns + FKs + indexes), ALTER users (3 columns + FK), ALTER tenants (wxcode_url); `down_revision = "005"` |
| 22 | All tests pass including 15 new integration tests | VERIFIED | `python3.11 -m pytest tests/ -x -q`: **129 passed** (114 pre-phase + 15 new SC1–SC4 tests) |

**Score:** 22/22 truths verified

---

### Required Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `backend/src/wxcode_adm/auth/models.py` | UserSession model with 10 metadata fields | VERIFIED | `class UserSession` at line 258; all 10 fields including `access_token_jti`, `last_active_at` |
| `backend/src/wxcode_adm/config.py` | GEOLITE2_DB_PATH, WXCODE_CODE_TTL, AVATAR_UPLOAD_DIR settings | VERIFIED | Lines 78–80: all three settings in Phase 7 section |
| `backend/src/wxcode_adm/auth/service.py` | `_issue_tokens` with UserSession, `parse_session_metadata`, wxcode helpers, `blacklist_jti` | VERIFIED | Lines 361, 823, 869, 942, 980, 1002 — all functions present and substantive |
| `backend/src/wxcode_adm/auth/dependencies.py` | `get_current_jti`, `last_active` Redis write per request | VERIFIED | Lines 52–67 (`get_current_jti`), lines 115–122 (SETEX in `get_current_user`) |
| `backend/src/wxcode_adm/users/schemas.py` | UserProfileResponse, UpdateProfileRequest/Response, AvatarUploadResponse, ChangePassword, Session schemas | VERIFIED | All 10 Pydantic schema classes present with correct fields |
| `backend/src/wxcode_adm/users/service.py` | `get_profile`, `update_profile`, `upload_avatar`, `change_password`, `list_sessions`, `revoke_session`, `revoke_all_other_sessions` | VERIFIED | All 7 service functions present and fully implemented |
| `backend/src/wxcode_adm/users/router.py` | GET/PATCH /users/me, POST /me/avatar, POST /me/change-password, GET/DELETE /me/sessions | VERIFIED | `users_router` with 7 endpoints; all use `require_verified` + `get_current_jti` where needed |
| `backend/src/wxcode_adm/auth/router.py` | POST /auth/wxcode/exchange; all auth flows pass request metadata to _issue_tokens | VERIFIED | Lines 479–519 for exchange endpoint; user_agent= wired in 5+ flows |
| `backend/src/wxcode_adm/auth/schemas.py` | WxcodeExchangeRequest/Response, LoginResponse wxcode fields | VERIFIED | Lines 249–250 (optional fields on LoginResponse), lines 258–280 (exchange schemas) |
| `backend/src/wxcode_adm/main.py` | `include_router(users_router)` | VERIFIED | Lines 194–195: lazy import + include_router after audit_router |
| `backend/alembic/versions/006_add_user_sessions_and_profile_columns.py` | Migration for Phase 7 schema changes | VERIFIED | Full upgrade/downgrade; down_revision="005" |
| `backend/tests/test_user_account.py` | 15 integration tests for SC1–SC4 | VERIFIED | 15 tests covering all 4 USER success criteria; all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `auth/service.py` | `auth/models.py` | `_issue_tokens` creates `UserSession(...)` row | VERIFIED | Line 925: `UserSession(refresh_token_id=rt.id, user_id=user.id, access_token_jti=jti, ...)` |
| `auth/dependencies.py` | Redis | `SETEX auth:session:last_active:{jti}` on every request | VERIFIED | Line 118: `await redis.setex(f"auth:session:last_active:{jti}", ...)` |
| `auth/service.py` | Redis | `auth:wxcode_code:{code}` store/retrieve | VERIFIED | Line 972: `redis.set(f"auth:wxcode_code:{code}", ...)` + line 995: `redis.getdel(...)` |
| `auth/router.py` | `auth/service.py` | Login calls `create_wxcode_code` + returns redirect URL | VERIFIED | Lines 263–271: `get_redirect_url` → `create_wxcode_code` → `wxcode_redirect_url` in response |
| `auth/router.py` | `auth/service.py` | Login/MFA/OAuth pass `user_agent=`, `ip_address=` to `_issue_tokens` | VERIFIED | grep confirms user_agent= at lines 222, 314, 380, 616, 659 in auth/router.py |
| `users/router.py` | `users/service.py` | Router calls service functions | VERIFIED | All 7 endpoints call `await service.*` or `service.get_profile` |
| `users/service.py` | `auth/models.py` | Queries UserSession + RefreshToken for session listing | VERIFIED | `users/service.py` imports `UserSession` from `auth.models`; line 337 inner join |
| `users/service.py` | Redis | Reads `auth:session:last_active:` in list_sessions; blacklists JTIs on revocation | VERIFIED | Line 348: `redis.get(f"auth:session:last_active:{jti}")`; revoke calls `blacklist_jti` |
| `main.py` | `users/router.py` | `app.include_router(users_router)` | VERIFIED | Lines 194–195 in main.py |
| `tests/test_user_account.py` | `users/router.py` | HTTP calls to `/api/v1/users/me` | VERIFIED | 12 tests call `/api/v1/users/me` endpoints |
| `tests/test_user_account.py` | `auth/router.py` | HTTP calls to `/api/v1/auth/wxcode/exchange` | VERIFIED | Lines 345, 395, 405 call `wxcode/exchange` |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|---------|
| USER-01 | 07-01, 07-02, 07-04 | User can view and edit profile (name, email, avatar) | SATISFIED | GET /users/me returns all 6 profile fields; PATCH /users/me updates display_name/email; avatar upload stores 256x256 JPEG; 5 SC1 tests pass |
| USER-02 | 07-02, 07-04 | User can change password (requires current password) | SATISFIED | POST /users/me/change-password verifies current password, hashes new, invalidates other sessions; 3 SC2 tests pass including old-password-rejection |
| USER-03 | 07-01, 07-03, 07-04 | User can list and revoke active sessions | SATISFIED | GET/DELETE /users/me/sessions with device/browser/IP/city metadata, is_current tag, JTI blacklisting, self-revocation prevention; 4 SC3 tests pass |
| USER-04 | 07-01, 07-03, 07-04 | User is redirected to wxcode with access token after login | SATISFIED | One-time code in LoginResponse (token never in URL); POST /auth/wxcode/exchange with GETDEL atomic consumption; 3 SC4 tests pass including single-use enforcement |

All 4 requirement IDs declared across plans are fully satisfied. No orphaned requirements.

---

### Anti-Patterns Found

None. Scanned `users/service.py`, `users/router.py`, `users/schemas.py` for TODO/FIXME/placeholder/empty returns — zero matches found. All implementations are substantive.

---

### Human Verification Required

#### 1. Avatar Upload — Image Resize

**Test:** POST a JPEG or PNG file to `/api/v1/users/me/avatar` via a real HTTP client or curl.
**Expected:** Server accepts the file, resizes it to exactly 256x256 pixels, saves as JPEG to `AVATAR_UPLOAD_DIR/{user_id}.jpg`, and returns `{ "avatar_url": "/avatars/{user_id}.jpg" }`. File on disk should be readable and dimensions confirmed with an image viewer.
**Why human:** Pillow image processing and filesystem writes cannot be verified by code grep. The logic exists and is substantive, but the actual output file and pixel dimensions require a running backend.

#### 2. Email Change OTP Delivery

**Test:** PATCH `/api/v1/users/me` with a new email address on a running backend with SMTP configured.
**Expected:** A verification email is delivered to the new address with a valid 6-digit OTP. User can verify the new email using that OTP.
**Why human:** arq job enqueueing is tested (`pool.enqueue_job("send_verification_email", ...)`), but actual email delivery and OTP validity require live SMTP + arq worker integration.

---

### Gaps Summary

No gaps. All 22 must-haves from plans 07-01 through 07-04 are verified as existing, substantive (not stubs), and wired. All 4 requirement IDs (USER-01, USER-02, USER-03, USER-04) are fully satisfied by the implementation. The full test suite of 129 tests passes with no regressions. Two items are flagged for human verification (avatar file I/O, email OTP delivery) but do not block goal achievement — the underlying implementations are complete and tested at the integration level.

---

_Verified: 2026-02-25T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
