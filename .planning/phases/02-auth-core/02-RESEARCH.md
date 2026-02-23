# Phase 2: Auth Core - Research

**Researched:** 2026-02-22
**Domain:** JWT RS256 authentication, email verification OTP, password hashing, refresh token rotation, Redis blacklist, itsdangerous signed links, JWKS endpoint, FastAPI auth dependencies
**Confidence:** HIGH (library versions verified against PyPI; patterns verified against official docs and FastAPI official documentation)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Token lifecycle
- Access token TTL: 24 hours
- Refresh token TTL: 7 days
- Single session policy: new login revokes all previous sessions (one device at a time)
- Refresh rotation: immediate revoke — old refresh token is invalidated the moment a new one is issued; replay detection triggers full logout

#### Email verification
- 6-digit code expires in 10 minutes
- Max 3 wrong attempts — code invalidated after 3 failures, user must request a new one
- Unverified users are fully blocked — can only verify email or resend code, no other endpoint access

#### Password reset
- Reset link expires in 24 hours
- Single-use enforcement (itsdangerous signed token, consumed on use)
- After successful reset: revoke ALL sessions (force re-login everywhere)
- Non-existent email returns same success response ("check your email") — prevents email enumeration

### Claude's Discretion
- Resend verification code cooldown (reasonable anti-abuse interval)
- Password reset request rate limit (reasonable anti-flooding interval)
- Error response format and HTTP status codes for auth failures
- RSA key size and rotation strategy for JWKS

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | User can sign up with email and password | pwdlib/argon2 for hashing; User model with email_verified=False; arq job enqueue for verification email |
| AUTH-02 | User receives 6-digit verification code by email after signup | arq task dispatches email via aiosmtplib/fastapi-mail; 6-digit code stored in Redis with 10min TTL; attempt counter as separate Redis key |
| AUTH-03 | User can verify email entering the 6-digit code | Redis lookup + attempt tracking; on success set email_verified=True in DB; on 3 failures delete code forcing resend |
| AUTH-04 | User can reset password via email link | itsdangerous URLSafeTimedSerializer with 24h max_age; single-use by deleting/marking token consumed; revoke all sessions on success |
| AUTH-05 | User receives JWT RS256 access token + refresh token on login | PyJWT 2.11.0 with RS256; refresh token stored in DB as UUID; access token signed with private key loaded from settings |
| AUTH-06 | Refresh token rotation with revocation on logout | RefreshToken DB table per user; on rotate: delete old token row, insert new; on logout: delete token row; on replay: delete ALL user tokens |
| AUTH-07 | JWKS endpoint exposes public key for wxcode to validate tokens locally | PyJWT RSAAlgorithm.to_jwk() converts loaded public key to JWK JSON; serve at /.well-known/jwks.json with kid in JWT header |
</phase_requirements>

---

## Summary

Phase 2 implements a complete email/password authentication system on top of the Phase 1 infrastructure. The implementation is straightforward because the technology decisions are already locked from prior research: PyJWT for RS256, pwdlib/argon2 for hashing, arq for background email tasks, itsdangerous for signed reset links, and slowapi for rate limiting.

The most architecturally significant piece is the **refresh token storage strategy**. Because the system requires single-session-per-user enforcement and replay detection, refresh tokens must be stateful: stored in the database as individual rows tied to a user. Redis blacklisting alone is insufficient for the rotation pattern because: (a) the old token must be immediately invalid (not just short-lived), and (b) replay detection requires knowing whether a token was already consumed, which needs a record of what was issued. The simplest correct implementation stores refresh tokens as DB rows, deletes on rotation (immediate revocation), and deletes all rows on replay detection (full logout).

The JWKS endpoint is the integration point with wxcode. By serving the RSA public key at `/.well-known/jwks.json`, wxcode can validate tokens without calling wxcode-adm on every request. PyJWT provides `RSAAlgorithm.to_jwk()` for this conversion. The `kid` claim in the JWT header pairs each token with a specific key, enabling future key rotation without invalidating in-flight tokens.

**Primary recommendation:** Implement in plan order — (02-01) RSA/JWT infrastructure + JWKS, (02-02) signup + email verification, (02-03) login + refresh rotation + logout, (02-04) password reset flow, (02-05) FastAPI auth dependencies + integration tests. Each plan is independently testable and unblocks the next.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyJWT | 2.11.0 | JWT RS256 sign + verify | Official Python JWT library; python-jose has known CVEs and is unmaintained; released 2026-01-30 |
| cryptography | 46.0.5 | RSA key ops (required by PyJWT[crypto]) | PyJWT dependency for RSA algorithms; provides key serialization and JWK conversion |
| pwdlib[argon2] | 0.3.0 | Argon2 password hashing | Replaces passlib (broken on Python 3.13); Argon2id is OWASP recommended algorithm; adopted by FastAPI official docs |
| itsdangerous | 2.2.0 | Signed timed URL tokens for password reset | Pallets project (Flask ecosystem); URLSafeTimedSerializer + max_age for expiry |
| slowapi | 0.1.9 | Rate limiting for auth endpoints | Decided in prior research over fastapi-limiter (unmaintained since 2023) |
| fastapi-mail | 1.6.2 | Email sending (verification, password reset) | Async-native; supports SMTP; works with arq by calling its async send from within arq jobs; released 2026-02-17 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| aiosmtplib | 5.1.0 | Lower-level async SMTP (fastapi-mail dependency) | Used transitively by fastapi-mail; can be used directly if fastapi-mail overhead undesired |
| redis (redis-py) | 5.3.1 | OTP code storage + rate limit state (already in stack) | Existing Phase 1 dependency; used for email verification codes and attempt counters |
| arq | 0.27.0 | Background email dispatch (already in stack) | Existing Phase 1 dependency; email sends happen in arq jobs, not request handlers |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyJWT | python-jose | python-jose has CVEs (GHSA-cjwg-qfpm-7377), last release 2022; PyJWT is actively maintained |
| pwdlib/argon2 | passlib/bcrypt | passlib uses deprecated `crypt` module removed in Python 3.13; pwdlib is the official replacement |
| DB rows for refresh tokens | Redis only for refresh tokens | Redis-only loses single-session enforcement on Redis restart; DB rows survive restarts and support complex queries (revoke by user, replay detection) |
| fastapi-mail | aiosmtplib directly | fastapi-mail adds template support and connection management; aiosmtplib is fine for simple transactional email |
| itsdangerous | DB-stored reset tokens (UUID) | Both work; itsdangerous avoids a DB row per reset request; single-use is implemented by consuming the token on verification |

**Installation (additions to pyproject.toml):**
```bash
pip install "PyJWT[crypto]==2.11.0" "pwdlib[argon2]==0.3.0" "itsdangerous==2.2.0" "slowapi==0.1.9" "fastapi-mail==1.6.2"
```

---

## Architecture Patterns

### Recommended Module Structure

```
backend/src/wxcode_adm/
├── auth/
│   ├── __init__.py
│   ├── models.py          # User, RefreshToken SQLAlchemy models
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── router.py          # FastAPI router: /auth/* endpoints
│   ├── service.py         # Business logic: signup, login, refresh, logout, verify, reset
│   ├── dependencies.py    # get_current_user, require_verified FastAPI Depends
│   ├── jwt.py             # create_access_token, decode_token, load_rsa_keys
│   ├── jwks.py            # public_key_to_jwk(), JWKS response builder
│   ├── email.py           # arq job functions: send_verification_email, send_reset_email
│   └── seed.py            # seed_super_admin() called from main.py lifespan
├── common/
│   ├── router.py          # health endpoint (Phase 1)
│   └── ...
└── ...
```

### Pattern 1: RSA Key Loading and JWT Signing

**What:** Load RSA PEM keys from pydantic settings at startup. Sign tokens with private key; verify with public key.

**When to use:** Every access token creation and every protected endpoint.

```python
# Source: PyJWT 2.11.0 official docs (pyjwt.readthedocs.io/en/latest/usage.html)
import jwt
from datetime import datetime, timedelta, timezone

def create_access_token(payload: dict, private_key: str, ttl_hours: int = 24) -> str:
    """Sign a JWT with RS256 using the RSA private key."""
    to_encode = payload.copy()
    to_encode.update({
        "exp": datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        "iat": datetime.now(timezone.utc),
        "kid": "current-key-id",  # matches JWKS kid
    })
    return jwt.encode(to_encode, private_key, algorithm="RS256")

def decode_access_token(token: str, public_key: str) -> dict:
    """Verify and decode a JWT using the RSA public key."""
    return jwt.decode(token, public_key, algorithms=["RS256"])
    # Raises jwt.ExpiredSignatureError, jwt.InvalidTokenError on failure
```

### Pattern 2: JWKS Endpoint

**What:** Convert the RSA public key to JWK format and serve at `/.well-known/jwks.json`. wxcode uses this to validate tokens without calling wxcode-adm.

**When to use:** `GET /.well-known/jwks.json` endpoint (no auth required).

```python
# Source: PyJWT 2.11.0 — RSAAlgorithm.to_jwk() converts public key to JWK JSON string
import json
import jwt
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

def public_key_to_jwk(public_key_pem: str, kid: str = "current-key-id") -> dict:
    """Convert RSA public key PEM to JWK dict for JWKS endpoint."""
    algo = RSAAlgorithm(RSAAlgorithm.SHA256)
    # Load the public key object
    public_key = serialization.load_pem_public_key(
        public_key_pem.encode(), backend=default_backend()
    )
    # to_jwk returns a JSON string representation
    jwk_str = algo.to_jwk(public_key)
    jwk_dict = json.loads(jwk_str)
    # Add standard JWKS fields
    jwk_dict.update({"use": "sig", "alg": "RS256", "kid": kid})
    return jwk_dict

def build_jwks_response(public_key_pem: str) -> dict:
    """Build the full JWKS response body."""
    return {"keys": [public_key_to_jwk(public_key_pem)]}
```

### Pattern 3: Password Hashing with pwdlib/argon2

**What:** Hash passwords on signup; verify on login.

```python
# Source: pwdlib 0.3.0 official docs (pypi.org/project/pwdlib)
from pwdlib import PasswordHash

# Module-level singleton — configured once
password_hash = PasswordHash.recommended()  # Uses Argon2id by default

def hash_password(plain: str) -> str:
    return password_hash.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)
```

### Pattern 4: Email Verification Code (Redis)

**What:** Store 6-digit OTP in Redis with 10-minute TTL. Track attempt count in a separate Redis key. On 3 failures, delete both keys forcing the user to request a new code. On success, delete both keys.

**Redis key schema:**
```
auth:otp:{user_id}         → "123456"     (TTL: 600 seconds)
auth:otp:attempts:{user_id} → "0"/"1"/"2" (TTL: 600 seconds, matches OTP)
auth:otp:cooldown:{user_id} → "1"          (TTL: 60 seconds — resend cooldown)
```

```python
# Source: redis-py 5.3.1 (already in stack)
import secrets
from redis.asyncio import Redis

async def create_verification_code(redis: Redis, user_id: str) -> str:
    code = str(secrets.randbelow(900000) + 100000)  # 100000–999999
    await redis.set(f"auth:otp:{user_id}", code, ex=600)        # 10 minutes
    await redis.set(f"auth:otp:attempts:{user_id}", "0", ex=600)
    await redis.set(f"auth:otp:cooldown:{user_id}", "1", ex=60)  # 1 min cooldown
    return code

async def verify_code(redis: Redis, user_id: str, submitted: str) -> bool:
    stored = await redis.get(f"auth:otp:{user_id}")
    if stored is None:
        return False  # Expired or never issued
    attempts = int(await redis.get(f"auth:otp:attempts:{user_id}") or "0")
    if attempts >= 3:
        await redis.delete(f"auth:otp:{user_id}", f"auth:otp:attempts:{user_id}")
        return False  # Invalidated — force resend
    if submitted != stored:
        await redis.incr(f"auth:otp:attempts:{user_id}")
        return False
    # Correct — clean up
    await redis.delete(f"auth:otp:{user_id}", f"auth:otp:attempts:{user_id}")
    return True
```

### Pattern 5: itsdangerous Password Reset Token

**What:** Sign user email + current password hash into a URL-safe timed token. Single-use is enforced because changing the password invalidates the token (the password hash embedded in the salt changes).

```python
# Source: itsdangerous 2.2.0 official docs (itsdangerous.palletsprojects.com)
from itsdangerous import URLSafeTimedSerializer
from itsdangerous.exc import SignatureExpired, BadSignature

def make_reset_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="password-reset")

def generate_reset_token(serializer: URLSafeTimedSerializer, email: str, pw_hash: str) -> str:
    """Generate a signed token. pw_hash is embedded as extra salt for single-use."""
    return serializer.dumps(email, salt=pw_hash)

def verify_reset_token(
    serializer: URLSafeTimedSerializer,
    token: str,
    pw_hash: str,
    max_age: int = 86400,  # 24 hours
) -> str:
    """Returns email on success. Raises SignatureExpired or BadSignature on failure."""
    return serializer.loads(token, salt=pw_hash, max_age=max_age)
```

**Key insight:** The user's current `password_hash` is used as the `salt` when signing. When the password is reset, the hash changes, making the token cryptographically invalid. This is the standard single-use enforcement pattern without requiring a DB row per token.

### Pattern 6: Refresh Token Rotation with DB Storage

**What:** Refresh tokens are stored as DB rows. On rotation: delete old row + insert new row in one transaction. On replay (token already deleted): delete ALL rows for that user (full logout).

**Database model:**
```python
# SQLAlchemy 2.0 — NOT a TenantModel (refresh tokens are platform-level auth, not tenant-scoped)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, String
import uuid

class RefreshToken(TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # No tenant_id — auth is platform-wide
```

**Rotation logic:**
```python
async def rotate_refresh_token(db: AsyncSession, old_token: str, user_id: uuid.UUID) -> str:
    # Fetch old token row
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token == old_token))
    if row is None:
        # REPLAY DETECTED — delete all user sessions
        await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
        raise ReplayDetectedError("Refresh token already consumed — all sessions revoked")
    if row.user_id != user_id:
        raise ForbiddenError(...)
    # Atomically: delete old, insert new
    await db.delete(row)
    new_token = secrets.token_urlsafe(32)
    db.add(RefreshToken(token=new_token, user_id=user_id, expires_at=...))
    return new_token  # session commit handled by get_session dependency
```

### Pattern 7: FastAPI Auth Dependencies

**What:** `get_current_user` extracts and validates JWT from Bearer header. `require_verified` adds email verification check.

```python
# Source: FastAPI official docs — oauth2-jwt pattern (fastapi.tiangolo.com/tutorial/security/oauth2-jwt)
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = decode_access_token(token, settings.JWT_PUBLIC_KEY.get_secret_value())
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise credentials_exception
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise credentials_exception
    return user

async def require_verified(user: User = Depends(get_current_user)) -> User:
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "EMAIL_NOT_VERIFIED", "message": "Email verification required"},
        )
    return user
```

### Pattern 8: slowapi Rate Limiting Setup

**What:** Apply rate limits to auth endpoints to prevent abuse. Per-IP limiting with Redis backend for distributed rate limit state.

```python
# Source: slowapi 0.1.9 official docs (slowapi.readthedocs.io)
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,  # Redis backend for distributed state
)

# In create_app():
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# On individual endpoints:
@router.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, ...):
    ...
```

**Recommended rate limits (Claude's Discretion):**
- `POST /auth/signup` — 5/minute per IP (prevent mass account creation)
- `POST /auth/login` — 10/minute per IP (credential stuffing protection)
- `POST /auth/verify-email` — 5/minute per IP (OTP guessing)
- `POST /auth/resend-verification` — 2/minute per IP (anti-spam)
- `POST /auth/forgot-password` — 3/minute per IP (prevent enumeration-by-timing)
- `POST /auth/reset-password` — 5/minute per IP

### Pattern 9: arq Email Job Dispatch

**What:** Email sends happen in arq background jobs, not in the request handler. FastAPI endpoint enqueues the job; arq worker executes it.

```python
# In API endpoint (request handler):
async def signup_endpoint(body: SignupRequest, db: AsyncSession = Depends(get_session)):
    user = await service.create_user(db, body)
    # Enqueue email job — do NOT block the response
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job("send_verification_email", str(user.id), user.email, code)
    finally:
        await pool.aclose()
    return {"message": "Check your email for a verification code"}

# In auth/email.py (arq job):
async def send_verification_email(ctx: dict, user_id: str, email: str, code: str) -> None:
    """arq job: sends verification code email."""
    # Use fastapi-mail or aiosmtplib directly
    ...

# In tasks/worker.py — add to WorkerSettings.functions:
from wxcode_adm.auth.email import send_verification_email, send_reset_email
class WorkerSettings:
    functions = [test_job, send_verification_email, send_reset_email]
    ...
```

### Anti-Patterns to Avoid

- **Storing refresh tokens only in Redis:** Redis data is volatile. On restart without persistence, all tokens appear to never have existed, and replay detection becomes impossible. Use DB rows for refresh tokens.
- **Not including `kid` in JWT header:** Without `kid`, key rotation requires coordinated downtime. Always set `kid` matching the JWKS entry.
- **Checking `email_verified` only in business logic:** The `require_verified` dependency must run BEFORE any data modification. Do not gate it conditionally in service code.
- **Using `datetime.utcnow()` for JWT `exp`:** PyJWT requires timezone-aware datetimes. Use `datetime.now(timezone.utc)`.
- **Storing plaintext OTP in Redis:** For a 6-digit numeric code, hashing is not strictly required (the search space is 1M entries, and the 10-minute TTL plus 3-attempt limit provide sufficient protection). Storing plaintext is acceptable here. Do NOT hash if it adds complexity without proportional security gain.
- **Allowing `alg: none` in JWT decode:** Always pass `algorithms=["RS256"]` explicitly. Never trust the `alg` header from the token.
- **Using `email` as the JWT `sub` claim:** Use `user_id` (UUID string) as `sub`. Email can change; UUIDs are stable identifiers.
- **Sending email synchronously in request handlers:** Always enqueue to arq. Email sending can take 1-3 seconds and fails unpredictably — the HTTP response must not depend on it.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT signing/verification | Custom HMAC or RSA signing | PyJWT 2.11.0 | Token expiry, algorithm confusion attacks, JWK conversion all handled |
| Password hashing | bcrypt or custom KDF | pwdlib[argon2] | Argon2id memory-hardness prevents GPU attacks; rehashing on verify handles algorithm upgrades |
| Signed reset tokens | DB table of UUIDs + expiry | itsdangerous URLSafeTimedSerializer | Stateless; tamper-proof; automatic expiry via max_age; single-use via pw_hash salt |
| Rate limiting | IP counting in Redis manually | slowapi | Handles distributed state, multiple backends, decorator API |
| JWKS public key export | Manual base64url encoding of RSA modulus/exponent | PyJWT RSAAlgorithm.to_jwk() | RSA JWK format has subtle encoding requirements (base64url without padding) |

**Key insight:** The auth domain is where custom implementations cause the most security incidents. Every item in this table has subtle edge cases (timing attacks, algorithm confusion, token replay) that the listed libraries handle correctly.

---

## Common Pitfalls

### Pitfall 1: RefreshToken as TenantModel
**What goes wrong:** Placing RefreshToken inside a TenantModel subclass causes TenantIsolationError on every token lookup because auth queries intentionally don't carry a tenant context — they're cross-tenant platform operations.
**Why it happens:** The tenant guard (`install_tenant_guard`) raises on any SELECT against a TenantModel subclass without `_tenant_enforced=True`. Auth service code doesn't set this option.
**How to avoid:** RefreshToken and User models must inherit from `TimestampMixin, Base` directly — NOT from `TenantModel`. Tenant context enters later (Phase 3) when fetching tenant-scoped resources.
**Warning signs:** `TenantIsolationError` raised during login/refresh tests.

### Pitfall 2: Access Token TTL of 24h Requires Redis Blacklist for Logout
**What goes wrong:** With a 24-hour access token and no blacklist, a logged-out user's access token remains valid for up to 24 hours after logout.
**Why it happens:** JWT access tokens are stateless — logout only revokes the refresh token in DB, but the access token is still cryptographically valid.
**How to avoid:** On logout, store the access token's `jti` (JWT ID) in Redis with TTL equal to the remaining token lifetime. The `get_current_user` dependency must check the blacklist. Add a unique `jti` claim (UUID) to every access token at creation time.
**Redis key schema:** `auth:blacklist:jti:{jti}` → `"1"` (TTL: remaining seconds until token expiry)
**Warning signs:** User can still hit protected endpoints after logout within the 24h window.

### Pitfall 3: itsdangerous Single-Use Not Automatic
**What goes wrong:** itsdangerous URLSafeTimedSerializer does NOT prevent reuse by itself. The same token can be submitted multiple times within the expiry window.
**Why it happens:** The library just checks the signature and timestamp — it has no concept of "consumed".
**How to avoid:** Use the current `password_hash` as the `salt` when calling `dumps()` and `loads()`. As soon as the password is changed, the stored hash changes, making the old token's signature invalid. This is the canonical single-use pattern for this library.
**Warning signs:** Same reset link works twice in tests.

### Pitfall 4: Single-Session Policy Requires Revoke-All on New Login
**What goes wrong:** If new login only creates a new refresh token row without deleting existing ones, the user has multiple valid sessions.
**Why it happens:** Missing "delete existing refresh tokens for this user" step before inserting new token on login.
**How to avoid:** Login service must: (1) DELETE all existing RefreshToken rows for the user, (2) INSERT new RefreshToken row. Do both in the same transaction.
**Warning signs:** User can login from two devices and both sessions remain valid.

### Pitfall 5: slowapi Requires `request: Request` Parameter in Endpoints
**What goes wrong:** `RateLimitExceeded` is never raised; rate limiting silently doesn't work.
**Why it happens:** slowapi reads the `Request` object to extract the client IP. If the endpoint signature doesn't include `request: Request`, slowapi cannot inject the rate limit check.
**How to avoid:** Every rate-limited endpoint MUST include `request: Request` as a parameter.
**Warning signs:** `@limiter.limit()` decorator applied but limits never enforced in tests.

### Pitfall 6: Unverified User Blocked Endpoints
**What goes wrong:** Blocking unverified users at the endpoint level with `require_verified` must cover ALL endpoints except the explicit allowlist: `POST /auth/verify-email`, `POST /auth/resend-verification`.
**Why it happens:** Forgetting to add `require_verified` dependency to new endpoints.
**How to avoid:** Apply `require_verified` as a router-level dependency using `router = APIRouter(dependencies=[Depends(require_verified)])` for all protected routers. Explicitly exclude the verification endpoints which use `get_current_user` (not `require_verified`).

### Pitfall 7: JWKS kid Mismatch
**What goes wrong:** wxcode fails to verify tokens with "kid not found in JWKS" error after key rotation.
**Why it happens:** The `kid` value in the JWT header doesn't match the `kid` value in the JWKS response.
**How to avoid:** Define `kid` as a constant (e.g., `"v1"` or a hash of the public key). Embed it in both `jwt.encode()` headers and the JWKS response. Use the same constant in both places.

---

## Code Examples

Verified patterns from official sources:

### RS256 Token with kid and jti Claims

```python
# Source: PyJWT 2.11.0 (pyjwt.readthedocs.io/en/latest/usage.html)
import uuid
import jwt
from datetime import datetime, timedelta, timezone

def create_access_token(
    user_id: str,
    private_key_pem: str,
    ttl_hours: int = 24,
    kid: str = "v1",
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=ttl_hours),
        "jti": str(uuid.uuid4()),  # For logout blacklist
        "kid": kid,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": kid})
```

### JWKS Response Generation

```python
# Source: PyJWT RSAAlgorithm.to_jwk (jwt.algorithms.RSAAlgorithm)
import json
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.backends import default_backend

def build_jwks(public_key_pem: str, kid: str = "v1") -> dict:
    pub_key = load_pem_public_key(public_key_pem.encode(), backend=default_backend())
    algo = RSAAlgorithm(RSAAlgorithm.SHA256)
    jwk_str = algo.to_jwk(pub_key)
    jwk_dict = json.loads(jwk_str)
    jwk_dict.update({"use": "sig", "alg": "RS256", "kid": kid})
    return {"keys": [jwk_dict]}
```

### Password Hashing (pwdlib)

```python
# Source: pwdlib 0.3.0 (pypi.org/project/pwdlib)
from pwdlib import PasswordHash

pwd_context = PasswordHash.recommended()  # Argon2id

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

### itsdangerous Reset Token (single-use via pw_hash salt)

```python
# Source: itsdangerous 2.2.0 (itsdangerous.palletsprojects.com/en/latest/url_safe/)
from itsdangerous import URLSafeTimedSerializer
from itsdangerous.exc import SignatureExpired, BadSignature

serializer = URLSafeTimedSerializer(secret_key="...", salt="password-reset")

# Generate — pw_hash is the user's CURRENT Argon2 hash
token = serializer.dumps(user.email, salt=user.password_hash)

# Verify — pass the SAME pw_hash that was current when token was generated
# After password change, pw_hash differs → BadSignature automatically raised
try:
    email = serializer.loads(token, salt=current_pw_hash, max_age=86400)  # 24h
except SignatureExpired:
    raise ...  # Token expired
except BadSignature:
    raise ...  # Invalid or already consumed (pw changed)
```

### slowapi Rate Limiting Setup

```python
# Source: slowapi 0.1.9 (slowapi.readthedocs.io)
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",
)

# In create_app():
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# On endpoint:
@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, ...):
    # request: Request MUST be present for slowapi to work
    ...
```

### Access Token Blacklist on Logout

```python
# Source: Redis pattern — store jti with TTL matching remaining token lifetime
import jwt as pyjwt
from datetime import datetime, timezone
from redis.asyncio import Redis

async def blacklist_access_token(redis: Redis, token: str, public_key: str) -> None:
    """Add access token's jti to Redis blacklist until it expires."""
    payload = pyjwt.decode(token, public_key, algorithms=["RS256"])
    jti = payload["jti"]
    exp = payload["exp"]
    remaining_seconds = int(exp - datetime.now(timezone.utc).timestamp())
    if remaining_seconds > 0:
        await redis.set(f"auth:blacklist:jti:{jti}", "1", ex=remaining_seconds)

async def is_token_blacklisted(redis: Redis, jti: str) -> bool:
    return await redis.exists(f"auth:blacklist:jti:{jti}") > 0
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| passlib/bcrypt for hashing | pwdlib[argon2] | Python 3.13 (2024) | passlib uses deprecated `crypt` module; removed in 3.13 |
| python-jose for JWT | PyJWT | 2022+ (CVEs) | python-jose has active CVEs; PyJWT is maintained by the JWT community |
| HS256 (symmetric) JWT | RS256 (asymmetric) JWT | Ongoing | RS256 enables JWKS — validators don't need the secret key |
| Manual Redis token blacklist | jti claim + Redis TTL | Ongoing | Auto-expiry via TTL avoids accumulation of stale blacklist entries |
| DB-stored reset tokens | itsdangerous signed tokens | Flask ecosystem pattern | Stateless; no DB row per reset request; automatic expiry |
| `datetime.utcnow()` | `datetime.now(timezone.utc)` | Python 3.12+ | `utcnow()` deprecated; PyJWT strict on timezone-aware datetimes |

**Deprecated/outdated:**
- `passlib`: Broken on Python 3.13 due to `crypt` module removal
- `python-jose`: CVE-2024-33664, CVE-2024-33663; last release 2022; avoid entirely
- `fastapi-jwt-auth`: Abandoned; do not use
- `fastapi-limiter`: Last commit 2023; no active maintenance; use slowapi instead

---

## Decisions Required (Claude's Discretion)

### RSA Key Size
**Recommendation: 2048 bits**
- NIST SP 800-131A: 2048-bit RSA provides 112 bits of security, acceptable through 2030
- 4096-bit provides more margin but has ~4x computational overhead for signing
- For a SaaS with 24h access tokens and planned key rotation, 2048-bit is the pragmatic choice
- Keys are generated once and stored as environment variables

### RSA Key Rotation Strategy
**Recommendation: Static single key for Phase 2; rotation deferred**
- Phase 2 serves a single `kid: "v1"` key in JWKS
- Rotation mechanism: add a second key to JWKS, update new token signing to use `kid: "v2"`, retire `kid: "v1"` after max(access_token_TTL) = 24h
- No code changes required for rotation if `kid` is used correctly — wxcode resolves by `kid` lookup in JWKS

### Resend Verification Cooldown
**Recommendation: 60 seconds**
- Stored as a Redis key with 60s TTL: `auth:otp:cooldown:{user_id}`
- Reject resend request if cooldown key exists (return 429 with time-remaining)
- Balance: short enough to not frustrate users; long enough to prevent email flooding

### Password Reset Rate Limit
**Recommendation: 3 requests per hour per IP**
- Implemented via slowapi: `@limiter.limit("3/hour")`
- Constant-time response whether email exists or not (prevents enumeration)

### Error Response Format
**Recommendation: Match existing `AppError` format**
The existing `app_error_handler` in `main.py` produces:
```json
{"error_code": "AUTH_INVALID_CREDENTIALS", "message": "Invalid email or password"}
```
Auth errors should raise domain exceptions inheriting from `AppError`:
- `AuthError(AppError)` — base; status 401
- `EmailNotVerifiedError(AppError)` — status 403
- `InvalidCredentialsError(AuthError)` — status 401; MUST use same message for wrong email AND wrong password
- `TokenExpiredError(AuthError)` — status 401
- `InvalidTokenError(AuthError)` — status 401

---

## Open Questions

1. **SMTP provider for Phase 2**
   - What we know: fastapi-mail supports SMTP; we need a mail host for dev and prod
   - What's unclear: Whether the project has a preferred provider (SendGrid, Mailgun, etc.) or will use SMTP relay
   - Recommendation: For development, use Mailpit (local SMTP mock, Docker image `axllent/mailpit`). For production, add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` to pydantic settings. The plan should stub out settings and leave SMTP config as a deployment concern.

2. **User model ownership**
   - What we know: The `users/` directory exists but is empty. User model needs to go somewhere.
   - What's unclear: Whether User lives in `auth/` or `users/`
   - Recommendation: User model in `auth/models.py` for Phase 2 (tightly coupled to auth). In Phase 3+ when tenant-user relationships are needed, `users/` can extend or reference it. This avoids circular imports between `auth/` and `users/`.

3. **Super-admin seed timing**
   - What we know: `main.py` has a Phase 2 stub comment: `await seed_super_admin(async_session_maker, settings)`
   - What's unclear: Whether super-admin is a tenant user or a platform user (no tenant_id)
   - Recommendation: Super-admin has `tenant_id = None` (platform user). The User model must support nullable `tenant_id` OR super-admin is excluded from TenantModel entirely. Given the guard behavior, User should NOT be a TenantModel subclass — user auth is platform-level.

---

## Sources

### Primary (HIGH confidence)
- PyJWT 2.11.0 official docs (pyjwt.readthedocs.io/en/latest/usage.html) — RS256 signing/verification, PyJWKClient
- PyPI: PyJWT 2.11.0 (released 2026-01-30) — version verified
- PyPI: pwdlib 0.3.0 (released 2025-10-25) — version, Argon2 support verified
- PyPI: itsdangerous 2.2.0 (released 2024-04-16) — version verified
- PyPI: slowapi 0.1.9 (released 2024-02-05) — version verified
- PyPI: fastapi-mail 1.6.2 (released 2026-02-17) — version verified
- PyPI: cryptography 46.0.5 (released 2026-02-10) — version verified
- slowapi official docs (slowapi.readthedocs.io) — setup pattern, limiter.limit decorator
- itsdangerous official docs (itsdangerous.palletsprojects.com/en/latest/url_safe/) — URLSafeTimedSerializer API
- FastAPI official docs — OAuth2 JWT pattern (fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) — get_current_user, pwdlib usage
- arq 0.27.0 official docs (arq-docs.helpmanual.io) — enqueue_job, WorkerSettings, context dict

### Secondary (MEDIUM confidence)
- NIST SP 800-131A — RSA 2048-bit key size recommendation through 2030 (multiple sources corroborate)
- PyJWT RSAAlgorithm.to_jwk() for JWKS endpoint construction (snyk.io verified, multiple sources agree)
- Redis jti blacklist pattern for logout with TTL (multiple blog posts, consistent pattern)
- itsdangerous pw_hash-as-salt for single-use reset tokens (multiple Flask ecosystem references)

### Tertiary (LOW confidence)
- None — all critical claims have been verified with official sources

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against PyPI as of 2026-02-22
- Architecture: HIGH — patterns drawn from official FastAPI, PyJWT, arq, itsdangerous, slowapi docs
- Pitfalls: HIGH — tenant guard pitfall verified from Phase 1 code; others from official docs and well-established patterns
- RSA key size recommendation: HIGH — NIST SP 800-131A corroborated by multiple sources

**Research date:** 2026-02-22
**Valid until:** 2026-03-22 (stable libraries; check PyJWT, fastapi-mail for patch releases)
