---
phase: 06-oauth-and-mfa
plan: "04"
subsystem: auth
tags: [mfa, totp, tenant-enforcement, oauth, password-reset, session-revocation]

# Dependency graph
requires:
  - phase: 06-03
    provides: two-stage MFA login, mfa_verify, trusted device cookie, mfa_enabled/mfa_secret on User
  - phase: 06-01
    provides: OAuthAccount model, resolve_oauth_account, nullable password_hash
provides:
  - enable_mfa_enforcement service function with immediate session revocation for non-MFA members
  - disable_mfa_enforcement service function
  - get_enforcing_tenants_for_user helper for login flow
  - PATCH /tenants/current/mfa-enforcement endpoint (Owner-only)
  - Login flow enforcement integration — mfa_setup_required signal for enforcing tenants
  - Trusted device skip suppressed for enforcing tenants
  - OAuth onboarding needs_onboarding check against pending invitations
  - Password reset flow for OAuth-only users (nullable password_hash)
affects:
  - 06-05 (OAuth routes, final phase integration)
  - Frontend login flow (mfa_setup_required signal handling)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - JSON mfa_pending value for enforcement flow (backward compat with plain string format)
    - _reset_salt() helper abstracts password_hash vs. fixed-salt for OAuth-only users
    - Lazy import of get_enforcing_tenants_for_user in login() to avoid circular import
    - Lazy import of Invitation model in resolve_oauth_account for pending invitation check

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/tenants/service.py
    - backend/src/wxcode_adm/tenants/router.py
    - backend/src/wxcode_adm/tenants/schemas.py
    - backend/src/wxcode_adm/auth/service.py
    - backend/src/wxcode_adm/auth/schemas.py

key-decisions:
  - "enable_mfa_enforcement raises MfaRequiredError if actor does not have MFA enabled — prevents owner locking all members including themselves"
  - "Immediate lockout: refresh tokens deleted for all non-MFA members on enforcement enable; access tokens expire naturally within ACCESS_TOKEN_TTL_HOURS"
  - "mfa_pending Redis value is JSON when setup_required=true, plain string for normal MFA flow — backward compatible"
  - "mfa_verify raises MFA_SETUP_REQUIRED (403) when setup_required=true in mfa_pending — enrollment must complete before token issuance"
  - "Trusted device check skipped entirely when user is in any enforcing tenant — always require TOTP"
  - "OAuth new user needs_onboarding=False when pending invitations exist for their email — auto-join via verify_email handles workspace assignment"
  - "_reset_salt uses f'no-password-{user.id}' for OAuth-only users — stable salt that becomes invalidated after password is set via reset"

patterns-established:
  - "Enforcement check in login(): enforcing_tenants query AFTER credential verification (no info leakage to invalid credentials)"
  - "JSON vs. plain string discrimination in mfa_pending key: try json.loads, fall back to plain string"

requirements-completed:
  - AUTH-12

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 06 Plan 04: Tenant MFA Enforcement Summary

**Owner-controlled TOTP enforcement toggle with immediate non-MFA session revocation, login flow integration suppressing device trust for enforcing tenants, and password reset support for OAuth-only users**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T18:13:52Z
- **Completed:** 2026-02-24T18:17:50Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Tenant MFA enforcement toggle: `PATCH /tenants/current/mfa-enforcement` (Owner-only); enabling requires Owner's own MFA, immediately revokes non-MFA member refresh tokens
- Login flow enforcement: users in enforcing tenants without MFA get `mfa_setup_required` signal; users with MFA in enforcing tenants always see TOTP prompt (no trusted device bypass)
- OAuth-only user improvements: `needs_onboarding=False` when pending invitations exist; `_reset_salt()` helper enables password reset for accounts with `password_hash=None`

## Task Commits

Each task was committed atomically:

1. **Task 1: Tenant MFA enforcement service and route** - `dc25ef0` (feat)
2. **Task 2: Login flow tenant enforcement integration and OAuth-only user onboarding** - `76d17a2` (feat)

**Plan metadata:** _committed with this summary_

## Files Created/Modified
- `backend/src/wxcode_adm/tenants/service.py` - Added enable_mfa_enforcement, disable_mfa_enforcement, get_enforcing_tenants_for_user; added delete + RefreshToken imports; added MfaRequiredError import
- `backend/src/wxcode_adm/tenants/router.py` - Added PATCH /tenants/current/mfa-enforcement endpoint; imported MfaEnforcementRequest/Response
- `backend/src/wxcode_adm/tenants/schemas.py` - Added MfaEnforcementRequest and MfaEnforcementResponse
- `backend/src/wxcode_adm/auth/service.py` - Updated login() with enforcement check; updated mfa_verify() to parse JSON mfa_pending; updated resolve_oauth_account() for invitation-aware needs_onboarding; added _reset_salt() helper; updated forgot_password/reset_password to use _reset_salt()
- `backend/src/wxcode_adm/auth/schemas.py` - Added mfa_setup_required field to LoginResponse

## Decisions Made
- `enable_mfa_enforcement` raises `MfaRequiredError` (403, MFA_REQUIRED error code) when actor has no MFA — plan specified this matches the existing exception; Owner cannot enforce on others without having it themselves
- mfa_pending Redis value uses JSON `{"user_id": ..., "setup_required": true}` for enforcement flow vs. plain string for normal TOTP flow — `mfa_verify` discriminates with try/except json.loads for backward compatibility
- `mfa_verify` raises `MFA_SETUP_REQUIRED` (403) when `setup_required=true` — client must redirect to `/auth/mfa/enroll` flow; user logs in again after enrollment
- Trusted device check guarded by `if not enforcing_tenants` — if user is a member of ANY enforcing tenant, device trust is completely bypassed
- `needs_onboarding` for new OAuth user is `len(pending_invitations) == 0` — if any pending invitation exists (even expired ones), we set `False` (conservative; auto_join will handle filtering expired ones)
- `_reset_salt(user)` returns `f"no-password-{user.id}"` for OAuth-only users — after they set a password via reset_password(), their new password_hash becomes the salt, auto-invalidating the reset token

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Tenant MFA enforcement is complete and integrated into the login flow
- OAuth-only users can now use password reset to set a password
- Ready for Phase 06-05: final OAuth route integration, provider management endpoints (unlink OAuth, etc.)

---
*Phase: 06-oauth-and-mfa*
*Completed: 2026-02-24*
