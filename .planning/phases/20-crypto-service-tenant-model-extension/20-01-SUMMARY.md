---
phase: 20-crypto-service-tenant-model-extension
plan: "01"
subsystem: api
tags: [cryptography, fernet, encryption, settings, config]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: config.py Settings class with SecretStr pattern

provides:
  - Fernet encrypt/decrypt service functions (encrypt_value, decrypt_value)
  - WXCODE_ENCRYPTION_KEY setting in config.py with dev default
  - Unit tests for crypto service (6 tests, all passing)

affects:
  - 20-crypto-service-tenant-model-extension (plan 02 — Tenant model extension uses encrypt_value/decrypt_value)
  - 22-claude-oauth (will use encrypt_value for Claude OAuth token storage)

# Tech tracking
tech-stack:
  added: []  # cryptography package already present via PyJWT[crypto]
  patterns:
    - "Lazy Fernet instantiation via _get_fernet() — reads key fresh per call, safe for monkeypatching in tests"
    - "Passphrase-to-key derivation via SHA-256 + urlsafe_b64encode — any string works as WXCODE_ENCRYPTION_KEY"

key-files:
  created:
    - backend/src/wxcode_adm/common/crypto.py
    - backend/tests/test_crypto.py
  modified:
    - backend/src/wxcode_adm/config.py

key-decisions:
  - "Lazy _get_fernet() helper reads key from settings per call — avoids module-level state, enables monkeypatching"
  - "SHA-256 passphrase derivation — arbitrary strings work as WXCODE_ENCRYPTION_KEY, no Fernet format requirement on dev"
  - "Dev default is 'change-me-in-production' — obvious non-production sentinel, no fake Fernet key hardcoded"

patterns-established:
  - "Crypto pattern: encrypt_value/decrypt_value as thin wrappers over _get_fernet() — reuse for any future at-rest encryption"

requirements-completed:
  - ENG-01

# Metrics
duration: 1min
completed: "2026-03-07"
---

# Phase 20 Plan 01: Crypto Service Summary

**Fernet symmetric encryption service with passphrase-to-key derivation, enabling at-rest encryption of sensitive tenant data (Claude OAuth tokens)**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-07T17:09:21Z
- **Completed:** 2026-03-07T17:10:42Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Created `crypto.py` with `encrypt_value` / `decrypt_value` using Fernet symmetric encryption
- Added `WXCODE_ENCRYPTION_KEY: SecretStr` to Settings (Phase 20 section, dev default "change-me-in-production")
- 6 unit tests pass: round-trip, ciphertext uniqueness, wrong-key rejection, empty string, unicode/emoji

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Fernet crypto service and add encryption key to Settings** - `ed8a31d` (feat)
2. **Task 2: Write tests for crypto service** - `44b1f0c` (test)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified

- `backend/src/wxcode_adm/common/crypto.py` - Fernet encrypt_value/decrypt_value with _get_fernet() helper and SHA-256 key derivation
- `backend/src/wxcode_adm/config.py` - Added WXCODE_ENCRYPTION_KEY: SecretStr to Settings (Phase 20 section)
- `backend/tests/test_crypto.py` - 6 unit tests covering all required test cases

## Decisions Made

- **Lazy _get_fernet():** Reading the key fresh per function call (not at module import time) makes monkeypatching trivial in tests and avoids stale state if settings are patched.
- **SHA-256 key derivation:** If WXCODE_ENCRYPTION_KEY is not already a valid 44-char URL-safe base64 Fernet key, it is derived via `SHA-256 + urlsafe_b64encode`. This allows arbitrary passphrase strings (including the dev default) to work without requiring users to generate a proper Fernet key format for development.
- **Dev default "change-me-in-production":** Obvious sentinel string rather than a hardcoded fake Fernet key. Safe for dev/test because key derivation works on any string.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

Production environments should set `WXCODE_ENCRYPTION_KEY` to a proper Fernet key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the output to the production `.env` file as `WXCODE_ENCRYPTION_KEY=<generated-key>`.

## Next Phase Readiness

- `encrypt_value` and `decrypt_value` are ready to be imported by Plan 02 (Tenant model extension for Claude OAuth token columns)
- The `_get_fernet()` helper pattern is established and documented for future at-rest encryption use cases

---
*Phase: 20-crypto-service-tenant-model-extension*
*Completed: 2026-03-07*

## Self-Check: PASSED

- backend/src/wxcode_adm/common/crypto.py: FOUND
- backend/src/wxcode_adm/config.py: FOUND
- backend/tests/test_crypto.py: FOUND
- .planning/phases/20-crypto-service-tenant-model-extension/20-01-SUMMARY.md: FOUND
- Commit ed8a31d (feat: crypto service + config): FOUND
- Commit 44b1f0c (test: crypto unit tests): FOUND
