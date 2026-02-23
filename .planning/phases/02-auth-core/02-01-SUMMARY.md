---
phase: 02-auth-core
plan: 01
subsystem: auth
tags: [jwt, rsa, rs256, jwks, argon2, pyjwt, pwdlib, sqlalchemy, fastapi]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Base, TimestampMixin, AppError, FastAPI app factory, config.py settings pattern

provides:
  - RS256 JWT create_access_token and decode_access_token functions
  - GET /.well-known/jwks.json endpoint returning valid JWKS document
  - User SQLAlchemy model (platform-level, not tenant-scoped)
  - Auth domain exceptions (AuthError, InvalidCredentialsError, TokenExpiredError, etc.)
  - Argon2id password hashing (hash_password / verify_password)
  - Phase 2 dependencies (PyJWT, pwdlib, itsdangerous, slowapi, fastapi-mail)

affects:
  - 02-02 (login/signup uses User model, hash_password, create_access_token, auth exceptions)
  - 02-03 (refresh token flow uses decode_access_token, auth exceptions)
  - 02-04 (password reset uses itsdangerous, email settings, User model)
  - 02-05 (email verification uses User.email_verified, fastapi-mail, SMTP settings)
  - 03-rbac (tenant membership links to User via FK)
  - all future plans consuming JWT-protected routes

# Tech tracking
tech-stack:
  added:
    - PyJWT[crypto]==2.11.0 (RS256 signing and JWKS conversion)
    - pwdlib[argon2]==0.3.0 (Argon2id password hashing)
    - itsdangerous==2.2.0 (password reset tokens — Plan 04)
    - slowapi==0.1.9 (rate limiting — Plans 02-03)
    - fastapi-mail==1.6.2 (email sending — Plans 02, 05)
    - cryptography (transitive, RSA key loading)
  patterns:
    - RS256 JWT with kid in JOSE header (not payload) for JWKS key rotation support
    - Module-level PasswordHash singleton (pwd_context) — thread-safe, avoids re-init per request
    - Auth exceptions extend AppError, caught by global handler in main.py
    - JWKS endpoint root-mounted (no API prefix) — RFC 5785 .well-known standard
    - User model uses Base+TimestampMixin (NOT TenantModel) — auth is platform-level

key-files:
  created:
    - backend/src/wxcode_adm/auth/jwt.py
    - backend/src/wxcode_adm/auth/jwks.py
    - backend/src/wxcode_adm/auth/router.py
    - backend/src/wxcode_adm/auth/models.py
    - backend/src/wxcode_adm/auth/exceptions.py
    - backend/src/wxcode_adm/auth/password.py
  modified:
    - backend/pyproject.toml
    - backend/src/wxcode_adm/config.py
    - backend/src/wxcode_adm/main.py

key-decisions:
  - "JWT kid set in JOSE header via jwt.encode headers param — NOT in payload — enables correct JWKS kid matching"
  - "User model inherits Base+TimestampMixin (not TenantModel) — auth is platform-level, users span multiple tenants"
  - "InvalidCredentialsError uses single generic message for wrong-email and wrong-password — prevents user enumeration"
  - "JWKS endpoint root-mounted without API prefix — RFC 5785 requires /.well-known/ at domain root"
  - "load_pem_public_key called without backend= argument — deprecated in modern cryptography library"
  - "Dev .env updated with real RSA keys generated with python-cryptography — placeholder keys replaced"

patterns-established:
  - "Auth exceptions: no-arg constructors with hardcoded error_code/message/status_code — consistent API error surface"
  - "JWT kid: JWT_KID='v1' config setting, same kid in jwt.encode headers and JWKS build_jwks_response"
  - "Settings extension: new config fields added to config.py with sensible defaults, no breaking changes"

requirements-completed:
  - AUTH-05
  - AUTH-07

# Metrics
duration: 4min
completed: 2026-02-23
---

# Phase 2 Plan 01: Auth Infrastructure Summary

**RS256 JWT signing/verification with JWKS endpoint, User SQLAlchemy model, Argon2id password hashing, and auth domain exceptions — cryptographic foundation for all Phase 2 auth operations**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-23T13:09:39Z
- **Completed:** 2026-02-23T13:13:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- RS256 JWT create/decode pipeline operational with kid in JOSE header, matching JWKS kid
- GET /.well-known/jwks.json endpoint live, returning valid JWKS with kty/n/e/use/alg/kid fields
- User model defined as Base+TimestampMixin (platform-level, not tenant-scoped) with all required columns
- Auth exceptions hierarchy: AuthError base + 6 concrete exceptions, all extending AppError
- Argon2id password hashing via pwdlib with module-level singleton for thread safety
- All Phase 2 dependencies installed: PyJWT, pwdlib, itsdangerous, slowapi, fastapi-mail

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Phase 2 dependencies, User model, auth exceptions, and password hashing** - `7c9bd15` (feat)
2. **Task 2: JWT RS256 signing/decoding, JWKS endpoint, and router registration** - `e509d02` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/auth/jwt.py` - create_access_token (RS256 + kid header) and decode_access_token
- `backend/src/wxcode_adm/auth/jwks.py` - build_jwks_response converting RSA PEM to JWK dict
- `backend/src/wxcode_adm/auth/router.py` - GET /.well-known/jwks.json endpoint (root-mounted)
- `backend/src/wxcode_adm/auth/models.py` - User(TimestampMixin, Base) with 5 columns
- `backend/src/wxcode_adm/auth/exceptions.py` - AuthError base + 6 concrete exceptions
- `backend/src/wxcode_adm/auth/password.py` - hash_password/verify_password using Argon2id
- `backend/pyproject.toml` - 5 Phase 2 dependencies added
- `backend/src/wxcode_adm/config.py` - JWT_KID, ACCESS_TOKEN_TTL_HOURS, REFRESH_TOKEN_TTL_DAYS, SMTP_* settings
- `backend/src/wxcode_adm/main.py` - auth_router included without prefix

## Decisions Made

- **kid in JOSE header, not payload:** `jwt.encode(..., headers={"kid": settings.JWT_KID})` — this is the correct placement; the JWKS kid must match the JWT header kid for key lookup, not a payload claim.
- **User NOT TenantModel:** Auth is platform-level. A user must be identified before tenant context is known (at login). TenantModel guard would block the lookup.
- **InvalidCredentialsError unified message:** "Invalid email or password" used for both wrong-email and wrong-password to prevent user enumeration attacks.
- **JWKS at root:** auth_router registered without prefix in main.py. JWKS must be at `/.well-known/jwks.json` per RFC 5785 — not under `/api/v1`.
- **load_pem_public_key without backend=:** Modern cryptography library does not accept the `backend=` parameter; removed to avoid DeprecationWarning/TypeError.
- **Real RSA keys in .env:** Replaced placeholder keys in backend/.env with newly generated 2048-bit RSA key pair using python-cryptography.

## Deviations from Plan

None — plan executed exactly as written. The only extra work was updating backend/.env with real RSA keys (replacing placeholder strings) so that the settings singleton could be initialized and JWT/JWKS round-trips could be verified against actual keys.

## Issues Encountered

- `pip` not on PATH (macOS system Python 3.9) — used `~/.pyenv/versions/3.12.3/bin/python3.12 -m pip install` with the pyenv-managed Python 3.12 that the project requires (`requires-python = ">=3.11"`). Dependencies installed successfully.
- Placeholder JWT keys in backend/.env caused settings import failures during verification — replaced with freshly generated RSA key pair.

## User Setup Required

None — RSA key pair generated and stored in backend/.env. SMTP defaults are for local Mailpit (port 1025). No external service configuration needed for this plan.

## Next Phase Readiness

- JWT and JWKS infrastructure ready for Plan 02 (login/signup endpoints)
- User model ready for Plan 02 (signup creates User, login queries User by email)
- Auth exceptions ready for Plan 02 (handlers return structured JSON)
- password.py ready for Plan 02 (hash on signup, verify on login)
- SMTP settings ready for Plans 04/05 (password reset and email verification)

---
*Phase: 02-auth-core*
*Completed: 2026-02-23*
