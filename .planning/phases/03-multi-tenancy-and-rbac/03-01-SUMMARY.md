---
phase: 03-multi-tenancy-and-rbac
plan: 01
subsystem: database
tags: [sqlalchemy, pydantic, tenants, rbac, python-slugify, enums]

# Dependency graph
requires:
  - phase: 02-auth-core
    provides: "User model (users.id FK target), Base+TimestampMixin base classes, ForbiddenError/NotFoundError/ConflictError exception bases"
provides:
  - "Tenant SQLAlchemy model (tenants table)"
  - "TenantMembership SQLAlchemy model (tenant_memberships table) with MemberRole enum"
  - "Invitation SQLAlchemy model (invitations table) with billing_access and token_hash"
  - "OwnershipTransfer SQLAlchemy model (ownership_transfers table)"
  - "MemberRole enum with 4 values (OWNER, ADMIN, DEVELOPER, VIEWER) and level property"
  - "9 tenant domain exceptions (NoTenantContextError, TenantNotFoundError, InsufficientRoleError, etc.)"
  - "Pydantic v2 request/response schemas for all tenant endpoints"
  - "python-slugify 8.0.4 installed for workspace slug generation"
  - "User.memberships relationship on auth User model"
  - "ROADMAP.md Phase 3 SC1/SC2/SC3 aligned with locked CONTEXT.md decisions"
affects: [03-02, 03-03, 03-04, 03-05]

# Tech tracking
tech-stack:
  added:
    - "python-slugify==8.0.4 (workspace slug generation)"
  patterns:
    - "native_enum=False on all MemberRole SQLAlchemy columns (avoids PostgreSQL enum type + Alembic migration issues)"
    - "from __future__ import annotations for Python 3.9 compat (Optional union types)"
    - "String ForeignKey references in relationships (avoids circular imports between tenants/models.py and auth/models.py)"
    - "Invitation.billing_access propagates to TenantMembership.billing_access on acceptance"

key-files:
  created:
    - "backend/src/wxcode_adm/tenants/models.py"
    - "backend/src/wxcode_adm/tenants/exceptions.py"
    - "backend/src/wxcode_adm/tenants/schemas.py"
  modified:
    - "backend/pyproject.toml (added python-slugify==8.0.4)"
    - "backend/src/wxcode_adm/auth/models.py (added User.memberships relationship)"
    - ".planning/ROADMAP.md (aligned Phase 3 SC1/SC2/SC3)"

key-decisions:
  - "native_enum=False on MemberRole Enum columns — avoids PostgreSQL CREATE TYPE and Alembic migration issues (RESEARCH.md pitfall #1)"
  - "from __future__ import annotations added to tenants/models.py — Python 3.9.6 does not support X | None syntax at runtime; Optional[X] used instead"
  - "billing_access is Boolean toggle on TenantMembership (not a role) — consistent with CONTEXT.md decision; propagated from Invitation on acceptance"
  - "User.memberships foreign_keys='TenantMembership.user_id' disambiguates from invited_by_id (both reference users.id)"
  - "Tenant/TenantMembership/Invitation/OwnershipTransfer inherit Base+TimestampMixin (NOT TenantModel) — these are structural tables, not tenant-scoped domain data"
  - "InviteRequest and ChangeRoleRequest reject OWNER role via field_validator — Owner only created at workspace creation time"

patterns-established:
  - "Tenant domain exceptions follow auth/exceptions.py pattern: no-arg constructors with hardcoded error_code/message"
  - "MemberRole.level property enables require_role comparison: membership.role.level >= required_role.level"

requirements-completed: [TNNT-01, TNNT-02, TNNT-04, TNNT-05, RBAC-01]

# Metrics
duration: 4min
completed: 2026-02-23
---

# Phase 3 Plan 01: Tenant Data Foundation Summary

**Tenant, TenantMembership (association object), Invitation, and OwnershipTransfer SQLAlchemy models plus domain exceptions and Pydantic v2 schemas for all tenant endpoints, with python-slugify installed**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-23T15:30:10Z
- **Completed:** 2026-02-23T15:33:32Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Created all 4 Phase 3 SQLAlchemy models: Tenant, TenantMembership (with MemberRole enum + billing_access toggle), Invitation (with token_hash + billing_access), OwnershipTransfer
- Created 9 tenant domain exceptions following existing auth/exceptions.py no-arg constructor pattern
- Created Pydantic v2 request/response schemas with field validators rejecting OWNER role on invite/change
- Installed python-slugify 8.0.4 and added User.memberships relationship to auth/models.py
- Aligned ROADMAP.md Phase 3 SC1/SC2/SC3 with locked CONTEXT.md decisions (4 roles, two-flow invitations, onboarding step)

## Task Commits

Each task was committed atomically:

1. **Task 1: Install python-slugify and create data models** - `81eb655` (feat)
2. **Task 2: Create tenant exceptions and Pydantic schemas** - `e9df4dd` (feat)
3. **Task 3: Align ROADMAP.md Phase 3 text with locked CONTEXT.md decisions** - `73a0fee` (docs)

## Files Created/Modified
- `backend/src/wxcode_adm/tenants/models.py` - Tenant, TenantMembership, Invitation, OwnershipTransfer, MemberRole
- `backend/src/wxcode_adm/tenants/exceptions.py` - 9 domain exceptions with correct HTTP status codes
- `backend/src/wxcode_adm/tenants/schemas.py` - Pydantic v2 request/response schemas for all tenant endpoints
- `backend/pyproject.toml` - Added python-slugify==8.0.4 under Phase 3 comment
- `backend/src/wxcode_adm/auth/models.py` - Added User.memberships relationship (string FK reference)
- `.planning/ROADMAP.md` - Phase 3 SC1/SC2/SC3 updated to match CONTEXT.md locked decisions

## Decisions Made
- native_enum=False on all MemberRole Enum columns to avoid PostgreSQL CREATE TYPE and Alembic migration pitfalls documented in RESEARCH.md
- Added `from __future__ import annotations` — Python 3.9.6 does not support `X | None` union syntax at runtime; required `Optional[X]` for nullable Mapped types
- billing_access propagates from Invitation to TenantMembership on acceptance (both explicit accept and auto-join flows)
- User.memberships uses foreign_keys='TenantMembership.user_id' string reference to disambiguate from invited_by_id (both reference users.id) and avoid circular imports

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Python 3.9 incompatible union type syntax**
- **Found during:** Task 1 (data models creation)
- **Issue:** `Mapped[uuid.UUID | None]` and `Mapped[datetime | None]` fail at runtime on Python 3.9 with "unsupported operand type(s) for |: 'type' and 'NoneType'"
- **Fix:** Added `from __future__ import annotations` and used `Mapped[Optional[uuid.UUID]]` / `Mapped[Optional[datetime]]`
- **Files modified:** backend/src/wxcode_adm/tenants/models.py
- **Verification:** All models import without error on Python 3.9.6
- **Committed in:** 81eb655 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug fix for Python 3.9 runtime compat)
**Impact on plan:** Necessary fix — runtime error prevented all imports. No scope creep.

## Issues Encountered
- Python 3.9.6 used in project (pyproject.toml requires >=3.11 but local system has 3.9.6) — the `X | None` union type syntax requires Python 3.10+ for runtime use without `from __future__ import annotations`. Added the import to enable the modern type hint syntax.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 SQLAlchemy models are importable and verified
- MemberRole enum with level property enables require_role comparisons in Phase 3 Plan 02
- Pydantic schemas are ready for endpoint implementations in Plans 02-04
- python-slugify is installed for workspace slug generation in Plan 02
- User.memberships relationship is in place for Plan 02's context dependency and Plan 05's Alembic migration
- ROADMAP.md Phase 3 success criteria match CONTEXT.md locked decisions — verifier will not flag stale text

---
*Phase: 03-multi-tenancy-and-rbac*
*Completed: 2026-02-23*
