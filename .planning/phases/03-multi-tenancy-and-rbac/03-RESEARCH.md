# Phase 3: Multi-Tenancy and RBAC - Research

**Researched:** 2026-02-23
**Domain:** FastAPI multi-tenancy, RBAC dependency injection, SQLAlchemy association object pattern, invitation token flow
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Tenant identity & onboarding
- Tenant is NOT created during sign-up — sign-up stays lean (email/password only)
- After sign-up + email verification, a separate onboarding step asks for workspace name
- Only workspace name is collected (single field) — slug is auto-generated from it
- Display name can be changed anytime; slug is permanent once set
- Users in "no tenant" state (just signed up, haven't created or joined a workspace) can access profile/account endpoints but tenant-scoped operations return 403 with clear message

#### Invitation rules
- Multi-tenant membership: a user can belong to multiple tenants simultaneously
- Per-tenant roles: role is per membership, not global (Owner in Tenant A, Viewer in Tenant B)
- Current tenant context determined by `X-Tenant-ID` (or slug) header on each request — stateless, explicit
- New user invitation flow: invite link → sign-up → email verification → auto-join tenant (no separate accept step)
- Existing user invitation: standard accept flow (user already has account, accepts to join the new tenant)
- 7-day expiry on invitation tokens (from roadmap)

#### Role permission boundaries
- Role hierarchy: Owner > Admin > Developer > Viewer (4 roles, not 5)
- Billing is NOT a role — it's a permission toggle ("billing access") that can be added to any role
- Role changes are immediate — Owner/Admin changes a member's role, takes effect instantly, no confirmation needed
- Owner cannot demote themselves — must transfer ownership first (prevents lockout)
- Claude's Discretion: exact Developer vs Viewer permission boundary (Developer can likely manage API keys and sensitive config; Viewer is read-only)

#### Member removal & re-entry
- Removed member's account persists — they just lose membership in that tenant, can still access other tenants
- Re-invitation is allowed immediately — no cooldown after removal, clean slate with new role
- Members can voluntarily leave a tenant (self-service), except Owner who must transfer ownership first
- Ownership transfer requires acceptance — target member gets a transfer request and must accept; current Owner retains ownership until accepted; upon acceptance, previous Owner is downgraded to Admin

### Claude's Discretion
- Developer vs Viewer exact permission matrix
- Slug generation algorithm (from workspace name)
- Invitation email content and formatting
- How "no tenant" state is communicated in API responses
- Tenant context validation (what happens if header references a tenant the user doesn't belong to)

### Deferred Ideas (OUT OF SCOPE)
- Tenant subdomain routing (my-company.wxcode.com) — future consideration, slug is prepared for it
- Tenant settings/preferences page — Phase 7 or later
- Team/group-based permissions within a tenant — not in scope, individual roles only
</user_constraints>

<phase_requirements>
## Phase Requirements

Note: CONTEXT decisions override original requirement text where they conflict.

| ID | Original Description | Actual Requirement (per CONTEXT) | Research Support |
|----|---------------------|----------------------------------|-----------------|
| TNNT-01 | Tenant auto-created on user sign-up | Tenant created in separate onboarding step after email verification | Onboarding endpoint pattern; `POST /api/v1/onboarding/workspace` |
| TNNT-02 | Tenant has human-readable slug identifier | Slug auto-generated from workspace name; permanent once set | python-slugify 8.0.4 + uniqueness collision strategy |
| TNNT-03 | User invitation by email with 7-day expiry token | Two distinct flows: new-user (auto-join) and existing-user (accept flow); itsdangerous token, max_age=604800 | itsdangerous URLSafeTimedSerializer; arq email job pattern from Phase 2 |
| TNNT-04 | Invited user belongs exclusively to the inviting tenant | Multi-tenant: user joins tenant without leaving others; per-tenant role via TenantMembership | Association object pattern (TenantMembership model) |
| TNNT-05 | Owner can transfer ownership to another member | Two-step: request stored in DB, target must accept; Owner stays Owner until acceptance | OwnershipTransfer model or status field on membership |
| RBAC-01 | 5 roles enforced | 4 roles (Owner/Admin/Developer/Viewer) + billing_access boolean toggle | Python Enum with native_enum=False; role_level integer for comparison |
| RBAC-02 | Owner/Admin can change member roles | Immediate role change; Owner cannot self-demote | require_role dependency factory with minimum level check |
| RBAC-03 | Owner/Admin can remove members from tenant | Soft-delete membership row; account persists | DELETE on TenantMembership row; ForbiddenError guard |
</phase_requirements>

---

## Summary

Phase 3 introduces three interconnected concerns: the data model (Tenant + TenantMembership association), the runtime context plumbing (X-Tenant-ID header → dependency chain), and the RBAC enforcement (role hierarchy → require_role factory). All three must be designed together because they share the TenantMembership join record as the single source of truth for "who belongs to which tenant with what role."

The existing codebase provides strong foundation patterns that Phase 3 extends. The tenant isolation guard (`install_tenant_guard`) is already live but fires `TenantIsolationError` on unguarded queries — Phase 3 must satisfy it by passing `execution_options(_tenant_enforced=True)` on every query against `TenantModel` subclasses. The `itsdangerous.URLSafeTimedSerializer` is already used for password reset tokens and exactly the right tool for invitation tokens. The `arq` email job pattern (`enqueue_job` → worker function) is established and just needs new job types for invitation emails.

The key architectural decision that drives everything else: `TenantMembership` is an **association object** (not a pure secondary join table) because it carries `role`, `billing_access`, and `invited_by` extra columns. This means user↔tenant queries traverse through the membership record explicitly, and the RBAC dependency loads the current membership to read the role. The tenant guard must be satisfied separately for `Tenant` queries (use `execution_options`) and for `TenantModel` subclass queries (tenant_id filter + option).

**Primary recommendation:** Build the data model and tenant context dependency first (Plan 03-01 and 03-02), then add invitation flow (03-03), member management (03-04), and close with cross-tenant isolation tests (03-05). Each plan is independently testable.

---

## Standard Stack

### Core (all already in pyproject.toml from Phases 1-2)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0 (async) | ORM + TenantModel/TenantMembership models | Already established; async pattern proven in Phase 2 |
| FastAPI | current | Router, Header dep, Depends chain | Already established; Header(convert_underscores) handles X-Tenant-ID |
| itsdangerous | 2.2.x | Invitation token (URLSafeTimedSerializer) | Already in use for password reset tokens; same pattern |
| python-slugify | 8.0.4 | Workspace name → URL slug | Handles unicode; standard library for slug generation |
| arq | current | Invitation email job enqueueing | Already established; same enqueue_job pattern |
| Alembic | current | Migration 002_add_tenants_and_memberships | Already established; migration 001 is the pattern |

### New Addition

| Library | Version | Purpose | Installation |
|---------|---------|---------|-------------|
| python-slugify | 8.0.4 | Workspace name → URL-safe slug | `pip install python-slugify` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-slugify | Manual re.sub + lower() | python-slugify handles unicode, accented chars, edge cases; hand-rolling misses "Ångström" → "angstrom" |
| itsdangerous for invitation | Storing token in DB | DB tokens are fine but itsdangerous is already in the project; same pattern consistency |
| itsdangerous for ownership transfer | DB status field | Ownership transfer is stored in DB (two-step needs persistence between request cycles); itsdangerous alone is stateless and can't be "pending" |

**Installation (new only):**
```bash
pip install python-slugify
```

---

## Architecture Patterns

### Recommended Project Structure

```
backend/src/wxcode_adm/
├── tenants/
│   ├── __init__.py          # (exists, empty)
│   ├── models.py            # Tenant, TenantMembership, OwnershipTransfer
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── service.py           # Business logic: create_workspace, invite, accept, transfer
│   ├── exceptions.py        # TenantNotFoundError, NotMemberError, InsufficientRoleError
│   ├── dependencies.py      # get_tenant_context, require_role, require_tenant_member
│   ├── router.py            # /api/v1/onboarding, /api/v1/tenants, /api/v1/invitations
│   └── email.py             # send_invitation_email arq job function
├── db/
│   └── tenant.py            # (exists) TenantModel guard — Phase 3 upgrades WARNING → RuntimeError
├── alembic/versions/
│   └── 002_add_tenants_and_memberships.py
└── tests/
    └── test_tenants.py      # integration tests for all Phase 3 endpoints
```

### Pattern 1: TenantMembership as Association Object

The join between `User` and `Tenant` carries extra data (`role`, `billing_access`, `invited_by_id`), so it MUST be an association object, not a secondary table.

**What:** A mapped class that IS the join table. Queried explicitly; not transparent.
**When to use:** Any many-to-many where the join record has extra columns.

```python
# Source: SQLAlchemy 2.0 docs - association object pattern
import enum
import uuid
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from wxcode_adm.db.base import Base, TimestampMixin


class MemberRole(enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"

    # Integer level for "minimum role" comparison in require_role
    @property
    def level(self) -> int:
        return {"owner": 4, "admin": 3, "developer": 2, "viewer": 1}[self.value]


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)

    # Relationship to memberships (not directly to Users — traverse via TenantMembership)
    memberships: Mapped[list["TenantMembership"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class TenantMembership(TimestampMixin, Base):
    """
    Association object: User <-> Tenant with per-membership role.
    This is the single source of truth for RBAC.
    """
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_tenant_memberships_user_tenant"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MemberRole] = mapped_column(
        sqlalchemy.Enum(MemberRole, native_enum=False, length=20),
        nullable=False,
    )
    billing_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id], back_populates="memberships")
    tenant: Mapped["Tenant"] = relationship(back_populates="memberships")
```

### Pattern 2: Tenant Context Dependency Chain

**What:** A two-level dependency chain. First level resolves and validates tenant from header. Second level loads the user's membership (role) within that tenant.
**When to use:** On all tenant-scoped endpoints.

```python
# Source: FastAPI docs - Header params + official pattern (verified)
from typing import Annotated
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.auth.models import User
from wxcode_adm.dependencies import get_session
from wxcode_adm.tenants.models import Tenant, TenantMembership, MemberRole
from wxcode_adm.tenants.exceptions import (
    NoTenantContextError,   # 403 — no tenant header supplied
    TenantNotFoundError,    # 404 — tenant not found or not member
    InsufficientRoleError,  # 403 — role below required level
)


async def get_tenant_context(
    x_tenant_id: Annotated[str | None, Header()] = None,
    user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_session),
) -> tuple[Tenant, TenantMembership]:
    """
    Resolve tenant from X-Tenant-ID header and verify user membership.

    Returns (tenant, membership) tuple.
    Raises NoTenantContextError (403) if header absent.
    Raises TenantNotFoundError (404) if tenant not found or user not a member.
    """
    if not x_tenant_id:
        raise NoTenantContextError()

    # Try UUID first, then slug
    try:
        tenant_uuid = uuid.UUID(x_tenant_id)
        stmt = select(Tenant).where(Tenant.id == tenant_uuid)
    except ValueError:
        stmt = select(Tenant).where(Tenant.slug == x_tenant_id)

    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise TenantNotFoundError()

    # Load membership
    membership_result = await db.execute(
        select(TenantMembership)
        .where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == user.id,
        )
        .execution_options(_tenant_enforced=True)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        raise TenantNotFoundError()  # Don't reveal tenant exists to non-members

    return tenant, membership


def require_role(minimum_role: MemberRole):
    """
    Dependency factory: returns a dependency that enforces a minimum role.

    Usage:
        @router.post("/settings")
        async def update_settings(
            ctx: Annotated[tuple, Depends(require_role(MemberRole.ADMIN))]
        ):
            tenant, membership = ctx
    """
    async def _check_role(
        ctx: tuple[Tenant, TenantMembership] = Depends(get_tenant_context),
    ) -> tuple[Tenant, TenantMembership]:
        tenant, membership = ctx
        if membership.role.level < minimum_role.level:
            raise InsufficientRoleError()
        return tenant, membership

    return _check_role
```

### Pattern 3: Tenant Guard Satisfaction

All queries on `TenantModel` subclasses MUST pass `execution_options(_tenant_enforced=True)`. This is how the Phase 1 guard is satisfied. The guard checks for this option before allowing the SELECT through.

```python
# Source: wxcode_adm/db/tenant.py (codebase) — verified existing behavior
# Pattern for any TenantModel subclass query:

# CORRECT — passes the guard option
result = await db.execute(
    select(SomeTenantModel)
    .where(SomeTenantModel.tenant_id == tenant.id)
    .execution_options(_tenant_enforced=True)
)

# WRONG — raises TenantIsolationError at runtime
result = await db.execute(
    select(SomeTenantModel).where(SomeTenantModel.tenant_id == tenant.id)
    # Missing execution_options — guard fires
)
```

Note: `Tenant` itself and `TenantMembership` are NOT `TenantModel` subclasses (they have no `tenant_id` column) — they use `Base + TimestampMixin` directly. The guard only fires on models that inherit `TenantModel`.

### Pattern 4: Invitation Token (itsdangerous)

The project already uses `URLSafeTimedSerializer` for password reset. The same pattern applies to invitations. The key difference: invitation tokens include `email` + `tenant_id` in the payload, and `max_age=604800` (7 days).

```python
# Source: auth/service.py (codebase) + itsdangerous docs
from itsdangerous import URLSafeTimedSerializer
from itsdangerous.exc import BadSignature, SignatureExpired

# Use the same JWT_PRIVATE_KEY secret, different salt namespace
invitation_serializer = URLSafeTimedSerializer(
    settings.JWT_PRIVATE_KEY.get_secret_value(),
    salt="tenant-invitation",
)

def generate_invitation_token(email: str, tenant_id: str) -> str:
    """Generate a 7-day invitation token encoding email + tenant_id."""
    return invitation_serializer.dumps({"email": email, "tenant_id": tenant_id})

def verify_invitation_token(token: str) -> dict:
    """
    Verify invitation token, return payload dict.
    Raises TokenExpiredError or InvalidTokenError.
    max_age=604800 = 7 days in seconds.
    """
    try:
        return invitation_serializer.loads(token, max_age=604800)
    except SignatureExpired:
        raise TokenExpiredError()
    except BadSignature:
        raise InvalidTokenError()
```

### Pattern 5: Slug Generation with Uniqueness

`python-slugify` handles the base slug. Uniqueness collision handling must be done at the service layer because the DB uniqueness constraint will raise an `IntegrityError` on collision.

```python
# Source: python-slugify 8.0.4 docs + service layer pattern
from slugify import slugify
from sqlalchemy import select

async def generate_unique_slug(db: AsyncSession, name: str) -> str:
    """
    Generate a URL-safe slug from workspace name, appending a counter on collision.
    'My Workspace' → 'my-workspace'
    'My Workspace' (collision) → 'my-workspace-2', 'my-workspace-3', ...
    """
    base_slug = slugify(name, max_length=80)  # max 80 chars for base
    slug = base_slug
    counter = 2

    while True:
        existing = await db.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        if existing.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1
```

### Pattern 6: Ownership Transfer (Two-Step, DB-Persisted)

Ownership transfer is NOT stateless (unlike invitation tokens) because the pending state must survive between request cycles. Store the pending transfer in a DB record.

```python
# Design for OwnershipTransfer model
class OwnershipTransfer(TimestampMixin, Base):
    """
    Pending ownership transfer request.
    One active row per tenant at most — new request replaces old.
    """
    __tablename__ = "ownership_transfers"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # Only one pending transfer per tenant
        index=True,
    )
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # No separate "accept" token needed — the to_user authenticates via JWT
    # and the endpoint confirms their identity + membership before accepting
```

### Anti-Patterns to Avoid

- **Using `TenantModel` for `Tenant` and `TenantMembership` themselves:** These are platform-level tables (they span tenants). Only rows WITHIN a tenant (e.g., API keys, projects) should inherit `TenantModel`.
- **Storing tenant context in Python thread-local or contextvars:** FastAPI's async model means requests can interleave; use explicit dependency injection per request instead.
- **Using SQLAlchemy `relationship.secondary` for the membership join:** The membership has extra columns (role, billing_access) so the association object pattern is required — secondary-only approach loses the extra data.
- **Native PostgreSQL ENUM for `MemberRole`:** Native enums require `CREATE TYPE` DDL and make Alembic migrations painful when adding new role values. Use `native_enum=False` (VARCHAR + Python validation) for a role enum that could evolve.
- **Checking role by string comparison:** Use `membership.role.level >= required.level` (integer comparison via `@property`) to support "Admin or above" without listing all qualifying roles.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slug generation from unicode names | Custom regex substitution | python-slugify 8.0.4 | Handles accented chars, CJK, mixed scripts; already used at PyPI |
| Timed invitation tokens | Custom HMAC + base64 + expiry | itsdangerous URLSafeTimedSerializer | Already in project for password reset; handles signature, timing, salt namespacing |
| Role hierarchy comparison | String list comparison | `MemberRole.level` property (integer) | Avoids listing all qualifying roles per check; easy to add new levels |
| Uniqueness constraint violation handling | Try/except IntegrityError | Pre-check query + slug counter loop | IntegrityError handling is dialect-specific and awkward; explicit pre-check is clear and testable |

**Key insight:** The project already has the two hardest "from scratch" pieces (itsdangerous for tokens, arq for email jobs). Phase 3 is primarily data model + dependency wiring on top of the existing foundation.

---

## Common Pitfalls

### Pitfall 1: Native PostgreSQL ENUM for MemberRole

**What goes wrong:** Using SQLAlchemy `Enum(MemberRole)` with default `native_enum=True` creates a PostgreSQL `CREATE TYPE memborrole AS ENUM (...)`. When a new role needs to be added, the migration must `ALTER TYPE ... ADD VALUE` which cannot be run inside a transaction — Alembic's transaction wrapping causes the migration to fail.

**Why it happens:** SQLAlchemy defaults to native enums on PostgreSQL because they are more space-efficient. But they are harder to alter.

**How to avoid:** Declare `Enum(MemberRole, native_enum=False, length=20)` explicitly. This stores values as VARCHAR(20) with Python-level validation. Adding a new role value is a code-only change with no DDL migration required.

**Warning signs:** Migration fails with `cannot run inside a transaction block` or `ALTER TYPE ADD VALUE cannot be used in a transaction`.

### Pitfall 2: Forgetting execution_options on TenantModel Queries

**What goes wrong:** Any `SELECT` on a `TenantModel` subclass without `.execution_options(_tenant_enforced=True)` raises `TenantIsolationError` (HTTP 500). The guard was installed in Phase 1 and runs on every SELECT.

**Why it happens:** Developer adds a new query against a model that inherits `TenantModel` but forgets the execution option. The error is a 500 (programming error) not a 404/403.

**How to avoid:** In Phase 3, `Tenant` and `TenantMembership` do NOT inherit `TenantModel` so they are not guarded. But any future model in the `tenants/` module that stores per-tenant data (e.g., `ApiKey`, `AuditLog`) will inherit `TenantModel` and must always include the option.

**Warning signs:** `TenantIsolationError: Unguarded query on TenantModel subclass` in logs. This is always a developer error.

### Pitfall 3: X-Tenant-ID Header Case Sensitivity

**What goes wrong:** HTTP headers are case-insensitive, but FastAPI's `Header()` dependency uses Python parameter name conventions: `x_tenant_id` (underscores) maps to `X-Tenant-Id` (hyphenated, title-case). If the client sends `X-Tenant-ID` (capital ID) it still works because headers are case-insensitive in ASGI. But if you declare the parameter name wrong in Python (e.g., `XTenantID`) it won't be found.

**How to avoid:** Use `x_tenant_id: Annotated[str | None, Header()] = None` — FastAPI converts underscores to hyphens automatically. `x_tenant_id` → `X-Tenant-Id` and HTTP clients sending `X-Tenant-ID` are matched case-insensitively.

### Pitfall 4: Conftest SQLite Metadata for New Models

**What goes wrong:** The test conftest's `_build_sqlite_metadata()` function manually imports model modules to register them in `Base.metadata`. If `wxcode_adm.tenants.models` is not imported in the conftest, the `tenants` and `tenant_memberships` tables won't exist in the test SQLite DB, and tests fail with `no such table`.

**How to avoid:** Add `import wxcode_adm.tenants.models  # noqa: F401` to the conftest's `_build_sqlite_metadata()` function alongside the existing auth models import.

**Warning signs:** `OperationalError: no such table: tenants` or `no such table: tenant_memberships` in test output.

### Pitfall 5: Owner Self-Demotion Guard Ordering

**What goes wrong:** If role-change logic checks "new role is valid" before checking "is the target user the Owner trying to self-demote," a bug lets the Owner set themselves to Viewer momentarily before the guard catches it.

**How to avoid:** Check owner self-demotion FIRST in the service function, before any role validation:

```python
# CORRECT order:
if target_membership.role == MemberRole.OWNER and target_membership.user_id == actor.id:
    raise ForbiddenError("OWNER_CANNOT_SELF_DEMOTE", "Transfer ownership first")
# Then proceed with role change
```

### Pitfall 6: Slug Uniqueness Race Condition

**What goes wrong:** Two concurrent requests for the same workspace name both check the DB (slug free), both proceed, and one gets an `IntegrityError` on commit.

**Why it happens:** The pre-check query + slug assignment is not atomic.

**How to avoid:** The `UNIQUE` constraint on `tenants.slug` is the authoritative guard. Let the service pre-check generate an initial candidate, but wrap the `db.flush()` in a try/except for `IntegrityError` and retry with an incremented counter. Alternatively, the uniqueness constraint plus PostgreSQL's `ON CONFLICT` is the correct backstop. The race condition is extremely rare in practice (two people creating the exact same workspace name within milliseconds).

### Pitfall 7: Invitation Token for New vs. Existing Users

**What goes wrong:** Using a single invitation flow for both new and existing users. A new user (no account yet) needs to sign up first, then their invitation token triggers auto-join. An existing user just needs to accept.

**How to avoid:** The invitation token payload should encode `invited_email`. At accept time:
1. Check if a User with that email exists.
2. If yes: auto-add to tenant (or show acceptance UI).
3. If no: redirect to sign-up. After sign-up + email verification, the stored invitation (by email lookup) triggers auto-join.

Store the invitation metadata in DB (email + tenant_id + token_hash + expires_at) so it can be looked up after sign-up completes. The itsdangerous token is the URL-safe representation; the DB record is the authoritative state.

---

## Code Examples

### Tenant Context Dependency (verified against FastAPI docs)

```python
# Source: FastAPI Header docs (https://fastapi.tiangolo.com/tutorial/header-params/)
# X-Tenant-ID header → x_tenant_id parameter (FastAPI auto-converts underscores to hyphens)

from typing import Annotated
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

async def get_tenant_context(
    x_tenant_id: Annotated[str | None, Header()] = None,
    user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_session),
) -> tuple[Tenant, TenantMembership]:
    if not x_tenant_id:
        raise NoTenantContextError()  # 403 with TENANT_CONTEXT_REQUIRED error_code
    # ... resolve tenant and membership
```

### require_role Dependency Factory (verified against FastAPI docs)

```python
# Source: FastAPI dependency injection docs + project patterns
# A closure that returns a dependency function — standard FastAPI pattern

def require_role(minimum_role: MemberRole):
    """
    Dependency factory. Returns async dependency that enforces minimum role.
    Usage: Depends(require_role(MemberRole.ADMIN))
    """
    async def _check(
        ctx: tuple[Tenant, TenantMembership] = Depends(get_tenant_context),
    ) -> tuple[Tenant, TenantMembership]:
        tenant, membership = ctx
        if membership.role.level < minimum_role.level:
            raise InsufficientRoleError(
                message=f"Requires {minimum_role.value} role or above"
            )
        return ctx
    return _check
```

### Invitation Token Generation (consistent with existing auth/service.py pattern)

```python
# Source: project codebase auth/service.py (reset_serializer pattern)
# Invitation uses same serializer approach with different salt + payload

invitation_serializer = URLSafeTimedSerializer(
    settings.JWT_PRIVATE_KEY.get_secret_value(),
    salt="tenant-invitation",  # namespaced from "password-reset" salt
)

def generate_invitation_token(email: str, tenant_id: str) -> str:
    return invitation_serializer.dumps({"email": email, "tenant_id": tenant_id})

def verify_invitation_token(token: str) -> dict:
    try:
        return invitation_serializer.loads(token, max_age=7 * 24 * 3600)  # 7 days
    except SignatureExpired:
        raise TokenExpiredError()
    except BadSignature:
        raise InvalidTokenError()
```

### Alembic Migration Pattern (follow existing 001 style)

```python
# Source: alembic/versions/001_add_users_and_refresh_tokens_tables.py (codebase)
# Follow same column ordering: id, created_at, updated_at, then domain columns

def upgrade() -> None:
    # 1. tenants table (no FKs, create first)
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=True)

    # 2. tenant_memberships table (FKs to users + tenants)
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        # ... columns ...
        sa.UniqueConstraint("user_id", "tenant_id", name=op.f("uq_tenant_memberships_user_tenant")),
    )

    # 3. invitations table
    # 4. ownership_transfers table
```

### TenantModel Guard Upgrade (Phase 1 note)

The Phase 1/01-01 plan noted: `TenantModel guard uses logged WARNING in Phase 1 — upgrades to RuntimeError in Phase 3`. The guard was already upgraded in Plan 01-04 to raise `TenantIsolationError`. No further upgrade needed here. The current behavior is correct.

### Developer vs. Viewer Permission Matrix (Claude's Discretion)

Based on the phase context (`Developer can likely manage API keys and sensitive config; Viewer is read-only`) and the analogy to Slack/Discord:

| Action | Owner | Admin | Developer | Viewer |
|--------|-------|-------|-----------|--------|
| View tenant data | Yes | Yes | Yes | Yes |
| Invite members | Yes | Yes | No | No |
| Change member roles | Yes | Yes | No | No |
| Remove members | Yes | Yes | No | No |
| Manage API keys (Phase 5) | Yes | Yes | Yes | No |
| View API keys (Phase 5) | Yes | Yes | Yes | No |
| Billing access (toggle) | Configurable | Configurable | Configurable | Configurable |
| Transfer ownership | Yes | No | No | No |
| Leave tenant | Yes* | Yes | Yes | Yes |
| Change tenant display name | Yes | Yes | No | No |

*Owner must transfer first.

**Recommendation:** `require_role(MemberRole.DEVELOPER)` for API key management. `require_role(MemberRole.ADMIN)` for member management and invitations. `require_role(MemberRole.OWNER)` for ownership transfer initiation.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-tenant per user | Multi-tenant membership (Slack model) | CONTEXT.md decision | TenantMembership association object, not a single FK on User |
| Native PostgreSQL ENUM | VARCHAR + Python Enum (native_enum=False) | Alembic limitation | Simpler migrations when adding role values |
| Tenant created at signup | Separate onboarding step | CONTEXT.md decision | No `Tenant` row until `POST /onboarding/workspace` |
| 5 roles (Owner/Admin/Developer/Viewer/Billing) | 4 roles + billing_access boolean | CONTEXT.md decision | `billing_access: bool` column on `TenantMembership` |
| Ownership transfer: immediate | Two-step: request + accept | CONTEXT.md decision | `OwnershipTransfer` DB table for pending state |

**Deprecated/outdated (from original requirements):**
- TNNT-01 "auto-created on sign-up": superseded by explicit onboarding step
- TNNT-04 "exclusively bound": superseded by multi-tenant membership
- RBAC-01 "5 roles including Billing": superseded by 4 roles + billing_access toggle

---

## Existing Codebase Integration Notes

These are codebase-specific facts the planner must know:

### TenantModel Guard is Already Active (Phase 1)
- `install_tenant_guard(async_session_maker)` runs at startup in `main.py`
- Guard raises `TenantIsolationError` on any SELECT without `execution_options(_tenant_enforced=True)`
- `Tenant` and `TenantMembership` are NOT `TenantModel` subclasses — they need NO option
- Any Phase 3 model that DOES inherit `TenantModel` requires the option on every query

### Alembic env.py Has Placeholder for tenants Import
- Line 17 in `alembic/env.py`: `# from wxcode_adm.tenants import models as _  # noqa`
- Un-comment this when creating the migration so autogenerate finds the new models

### conftest.py Must Import New Models
- `_build_sqlite_metadata()` has `import wxcode_adm.auth.models  # noqa: F401`
- Phase 3 must add `import wxcode_adm.tenants.models  # noqa: F401` to the same function
- The `test_db` fixture calls `Base.metadata.create_all` — models must be imported before this runs

### arq Worker Must Register New Email Jobs
- `worker.py` lists jobs in `WorkerSettings.functions`
- Phase 3 `send_invitation_email` job must be added to this list
- Pattern is established: function defined in `tenants/email.py`, imported + registered in `worker.py`

### Error Pattern: AppError Subclasses
- All domain errors inherit from `AppError` (or `ForbiddenError`, `NotFoundError`, `ConflictError`)
- The global handler in `main.py` translates them to `{"error_code": ..., "message": ...}` JSON
- Phase 3 new exceptions follow same pattern — no HTTPException ever raised directly

### get_session Dependency Commits on Success
- The `get_session` dependency in `dependencies.py` commits on success, rolls back on exception
- Service functions call `db.add()`, `db.flush()`, modify ORM objects — session commits automatically
- No explicit `await db.commit()` needed in service functions

### Invitation Token Serializer Must Be Defined at Module Level
- The `reset_serializer` in `auth/service.py` is a module-level singleton
- The monkeypatch in `conftest.py` must patch it explicitly for tests
- Phase 3's `invitation_serializer` in `tenants/service.py` follows the same pattern and needs the same conftest treatment

---

## Open Questions

1. **Where to store pending invitations (for new-user flow)**
   - What we know: New users sign up THEN auto-join. The invitation token must survive the sign-up → verify → join sequence.
   - What's unclear: Store invitation state in DB (Invitation model with email+tenant_id+token_hash+expires_at) vs. rely solely on the signed token URL that the new user carries through sign-up.
   - Recommendation: Use a DB `Invitation` table. The token in the URL is the delivery mechanism; the DB record is the authoritative state. On sign-up, the invitation email link includes the token as a query parameter. After email verification, the client passes the token to `POST /invitations/accept`. This avoids re-parsing a URL parameter across multiple redirect hops.

2. **Slug uniqueness for short/common workspace names**
   - What we know: Slugify + counter loop is the pattern; slug is permanent once set.
   - What's unclear: Maximum counter iterations before giving up (or proposing a different name).
   - Recommendation: Cap at 10 iterations in the loop. If all `my-workspace` through `my-workspace-10` are taken, raise `ConflictError("SLUG_UNAVAILABLE", "Workspace name is taken, try a different one")`. This is a soft failure — user just picks another name.

3. **Tenant context when header references unknown/non-member tenant**
   - What we know: CONTEXT says this is Claude's Discretion.
   - Recommendation: Return `404 TENANT_NOT_FOUND` ("Tenant not found or you are not a member") — this prevents leaking information about whether a tenant exists to non-members. Same message for "doesn't exist" and "you're not a member."

4. **No-tenant state response for tenant-scoped endpoints**
   - What we know: CONTEXT says 403 with clear message.
   - Recommendation: `403 TENANT_CONTEXT_REQUIRED` with message "This endpoint requires a tenant context. Include X-Tenant-ID header or complete workspace setup at POST /api/v1/onboarding/workspace."

---

## Sources

### Primary (HIGH confidence)
- Existing codebase (`wxcode_adm/db/tenant.py`, `auth/service.py`, `auth/dependencies.py`, `tests/conftest.py`) — codebase patterns verified by direct read
- FastAPI official docs (https://fastapi.tiangolo.com/tutorial/header-params/) — Header dependency pattern, underscore-to-hyphen conversion
- SQLAlchemy 2.0 official docs (https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#association-object) — Association object pattern
- SQLAlchemy 2.0 official docs (https://docs.sqlalchemy.org/en/20/orm/session_basics.html) — execution_options() on SELECT statements
- itsdangerous official docs (https://itsdangerous.palletsprojects.com/en/2.2.x/url_safe/) — URLSafeTimedSerializer API

### Secondary (MEDIUM confidence)
- python-slugify 8.0.4 PyPI (https://pypi.org/project/python-slugify/) — version, unicode handling, max_length parameter
- SQLAlchemy 2.0 docs on Enum type (https://docs.sqlalchemy.org/en/20/core/type_basics.html) — native_enum parameter, VARCHAR strategy
- Alembic enum migration articles — native_enum=False recommendation for evolvable enums

### Tertiary (LOW confidence)
- WebSearch results on FastAPI RBAC patterns — general direction confirmed but not specific implementation; codebase patterns took precedence

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All libraries either already in project or verified via official PyPI page
- Architecture (data model): HIGH — SQLAlchemy association object is official documented pattern; codebase structure follows established Phase 2 conventions
- Architecture (dependency chain): HIGH — FastAPI Header docs verified; pattern consistent with existing `get_current_user` → `require_verified` chain
- Invitation token: HIGH — Same itsdangerous pattern already in project for password reset
- Pitfalls: HIGH — Most pitfalls derived from reading actual codebase code (guard, conftest, alembic env)
- Permission matrix: MEDIUM — Claude's Discretion area; reasonable defaults based on Slack/Discord analogy in CONTEXT

**Research date:** 2026-02-23
**Valid until:** 2026-03-23 (30 days — SQLAlchemy and FastAPI stable; python-slugify stable)
