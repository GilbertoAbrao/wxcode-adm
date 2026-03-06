---
phase: 06-oauth-and-mfa
plan: 02
subsystem: auth
tags: [mfa, totp, pyotp, qrcode, backup-codes, argon2, enrollment, fastapi, sqlalchemy]

# Dependency graph
requires:
  - phase: 06-01
    provides: MfaBackupCode model, MfaInvalidCodeError exception, MFA schemas (MfaEnrollBeginResponse etc.), User.mfa_enabled/mfa_secret columns
  - phase: 02-auth-core
    provides: hash_password/verify_password (argon2id), require_verified dependency, write_audit

provides:
  - generate_backup_codes(): 10 formatted "XXXXX-XXXXX" codes with argon2id hashes (tuple return)
  - generate_qr_code_base64(): base64 PNG from otpauth:// provisioning URI using qrcode[pil]
  - mfa_begin_enrollment(): generates pyotp secret + QR, stores temp mfa_secret (mfa_enabled NOT set)
  - mfa_confirm_enrollment(): verifies TOTP (valid_window=1), sets mfa_enabled=True, creates 10 MfaBackupCode rows
  - mfa_disable(): accepts TOTP or unused backup code (strips dashes for comparison), clears mfa state
  - POST /api/v1/auth/mfa/enroll — begin enrollment, returns secret + qr_code + provisioning_uri
  - POST /api/v1/auth/mfa/confirm — confirm with TOTP, returns 10 plaintext backup codes (shown ONCE)
  - DELETE /api/v1/auth/mfa — disable MFA with TOTP or backup code
  - GET /api/v1/auth/mfa/status — check mfa_enabled boolean

affects:
  - 06-03-PLAN (Alembic migration creates mfa_backup_codes table used by this plan)
  - 06-04-PLAN (MFA verify flow at login calls same TOTP/backup code logic patterns)

# Tech tracking
tech-stack:
  added:
    - pyotp==2.9.0 (TOTP generation/verification via pyotp.random_base32, pyotp.TOTP.verify)
    - qrcode[pil]==8.2 (QR code image generation with Pillow backend)
  patterns:
    - Backup code format: "XXXXX-XXXXX" display, dash stripped before argon2id hashing
    - TOTP window: valid_window=1 allows ±30s clock skew for authenticator app drift
    - Enrollment two-step: begin (stores mfa_secret) then confirm (sets mfa_enabled=True)
    - Backup code verification: iterate unused MfaBackupCode rows, call verify_password per row
    - MFA disable tries TOTP first, falls back to backup code (ordered for performance)

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/auth/service.py
    - backend/src/wxcode_adm/auth/router.py

key-decisions:
  - "generate_backup_codes returns (plaintext_formatted, hashed) tuple — caller controls what is stored vs shown"
  - "BACKUP_CODE_COUNT = 10 constant at module level for easy future adjustment"
  - "QR code base64 has no data URI prefix — frontend adds 'data:image/png;base64,' prefix as needed"
  - "mfa_disable tries TOTP first for performance — TOTP is O(1), backup code scan is O(n)"

patterns-established:
  - "MFA enrollment is two-step: begin stores temp mfa_secret, confirm sets mfa_enabled=True"
  - "Backup codes: formatted XXXXX-XXXXX for display, raw (no dash) hashed with argon2id"
  - "All MFA routes use require_verified: JWT validated + email verified + not inactive"

requirements-completed: [AUTH-10]

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 6 Plan 02: MFA Enrollment Summary

**TOTP MFA enrollment via pyotp: begin/confirm two-step with QR code generation, 10 argon2id-hashed backup codes, and disable flow accepting TOTP or unused backup code**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-24T17:54:16Z
- **Completed:** 2026-02-24T18:01:39Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- MFA enrollment service functions: begin (generates pyotp secret + QR code), confirm (verifies TOTP + creates 10 argon2id-hashed MfaBackupCode rows), disable (accepts TOTP or backup code)
- All 4 MFA enrollment routes registered on auth_api_router with require_verified + audit log
- 90 existing tests still pass — zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: MFA enrollment service functions** - `1021c53` (feat)
2. **Task 2: MFA enrollment API routes** - `23d7862` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `backend/src/wxcode_adm/auth/service.py` - Added generate_backup_codes, generate_qr_code_base64, mfa_begin_enrollment, mfa_confirm_enrollment, mfa_disable; imports pyotp, qrcode, MfaBackupCode, MfaInvalidCodeError
- `backend/src/wxcode_adm/auth/router.py` - Added POST /mfa/enroll, POST /mfa/confirm, DELETE /mfa, GET /mfa/status routes; imports MFA request/response schemas

## Decisions Made

- generate_backup_codes returns a tuple (plaintext_formatted, hashed) so the router never sees the hashed values and the service never stores plaintext
- TOTP valid_window=1 allows one 30-second window in either direction to handle authenticator clock drift
- mfa_disable tries TOTP first (O(1)) then iterates unused backup codes (O(n)) — performance ordering
- QR code base64 returned without data URI prefix — frontend appends "data:image/png;base64," as needed
- Backup code display format "XXXXX-XXXXX" uses first 10 chars of secrets.token_urlsafe(8).upper() split at position 5

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed pyotp==2.9.0 and qrcode[pil]==8.2 into pyenv 3.12.3**
- **Found during:** Pre-execution check (before Task 1)
- **Issue:** pyotp and qrcode were listed in pyproject.toml but not installed in the local Python environment used for verification
- **Fix:** Ran `pip3.12 install "pyotp==2.9.0" "qrcode[pil]==8.2"` and also installed `authlib==1.6.8` (needed by router import chain)
- **Files modified:** None (dependency installation only)
- **Verification:** `python3.12 -c "import pyotp, qrcode; print('OK')"` succeeds
- **Committed in:** Not committed (environment setup, not source change)

---

**Total deviations:** 1 auto-fixed (1 blocking — dependency installation)
**Impact on plan:** Necessary to run verification commands. No source code scope creep.

## Issues Encountered

None — plan executed as specified after dependency installation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- MFA enrollment endpoints are complete and ready for use
- Plan 06-03 (Alembic migration) must be run before these endpoints work in production (creates mfa_backup_codes table)
- Plan 06-04 (MFA verify at login) can now build on the same TOTP verification pattern

## Self-Check: PASSED

All files exist and all commits verified:
- FOUND: backend/src/wxcode_adm/auth/service.py
- FOUND: backend/src/wxcode_adm/auth/router.py
- FOUND: .planning/phases/06-oauth-and-mfa/06-02-SUMMARY.md
- FOUND commit: 1021c53 (Task 1 - MFA enrollment service functions)
- FOUND commit: 23d7862 (Task 2 - MFA enrollment API routes)

---
*Phase: 06-oauth-and-mfa*
*Completed: 2026-02-24*
