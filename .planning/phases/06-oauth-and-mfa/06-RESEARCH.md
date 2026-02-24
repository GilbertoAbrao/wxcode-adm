# Phase 6: OAuth and MFA - Research

**Researched:** 2026-02-24
**Domain:** OAuth 2.0 Social Login (Google, GitHub) + TOTP MFA + Tenant Enforcement + Remember-Device
**Confidence:** MEDIUM-HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Account Linking
- When OAuth email matches an existing password account, **prompt the user to enter their existing password** to confirm ownership, then link the OAuth provider to that account in the same flow
- **One OAuth provider per account** — user must unlink current provider before linking a different one
- User can **unlink OAuth only if a password is set** — prevents account lockout
- Email sync from provider changes: Claude's discretion (link by provider user ID, not email)

#### OAuth-only Users
- OAuth-only users **can set a password later** from account settings (implemented in Phase 7)
- Same onboarding flow as email/password users, but **skip workspace creation if already invited to a tenant** — go straight to that tenant
- **Still require email OTP verification** even though OAuth provider verified the email — extra security layer
- If OAuth provider account is deleted/suspended and no password set, user can **use the password reset flow** to set a password and regain access

#### MFA Enrollment
- Number of backup codes: **Claude's discretion** (industry standard)
- All backup codes exhausted + authenticator lost: **contact super-admin** for manual identity verification and MFA reset — no self-service recovery
- **No backup code regeneration** — user must disable MFA and re-enable it to get new codes
- User can **disable MFA with a valid TOTP code or backup code**; if tenant enforcement is on, they will be re-prompted to enroll on next login

#### Tenant Enforcement
- **Immediate lockout** when enforcement is turned on — active sessions are revoked, members without MFA must enroll on next login
- **Owner must have MFA enabled** on their own account before they can turn on enforcement for the tenant
- **No remember-device when tenant enforces MFA** — TOTP required on every login for enforced tenants
- **Per-tenant trust evaluation** — a user in multiple tenants gets remember-device in non-enforcing tenants even if another tenant enforces MFA

### Claude's Discretion
- OAuth email sync behavior (recommended: link by provider user ID, not email)
- Number of backup codes (standard: 8-10)
- TOTP window tolerance (standard: 1 step = 30 seconds)
- Remember-device cookie implementation details

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-08 | User can sign in with Google via OAuth 2.0 (PKCE) | authlib 1.6.8 starlette client, `code_challenge_method='S256'`, Google OIDC metadata URL, SessionMiddleware for state storage |
| AUTH-09 | User can sign in with GitHub via OAuth 2.0 (PKCE) | authlib 1.6.8 starlette client, `user:email` scope, secondary `/user/emails` API call for private emails, GitHub added PKCE support July 2025 |
| AUTH-10 | User can enable MFA via TOTP (QR code setup + backup codes) | pyotp 2.9.0 `random_base32()`, `provisioning_uri()`, `verify(valid_window=1)`, qrcode 8.2 for QR image; 10 backup codes stored as individual argon2 hashes |
| AUTH-11 | User is prompted for TOTP code on login when MFA enabled | Login flow split: first step returns `mfa_required` signal; second step accepts TOTP or backup code to complete token issuance |
| AUTH-12 | Tenant owner can enforce MFA for all tenant members | `mfa_enforced` boolean on Tenant model; enforcement toggle revokes all non-MFA member sessions via DELETE on refresh_tokens |
| AUTH-13 | User can skip MFA on remembered devices (30-day) | HttpOnly, Secure, SameSite=Lax cookie containing opaque token; stored in `trusted_devices` table; suppressed when tenant enforces MFA |
</phase_requirements>

---

## Summary

This phase adds two orthogonal capabilities to the existing auth system: OAuth social login (Google and GitHub) and TOTP-based MFA with tenant enforcement. Both capabilities require new database tables, new API routes under `/api/v1/auth/`, and modifications to the login flow to insert new steps between credential validation and token issuance.

The OAuth flow uses authlib 1.6.8 (the confirmed current version as of February 2026) with its Starlette client integration. PKCE is enabled by setting `code_challenge_method='S256'` in `client_kwargs` at registration time — authlib handles all PKCE mechanics internally (code verifier generation, challenge computation, state management) via `SessionMiddleware`. The GitHub provider requires a secondary API call to `https://api.github.com/user/emails` when the user's email is set to private; the loginpass library's GitHub provider handles this automatically but the pattern must be replicated or adapted for Starlette.

For MFA, pyotp 2.9.0 provides TOTP generation and verification. Backup codes (recommendation: 10 codes) should be stored as individual bcrypt/argon2 hashes in a separate table — each code is single-use and must be invalidated on redemption. The login flow becomes a two-stage flow: stage 1 validates credentials and returns a short-lived "MFA pending" token; stage 2 accepts the TOTP/backup code and issues the real access+refresh pair. Tenant MFA enforcement (`mfa_enforced` flag on Tenant) triggers immediate session revocation for all members who do not have MFA enabled.

**Primary recommendation:** Use authlib 1.6.8 with Starlette client + pyotp 2.9.0 + qrcode 8.2. Add 5 new DB tables (oauth_accounts, mfa_backup_codes, trusted_devices, plus alter users table for mfa fields, alter tenants table for mfa_enforced). All new auth routes follow the existing pattern in `auth/router.py`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| authlib | 1.6.8 | OAuth 2.0 client for Google and GitHub (Starlette integration) | Only Python OAuth library with first-class async Starlette support; implements RFC7636 PKCE automatically; confirmed current version Feb 2026 |
| pyotp | 2.9.0 | TOTP generation, verification, provisioning URIs | RFC 6238 compliant; implements `random_base32()`, `TOTP.verify(valid_window=N)`, `provisioning_uri()` for authenticator apps |
| qrcode[pil] | 8.2 | Generate QR code images for TOTP provisioning URI | Latest stable release May 2025; Pillow backend required for PNG/SVG output; returns base64 encoded image for API response |
| itsdangerous | 2.2.0 | Already in project — can sign OAuth state nonce if needed | Already used for password reset tokens; same pattern applicable |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| starlette SessionMiddleware | (part of starlette, bundled with fastapi) | Store OAuth state + PKCE code verifier during redirect flow | Required by authlib Starlette client; must be added to FastAPI app |
| pwdlib[argon2] | 0.3.0 | Already in project — hash backup codes | Same library used for passwords; backup codes hashed with argon2id; each code stored as individual row |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| authlib Starlette client | httpx-based manual OAuth | authlib handles state, PKCE, token exchange automatically; manual flow is error-prone |
| pyotp | mintotp or manual RFC6238 | pyotp is the canonical Python TOTP library; alternatives have minimal docs |
| qrcode[pil] | segno | qrcode is more widely used; segno is lighter but less documentation |
| argon2 for backup codes | bcrypt | argon2id already in project (pwdlib); no need to add bcrypt |

**Installation:**
```bash
pip install "authlib==1.6.8" "pyotp==2.9.0" "qrcode[pil]==8.2"
```

Add to `pyproject.toml` under `dependencies`:
```toml
# Phase 6 — OAuth and MFA
"authlib==1.6.8",
"pyotp==2.9.0",
"qrcode[pil]==8.2",
```

---

## Architecture Patterns

### Recommended Project Structure

New files in Phase 6:
```
backend/src/wxcode_adm/
├── auth/
│   ├── models.py          # ADD: OAuthAccount, MfaBackupCode, TrustedDevice; ALTER User fields
│   ├── service.py         # ADD: oauth_*, mfa_*, trusted_device_* functions
│   ├── router.py          # ADD: /auth/oauth/*, /auth/mfa/* routes
│   ├── schemas.py         # ADD: OAuth and MFA request/response schemas
│   └── oauth.py           # NEW: authlib OAuth registry (Google + GitHub providers)
├── tenants/
│   ├── models.py          # ALTER: add mfa_enforced to Tenant
│   ├── service.py         # ADD: enforce_mfa(), revoke_non_mfa_sessions()
│   └── router.py          # ADD: PATCH /tenants/{id}/mfa-enforcement
└── alembic/versions/
    └── 005_add_oauth_mfa_tables.py  # NEW: migration
```

### Pattern 1: authlib OAuth Registration (oauth.py)

**What:** Create a module-level OAuth registry and register Google and GitHub providers with PKCE.
**When to use:** At app startup; imported by the router module.

```python
# Source: https://docs.authlib.org/en/latest/client/frameworks.html
from authlib.integrations.starlette_client import OAuth
from wxcode_adm.config import settings

oauth = OAuth()

# Google: uses OIDC discovery, handles PKCE automatically via client_kwargs
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
        "code_challenge_method": "S256",  # PKCE: only S256 is supported
    },
)

# GitHub: no OIDC discovery; explicit endpoints required
# scope user:email is required; email may still be null if user set profile private
# Secondary call to /user/emails is required for private emails (see Pattern 3)
oauth.register(
    name="github",
    client_id=settings.GITHUB_CLIENT_ID,
    client_secret=settings.GITHUB_CLIENT_SECRET.get_secret_value(),
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={
        "scope": "user:email",
        "code_challenge_method": "S256",
    },
)
```

### Pattern 2: OAuth Redirect + Callback Routes

**What:** Two paired routes per provider — redirect initiates flow, callback completes it.
**When to use:** Always; one pair per OAuth provider.

```python
# Source: https://docs.authlib.org/en/latest/client/fastapi.html
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from wxcode_adm.auth.oauth import oauth

@router.get("/oauth/{provider}/login")
async def oauth_login(provider: str, request: Request):
    """Redirect user to OAuth provider's authorization page."""
    redirect_uri = request.url_for("oauth_callback", provider=provider)
    client = oauth.create_client(provider)
    return await client.authorize_redirect(request, str(redirect_uri))

@router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request, db=Depends(get_session), redis=Depends(get_redis)):
    """Handle provider callback: exchange code for token, upsert user."""
    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)
    # provider-specific userinfo extraction (see Pattern 3)
    user_info = await extract_userinfo(provider, client, token)
    # account resolution (see Pattern 4)
    result = await resolve_oauth_account(db, redis, provider, user_info)
    return result
```

**CRITICAL:** `SessionMiddleware` MUST be added to the FastAPI app before any OAuth route is reachable. The authlib Starlette client uses `request.session` to store state and PKCE code_verifier between the redirect and callback.

```python
# In app factory / main.py
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)
```

Add `SESSION_SECRET_KEY: SecretStr` to `config.py` Settings.

### Pattern 3: GitHub Email Extraction (Private Emails)

**What:** GitHub's `/user` endpoint returns `null` for email when user's profile email is private. A secondary call to `/user/emails` is required.
**When to use:** Always in the GitHub callback — the primary email may be null.

```python
# Source: https://github.com/authlib/loginpass/blob/master/loginpass/github.py
async def get_github_email(client, token: dict) -> str:
    """Fetch primary email from GitHub, including private emails."""
    # Try the /user endpoint first
    resp = await client.get("user", token=token)
    profile = resp.json()
    email = profile.get("email")

    if email is None:
        # User's email is private — fetch from /user/emails
        resp = await client.get("user/emails", token=token)
        emails = resp.json()
        # Select the primary email
        email = next(
            (e["email"] for e in emails if e.get("primary")),
            None,
        )

    if email is None:
        raise OAuthEmailUnavailableError()

    return email, str(profile["id"])  # (email, provider_user_id)
```

### Pattern 4: OAuth Account Resolution Logic

**What:** Given provider userinfo, determine whether to: (a) create new account, (b) link to existing, or (c) complete existing session.
**When to use:** In the OAuth callback after userinfo is extracted.

```python
# State machine for OAuth account resolution
async def resolve_oauth_account(db, redis, provider, user_info):
    """
    Resolution priority:
    1. Find existing OAuthAccount by (provider, provider_user_id) → existing linked user
    2. Find existing User by email → account linking flow (return link_required signal)
    3. Neither found → create new User + OAuthAccount

    Account linking by provider_user_id is authoritative, NOT by email.
    Email is only used to detect potential conflicts with existing accounts.
    """
    existing_oauth = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == user_info.provider_user_id,
        )
    )
    # ... (implementation details in service layer)
```

### Pattern 5: TOTP Enrollment Flow

**What:** Three-step enrollment: generate secret → show QR + backup codes → confirm with TOTP code.
**When to use:** User initiates MFA enrollment from settings or during forced enrollment.

```python
# Source: https://pyauth.github.io/pyotp/
import pyotp
import qrcode
import io, base64

def generate_totp_secret() -> str:
    """Generate a new base32 TOTP secret."""
    return pyotp.random_base32()  # returns 32-char base32 string

def get_provisioning_uri(secret: str, email: str) -> str:
    """Get otpauth:// URI for QR code scanning."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name="WXCODE")

def verify_totp_code(secret: str, code: str) -> bool:
    """Verify a TOTP code with ±1 window tolerance (±30s clock skew)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)

def generate_qr_code_base64(uri: str) -> str:
    """Generate a base64-encoded PNG QR code from a provisioning URI."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
```

### Pattern 6: Backup Code Generation and Storage

**What:** Generate N random codes, hash each with argon2id, store one row per code. Return plaintext codes once only.
**When to use:** During MFA enrollment, stored alongside the TOTP secret.

Recommendation: **10 backup codes** (industry standard range is 8-10; 10 is common in GitHub, Google, etc.)

```python
import secrets
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Reuse the existing password hasher from auth/password.py
from wxcode_adm.auth.password import hash_password, verify_password

BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 10  # 10 alphanumeric characters; displayed as XXXXX-XXXXX

def generate_backup_codes() -> tuple[list[str], list[str]]:
    """
    Generate backup codes.

    Returns:
        (plaintext_codes, hashed_codes)
        Plaintext codes are returned to the user ONCE and never stored.
        Hashed codes are stored in mfa_backup_codes table, one row per code.
    """
    plaintext = []
    hashed = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = secrets.token_urlsafe(8)[:10].upper()  # 10-char code
        plaintext.append(raw)
        hashed.append(hash_password(raw))  # argon2id hash
    return plaintext, hashed
```

### Pattern 7: Two-Stage Login Flow (MFA)

**What:** Login becomes a two-request flow when MFA is enabled. Stage 1 validates credentials and returns a short-lived MFA challenge token. Stage 2 validates the TOTP/backup code and issues the real JWT pair.
**When to use:** Any time a user with `mfa_enabled=True` logs in (or a user logging into a tenant with `mfa_enforced=True`).

```python
# Stage 1: POST /api/v1/auth/login
# Returns: { "mfa_required": true, "mfa_token": "<short-lived opaque token>" }
# OR: { "access_token": "...", "refresh_token": "..." }  (no MFA case)

# Stage 2: POST /api/v1/auth/mfa/verify
# Body: { "mfa_token": "<token from stage 1>", "code": "<6-digit TOTP or backup code>" }
# Returns: { "access_token": "...", "refresh_token": "..." }

# MFA token stored in Redis:
# Key: auth:mfa_pending:{token}  →  user_id
# TTL: 300 seconds (5 minutes to enter TOTP)
```

### Pattern 8: Remember-Device Cookie

**What:** After successful MFA verification, optionally set a long-lived HttpOnly cookie. On next login, if cookie is present and valid, skip TOTP prompt.
**When to use:** User opts in; NOT applied when tenant enforces MFA.

```python
# Cookie name: wxcode_trusted_device
# Cookie properties: HttpOnly=True, Secure=True, SameSite=Lax, Max-Age=30*86400
# Cookie value: opaque 32-byte token (secrets.token_urlsafe(32))
# DB record: trusted_devices table (user_id, device_token_hash, expires_at, tenant_id=null)

response.set_cookie(
    key="wxcode_trusted_device",
    value=device_token,
    httponly=True,
    secure=True,   # HTTPS only; set to False in dev
    samesite="lax",
    max_age=30 * 86400,
)
```

**Per-tenant trust evaluation:** When a user logs into a specific tenant context, check if that tenant enforces MFA. If yes, ignore the trusted_device cookie and require TOTP. The cookie itself is global (not per-tenant), but its effect is suppressed per-tenant.

### Pattern 9: Tenant MFA Enforcement Toggle

**What:** PATCH endpoint on the tenants router that sets `mfa_enforced=True` and immediately revokes all refresh tokens for members without MFA.
**When to use:** Tenant owner enables enforcement.

```python
async def enable_mfa_enforcement(db: AsyncSession, redis: Redis, tenant_id: UUID, actor: User) -> None:
    """
    Enable MFA enforcement for a tenant.

    Pre-condition: actor must have MFA enabled (mfa_enabled=True on User).
    Effect: Set Tenant.mfa_enforced=True, delete all refresh tokens for
            members who do NOT have MFA enabled.
    """
    # 1. Verify actor has MFA
    if not actor.mfa_enabled:
        raise AppError("MFA_REQUIRED_FOR_OWNER", "Owner must enable MFA first", 400)

    # 2. Set enforcement flag
    tenant = await db.get(Tenant, tenant_id)
    tenant.mfa_enforced = True

    # 3. Revoke sessions for members without MFA
    # JOIN: tenant_memberships → users where mfa_enabled=False
    non_mfa_user_ids = (
        select(TenantMembership.user_id)
        .join(User, User.id == TenantMembership.user_id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            User.mfa_enabled == False,
        )
    )
    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id.in_(non_mfa_user_ids))
    )
```

### Anti-Patterns to Avoid

- **Auto-linking OAuth accounts by email alone:** An attacker who creates a Google account with someone else's email gets access. Always require password confirmation when linking to an existing account.
- **Storing TOTP secret as plaintext in an unencrypted column:** TOTP secrets must be treated like passwords. Store encrypted at rest (or as a `SecretStr` protected field). In this project, use a standard VARCHAR — PostgreSQL column encryption is out of scope, but the value must not appear in logs.
- **Using `valid_window=0` for TOTP:** This requires perfect clock sync; `valid_window=1` (±30s) is the standard recommendation and does not meaningfully weaken security.
- **Regenerating backup codes in-place:** The decision is disable-then-reenable only. No partial regeneration — avoids state where some old codes are still valid.
- **Long-lived MFA pending tokens:** The MFA pending token in Redis should expire in 5 minutes. Longer windows allow offline brute-force of 6-digit codes.
- **SessionMiddleware with a hardcoded secret:** The session secret must be a strong random value from `settings.SESSION_SECRET_KEY`, not a hardcoded string.
- **Trusting OAuth email for account resolution:** Link by `(provider, provider_user_id)`, not by email. If a user changes their email at the provider, the link must survive.

---

## Database Schema Changes

### New Tables

```sql
-- Alembic migration 005
-- 1. ALTER users table
ALTER TABLE users
  ADD COLUMN password_hash_nullable VARCHAR(255);  -- allow null for OAuth-only users
  -- NOTE: existing password_hash column is NOT NULL; migration must handle this carefully
  -- RECOMMENDED: add oauth_provider_id first, then make password_hash nullable in a separate step

-- Actually: do NOT rename password_hash. Instead add new columns:
ALTER TABLE users
  ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN mfa_secret VARCHAR(64);  -- base32 TOTP secret, nullable (NULL when not enrolled)

-- 2. ALTER tenants table
ALTER TABLE tenants
  ADD COLUMN mfa_enforced BOOLEAN NOT NULL DEFAULT FALSE;

-- 3. oauth_accounts: links a user to an OAuth provider identity
CREATE TABLE oauth_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider VARCHAR(20) NOT NULL,          -- 'google' | 'github'
  provider_user_id VARCHAR(255) NOT NULL, -- stable ID from provider (not email)
  UNIQUE (provider, provider_user_id),
  UNIQUE (user_id, provider)             -- one provider per user
);
CREATE INDEX ix_oauth_accounts_user_id ON oauth_accounts(user_id);

-- 4. mfa_backup_codes: one row per code, argon2 hashed
CREATE TABLE mfa_backup_codes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash VARCHAR(255) NOT NULL,  -- argon2id hash of plaintext code
  used_at TIMESTAMPTZ              -- NULL = not used; set on redemption
);
CREATE INDEX ix_mfa_backup_codes_user_id ON mfa_backup_codes(user_id);

-- 5. trusted_devices: remember-device tokens
CREATE TABLE trusted_devices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash VARCHAR(64) NOT NULL,  -- SHA-256 hex of the cookie value
  expires_at TIMESTAMPTZ NOT NULL,
  UNIQUE (token_hash)
);
CREATE INDEX ix_trusted_devices_user_id ON trusted_devices(user_id);
```

### password_hash Nullable Migration

The existing `users.password_hash` is `NOT NULL`. OAuth-only users have no password. Two safe approaches:

**Option A (recommended):** Keep `password_hash` NOT NULL but set a sentinel value `''` (empty string) for OAuth-only users. The `verify_password` function will always return `False` for empty hashes, acting as a safe default. Set `password_hash = ''` when creating OAuth-only users.

**Option B:** Make `password_hash` nullable and update all existing users' column to be nullable. Requires a one-time migration `ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL`.

Research supports Option A as simpler: no data migration, existing login code fails safely, argon2 never produces `''` as a hash so there's no collision risk.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth state + PKCE code verifier storage | Custom Redis/DB state tracking | authlib Starlette client + SessionMiddleware | authlib handles state generation, PKCE challenge computation, state verification on callback — all in one `authorize_redirect()` call |
| TOTP code generation and verification | Custom RFC6238 implementation | pyotp.TOTP | RFC6238 is non-trivial (HMAC-SHA1, time-step math, base32 encoding); pyotp is audited and correct |
| QR code image generation | Manual PNG generation | qrcode[pil] | QR encoding is complex (error correction levels, data masking); qrcode implements the full spec |
| Backup code hashing | Custom hash scheme | pwdlib argon2id (already in project) | Argon2id is already the password hashing standard in this codebase; no new dependency needed |
| OAuth provider endpoints | Manually configured URLs | authlib's loginpass GitHub provider pattern (adapt for Starlette) | Google OIDC discovery URL auto-configures all endpoints; GitHub endpoints are well-known but verified |
| CSRF protection for OAuth | Custom nonce/token validation | authlib state parameter (handled automatically) | authlib generates and validates the `state` parameter; do not bypass this |

**Key insight:** OAuth 2.0 with PKCE has many subtle security requirements (state validation, PKCE verifier matching, redirect URI exact matching). authlib handles all of these correctly; hand-rolling exposes the application to authorization code injection and CSRF attacks described in RFC 9700 (January 2025).

---

## Common Pitfalls

### Pitfall 1: GitHub Email Null on Private Profiles
**What goes wrong:** `token['userinfo'].get('email')` returns `None` for GitHub users who have set their email to private. If the code just uses this value, user creation fails or the email stored is null.
**Why it happens:** GitHub's `/user` endpoint omits email from the response when the user's "Keep my email address private" setting is enabled. This is common — GitHub users often keep emails private to avoid spam from automated scrapers.
**How to avoid:** After getting the access token, always make a secondary request to `https://api.github.com/user/emails` and select the entry where `primary=True`. The loginpass GitHub provider does this automatically; the Starlette client must replicate this logic explicitly.
**Warning signs:** New GitHub users failing to complete OAuth signup with a null email error.

### Pitfall 2: SessionMiddleware Secret Key Weakness
**What goes wrong:** If `SessionMiddleware` is added with a hardcoded or weak `secret_key`, session cookies are not cryptographically protected. An attacker could forge OAuth state parameters, bypassing CSRF protection.
**Why it happens:** Examples and tutorials often use `secret_key="some-random-string"` — not suitable for production.
**How to avoid:** Add `SESSION_SECRET_KEY: SecretStr` to Settings in `config.py`. Generate a strong random value (32+ bytes). Never reuse `JWT_PRIVATE_KEY` or `JWT_PUBLIC_KEY` as session secret.
**Warning signs:** Settings validation passes with a weak hardcoded value in production.

### Pitfall 3: PKCE Not Supported by GitHub OAuth Apps (Historical — Now Resolved)
**What goes wrong:** Older documentation states GitHub does not support PKCE for OAuth apps. Attempting to use it would cause authorization failures.
**Why it happens:** GitHub added PKCE support for OAuth Apps in July 2025 (GitHub Changelog). Prior to this, setting `code_challenge_method='S256'` would break GitHub auth.
**How to avoid:** Use authlib 1.6.8 (released February 2026) which is aware of current GitHub capabilities. If testing against an older GitHub Enterprise Server instance, verify PKCE is supported.
**Warning signs:** GitHub OAuth callback returning an error about unsupported `code_challenge`.

### Pitfall 4: TOTP Replay — Same Code Used Twice in One Window
**What goes wrong:** TOTP codes are valid for one 30-second window. If an attacker intercepts a valid code and submits it again within the window, they can authenticate.
**Why it happens:** pyotp's `verify()` does not track used codes by default.
**How to avoid:** After a successful TOTP verification, store the used code (or the timestamp of last successful verification) in Redis with a TTL of 60 seconds (enough to cover the `valid_window=1` range). Reject codes that match the stored "last used" value.
**Warning signs:** No replay detection in TOTP verification path.

Key: `auth:mfa:used:{user_id}` → `{totp_code}:{timestamp}` with TTL 60s.

### Pitfall 5: Linking by Email Instead of Provider User ID
**What goes wrong:** If you link OAuth accounts by matching email, a user who changes their email at Google/GitHub silently loses access to their linked account, or worse — another person with the same email gets linked.
**Why it happens:** Email seems like the natural unique identifier, but OAuth providers use internal numeric/string user IDs that never change.
**How to avoid:** Always link and look up by `(provider, provider_user_id)`. Email is only used to detect a potential conflict with an existing password account (requiring password confirmation to link).
**Warning signs:** `oauth_accounts` table has no `provider_user_id` column or uses email as the FK.

### Pitfall 6: MFA Pending Token Too Long-Lived
**What goes wrong:** A 6-digit TOTP code has 1,000,000 possible values. If the MFA pending token is valid for hours, an attacker with the pending token can brute-force the TOTP offline.
**Why it happens:** Defaulting to session TTL (hours/days) for MFA intermediate state.
**How to avoid:** Set Redis TTL for `auth:mfa_pending:{token}` to 300 seconds (5 minutes). This limits offline brute-force to ~10k guesses if rate limiting is enforced.
**Warning signs:** MFA pending token TTL equal to refresh token TTL.

### Pitfall 7: Tenant Enforcement — Owner Self-Lock
**What goes wrong:** An owner enables MFA enforcement without having MFA set up themselves. Their own session gets revoked and they cannot re-enroll because every login attempt asks for MFA.
**Why it happens:** The enforcement toggle does not check the owner's own MFA status.
**How to avoid:** Before setting `mfa_enforced=True`, verify the actor (owner) has `mfa_enabled=True`. This is a locked decision and must be enforced in the service layer, not just the API layer.
**Warning signs:** No pre-condition check on the enforcement toggle endpoint.

### Pitfall 8: OAuth-Only User Password Reset Flow
**What goes wrong:** The existing `forgot_password` service uses `user.password_hash` as the itsdangerous salt. If `password_hash` is `''` (sentinel for OAuth-only), the salt is effectively empty for all OAuth-only users, weakening the signed token.
**Why it happens:** The existing reset token uses `pw_hash` as a per-user nonce to make tokens single-use.
**How to avoid:** For OAuth-only users (sentinel `password_hash=''`), add a separate `password_reset_nonce` (UUID or random token) column that serves as the salt. Or: allow setting a real password via the reset flow, which itself sets `password_hash` to a valid hash, invalidating the reset token (same single-use mechanism). The latter is the simplest — the password reset flow already works as the recovery mechanism.
**Warning signs:** Reset token signing uses an empty string as salt.

---

## Code Examples

Verified patterns from official sources:

### authlib: Google OAuth Registration with PKCE
```python
# Source: https://docs.authlib.org/en/latest/client/frameworks.html
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
oauth.register(
    "google",
    client_id="...",
    client_secret="...",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
        "code_challenge_method": "S256",  # PKCE; only S256 is supported
    },
)
```

### authlib: GitHub OAuth Registration with PKCE
```python
# Source: https://docs.authlib.org/en/latest/client/frameworks.html
oauth.register(
    "github",
    client_id="...",
    client_secret="...",
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={
        "scope": "user:email",
        "code_challenge_method": "S256",
    },
)
```

### authlib: Redirect and Callback Routes (FastAPI)
```python
# Source: https://docs.authlib.org/en/latest/client/fastapi.html
@router.get("/oauth/{provider}/login")
async def oauth_login(provider: str, request: Request):
    client = oauth.create_client(provider)
    redirect_uri = request.url_for("oauth_callback", provider=provider)
    return await client.authorize_redirect(request, str(redirect_uri))

@router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request, db=Depends(get_session)):
    client = oauth.create_client(provider)
    token = await client.authorize_access_token(request)
    # token contains: access_token, userinfo (Google), etc.
    return await service.handle_oauth_callback(db, provider, token)
```

### pyotp: TOTP Enrollment
```python
# Source: https://pyauth.github.io/pyotp/
import pyotp

secret = pyotp.random_base32()   # "JBSWY3DPEHPK3PXP" — 32-char base32
totp = pyotp.TOTP(secret)

# For QR code
uri = totp.provisioning_uri(name="alice@example.com", issuer_name="WXCODE")
# "otpauth://totp/WXCODE:alice%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=WXCODE"

# For verification (valid_window=1 allows ±30 seconds clock skew)
is_valid = totp.verify("123456", valid_window=1)
```

### pyotp: QR Code Generation
```python
# Source: https://pypi.org/project/qrcode/ (version 8.2, released May 2025)
import qrcode, io, base64

def make_qr_base64(uri: str) -> str:
    img = qrcode.make(uri)  # returns PIL.Image
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
```

### Trusted Device Cookie
```python
# Source: FastAPI docs + common pattern
import secrets, hashlib
from datetime import datetime, timedelta, timezone

def set_trusted_device_cookie(response, user_id: UUID, db: AsyncSession) -> None:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    # Persist to trusted_devices table
    db.add(TrustedDevice(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    ))

    # Set HttpOnly cookie
    response.set_cookie(
        key="wxcode_trusted_device",
        value=token,
        httponly=True,
        secure=True,       # False in dev; True in production
        samesite="lax",
        max_age=30 * 86400,
    )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GitHub OAuth without PKCE | GitHub OAuth with PKCE supported | July 2025 | Can now use `code_challenge_method='S256'` for GitHub; but client_secret is still required (GitHub doesn't distinguish public/confidential clients yet) |
| SMS-based MFA | TOTP-based MFA (RFC 6238) | Industry shift 2020-2023 | SMS is SIM-swappable; TOTP is offline and unphishable |
| OAuth account auto-linking by email | Require password confirmation for linking | RFC 9700 January 2025 best practice | Prevents pre-account takeover via email claim |
| Manual OAuth2 state management | authlib Starlette client handles state automatically | authlib 1.x | Eliminates entire class of OAuth CSRF vulnerabilities |

**Deprecated/outdated:**
- `resource owner password credentials grant` (RFC 9700, January 2025): MUST NOT be used. This project does not use it.
- GitHub PKCE block (pre-July 2025): GitHub OAuth Apps now support PKCE. Old docs saying "PKCE not supported" are outdated.

---

## Open Questions

1. **OAuth-only user email OTP — where is OTP sent?**
   - What we know: The locked decision says OAuth users must still verify email via OTP, even though the OAuth provider already verified it.
   - What's unclear: The OAuth provider gives us the email — we send the OTP to that email. But if it's a new account, the email comes from the provider (trusted). If linking to an existing account, the email is already verified. The OTP requirement may add friction without security value for truly new OAuth users.
   - Recommendation: Still implement as decided (extra security layer). The OTP is sent to the email address from the OAuth provider; user must enter it on the OTP verification screen. Same flow as password signup.

2. **password_hash sentinel value for OAuth-only users**
   - What we know: Option A (sentinel `''`) keeps `password_hash` NOT NULL, simpler migration. Option B (nullable) is cleaner semantically.
   - What's unclear: Whether future code (Phase 7 profile management) will need to distinguish "no password set" vs "password set" — nullable makes this distinction explicit.
   - Recommendation: Use Option B (nullable `password_hash`). Phase 7 adds "set password" feature for OAuth users, so the distinction matters. Migration: `ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL`. Update existing login service to check `password_hash is not None` before calling `verify_password`.

3. **trusted_devices — per-tenant or global?**
   - What we know: The decision says "per-tenant trust evaluation" — a device trusted in one tenant is NOT trusted in an enforcing tenant.
   - What's unclear: Whether to store `tenant_id` on the `trusted_devices` table or compute trust at request time by checking the requested tenant's `mfa_enforced` flag.
   - Recommendation: Store trusted_devices without `tenant_id` — trust is global (device is trusted for the user). At login time, when the user selects a tenant, check if that tenant has `mfa_enforced=True`. If yes, ignore the trusted device cookie and require TOTP for that session. The cookie persists and is honored in non-enforcing tenants. No schema change needed.

4. **MFA secret encryption at rest**
   - What we know: TOTP secrets must be retrievable (they cannot be hashed like passwords). Storing them as plaintext in the DB is the common approach but not ideal.
   - What's unclear: Whether to encrypt TOTP secrets with a server-side key from settings.
   - Recommendation: Store as plaintext VARCHAR for Phase 6 (consistent with how other secrets are handled in this project — secrets come from env vars, not DB-level encryption). Flag as a known security trade-off. Phase 7+ could add at-rest encryption if needed.

---

## Sources

### Primary (HIGH confidence)
- Authlib official docs (https://docs.authlib.org/en/latest/client/frameworks.html) — PKCE configuration, OAuth registration API
- Authlib official docs (https://docs.authlib.org/en/latest/client/fastapi.html) — FastAPI/Starlette OAuth client
- Authlib official docs (https://docs.authlib.org/en/latest/client/starlette.html) — SessionMiddleware requirement, async routes
- pyotp official docs (https://pyauth.github.io/pyotp/) — TOTP class API, valid_window parameter, provisioning_uri
- GitHub official docs (https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps) — user:email scope
- loginpass GitHub source (https://github.com/authlib/loginpass/blob/master/loginpass/github.py) — private email fallback pattern
- PyPI qrcode (https://pypi.org/project/qrcode/) — version 8.2, released May 2025, Python >= 3.9

### Secondary (MEDIUM confidence)
- GitHub Changelog (https://github.blog/changelog/2025-07-14-pkce-support-for-oauth-and-github-app-authentication/) — GitHub OAuth PKCE support added July 2025
- RFC 9700 (https://datatracker.ietf.org/doc/rfc9700/) — OAuth 2.0 security best practices, January 2025; no auto-link by email alone
- authlib GitHub README (https://github.com/authlib/authlib) — version 1.6.8 confirmed February 14, 2026
- PyPI pyotp (https://pypi.org/project/pyotp/) — version 2.9.0, July 2023; stable

### Tertiary (LOW confidence)
- General pattern for backup code count (10 codes): cross-referenced from GitHub/Google account pages — industry convention, no single authoritative RFC
- TOTP replay prevention via Redis last-used token: common implementation pattern found across multiple articles; no authoritative single source

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions confirmed from PyPI, GitHub, official docs; authlib 1.6.8 confirmed Feb 14 2026
- Architecture: MEDIUM-HIGH — patterns verified from official authlib and pyotp docs; DB schema based on codebase conventions
- Pitfalls: HIGH for GitHub email null (verified from loginpass source); HIGH for SessionMiddleware requirement (official docs); MEDIUM for replay prevention (common pattern)

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (30 days — authlib and pyotp are stable; GitHub PKCE support confirmed recent)
