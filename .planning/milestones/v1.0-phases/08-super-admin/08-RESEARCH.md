# Phase 8: Super-Admin - Research

**Researched:** 2026-02-26
**Domain:** FastAPI super-admin API, JWT audience isolation, SQLAlchemy admin queries, MRR aggregation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Admin auth flow
- Dedicated /admin/login endpoint — separate from tenant /auth/login; only accepts super-admin credentials; only issues admin-audience JWTs (aud: "wxcode-adm-admin")
- IP allowlist is optional — if ADMIN_ALLOWED_IPS env var is set, enforce it; if empty/unset, skip IP check (dev-friendly)
- All admin endpoints live under /api/v1/admin/* — same API version prefix, clear admin namespace
- Admin session TTL same as regular users — use existing ACCESS_TOKEN_TTL_HOURS and REFRESH_TOKEN_TTL_DAYS settings

#### Suspension & blocking
- Tenant suspension is immediate invalidation — all refresh tokens deleted, access tokens blacklisted; members kicked out within minutes
- Admin can reactivate suspended tenants — POST /api/v1/admin/tenants/{id}/reactivate restores access
- Tenant soft-delete has indefinite retention — is_deleted=True flag, data stays forever; no scheduled purge
- User block is per-tenant scope — admin blocks user within a specific tenant; user can still access other tenants; sessions for that tenant invalidated immediately

#### User search & actions
- Admin sees full profile + memberships + sessions — email, name, avatar, MFA status, email verified, created date, all tenant memberships with roles, plus active sessions (device, IP, last active)
- Force password reset: invalidate + send email — current password invalidated immediately, reset email sent automatically; user must set new password to log in
- User search supports email + name + tenant — search by email, display name, or filter by tenant membership
- Admin actions require a reason — block and force-reset require a "reason" string stored in the audit log alongside the action

#### MRR dashboard
- Data sourced from local DB (webhook-cached) — subscription data already in DB from webhook processing; dashboard aggregates local data; fast and reliable
- Snapshot + 30-day trend — current MRR numbers plus trend over last 30 days
- Trend computed on-demand — calculate from TenantSubscription history (created_at, canceled_at timestamps) when admin opens dashboard; no daily cron job needed
- Includes churn data — canceled subscription count and churn rate shown alongside MRR and plan distribution

### Claude's Discretion
- Admin login rate limiting specifics
- DashboardSnapshot response schema design
- Pagination defaults for tenant/user listing
- Exact IP allowlist parsing format

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SADM-01 | View all tenants (paginated, with plan/status/members) | SQLAlchemy JOIN query pattern: Tenant + TenantSubscription + Plan + member count subquery; audit router shows the offset/limit pagination pattern already used in project |
| SADM-02 | Suspend or soft-delete tenant | Tenant model needs `is_suspended` + `is_deleted` columns (migration 007); suspension = delete RefreshTokens + blacklist UserSession JTIs via existing `blacklist_jti`; soft-delete sets `is_deleted=True` |
| SADM-03 | View all users (search by email, view membership/status) | SQLAlchemy `ilike` for email/display_name search; `selectinload` for memberships + UserSessions; User model already has all profile fields from Phase 7 |
| SADM-04 | Block user or force password reset | `TenantMembership` needs `is_blocked` column (migration 007); force-reset needs `password_reset_required` on User (migration 007) + reuse existing `forgot_password` email flow |
| SADM-05 | MRR dashboard (active subscriptions, revenue, plan distribution) | Aggregate `TenantSubscription` + `Plan` (already eager-loaded); trend from `created_at`/`canceled_at` timestamps via Python time-series grouping |
</phase_requirements>

---

## Summary

Phase 8 introduces a super-admin control plane on top of the existing FastAPI application. The key architectural challenge is JWT audience isolation: admin tokens must carry `aud: "wxcode-adm-admin"` and regular tenant JWTs must not be usable on admin endpoints — and vice versa. PyJWT 2.11.0 (already installed) provides this natively: tokens with an `aud` claim fail `jwt.decode()` unless the caller passes the matching `audience=` parameter. This means `decode_access_token()` (which omits `audience=`) will correctly reject admin tokens, and a new `decode_admin_token()` (which passes `audience="wxcode-adm-admin"`) will correctly reject tenant tokens.

The codebase is well-structured to extend. Every prior phase followed a `models.py → service.py → router.py → schemas.py` pattern with a new module directory. Phase 8 adds `backend/src/wxcode_adm/admin/` following the same pattern. Migration 007 adds four columns to existing tables: `Tenant.is_suspended`, `Tenant.is_deleted`, `TenantMembership.is_blocked`, and `User.password_reset_required`. No new tables are needed — all admin actions operate on existing models.

The MRR dashboard computes on-demand from the existing `TenantSubscription` + `Plan` tables. The `TenantSubscription` relationship already eager-loads the `Plan` via `lazy="joined"`, making aggregation straightforward. Trend data uses Python-side grouping by week over the last 30 days, derived from `created_at` and `canceled_at` timestamps. No Stripe API calls are needed — all data is already cached locally via webhook processing from Phase 4.

**Primary recommendation:** Add `backend/src/wxcode_adm/admin/` module with its own router, service, and schemas. Migration 007 adds the four new columns. The `require_admin` dependency mirrors `require_superuser` in `billing/router.py` but verifies the JWT `aud` claim instead of just `is_superuser`. Reuse existing `blacklist_jti`, `write_audit`, and `forgot_password` functions without modification.

---

## Standard Stack

### Core (all already installed — no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyJWT | 2.11.0 | JWT encode/decode with `aud` claim | Already used; `audience=` param provides isolation |
| SQLAlchemy (async) | latest (installed) | Admin queries — JOIN, ilike, func.count, subqueries | Already used across all modules |
| FastAPI | latest (installed) | Admin router with Query params for pagination/filtering | Already used |
| slowapi | installed | Rate limiting for `/admin/login` | Already wired in `main.py` |
| fakeredis | installed (dev) | Test isolation | Already used in test suite |

### No New Dependencies

This phase requires zero new pip packages. Everything needed is already installed:
- JWT audience claims: PyJWT 2.11.0 (already installed)
- Password reset email: `send_reset_email` arq job (already in `tasks/`)
- Session invalidation: `blacklist_jti` (already in `auth/service.py`)
- Audit logging: `write_audit` (already in `audit/service.py`)
- Pagination: Query params with `limit`/`offset` (already used in `audit/router.py`)

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyJWT `audience=` param | Separate signing key pair for admin | Same isolation, simpler; new key pair requires JWKS update and external service coordination |
| Python-side MRR trend grouping | PostgreSQL `date_trunc` with GROUP BY | DB aggregation more efficient at scale; Python grouping simpler for 30 days of data, no raw SQL needed |
| `is_suspended` column on Tenant | Separate TenantStatus enum | Boolean simpler; status enum unnecessary complexity when only two states (active/suspended) matter for enforcement |

---

## Architecture Patterns

### Recommended Project Structure

```
backend/src/wxcode_adm/admin/
├── __init__.py
├── dependencies.py     # require_admin dependency (JWT aud check)
├── exceptions.py       # AdminAuthError (if needed, else reuse ForbiddenError)
├── router.py           # All /api/v1/admin/* endpoints
├── schemas.py          # Request/response Pydantic models
└── service.py          # Admin business logic (list, suspend, block, mrr)
```

Migration 007 (Alembic):
```
backend/alembic/versions/007_add_super_admin_columns.py
```

Test file:
```
backend/tests/test_super_admin.py
```

### Pattern 1: JWT Audience Claim Isolation

**What:** Admin tokens include `aud: "wxcode-adm-admin"` in the payload. PyJWT 2.x enforces bidirectional isolation automatically.

**When to use:** All admin token creation and verification.

**Example:**
```python
# Source: PyJWT 2.11.0 official API (verified with local runtime)

# CREATE admin token — add aud to extra_claims
def create_admin_access_token(user_id: str) -> str:
    """Issue an admin-audience JWT. Must ONLY be called from /admin/login."""
    return create_access_token(
        user_id=user_id,
        extra_claims={"aud": "wxcode-adm-admin"},
    )

# DECODE admin token — MUST pass audience= or regular tokens pass through
def decode_admin_access_token(token: str) -> dict:
    """
    Decode and verify an admin JWT with aud='wxcode-adm-admin'.

    PyJWT 2.x behavior (verified):
    - Token WITH aud='wxcode-adm-admin' and audience='wxcode-adm-admin' -> SUCCESS
    - Token WITHOUT aud claim and audience='wxcode-adm-admin' -> MissingRequiredClaimError
    - Token WITH aud='wxcode-adm-admin' and no audience= param -> InvalidAudienceError
    All three cases raise InvalidTokenError in our error translation.
    """
    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY.get_secret_value(),
            algorithms=["RS256"],
            audience="wxcode-adm-admin",  # CRITICAL: rejects all non-admin tokens
        )
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise InvalidTokenError()
    return payload
```

**Isolation guarantees (confirmed via local PyJWT 2.11.0 test):**
1. Admin token decoded without `audience=` → `InvalidAudienceError` (regular `decode_access_token` rejects admin tokens)
2. Regular token decoded with `audience="wxcode-adm-admin"` → `MissingRequiredClaimError` (admin decode rejects regular tokens)
3. Admin token decoded with wrong audience → `InvalidAudienceError`

### Pattern 2: Admin Dependency Chain

**What:** `require_admin` dependency mirrors `require_superuser` from `billing/router.py` but uses `decode_admin_access_token` instead of `decode_access_token`.

**Example:**
```python
# Source: billing/router.py pattern (existing codebase)
# In admin/dependencies.py

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.admin.jwt import decode_admin_access_token
from wxcode_adm.auth.models import User
from wxcode_adm.auth.service import is_token_blacklisted
from wxcode_adm.common.exceptions import ForbiddenError, InvalidTokenError
from wxcode_adm.dependencies import get_redis, get_session

# Separate OAuth2 scheme pointing to admin login URL
admin_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/admin/login",
    auto_error=True,
)

async def require_admin(
    token: str = Depends(admin_oauth2_scheme),
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> User:
    """
    Verify admin JWT (aud='wxcode-adm-admin'), check blacklist, load user.
    Rejects non-superuser accounts even with valid admin tokens.
    """
    payload = decode_admin_access_token(token)  # raises if not admin-audience
    sub = payload.get("sub")
    jti = payload.get("jti")
    if not sub or not jti:
        raise InvalidTokenError()
    if await is_token_blacklisted(redis, jti):
        raise InvalidTokenError()
    user = await db.get(User, uuid.UUID(sub))
    if user is None or not user.is_active or not user.is_superuser:
        raise ForbiddenError(
            error_code="ADMIN_REQUIRED",
            message="Super-admin access required",
        )
    return user
```

### Pattern 3: Tenant Suspension — Immediate Invalidation

**What:** Suspend = delete all `RefreshToken` rows for all members + blacklist their active `UserSession.access_token_jti` values. Members are kicked within one access token TTL (24h max, usually much faster on next request).

**Example:**
```python
# Source: existing auth/service.py blacklist_jti + auth/models.py RefreshToken pattern

async def suspend_tenant(
    db: AsyncSession, redis: Redis, tenant_id: uuid.UUID, reason: str, actor_id: uuid.UUID
) -> Tenant:
    """Mark tenant suspended, invalidate all member sessions immediately."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError(error_code="TENANT_NOT_FOUND", message="Tenant not found")
    if tenant.is_suspended:
        raise ConflictError(error_code="ALREADY_SUSPENDED", message="Tenant is already suspended")

    tenant.is_suspended = True  # New column from migration 007

    # Get all user_ids for this tenant's memberships
    membership_result = await db.execute(
        select(TenantMembership.user_id).where(TenantMembership.tenant_id == tenant_id)
    )
    user_ids = membership_result.scalars().all()

    # Blacklist active access tokens via UserSession JTIs
    sessions_result = await db.execute(
        select(UserSession.access_token_jti).where(UserSession.user_id.in_(user_ids))
    )
    jtis = sessions_result.scalars().all()
    for jti in jtis:
        await blacklist_jti(redis, jti)

    # Delete all refresh tokens (prevents re-issue after access token expires)
    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id.in_(user_ids))
    )

    await write_audit(db, action="suspend_tenant", resource_type="tenant",
                      actor_id=actor_id, resource_id=str(tenant_id),
                      details={"reason": reason})
    return tenant
```

**Critical note on scope:** Unlike `is_superuser` check in `get_current_user`, the suspension check happens in the **tenant context dependency** (`get_tenant_context` in `tenants/dependencies.py`). Phase 8 must add `is_suspended` check there so suspended tenants are blocked on every tenant-scoped request, not just on login.

### Pattern 4: Admin Login Endpoint

**What:** POST `/api/v1/admin/login` accepts only `is_superuser=True` users and issues admin-audience JWTs. Rate limited strictly. IP allowlist check runs before credential check.

**Example:**
```python
# Source: auth/router.py login pattern + billing/router.py superuser pattern

@admin_router.post("/login", response_model=AdminTokenResponse)
@limiter.limit("10/minute")  # Stricter than regular auth (5/minute)
async def admin_login(
    request: Request,
    body: AdminLoginRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> AdminTokenResponse:
    # 1. IP allowlist check (if ADMIN_ALLOWED_IPS is set)
    if settings.ADMIN_ALLOWED_IPS:
        client_ip = request.client.host if request.client else ""
        allowed = [ip.strip() for ip in settings.ADMIN_ALLOWED_IPS.split(",")]
        if client_ip not in allowed:
            raise ForbiddenError(
                error_code="IP_NOT_ALLOWED",
                message="Access denied from this IP address",
            )

    # 2. Load user — must be is_superuser=True
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_superuser or not verify_password(body.password, user.password_hash):
        raise InvalidCredentialsError()

    # 3. Issue admin-audience tokens
    access_token = create_admin_access_token(user_id=str(user.id))
    # Refresh token uses same model — admin sessions tracked same way
    ...
```

### Pattern 5: Pagination with Count — Audit Router Style

**What:** `limit` + `offset` Query params + separate `func.count()` query for total. The `audit/router.py` already uses this exact pattern.

**Example:**
```python
# Source: audit/router.py (existing codebase)
# Use same pattern for tenant/user listing

@admin_router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_admin)],
    limit: int = Query(default=20, ge=1, le=100),  # Claude's Discretion: 20 default
    offset: int = Query(default=0, ge=0),
    plan_slug: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),  # "active" | "suspended" | "deleted"
) -> TenantListResponse:
    base_q = select(Tenant).options(selectinload(Tenant.subscription))
    count_q = select(func.count()).select_from(Tenant)

    if plan_slug:
        # JOIN via TenantSubscription -> Plan
        base_q = base_q.join(TenantSubscription).join(Plan).where(Plan.slug == plan_slug)
        count_q = count_q.join(TenantSubscription).join(Plan).where(Plan.slug == plan_slug)
    if status == "suspended":
        base_q = base_q.where(Tenant.is_suspended == True)
        count_q = count_q.where(Tenant.is_suspended == True)
    elif status == "deleted":
        base_q = base_q.where(Tenant.is_deleted == True)
        count_q = count_q.where(Tenant.is_deleted == True)
    elif status == "active":
        base_q = base_q.where(Tenant.is_suspended == False, Tenant.is_deleted == False)
        count_q = count_q.where(Tenant.is_suspended == False, Tenant.is_deleted == False)

    total = (await db.execute(count_q)).scalar_one()
    results = (await db.execute(base_q.order_by(Tenant.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return TenantListResponse(items=[...], total=total)
```

### Pattern 6: Member Count Subquery

**What:** For SADM-01, each tenant listing row shows `member_count`. Use a correlated subquery or a scalar subquery.

**Example:**
```python
# Source: SQLAlchemy async docs pattern
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

# Subquery: count TenantMembership rows per tenant
member_count_subq = (
    select(func.count(TenantMembership.id))
    .where(TenantMembership.tenant_id == Tenant.id)
    .correlate(Tenant)
    .scalar_subquery()
)

# Use in main query
stmt = select(Tenant, member_count_subq.label("member_count"))
```

### Pattern 7: User Search with ilike

**What:** Search users by email or display_name using case-insensitive `ilike`. Filter by tenant membership via JOIN.

**Example:**
```python
# Source: SQLAlchemy async + existing codebase patterns

from sqlalchemy import or_

base_q = select(User)
if q:  # search string
    base_q = base_q.where(
        or_(
            User.email.ilike(f"%{q}%"),
            User.display_name.ilike(f"%{q}%"),
        )
    )
if tenant_id:
    # Filter users who are members of a specific tenant
    base_q = base_q.join(TenantMembership).where(
        TenantMembership.tenant_id == tenant_id_uuid
    )
```

### Pattern 8: MRR Dashboard On-Demand Calculation

**What:** Current MRR = sum of `Plan.monthly_fee_cents` for all `TenantSubscription` where `status=ACTIVE`. Plan distribution = count per plan. Trend = iterate 30 days of daily/weekly snapshots computed from `created_at`/`canceled_at`.

**Example:**
```python
# Source: billing/models.py + billing/service.py patterns (verified in codebase)
from datetime import datetime, timedelta, timezone
from collections import defaultdict

async def compute_mrr_dashboard(db: AsyncSession) -> MRRDashboard:
    # 1. Active subscriptions — eager load plan via lazy="joined" (already configured)
    active_subs = (await db.execute(
        select(TenantSubscription)
        .where(TenantSubscription.status == SubscriptionStatus.ACTIVE)
    )).scalars().all()

    active_count = len(active_subs)
    mrr_cents = sum(sub.plan.monthly_fee_cents for sub in active_subs)

    # 2. Plan distribution
    plan_dist: dict[str, int] = defaultdict(int)
    for sub in active_subs:
        plan_dist[sub.plan.slug] += 1

    # 3. Canceled count + churn rate
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    canceled_result = await db.execute(
        select(func.count(TenantSubscription.id))
        .where(TenantSubscription.status == SubscriptionStatus.CANCELED)
        .where(TenantSubscription.updated_at >= thirty_days_ago)
    )
    canceled_30d = canceled_result.scalar_one()
    churn_rate = (canceled_30d / (active_count + canceled_30d)) if (active_count + canceled_30d) > 0 else 0.0

    # 4. 30-day trend: weekly MRR snapshots (or daily — Claude's Discretion)
    # Load all subs created in last 30 days to build trend
    # Each data point = cumulative MRR at that date
    trend = _compute_trend(all_subs_result, thirty_days_ago, now)

    return MRRDashboard(
        active_subscription_count=active_count,
        mrr_cents=mrr_cents,
        plan_distribution=dict(plan_dist),
        canceled_count_30d=canceled_30d,
        churn_rate=round(churn_rate, 4),
        trend=trend,
        computed_at=now,
    )
```

### Pattern 9: Force Password Reset

**What:** Admin-triggered invalidation — set `User.password_reset_required = True` + delete all refresh tokens + blacklist all active JTIs + enqueue reset email. User's next login attempt sees the flag and is rejected with `PASSWORD_RESET_REQUIRED`.

**Two-step approach:**
1. **Migration 007:** Add `User.password_reset_required = Boolean, default=False`
2. **Auth service:** Check `password_reset_required` in `get_current_user` and raise error if set
3. **Reset flow:** Completing a password reset clears the flag

**Alternative approach (simpler, no new flag):**
- Invalidate password by setting `password_hash = None` (already nullable for OAuth users)
- Call `forgot_password()` to send reset email
- User cannot log in (wrong password) until they reset

**Recommended:** Use `password_reset_required` flag because:
- The auth team can display a specific error vs. generic "wrong password"
- `password_hash = None` is reserved for OAuth-only users (semantic conflict)
- Flag is clearer in audit trail

### Pattern 10: Per-Tenant User Block

**What:** Add `TenantMembership.is_blocked = Boolean, default=False`. When blocked, user's sessions for that tenant are invalidated. User can still log in — block is enforced at `get_tenant_context` level.

**Enforcement location:** `tenants/dependencies.py:get_tenant_context` must check `membership.is_blocked` and raise `ForbiddenError(error_code="USER_BLOCKED")`.

**Session invalidation:** Can only blacklist access token JTIs we know are in use. The `UserSession` table has `user_id` + `access_token_jti`. For a per-tenant block, we cannot easily scope sessions to a specific tenant (sessions are user-scoped, not tenant-scoped). **Resolution:** Blacklist ALL active JTIs for the user across all tenants (sessions are device-level, not per-tenant). This is more aggressive than strictly necessary but simpler and safe — user can re-authenticate to other tenants immediately.

**Alternative:** Only block at the `get_tenant_context` dependency, accepting that the current access token still works until expiry (24h max). Since the block is enforced on every tenant-scoped request, the user is effectively blocked immediately on any subsequent tenant API call.

**Recommended:** Block at `get_tenant_context` without JTI blacklist — the membership check happens every request, so enforcement is immediate. No session invalidation needed for per-tenant block.

### Anti-Patterns to Avoid

- **Using regular `require_superuser` for admin endpoints:** The existing `require_superuser` in `billing/router.py` uses `decode_access_token` (no audience check). A regular user cannot trick it, but the isolation from the audience claim is missing. Phase 8 MUST use `require_admin` which calls `decode_admin_access_token`.
- **Putting admin router without its own OAuth2 scheme:** If `admin_oauth2_scheme` uses the same `tokenUrl` as regular auth, Swagger UI will offer the wrong login endpoint. Use a separate `OAuth2PasswordBearer(tokenUrl="/api/v1/admin/login")`.
- **Forgetting to add `is_suspended` check to `get_tenant_context`:** Suspension is only effective if the tenant context dependency enforces it. Without this, suspended tenant members can still call all tenant-scoped endpoints.
- **Forgetting `is_deleted` Tenant default False:** Migration must set `server_default=false` or existing tenants will appear deleted.
- **MRR trend with raw PostgreSQL date_trunc:** Not necessary for 30 days of data. Python-side grouping is simpler and the test suite uses SQLite (which doesn't support `date_trunc`). Keep it in Python.
- **Admin refresh token using admin-audience:** Admin refresh tokens should follow the same pattern as regular refresh tokens (opaque tokens, stored in DB). Only access tokens carry the `aud` claim. The `/admin/refresh` endpoint issues a new admin access token + new refresh token.
- **Blacklisting on admin token decode for logout:** The `blacklist_access_token` function uses `options={"verify_exp": False}` but still verifies `aud` by default. Admin logout must use `options={"verify_exp": False, "verify_aud": False}` or pass `audience="wxcode-adm-admin"` when blacklisting admin tokens.

---

## Migration 007: New Columns Required

Migration 007 must add these four Boolean columns:

```python
# Revision: 007, Down revision: 006

def upgrade():
    # Tenant: suspension + soft-delete
    op.add_column("tenants", sa.Column(
        "is_suspended", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("tenants", sa.Column(
        "is_deleted", sa.Boolean(), nullable=False, server_default="false"
    ))

    # TenantMembership: per-tenant user block
    op.add_column("tenant_memberships", sa.Column(
        "is_blocked", sa.Boolean(), nullable=False, server_default="false"
    ))

    # User: force password reset flag
    op.add_column("users", sa.Column(
        "password_reset_required", sa.Boolean(), nullable=False, server_default="false"
    ))
```

Model changes (no new models, just new columns):
- `tenants/models.py:Tenant` — add `is_suspended: Mapped[bool]` + `is_deleted: Mapped[bool]`
- `tenants/models.py:TenantMembership` — add `is_blocked: Mapped[bool]`
- `auth/models.py:User` — add `password_reset_required: Mapped[bool]`

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT audience enforcement | Custom middleware parsing aud claim | PyJWT `audience=` param in `jwt.decode()` | Native, single-line, already installed |
| Admin token blacklisting | New Redis key namespace | Existing `blacklist_jti()` in `auth/service.py` | Already handles TTL, same Redis instance |
| Password reset email | New email template | Existing `send_reset_email` arq job + `forgot_password()` | Already tested, handles OAuth-only users |
| Audit logging | Custom admin action log | Existing `write_audit()` in `audit/service.py` | Writes into same `audit_logs` table |
| Rate limiting | Custom Redis counter | `@limiter.limit()` from slowapi | Already wired in `main.py`, same Redis |
| Pagination count | Two queries manually | `func.count()` subquery (audit router pattern) | One-liner, consistent with rest of project |
| Session invalidation | Iterate and expire cookies | `blacklist_jti()` + `delete(RefreshToken)` | Existing primitives, no client cooperation needed |
| IP parsing | Custom CIDR/range parsing | Simple string split + `in` check (single IPs) | Claude's Discretion allows simple approach; no CIDR required unless specified |

**Key insight:** Phase 8 is almost entirely orchestration of existing primitives. The `blacklist_jti`, `write_audit`, `is_token_blacklisted`, and `forgot_password` functions cover 80% of the admin actions. The main new code is routing, the admin JWT audience functions, and the MRR aggregation query.

---

## Common Pitfalls

### Pitfall 1: Admin Token Blacklisting Fails Due to Audience Check

**What goes wrong:** `blacklist_access_token()` in `auth/service.py` calls `pyjwt.decode()` with `options={"verify_exp": False}` but WITHOUT `options={"verify_aud": False}`. If admin tokens carry `aud: "wxcode-adm-admin"`, this decode will raise `InvalidAudienceError` and the function silently returns without blacklisting.

**Why it happens:** PyJWT 2.x verifies `aud` by default. `verify_exp: False` only skips expiry check.

**How to avoid:** Admin logout must either:
1. Call `blacklist_jti(redis, jti)` directly (passing the JTI from the decoded payload), OR
2. Use a new `blacklist_admin_access_token()` that passes `audience="wxcode-adm-admin"` and `options={"verify_exp": False}`

**Recommended:** Use `blacklist_jti()` directly in the admin logout handler after decoding with `decode_admin_access_token()` (which already verifies the audience). Extract the `jti` from the decoded payload, then call `blacklist_jti(redis, jti)`.

**Warning signs:** Admin logout returns 200 but re-using the same token still succeeds on admin endpoints.

### Pitfall 2: Suspended Tenant Members Not Actually Blocked

**What goes wrong:** `Tenant.is_suspended = True` is set in the DB but suspended members can still call tenant-scoped API endpoints because the suspension flag is never checked.

**Why it happens:** Suspension enforcement requires modifying `get_tenant_context` in `tenants/dependencies.py`. Without this change, the column exists but has no effect.

**How to avoid:** In migration 007 testing: after suspending a tenant, immediately test that a member's next API call returns 403 with `error_code: "TENANT_SUSPENDED"`.

**Warning signs:** `POST /api/v1/admin/tenants/{id}/suspend` returns 200 but member calls still succeed.

### Pitfall 3: Per-Tenant Block Doesn't Clear Sessions

**What goes wrong:** `TenantMembership.is_blocked = True` blocks the user at the tenant context dependency, but the user holds a valid access token that can access platform-level endpoints (e.g., `GET /users/me`). This is expected behavior, but the admin UI may appear to show incomplete blocking.

**Why it happens:** User block is per-tenant (locked decision). The user retains valid platform-wide access. Their access token is not invalidated.

**How to avoid:** Document the behavior clearly in API responses. The block error message should say "blocked within this tenant" not "account blocked".

**Warning signs:** Blocked user can still call `/api/v1/auth/me` — this is CORRECT behavior per the locked decision.

### Pitfall 4: MRR Trend Double-Counts Cancelled-Then-Resubscribed Plans

**What goes wrong:** Computing trend from `TenantSubscription.created_at` counts a tenant that cancelled and re-subscribed twice in the trend window.

**Why it happens:** `TenantSubscription` has one row per tenant (unique=True on tenant_id). A tenant can only have one active subscription record. When they cancel and resubscribe, the existing row is updated (status changes), not replaced. So `created_at` is the original subscription date, not the resubscription date.

**How to avoid:** Trend tracks status changes over time, not creations. Use `TenantSubscription.updated_at` to detect when status changed to ACTIVE or CANCELED within the trend window.

**Warning signs:** Trend shows MRR increasing faster than expected.

### Pitfall 5: Admin Login Issues Regular-Audience Tokens

**What goes wrong:** The admin login function calls `create_access_token(user_id)` without `extra_claims={"aud": "wxcode-adm-admin"}`. The token issued lacks the `aud` claim. Admin endpoints using `decode_admin_access_token()` reject it. Admin can't log in.

**Why it happens:** Copy-paste from regular login handler.

**How to avoid:** Create a `create_admin_access_token()` wrapper that always includes the `aud` claim. Never call `create_access_token()` directly from the admin login handler.

**Warning signs:** `/api/v1/admin/login` returns 200 with a token, but all subsequent admin calls return 401.

### Pitfall 6: Tenant List Query N+1 — Member Count Subquery

**What goes wrong:** Naively loading memberships for each tenant separately results in N+1 queries (one per tenant in the list).

**Why it happens:** Using `len(tenant.memberships)` after a simple `select(Tenant)` query triggers lazy-loading per row.

**How to avoid:** Use a correlated scalar subquery for member count in the main query, or use `select(Tenant, func.count(TenantMembership.id))` with a GROUP BY + LEFT OUTER JOIN.

**Warning signs:** Slow admin tenant list endpoint, SQLAlchemy logs showing one SELECT per tenant.

### Pitfall 7: SQLite Test Incompatibility with `ilike`

**What goes wrong:** SQLAlchemy's `.ilike()` maps to `LIKE` in SQLite (case-insensitive for ASCII) but the test may fail for non-ASCII characters.

**Why it happens:** SQLite's built-in `LIKE` is case-insensitive only for ASCII. PostgreSQL's `ILIKE` handles Unicode.

**How to avoid:** Tests should use ASCII email/name test data. The pitfall is only a production concern for non-ASCII display names. Flag this as a known limitation.

**Warning signs:** Tests pass but production search misses non-ASCII names.

---

## Code Examples

### Admin JWT — Full Round Trip

```python
# Source: verified with local PyJWT 2.11.0 runtime test

# In admin/jwt.py (new file)
import jwt
from wxcode_adm.auth.exceptions import InvalidTokenError, TokenExpiredError
from wxcode_adm.auth.jwt import create_access_token
from wxcode_adm.config import settings

ADMIN_AUDIENCE = "wxcode-adm-admin"

def create_admin_access_token(user_id: str) -> str:
    """Issue access token with aud='wxcode-adm-admin'. ONLY for admin login."""
    return create_access_token(user_id=user_id, extra_claims={"aud": ADMIN_AUDIENCE})

def decode_admin_access_token(token: str) -> dict:
    """
    Decode admin JWT. Rejects all tokens without aud='wxcode-adm-admin'.
    Regular tenant tokens (no aud claim) raise MissingRequiredClaimError -> InvalidTokenError.
    """
    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY.get_secret_value(),
            algorithms=["RS256"],
            audience=ADMIN_AUDIENCE,
        )
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise InvalidTokenError()
    return payload
```

### Tenant List with Member Count (No N+1)

```python
# Source: SQLAlchemy correlated subquery pattern

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

member_count_subq = (
    select(func.count(TenantMembership.id))
    .where(TenantMembership.tenant_id == Tenant.id)
    .correlate(Tenant)
    .scalar_subquery()
)

stmt = (
    select(Tenant, member_count_subq.label("member_count"))
    .outerjoin(TenantSubscription, TenantSubscription.tenant_id == Tenant.id)
    .options(contains_eager(...))  # if eager loading subscription
    .order_by(Tenant.created_at.desc())
    .limit(limit)
    .offset(offset)
)
rows = (await db.execute(stmt)).all()
# Each row: (Tenant instance, member_count int)
```

### IP Allowlist Parsing (Claude's Discretion)

```python
# Simple comma-separated IP list parsing
# In config.py — add ADMIN_ALLOWED_IPS setting

ADMIN_ALLOWED_IPS: str = ""  # Empty = disabled (dev-friendly)

# In admin/router.py
def _check_ip_allowlist(request: Request) -> None:
    """Check IP allowlist if ADMIN_ALLOWED_IPS is set. No-op if empty."""
    if not settings.ADMIN_ALLOWED_IPS.strip():
        return  # Allowlist disabled
    allowed = {ip.strip() for ip in settings.ADMIN_ALLOWED_IPS.split(",")}
    client_ip = request.client.host if request.client else ""
    if client_ip not in allowed:
        raise ForbiddenError(
            error_code="IP_NOT_ALLOWED",
            message="Access denied from this IP address",
        )
```

### Force Password Reset

```python
# Source: auth/service.py forgot_password + _issue_tokens patterns

async def admin_force_password_reset(
    db: AsyncSession, redis: Redis,
    user_id: uuid.UUID, reason: str, actor_id: uuid.UUID,
) -> None:
    """
    Force password reset:
    1. Set password_reset_required = True (new flag from migration 007)
    2. Delete all RefreshTokens (forces re-auth after access token expires)
    3. Blacklist all active access token JTIs
    4. Send password reset email via arq job
    5. Write audit log
    """
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError(error_code="USER_NOT_FOUND", message="User not found")

    user.password_reset_required = True

    # Blacklist active sessions
    sessions_result = await db.execute(
        select(UserSession.access_token_jti).where(UserSession.user_id == user_id)
    )
    for jti in sessions_result.scalars():
        await blacklist_jti(redis, jti)

    # Delete refresh tokens
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))

    # Enqueue reset email (reuse existing flow)
    token = generate_reset_token(user.email, _reset_salt(user))
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job("send_reset_email", str(user.id), user.email, reset_link)
    finally:
        await pool.aclose()

    await write_audit(db, action="force_password_reset", resource_type="user",
                      actor_id=actor_id, resource_id=str(user_id),
                      details={"reason": reason})
```

### Admin Rate Limiting (Claude's Discretion)

```python
# Source: auth/router.py @limiter.limit pattern

# Recommended: 10 attempts/minute for admin login
# Rationale: stricter than regular auth (5/min) but admin is a single known user
# Use IP-based rate limiting (same as rest of app)

@admin_router.post("/login")
@limiter.limit("10/minute")  # Claude's Discretion: slightly more lenient than regular auth
async def admin_login(request: Request, ...):
    ...
```

### Pagination Defaults (Claude's Discretion)

```python
# Recommended defaults based on admin use cases
# Tenants: 20 per page (admins scan, don't usually have thousands of tenants)
# Users: 20 per page (same reasoning)
# Both: max 100 per page (prevent accidental huge loads)

limit: int = Query(default=20, ge=1, le=100)
offset: int = Query(default=0, ge=0)
```

---

## Admin Router Map (Complete Endpoint Set)

```
POST   /api/v1/admin/login                          # Admin login — issues aud=admin tokens
POST   /api/v1/admin/refresh                        # Rotate admin token pair
POST   /api/v1/admin/logout                         # Blacklist admin token

GET    /api/v1/admin/tenants                        # SADM-01: List all tenants (paginated)
GET    /api/v1/admin/tenants/{tenant_id}            # SADM-01: Get single tenant details
POST   /api/v1/admin/tenants/{tenant_id}/suspend    # SADM-02: Suspend tenant
POST   /api/v1/admin/tenants/{tenant_id}/reactivate # SADM-02: Reactivate suspended tenant
DELETE /api/v1/admin/tenants/{tenant_id}            # SADM-02: Soft-delete tenant

GET    /api/v1/admin/users                          # SADM-03: Search users
GET    /api/v1/admin/users/{user_id}                # SADM-03: Get user detail (memberships+sessions)
POST   /api/v1/admin/users/{user_id}/block          # SADM-04: Block user in a tenant
POST   /api/v1/admin/users/{user_id}/unblock        # SADM-04: Unblock user in a tenant
POST   /api/v1/admin/users/{user_id}/force-reset    # SADM-04: Force password reset

GET    /api/v1/admin/dashboard/mrr                  # SADM-05: MRR dashboard snapshot
```

---

## Config Changes Required

Add to `config.py:Settings`:

```python
# Phase 8 — Super-Admin
ADMIN_ALLOWED_IPS: str = ""  # Claude's Discretion: comma-separated IPs, empty = disabled
```

No other config changes needed. `ACCESS_TOKEN_TTL_HOURS` and `REFRESH_TOKEN_TTL_DAYS` are reused as-is.

---

## main.py Router Registration

```python
# In create_app(), following the existing pattern:
from wxcode_adm.admin.router import admin_router  # noqa: PLC0415
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate admin app/port | Same app, separate JWT audience | Standard practice ~2022+ | Simpler infra, single deployment |
| Admin-only DB user | Application-level `is_superuser` flag | Project design decision (Phase 2) | Already implemented, build on it |
| MRR from Stripe API | Local DB aggregation (webhook-cached) | Phase 4 decision | No Stripe API rate limits, faster dashboard |

**No deprecated patterns in use.** PyJWT 2.x `audience=` param is the current API (PyJWT 1.x used `options={"verify_aud": True}` which is obsolete).

---

## Open Questions

1. **Admin refresh token audience**
   - What we know: Admin issues access tokens with `aud: "wxcode-adm-admin"`. Refresh tokens are opaque strings stored in DB (no JWT claim).
   - What's unclear: Should the admin `/refresh` endpoint accept ANY refresh token, or only those associated with superuser accounts?
   - Recommendation: At `/admin/refresh`, decode the incoming admin access token to get `sub`, verify `is_superuser`, then issue a new admin access token. The refresh token itself doesn't need an audience claim since it's verified by DB lookup + `is_superuser` check.

2. **MRR trend granularity**
   - What we know: Claude's Discretion on dashboard schema design. 30 days of trend data.
   - What's unclear: Should trend be daily (30 points) or weekly (4-5 points)?
   - Recommendation: Weekly (5 data points for 30 days). Daily requires 30 iterations of the historical computation, weekly is simpler and sufficient for trend visibility. Return as `List[{"week_start": ISO8601, "mrr_cents": int}]`.

3. **`is_deleted` Tenant visibility**
   - What we know: Soft-deleted tenants have `is_deleted=True`. Data retained indefinitely.
   - What's unclear: Should deleted tenants appear in the admin tenant list by default?
   - Recommendation: Default `status` filter shows only non-deleted tenants. Pass `status=deleted` to see deleted ones. This matches the `status=active|suspended|deleted` filter pattern.

4. **Force password reset for OAuth-only users**
   - What we know: `User.password_hash` is nullable for OAuth-only users. `forgot_password` handles this via `_reset_salt(user)`.
   - What's unclear: Can admin force-reset an OAuth-only user (no password to reset)?
   - Recommendation: For OAuth-only users, `force_password_reset` should: set `password_reset_required=True`, revoke sessions, but NOT send a reset email (they have no password). Instead, audit log notes "OAuth-only user — session invalidated, no email sent". This edge case should be documented in the endpoint schema.

---

## Sources

### Primary (HIGH confidence)

- Local codebase — `backend/src/wxcode_adm/` — all modules read directly
- PyJWT 2.11.0 runtime test (local Python) — `audience=` param behavior confirmed with actual encode/decode calls
- SQLAlchemy async documentation patterns — used throughout existing codebase

### Secondary (MEDIUM confidence)

- PyJWT 2.x changelog / docs — `audience` parameter in `jwt.decode()` is the documented API
- Existing `billing/router.py` `require_superuser` pattern — used as baseline for `require_admin`
- Existing `audit/router.py` pagination pattern — confirmed working in production setup

### Tertiary (LOW confidence)

- MRR trend weekly granularity recommendation — based on common dashboard UX patterns, not a formal source

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, all existing libraries verified
- Architecture: HIGH — follows exact patterns from 7 prior phases of this codebase
- JWT isolation: HIGH — verified with local PyJWT 2.11.0 runtime tests
- MRR aggregation: HIGH — `TenantSubscription` + `Plan` models read directly
- Migration columns: HIGH — derived directly from locked decisions
- Trend calculation: MEDIUM — algorithm correct but granularity is Claude's Discretion
- Pitfalls: HIGH — most derived from verified code analysis

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (stable stack, 30-day estimate)
