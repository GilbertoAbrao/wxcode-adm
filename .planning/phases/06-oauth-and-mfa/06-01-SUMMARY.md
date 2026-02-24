---
phase: 06-oauth-and-mfa
plan: 01
subsystem: auth
tags: [oauth, authlib, google, github, pkce, mfa, totp, sqlalchemy, pydantic]

# Dependency graph
requires:
  - phase: 05-platform-security
    provides: rate limiting (slowapi), audit log, SessionMiddleware wiring point
  - phase: 02-auth-core
    provides: User model, RefreshToken, JWT token issuance, login flow

provides:
  - authlib OAuth registry with Google and GitHub providers (PKCE, conditional registration)
  - OAuthAccount, MfaBackupCode, TrustedDevice SQLAlchemy models
  - User.password_hash nullable; User.mfa_enabled/mfa_secret columns
  - Tenant.mfa_enforced column
  - resolve_oauth_account state machine (new user / link-required / existing login)
  - get_github_email with private email fallback via /user/emails
  - get_google_userinfo with email_verified claim check
  - confirm_oauth_link with password ownership verification
  - _issue_tokens shared helper (extracted from login for reuse)
  - OAuth redirect routes: GET /auth/oauth/{provider}/login
  - OAuth callback routes: GET /auth/oauth/{provider}/callback
  - Link confirm route: POST /auth/oauth/link/confirm
  - All OAuth and MFA Pydantic schemas (OAuthCallbackResponse, OAuthLinkResponse, LoginResponse, etc.)
  - All OAuth and MFA exception classes (OAuthEmailUnavailableError, OAuthLinkRequiredError, etc.)
  - SESSION_SECRET_KEY config setting; SessionMiddleware wired in app factory

affects:
  - 06-02-PLAN (MFA enrollment uses OAuthAccount model, _issue_tokens, MFA schemas)
  - 06-03-PLAN (Alembic migration for OAuth/MFA tables)

# Tech tracking
tech-stack:
  added:
    - authlib==1.6.8 (OAuth 2.0 + OIDC client with Starlette integration)
    - pyotp==2.9.0 (TOTP MFA code generation/verification)
    - qrcode[pil]==8.2 (QR code image generation for MFA enrollment)
    - starlette.middleware.sessions.SessionMiddleware (for authlib state/PKCE storage)
  patterns:
    - Conditional OAuth provider registration (no startup crash when env vars empty)
    - OAuth account resolution state machine (3 cases: new/link-required/existing)
    - Link token pattern: Redis key auth:oauth_link:{token} with TTL = MFA_PENDING_TTL_SECONDS
    - _issue_tokens helper: DRY single-session token issuance shared across login/OAuth/MFA
    - GitHub private email fallback via /user/emails endpoint
    - Google email_verified claim validation before trusting email

key-files:
  created:
    - backend/src/wxcode_adm/auth/oauth.py
  modified:
    - backend/pyproject.toml
    - backend/src/wxcode_adm/config.py
    - backend/src/wxcode_adm/auth/models.py
    - backend/src/wxcode_adm/auth/exceptions.py
    - backend/src/wxcode_adm/auth/schemas.py
    - backend/src/wxcode_adm/auth/service.py
    - backend/src/wxcode_adm/auth/router.py
    - backend/src/wxcode_adm/tenants/models.py
    - backend/src/wxcode_adm/main.py

key-decisions:
  - "User.password_hash nullable (Option B) — OAuth-only users have no password; required for correct Phase 7 compatibility"
  - "Conditional OAuth provider registration — prevents startup crash when Google/GitHub env vars are empty in dev mode"
  - "OAuthLinkRequiredError returns link_token in Redis — prompts password confirmation to prevent account takeover via OAuth"
  - "One OAuth provider per account — OAuthProviderAlreadyLinkedError raised if user has another provider already linked"
  - "_issue_tokens extracted from login() — avoids duplicating single-session enforcement across login, OAuth, and MFA verify"
  - "SESSION_SECRET_KEY is required (no default) — prevents accidental use of a weak session key in production"
  - "SessionMiddleware added after SlowAPI and before CORS — correct middleware order for authlib state storage"

patterns-established:
  - "OAuth state machine: check OAuthAccount -> check User by email (with/without password) -> create new"
  - "Link token: Redis-stored JSON with TTL = MFA_PENDING_TTL_SECONDS; single-use (deleted after confirm)"
  - "GitHub email: always call /user/emails as fallback when profile email is None"

requirements-completed: [AUTH-08, AUTH-09]

# Metrics
duration: 9min
completed: 2026-02-24
---

# Phase 6 Plan 01: OAuth and MFA Foundation Summary

**authlib OAuth registry with Google + GitHub providers, PKCE, account resolution state machine, and all Phase 6 model/schema infrastructure**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-24T00:00:41Z
- **Completed:** 2026-02-24T00:09:41Z
- **Tasks:** 2
- **Files modified:** 9 files modified, 1 created

## Accomplishments

- Installed authlib==1.6.8, pyotp==2.9.0, qrcode[pil]==8.2 and wired SessionMiddleware for OAuth state/PKCE storage
- Added three new models (OAuthAccount, MfaBackupCode, TrustedDevice), nullable password_hash on User, and mfa_enforced on Tenant
- Implemented full OAuth flow: redirect + callback routes for Google and GitHub, account resolution state machine, and password-confirmed account linking

## Task Commits

Each task was committed atomically:

1. **Task 1: Foundation — dependencies, config, models, OAuth registry, SessionMiddleware, exceptions, schemas** - `6f27c0e` (feat)
2. **Task 2: Google + GitHub OAuth routes and account resolution service** - `cebb75d` (feat)

**Plan metadata:** (see final commit below)

## Files Created/Modified

- `backend/pyproject.toml` — Added authlib, pyotp, qrcode[pil] dependencies
- `backend/src/wxcode_adm/config.py` — Added GOOGLE/GITHUB_CLIENT_ID/SECRET, SESSION_SECRET_KEY (required), MFA_PENDING_TTL_SECONDS, TRUSTED_DEVICE_TTL_DAYS
- `backend/src/wxcode_adm/auth/models.py` — User.password_hash nullable; mfa_enabled/mfa_secret; new OAuthAccount, MfaBackupCode, TrustedDevice models
- `backend/src/wxcode_adm/tenants/models.py` — mfa_enforced column on Tenant
- `backend/src/wxcode_adm/auth/oauth.py` (NEW) — authlib OAuth registry with conditional Google + GitHub registration
- `backend/src/wxcode_adm/auth/exceptions.py` — Five new exception classes: OAuthEmailUnavailableError, OAuthLinkRequiredError, OAuthProviderAlreadyLinkedError, MfaRequiredError, MfaInvalidCodeError
- `backend/src/wxcode_adm/auth/schemas.py` — Nine new Pydantic schemas for OAuth and MFA flows including LoginResponse for two-stage MFA
- `backend/src/wxcode_adm/auth/service.py` — _issue_tokens helper; get_github_email; get_google_userinfo; resolve_oauth_account; confirm_oauth_link; login() refactored to use _issue_tokens
- `backend/src/wxcode_adm/auth/router.py` — Three new OAuth routes: GET /auth/oauth/{provider}/login, GET /auth/oauth/{provider}/callback, POST /auth/oauth/link/confirm
- `backend/src/wxcode_adm/main.py` — SessionMiddleware wired (after SlowAPI, before CORS)

## Decisions Made

- **password_hash nullable:** OAuth-only accounts have no password. Uses Option B (nullable column) for Phase 7 compatibility — avoids a separate OAuthUser discriminator table.
- **Conditional provider registration:** `if settings.GOOGLE_CLIENT_ID:` guards prevent authlib crashing on startup when OAuth is not configured in dev mode.
- **Link token in Redis (not DB):** Short-lived account linking state stored as `auth:oauth_link:{token}` with TTL = MFA_PENDING_TTL_SECONDS (300s). Avoids a DB table for ephemeral pending state.
- **One OAuth provider per account:** Raises OAuthProviderAlreadyLinkedError if user already has a different OAuth provider. Prevents accidental account merging.
- **_issue_tokens helper:** Extracted single-session token issuance from login() to avoid duplicating the revoke-old-tokens + write-shadow-keys + create-new-tokens pattern in OAuth and MFA verify flows.
- **SESSION_SECRET_KEY required:** No default value — fails fast if not set. Added to .env for dev.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- `pip` resolves to Python 3.9.6 on this machine (below the `>=3.11` requirement). All commands run via `/opt/homebrew/bin/pip3.11` instead. This is an environment concern, not a code issue.

## User Setup Required

None — no external service configuration required for the code to load. OAuth credentials (GOOGLE_CLIENT_ID, GITHUB_CLIENT_ID, etc.) are optional; providers are only registered when credentials are set. SESSION_SECRET_KEY is added to .env with a dev placeholder.

## Next Phase Readiness

- Plan 02 (MFA enrollment) can use the OAuthAccount model, _issue_tokens helper, and MFA schemas defined here
- Plan 03 (Alembic migration) will need to add columns: users.mfa_enabled, users.mfa_secret, users.password_hash nullable, tenants.mfa_enforced, plus create oauth_accounts, mfa_backup_codes, trusted_devices tables
- All 90 existing tests pass — no regressions from nullable password_hash or new models

## Self-Check: PASSED

- FOUND: backend/src/wxcode_adm/auth/oauth.py
- FOUND: backend/src/wxcode_adm/auth/models.py
- FOUND: backend/src/wxcode_adm/auth/service.py
- FOUND: backend/src/wxcode_adm/auth/router.py
- FOUND: .planning/phases/06-oauth-and-mfa/06-01-SUMMARY.md
- FOUND commit: 6f27c0e (Task 1)
- FOUND commit: cebb75d (Task 2)

---
*Phase: 06-oauth-and-mfa*
*Completed: 2026-02-24*
