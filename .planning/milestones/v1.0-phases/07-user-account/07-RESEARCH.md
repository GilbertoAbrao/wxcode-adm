# Phase 7: User Account - Research

**Researched:** 2026-02-25
**Domain:** FastAPI user profile management, session metadata, Redis token operations, IP geolocation, one-time code exchange
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Session visibility
- Rich session metadata: IP address, device type (Desktop/Mobile/Tablet), browser name/version, and approximate city from IP geolocation
- "Last active" updated on every authenticated API request (Redis write per request)
- Session revocation is immediate: blacklist active access tokens in Redis so revoked sessions are rejected within seconds
- Current session is tagged as "Current session" in the list to prevent accidental self-revocation

#### wxcode redirect
- One-time code exchange pattern: after login, redirect to wxcode with a short-lived authorization code; wxcode backend exchanges the code for the JWT via a server-to-server call — token never appears in URL
- wxcode application URL is a per-tenant setting stored in the database — allows custom domains / whitelabel
- Multi-tenant users auto-redirect to their last-used or primary tenant's wxcode URL after login; tenant switching happens from within wxcode

### Claude's Discretion
- Profile fields and avatar handling (upload storage, size limits, validation)
- Password change session behavior (which other sessions to invalidate)
- Email change re-verification flow
- One-time code TTL (recommend 30-60 seconds based on security best practices)
- How "default tenant" is determined (last-used vs primary vs most recent membership)
- IP geolocation approach (library or service choice)
- User-Agent parsing strategy for device/browser extraction

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| USER-01 | User can view and edit profile (name, email, avatar) | Profile endpoint pattern using `require_verified`; new `display_name`/`avatar_url` columns on `users`; `UploadFile` for avatar with content-type + size validation; Pillow for image resampling |
| USER-02 | User can change password (requires current password) | `pwdlib` already in stack for verify + hash; password change invalidates all OTHER sessions (blacklist all active JTIs for old access tokens, delete all refresh tokens); OAuth-only users with null `password_hash` may ADD a password |
| USER-03 | User can list and revoke active sessions (device, IP, last active) | New `UserSession` DB model tracking `user_agent`, `ip_address`, `city`, `last_active_at`; `user-agents` library for device/browser parsing; `geoip2` + GeoLite2-City MMDB for city lookup; per-request Redis `SETEX` for last_active; blacklist JTI on revocation |
| USER-04 | User is redirected to wxcode with access token after login | One-time code stored in Redis with 30-second TTL; new `wxcode_url` column on `Tenant`; post-login redirect endpoint issues code + redirects; wxcode exchange endpoint consumes code, deletes it, returns JWT |
</phase_requirements>

---

## Summary

Phase 7 builds on top of the fully-implemented auth stack (Phases 2–6) to expose user-facing account management endpoints and a secure post-login redirect flow. The existing codebase provides all the foundational infrastructure: `require_verified` dependency for protected endpoints, `write_audit` for audit trail, `blacklist_access_token` and `_issue_tokens` helpers for token operations, and the `RefreshToken` model as the session anchor. Phase 7 does not replace any of these — it extends them.

The most significant new infrastructure item is a `UserSession` model (migration 006) that attaches rich metadata to each `RefreshToken` row: user-agent string, parsed device type, browser name/version, client IP, geolocated city, and a Redis-backed `last_active_at` timestamp. Session listing queries this table; revocation blacklists the stored access token JTI in Redis (immediate rejection) and deletes the `RefreshToken` row. The `_issue_tokens` helper must be updated to accept optional session metadata and persist a `UserSession` row alongside each new `RefreshToken`.

The wxcode redirect (USER-04) uses a one-time authorization code pattern: a `secrets.token_urlsafe(32)` value is stored in Redis under `auth:wxcode_code:{code}` with a 30-second TTL. The login flow issues this code and redirects the browser to `{wxcode_url}?code={code}`. The wxcode backend exchanges the code via a server-to-server `POST /api/v1/auth/wxcode/exchange` call; wxcode-adm deletes the Redis key atomically and returns the JWT. The token never appears in a URL that could be logged or leaked via Referer headers.

**Primary recommendation:** Build a `users` module (`router.py`, `service.py`, `schemas.py`) at `/api/v1/users/me/*` for profile endpoints; add a `UserSession` model to `auth/models.py`; update `_issue_tokens` to accept and persist session metadata; add `wxcode_url` to `Tenant`; implement the one-time code exchange as a new route pair in `auth/router.py`.

---

## Standard Stack

### Core (already installed — no new pip installs for most features)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.131.0 | Route definitions, UploadFile, Depends | Already in stack |
| sqlalchemy | 2.0.46 | UserSession model, async queries | Already in stack |
| redis | 5.3.1 | last_active writes, one-time codes, JTI blacklist | Already in stack |
| pwdlib[argon2] | 0.3.0 | Password verify + hash for change-password | Already in stack |
| PyJWT[crypto] | 2.11.0 | decode JTI from existing access token for blacklist | Already in stack |

### New Libraries Required

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| user-agents | 2.2.0 | Parse User-Agent string → device type, browser name/version | Wraps ua-parser, provides `is_mobile`, `is_tablet`, `is_pc` booleans and `browser.family`, `browser.version_string` |
| geoip2 | 5.2.0 | Offline IP-to-city lookup using local MMDB file | Official MaxMind Python client; no network latency; free GeoLite2-City database |

**Installation:**
```bash
pip install "user-agents==2.2.0" "geoip2==5.2.0"
```

**GeoLite2-City MMDB download:**
MaxMind requires a free account registration to download GeoLite2-City.mmdb. The database file is updated weekly (every Tuesday). Store it at a configurable path and load it at app startup via `geoip2.database.Reader`. The reader object must be shared (not reopened per request) — create it once in the lifespan context.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| geoip2 + GeoLite2 | ip-api.com HTTP service | External API: network latency per request, rate limits, no offline fallback — rejected |
| geoip2 + GeoLite2 | ipinfo.io HTTP service | Same external API concerns — rejected |
| user-agents | ua-parser (lower-level) | user-agents wraps ua-parser and adds convenience boolean properties — preferred |
| Local avatar storage | S3/boto3 | S3 is better for production scale but adds AWS dependency; for Phase 7 use local filesystem storage in a configured `AVATAR_UPLOAD_DIR`, with `boto3` as a v2 upgrade path |

---

## Architecture Patterns

### Recommended Module Structure

```
backend/src/wxcode_adm/
├── auth/
│   ├── models.py           # Add UserSession model
│   ├── service.py          # Update _issue_tokens; add session listing, revocation, one-time code helpers
│   ├── router.py           # Add /auth/wxcode/exchange and /auth/wxcode/redirect endpoints
│   └── schemas.py          # Add session listing schemas, wxcode redirect/exchange schemas
├── users/
│   ├── __init__.py
│   ├── router.py           # GET/PATCH /me, POST /me/avatar, POST /me/change-password, POST /me/change-email
│   ├── service.py          # update_profile, change_password, change_email, upload_avatar
│   └── schemas.py          # ProfileResponse, UpdateProfileRequest, ChangePasswordRequest, etc.
└── alembic/versions/
    └── 006_add_user_account_tables.py   # UserSession model, users columns, tenant wxcode_url
```

### Pattern 1: UserSession Model (new DB table)

**What:** Attach rich session metadata to each `RefreshToken` row in a 1:1 relationship. When `_issue_tokens` creates a `RefreshToken`, it also creates a `UserSession` row with the access token JTI (needed for blacklisting on revocation), user_agent string, parsed device/browser info, client IP, geolocated city, and `last_active_at`.

**Why separate table:** Avoids widening the `refresh_tokens` table with nullable columns; keeps session metadata cleanly separated; can be independently queried for listing without loading the raw token.

```python
# Source: codebase pattern (auth/models.py style)
class UserSession(TimestampMixin, Base):
    """
    Rich session metadata attached to a RefreshToken.

    Stores the access token JTI so it can be blacklisted immediately on
    session revocation. The refresh_token_id FK cascades on delete so
    rows are cleaned up when the RefreshToken is removed.

    last_active_at is kept in Redis (auth:session:last_active:{session_id})
    to avoid a DB write on every request; this column stores the last
    flushed value (populated at session creation, not updated per-request).
    """
    __tablename__ = "user_sessions"

    refresh_token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Access token JTI for immediate blacklisting on revocation
    access_token_jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Raw user-agent for audit/display
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Parsed display values
    device_type: Mapped[str | None] = mapped_column(String(20), nullable=True)   # Desktop/Mobile/Tablet
    browser_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    browser_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Network info
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)    # IPv6 max 45 chars
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # last_active flushed from Redis periodically or at logout
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### Pattern 2: Per-Request Last Active Update

**What:** In `get_current_user` (dependencies.py), after the user is resolved, issue a Redis `SETEX` to update the session's last active timestamp. Use the `jti` from the decoded JWT to identify the session.

**When to use:** Every authenticated request that passes through `get_current_user`.

**Redis key pattern:** `auth:session:last_active:{jti}` → ISO timestamp string, TTL = ACCESS_TOKEN_TTL_HOURS.

**Why Redis, not DB:** A DB write on every API request would be a performance bottleneck. Redis `SET` with TTL is O(1) and sub-millisecond.

```python
# Source: codebase pattern (auth/dependencies.py extension)
# In get_current_user, after resolving the user:
now_iso = datetime.now(timezone.utc).isoformat()
ttl = settings.ACCESS_TOKEN_TTL_HOURS * 3600
await redis.set(f"auth:session:last_active:{jti}", now_iso, ex=ttl)
```

**Session listing reads last_active from Redis first, falling back to `UserSession.last_active_at` (DB):**

```python
# In list_sessions service function:
last_active_raw = await redis.get(f"auth:session:last_active:{session.access_token_jti}")
last_active = (
    datetime.fromisoformat(last_active_raw)
    if last_active_raw
    else session.last_active_at
)
```

### Pattern 3: Session Revocation with Immediate Blacklist

**What:** When the user revokes a session, load the `UserSession.access_token_jti`, call `blacklist_access_token` with a reconstructed token (actually: directly write `redis.set(f"auth:blacklist:jti:{jti}", "1", ex=remaining_ttl)`), then delete the `RefreshToken` row (cascades to `UserSession`).

**Important:** The existing `blacklist_access_token(redis, token)` function decodes the full token to extract the JTI and compute remaining TTL. For revocation, we have the JTI already but NOT the full token. Write the blacklist key directly using a fixed TTL (ACCESS_TOKEN_TTL_HOURS * 3600 seconds is safe — the key auto-expires even if the token already expired).

```python
# Source: codebase pattern (auth/service.py)
async def revoke_session(
    db: AsyncSession, redis: Redis, session_id: uuid.UUID, current_jti: str
) -> None:
    session = await db.get(UserSession, session_id)
    if session is None:
        raise NotFoundError(error_code="SESSION_NOT_FOUND", message="Session not found")

    # Prevent self-revocation: compare against the current request's JTI
    if session.access_token_jti == current_jti:
        raise AppError(
            error_code="CANNOT_REVOKE_CURRENT_SESSION",
            message="Cannot revoke your current session. Use logout instead.",
            status_code=400,
        )

    # Immediately blacklist the access token JTI
    ttl = settings.ACCESS_TOKEN_TTL_HOURS * 3600
    await redis.set(f"auth:blacklist:jti:{session.access_token_jti}", "1", ex=ttl)

    # Delete refresh token (cascades to UserSession)
    await db.execute(
        delete(RefreshToken).where(RefreshToken.id == session.refresh_token_id)
    )
```

### Pattern 4: One-Time wxcode Code Exchange

**What:** After login, instead of embedding the JWT in a URL, issue a `secrets.token_urlsafe(32)` code stored in Redis under `auth:wxcode_code:{code}` mapping to the access + refresh token pair. Redirect the browser to `{wxcode_url}?code={code}`. The wxcode backend calls `POST /api/v1/auth/wxcode/exchange` with the code; wxcode-adm deletes the Redis key atomically (`GETDEL`) and returns the tokens.

**TTL:** 30 seconds. This is the industry standard for authorization codes (OAuth 2.0 spec recommends max 10 minutes but short-lived codes reduce attack surface). 30 seconds is long enough for a server-to-server exchange but short enough to be useless if leaked.

```python
# Source: derived from OAuth 2.0 authorization code flow pattern
import json, secrets
from redis.asyncio import Redis

WXCODE_CODE_TTL = 30  # seconds — stored in settings as WXCODE_CODE_TTL

async def issue_wxcode_code(redis: Redis, access_token: str, refresh_token: str) -> str:
    """Issue a one-time wxcode code mapping to a token pair. TTL = 30s."""
    code = secrets.token_urlsafe(32)
    payload = json.dumps({"access_token": access_token, "refresh_token": refresh_token})
    await redis.set(f"auth:wxcode_code:{code}", payload, ex=WXCODE_CODE_TTL)
    return code


async def exchange_wxcode_code(redis: Redis, code: str) -> dict:
    """
    Atomically consume a wxcode code and return the token pair.
    Uses GETDEL to prevent replay in one round-trip.
    """
    raw = await redis.getdel(f"auth:wxcode_code:{code}")
    if raw is None:
        raise AppError(
            error_code="INVALID_WXCODE_CODE",
            message="Code is invalid or has expired",
            status_code=401,
        )
    return json.loads(raw)
```

**Redirect endpoint (GET /api/v1/auth/wxcode/redirect):**
- Requires `require_verified` (authenticated user)
- Looks up the user's primary tenant `wxcode_url` from DB
- Calls `_issue_tokens` to get fresh tokens
- Calls `issue_wxcode_code` to get the code
- Returns `RedirectResponse` to `{wxcode_url}?code={code}`

**Exchange endpoint (POST /api/v1/auth/wxcode/exchange):**
- Public (no auth header required) — wxcode backend calls this server-to-server
- Rate-limited to prevent brute force against short codes
- Accepts `{"code": "..."}` body
- Returns `{"access_token": "...", "refresh_token": "...", "token_type": "bearer"}`

### Pattern 5: Profile Update Endpoint

**What:** `PATCH /api/v1/users/me` accepts a partial update (display_name, email). Changes are applied to the authenticated user. Email change triggers a new verification flow — the new email gets an OTP and `email_verified` is set to `False` until confirmed.

**New columns on `users` table (migration 006):**
- `display_name: String(255), nullable=True` — user's chosen display name
- `avatar_url: String(500), nullable=True` — path/URL to stored avatar image

**Email change flow:**
1. User submits `PATCH /me` with new email
2. Service checks new email is not taken
3. Updates `users.email` and sets `email_verified = False`
4. Sends OTP to new email (reuses existing `signup`/`verify_email` OTP pattern)
5. All other active sessions should be preserved (email change does not invalidate sessions per Phase 7 design — the JWT `sub` is the user UUID, not the email)
6. User must re-verify email before accessing protected endpoints again (the `require_verified` dependency already enforces `email_verified = True`)

### Pattern 6: Password Change

**What:** `POST /api/v1/users/me/change-password` requires current password + new password. For OAuth-only users (null `password_hash`), the "current password" field is omitted and a new hash is set (adds password to the account).

**Session behavior (Claude's discretion — recommendation):** Invalidate all OTHER sessions (not the current one) on password change. This is the security-conscious default: a password change means other sessions may be compromised. Current session stays alive so the user is not immediately logged out.

```python
# Source: codebase pattern
async def change_password(
    db: AsyncSession, redis: Redis, user: User,
    current_password: str | None, new_password: str,
    current_jti: str
) -> None:
    # 1. Verify current password (skip if OAuth-only and adding password for first time)
    if user.password_hash is not None:
        if current_password is None or not password_context.verify(current_password, user.password_hash):
            raise AppError(error_code="INVALID_PASSWORD", message="Current password is incorrect", status_code=401)

    # 2. Hash and set new password
    user.password_hash = password_context.hash(new_password)

    # 3. Revoke all OTHER sessions (not current)
    other_sessions_result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.access_token_jti != current_jti
        )
    )
    other_sessions = other_sessions_result.scalars().all()
    ttl = settings.ACCESS_TOKEN_TTL_HOURS * 3600
    pipe = redis.pipeline()
    for s in other_sessions:
        pipe.set(f"auth:blacklist:jti:{s.access_token_jti}", "1", ex=ttl)
    await pipe.execute()
    # Delete other refresh tokens (cascades to UserSession rows)
    # ... delete query ...
```

### Pattern 7: Avatar Upload

**What:** `POST /api/v1/users/me/avatar` accepts `multipart/form-data` with a single `UploadFile`. Validate content-type (JPEG or PNG only), validate size (max 2 MB), resize to 256x256 using Pillow, save to `{AVATAR_UPLOAD_DIR}/{user_id}.jpg`, update `users.avatar_url`.

**Recommendation (Claude's discretion):**
- **Storage:** Local filesystem at `AVATAR_UPLOAD_DIR` (configurable setting). Simple, no external dependency. Serves via `StaticFiles` mount or a redirect endpoint.
- **Size limit:** 2 MB raw upload. After resize/compress to 256x256 JPEG, output will be under 50 KB.
- **Allowed types:** `image/jpeg`, `image/png` only. Validate `content_type` + verify magic bytes with Pillow (open the image — if PIL raises, it's not a valid image).
- **Filename:** `{user_id}.jpg` (fixed name, no user-controlled input in path).

```python
# Source: FastAPI UploadFile pattern + Pillow
from fastapi import UploadFile
from PIL import Image
import io, os

MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
AVATAR_SIZE = (256, 256)

async def upload_avatar(user: User, file: UploadFile, avatar_dir: str) -> str:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise AppError(error_code="INVALID_FILE_TYPE", message="Only JPEG and PNG are supported", status_code=422)

    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        raise AppError(error_code="FILE_TOO_LARGE", message="Avatar must be under 2 MB", status_code=422)

    # Validate and resize with Pillow
    try:
        img = Image.open(io.BytesIO(contents))
        img = img.convert("RGB")  # normalize to RGB (handles RGBA PNG)
        img.thumbnail(AVATAR_SIZE, Image.LANCZOS)
    except Exception:
        raise AppError(error_code="INVALID_IMAGE", message="File is not a valid image", status_code=422)

    # Save with fixed filename (no user-controlled path)
    filename = f"{user.id}.jpg"
    path = os.path.join(avatar_dir, filename)
    img.save(path, "JPEG", quality=85)

    return f"/avatars/{filename}"  # URL path served by StaticFiles
```

**Note:** Pillow is already a transitive dependency (via `qrcode[pil]` installed in Phase 6). No new install needed.

### Pattern 8: User-Agent Parsing

```python
# Source: user-agents 2.2.0 pypi
from user_agents import parse as parse_ua

def parse_device_info(user_agent_string: str | None) -> tuple[str | None, str | None, str | None]:
    """Return (device_type, browser_name, browser_version) from raw User-Agent."""
    if not user_agent_string:
        return None, None, None
    ua = parse_ua(user_agent_string)
    if ua.is_mobile:
        device_type = "Mobile"
    elif ua.is_tablet:
        device_type = "Tablet"
    elif ua.is_pc:
        device_type = "Desktop"
    else:
        device_type = "Unknown"
    browser_name = ua.browser.family or None
    browser_version = ua.browser.version_string or None
    return device_type, browser_name, browser_version
```

### Pattern 9: IP Geolocation

```python
# Source: geoip2 5.2.0 readthedocs.io
import geoip2.database
import geoip2.errors

# Opened once at lifespan startup; shared across requests
_geoip_reader: geoip2.database.Reader | None = None

def get_city_from_ip(ip: str | None) -> str | None:
    """Return approximate city name for an IP address, or None if unavailable."""
    if not ip or _geoip_reader is None:
        return None
    try:
        response = _geoip_reader.city(ip)
        return response.city.name  # e.g., "São Paulo"
    except (geoip2.errors.AddressNotFoundError, ValueError):
        return None  # Private/loopback IP or not in database
```

**Lifespan integration (main.py):**
```python
# In lifespan startup, after Redis check:
if settings.GEOLITE2_DB_PATH:
    import geoip2.database
    from wxcode_adm.users import geo  # or auth/geo.py
    geo._geoip_reader = geoip2.database.Reader(settings.GEOLITE2_DB_PATH)
```

**New setting to add to `config.py`:**
```python
GEOLITE2_DB_PATH: str = ""  # Path to GeoLite2-City.mmdb; empty string = geolocation disabled
WXCODE_CODE_TTL: int = 30   # One-time code TTL in seconds
AVATAR_UPLOAD_DIR: str = "/app/avatars"  # Local avatar storage directory
```

### Pattern 10: Updating _issue_tokens to Accept Session Metadata

The existing `_issue_tokens(db, redis, user)` signature must be extended to accept optional session metadata. All callers (login, oauth callback, mfa_verify, confirm_oauth_link) must pass the `Request` object or extracted metadata.

```python
# Source: codebase pattern extension
async def _issue_tokens(
    db: AsyncSession,
    redis: Redis,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    # ... existing logic ...
    # After creating RefreshToken:
    access_token = create_access_token(str(user.id))
    # Extract JTI from the just-created token:
    payload = decode_access_token(access_token)
    jti = payload["jti"]

    device_type, browser_name, browser_version = parse_device_info(user_agent)
    city = get_city_from_ip(ip_address)

    db.add(UserSession(
        refresh_token_id=rt.id,   # set after db.flush() or assign RT first
        user_id=user.id,
        access_token_jti=jti,
        user_agent=user_agent,
        device_type=device_type,
        browser_name=browser_name,
        browser_version=browser_version,
        ip_address=ip_address,
        city=city,
        last_active_at=datetime.now(timezone.utc),
    ))
    # ...
```

**Note:** `db.flush()` is needed to get the `RefreshToken.id` before creating `UserSession`. SQLAlchemy async: `await db.flush()` after `db.add(rt)`.

### Anti-Patterns to Avoid

- **Storing JWT in redirect URL query parameter:** The wxcode URL must never contain the access token directly. Use one-time code exchange instead (already decided).
- **DB write on every request for last_active:** Writing to PostgreSQL on every authenticated request is O(n) write pressure. Use Redis `SET` with TTL instead.
- **Re-opening geoip2 Reader per request:** The `geoip2.database.Reader` loads an MMDB file into memory on open. It must be opened once and shared. Opening per request is O(MMDB file size) work.
- **User-controlled avatar filename in path:** Never use `file.filename` directly in the storage path. Use `{user_id}.jpg` to prevent path traversal.
- **Revoking current session via "revoke all":** The "revoke all other sessions" endpoint must exclude the current session's `jti`. The current jti comes from the `get_current_user` dependency's decoded payload.
- **Email change without re-verification:** Setting `email_verified = False` is mandatory when the email changes. The `require_verified` dependency will then block access until the new email is verified.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| User-agent string parsing | Custom regex for browser/OS/device detection | `user-agents==2.2.0` | UA parsing is notoriously complex; the ua-parser regex database covers thousands of browsers and devices |
| IP geolocation | HTTP call to ip-api.com or ipinfo.io per request | `geoip2==5.2.0` + GeoLite2 MMDB | Offline, zero latency, no rate limits, works in all environments |
| Image validation | Check file extension or content-type header only | `Pillow` (already installed via `qrcode[pil]`) | Content-type can be spoofed; Pillow.Image.open() verifies actual image bytes |
| One-time code uniqueness | Sequential IDs or UUID v4 | `secrets.token_urlsafe(32)` | Cryptographically random, URL-safe, 32 bytes = 256 bits of entropy — brute force infeasible |

**Key insight:** The authentication infrastructure already handles the hard parts (JWT, Redis blacklist, argon2 hashing). Phase 7 is primarily wiring existing primitives together in new combinations, not building novel infrastructure.

---

## Common Pitfalls

### Pitfall 1: `_issue_tokens` flush/flush ordering for UserSession FK

**What goes wrong:** `UserSession.refresh_token_id` references `refresh_tokens.id`. If the `RefreshToken` object is added to the session but not flushed, its `id` is `None` (UUID not yet assigned by the DB) when the `UserSession` is created, causing a FK constraint violation.

**Why it happens:** SQLAlchemy async does not auto-flush by default between `db.add()` calls. The `id` is populated via `server_default=text("gen_random_uuid()")` only after a flush or commit.

**How to avoid:** Use the Python-side `default=uuid.uuid4` on the `id` column (which is already set in `TimestampMixin`). The Python-level default runs immediately on object construction, before flush. Assign the `RefreshToken` object to a variable, then use `rt.id` for the `UserSession.refresh_token_id`. Do NOT rely on `db.flush()` for ID population in tests (SQLite uses Python defaults, PostgreSQL uses server defaults — Python defaults work in both environments).

**Warning signs:** `IntegrityError: NOT NULL constraint failed: user_sessions.refresh_token_id` in SQLite tests.

### Pitfall 2: geoip2 AddressNotFoundError for localhost/private IPs

**What goes wrong:** `reader.city("127.0.0.1")` or `reader.city("::1")` raises `geoip2.errors.AddressNotFoundError` — private/loopback IPs are not in the database.

**Why it happens:** The GeoLite2-City database only contains public IP ranges.

**How to avoid:** Always wrap `reader.city()` in a try/except for `AddressNotFoundError` and return `None`. In development (where `request.client.host` is often `127.0.0.1` or `testclient`), city will be `None` — that is correct behavior.

**Warning signs:** `AddressNotFoundError` in server logs during local development.

### Pitfall 3: One-time wxcode code race condition / replay

**What goes wrong:** Two simultaneous exchange requests for the same code both succeed because `GET` then `DELETE` is not atomic.

**Why it happens:** Non-atomic read-then-delete.

**How to avoid:** Use Redis `GETDEL` (available in redis-py 4.0+, already at 5.3.1 in this stack). `GETDEL` atomically returns the value and deletes the key in one command. If the code doesn't exist, it returns `None`.

**Warning signs:** Double-spending of tokens in load tests.

### Pitfall 4: test_db SQLite + JSONB columns for `UserSession`

**What goes wrong:** If any new column uses `JSONB` or PostgreSQL-specific types, the `test_db` fixture needs to be updated to patch them, following the pattern established in `conftest.py`.

**Why it happens:** SQLite does not support PostgreSQL-specific types.

**How to avoid:** Avoid `JSONB` for `UserSession` columns — use simple `String` types for device_type, browser_name, etc. No JSONB needed for session metadata.

### Pitfall 5: `_issue_tokens` signature change breaks all callers

**What goes wrong:** Adding required parameters to `_issue_tokens` breaks the existing callers in `login`, `mfa_verify`, `resolve_oauth_account`, and `confirm_oauth_link`.

**Why it happens:** All callers must be updated simultaneously.

**How to avoid:** Use keyword-only arguments with `None` defaults: `def _issue_tokens(db, redis, user, *, user_agent=None, ip_address=None)`. This is backward-compatible — callers that don't pass metadata will create `UserSession` rows with `None` values, which is acceptable (the session will still appear in the list, just without device/geo info).

### Pitfall 6: `write_audit` does not commit (Phase 5 decision)

**What goes wrong:** New profile/session endpoints that call `write_audit` must NOT call `await db.commit()` separately. The `get_session` dependency commits at the end of the request automatically.

**Why it happens:** `write_audit` only does `db.add(entry)` — no commit. This is by design (Phase 05-platform-security decision: caller's session commit includes audit entry atomically).

**How to avoid:** Follow the existing router pattern: call `write_audit(db, ...)` in the router, return the response. The `get_session` dependency handles the commit.

### Pitfall 7: Avatar URL as absolute vs relative path

**What goes wrong:** Storing absolute URLs (e.g., `http://localhost:8060/avatars/...`) ties the stored value to the current host, breaking in production or after hostname changes.

**Why it happens:** Using `str(request.base_url)` when building the avatar URL.

**How to avoid:** Store only the relative path `/avatars/{user_id}.jpg`. The frontend constructs the full URL by prepending the API base URL. Alternatively, store just the filename and construct the URL in the response schema.

---

## Code Examples

### Session Listing Response Shape

```python
# Source: codebase pattern (auth/schemas.py style)
from pydantic import BaseModel
from datetime import datetime
import uuid

class SessionResponse(BaseModel):
    id: uuid.UUID           # UserSession.id
    device_type: str | None
    browser_name: str | None
    browser_version: str | None
    ip_address: str | None
    city: str | None
    last_active_at: datetime | None
    created_at: datetime
    is_current: bool        # True if this session's JTI matches the request's JWT JTI

class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
```

### Alembic Migration 006 Structure

```python
# 006_add_user_account_tables.py
# Changes:
# 1. ALTER users: add display_name (String 255 nullable), avatar_url (String 500 nullable)
# 2. ALTER tenants: add wxcode_url (String 500 nullable)
# 3. CREATE user_sessions: rich session metadata table
#    - id UUID PK
#    - refresh_token_id UUID FK refresh_tokens.id CASCADE UNIQUE
#    - user_id UUID FK users.id CASCADE INDEX
#    - access_token_jti String(64) UNIQUE NOT NULL
#    - user_agent String(512) nullable
#    - device_type String(20) nullable
#    - browser_name String(100) nullable
#    - browser_version String(50) nullable
#    - ip_address String(45) nullable
#    - city String(100) nullable
#    - last_active_at TIMESTAMP WITH TIME ZONE nullable
#    - created_at, updated_at (from TimestampMixin)
```

### Existing Patterns to Reuse

```python
# get_current_user dependency (already extracts jti — pass it to services needing it)
# auth/dependencies.py — jti is already decoded; expose it via a new dependency or
# pass it as a parameter from the router

# EXISTING: how to get current jti in a route
from wxcode_adm.auth.jwt import decode_access_token
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# In routes requiring jti for self-revocation protection:
# Option 1: add a get_current_jti dependency that re-decodes the token
# Option 2: extend get_current_user to return a (user, jti) pair — RECOMMENDED
#   because jti is already decoded in get_current_user; no second decode needed.
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Token in redirect URL (`?access_token=...`) | One-time code exchange (RFC 6749 §4.1) | Token never in URL/browser history/logs |
| DB write for every session activity | Redis SETEX for last_active per request | O(1) Redis vs O(log n) DB index write |
| Global avatar storage URL | Per-tenant custom domain in `wxcode_url` | Allows white-label deployments |

---

## Open Questions

1. **`get_current_user` exposing JTI to service layer**
   - What we know: `get_current_user` decodes the JWT and has `jti` available, but currently only returns `User`.
   - What's unclear: Should `get_current_user` be modified to return `(User, jti)`, or should a separate `get_current_jti` dependency be created?
   - Recommendation: Create a lightweight `get_current_jti(token: str = Depends(oauth2_scheme)) -> str` dependency that decodes and returns only the JTI, then use it alongside `get_current_user` in routes that need both. Avoids modifying the widely-used `get_current_user` signature. The double-decode overhead is negligible (RSA verify is cached at OS level).

2. **GeoLite2-City MMDB file distribution**
   - What we know: MaxMind requires a free account registration to download the file; it cannot be bundled in the Docker image due to license terms (redistribution requires attribution).
   - What's unclear: How to make the file available in Docker/CI without committing it to the repo.
   - Recommendation: Add `GEOLITE2_DB_PATH` to config with empty string default (geolocation disabled if not set). Document the download step in the README. In CI, skip geolocation (city will be `None`). In production, mount the file as a volume.

3. **Default tenant for multi-tenant users**
   - What we know: `TenantMembership` has `created_at` but no "last_used" or "primary" flag.
   - What's unclear: How to determine "last-used" tenant without a separate column.
   - Recommendation: Add `last_used_tenant_id: uuid.UUID | None` nullable column to the `users` table in migration 006, updated on wxcode redirect. This gives a persistent "last used" signal. Falls back to the oldest membership (`TenantMembership.created_at ASC LIMIT 1`) for users without a last-used record.

---

## Sources

### Primary (HIGH confidence)
- Codebase: `backend/src/wxcode_adm/auth/service.py` — `_issue_tokens`, `blacklist_access_token`, Redis key patterns
- Codebase: `backend/src/wxcode_adm/auth/models.py` — `User`, `RefreshToken`, existing model patterns
- Codebase: `backend/src/wxcode_adm/auth/dependencies.py` — `get_current_user`, `require_verified`
- Codebase: `backend/src/wxcode_adm/tenants/models.py` — `Tenant`, `TenantMembership`
- Codebase: `backend/src/wxcode_adm/db/base.py` — `TimestampMixin`, `Base`
- Codebase: `backend/tests/conftest.py` — test fixture patterns, SQLite JSONB workaround
- [geoip2 5.2.0 docs](https://geoip2.readthedocs.io/) — Reader API, city lookup, AddressNotFoundError
- [user-agents 2.2.0 PyPI](https://pypi.org/project/user-agents/) — parse(), is_mobile/tablet/pc, browser.family/version_string

### Secondary (MEDIUM confidence)
- [FastAPI UploadFile reference](https://fastapi.tiangolo.com/reference/uploadfile/) — UploadFile.content_type, await file.read()
- [GeoLite2 Free Geolocation Data](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data/) — MMDB format, weekly updates, license terms
- [MaxMind GeoIP2 Python API](https://geoip2.readthedocs.io/) — Reader reuse pattern, thread/async safety

### Tertiary (LOW confidence)
- WebSearch: IP geolocation offline vs HTTP service tradeoffs (multiple blog sources agree on Redis/offline approach)
- WebSearch: FastAPI avatar upload Pillow + size validation patterns (community blogs, consistent advice)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all new libraries (geoip2, user-agents) verified against PyPI and official docs; Pillow confirmed as transitive dep
- Architecture: HIGH — patterns are direct extensions of existing codebase conventions; UserSession model follows established model patterns exactly
- Pitfalls: HIGH — derived from actual codebase analysis (SQLite test fixture, async flush ordering, Redis GETDEL atomicity)
- wxcode redirect pattern: HIGH — standard OAuth 2.0 authorization code flow, verified against RFC 6749 §4.1 semantics

**Research date:** 2026-02-25
**Valid until:** 2026-03-27 (30 days — stable stack)
