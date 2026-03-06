---
phase: 03-multi-tenancy-and-rbac
plan: "04"
subsystem: api
tags: [fastapi, sqlalchemy, rbac, ownership-transfer, member-management]

# Dependency graph
requires:
  - phase: 03-02
    provides: "TenantMembership, OwnershipTransfer models, require_role/require_tenant_member dependencies, tenant router scaffold"
provides:
  - "change_role service function with correct guard ordering (owner self-demotion first)"
  - "remove_member service function (admin action, preserves user account)"
  - "leave_tenant service function (self-service, owner blocked until transfer)"
  - "initiate_transfer service function (two-step ownership transfer, 7-day expiry)"
  - "accept_transfer service function (role swap: old owner->admin, new owner->owner)"
  - "get_pending_transfer service function (auto-deletes expired transfers)"
  - "PATCH /api/v1/tenants/current/members/{user_id}/role endpoint"
  - "DELETE /api/v1/tenants/current/members/{user_id} endpoint"
  - "POST /api/v1/tenants/current/leave endpoint"
  - "POST /api/v1/tenants/current/transfer endpoint (201)"
  - "POST /api/v1/tenants/current/transfer/accept endpoint"
  - "GET /api/v1/tenants/current/transfer endpoint"
affects:
  - "03-05 (invitation service completes RBAC surface)"
  - "phase-07 (frontend integration with ownership transfer UX)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Owner self-demotion guard checked before privilege guard to avoid false positives"
    - "from __future__ import annotations for Python 3.9 union type compatibility"
    - "Timezone-naive datetime normalization via _normalize_expires_at helper"
    - "Service returns membership; router independently looks up user email for MembershipResponse"

key-files:
  created: []
  modified:
    - "backend/src/wxcode_adm/tenants/service.py"
    - "backend/src/wxcode_adm/tenants/router.py"

key-decisions:
  - "from __future__ import annotations added to service.py — Python 3.9 runtime does not support bool | None syntax; matches pattern already used in models.py"
  - "Router queries User email separately after change_role returns membership — service stays pure (no ORM joins with User), router handles response shaping"
  - "_normalize_expires_at helper attaches UTC tzinfo to naive datetimes — handles SQLite test environment vs PostgreSQL production, same pattern as auth/service.py"
  - "accept_transfer uses TokenExpiredError from auth.exceptions — transfer expiry semantically matches token expiry; no new exception class needed"

patterns-established:
  - "Guard ordering for role changes: check owner self-demotion FIRST before privilege-level checks to avoid false 'insufficient role' errors on valid Owner actions"
  - "Stale transfer cleanup: initiate_transfer auto-deletes expired transfers before creating new ones (prevents accumulation)"

requirements-completed:
  - TNNT-05
  - RBAC-02
  - RBAC-03

# Metrics
duration: 4min
completed: 2026-02-23
---

# Phase 03 Plan 04: Member Management and Ownership Transfer Summary

**Six service functions and six endpoints completing the RBAC administrative surface: role changes, member removal, voluntary leave, and two-step ownership transfer with 7-day expiry**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-23T15:42:36Z
- **Completed:** 2026-02-23T15:47:17Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Member management service layer: `change_role`, `remove_member`, `leave_tenant` with all guard conditions per RBAC rules
- Two-step ownership transfer: `initiate_transfer` creates a 7-day expiring record, `accept_transfer` atomically swaps roles
- Six new endpoints covering all administrative membership operations, all existing 21 tests still passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Member management and ownership transfer service functions** - `f82942f` (feat)
2. **Task 2: Member management and ownership transfer endpoints** - `3468e8a` (feat)

**Plan metadata:** (to be added)

## Files Created/Modified

- `backend/src/wxcode_adm/tenants/service.py` - Added 6 new functions: `change_role`, `remove_member`, `leave_tenant`, `initiate_transfer`, `accept_transfer`, `get_pending_transfer`; added `from __future__ import annotations`
- `backend/src/wxcode_adm/tenants/router.py` - Added 6 new endpoints for member management and ownership transfer operations

## Decisions Made

- **`from __future__ import annotations`** added to `service.py`: Python 3.9 runtime does not support `bool | None` union syntax; `from __future__ import annotations` defers evaluation, matching the pattern already established in `models.py`. (Rule 1 - auto-fix)
- **Router queries User email separately**: `change_role` service returns the updated `TenantMembership`; the router independently queries `User.email` to construct `MembershipResponse`. Keeps service pure without ORM joins.
- **`_normalize_expires_at` helper**: Attaches UTC tzinfo to naive datetimes from SQLite (test environment) before comparison against timezone-aware `datetime.now(tz=timezone.utc)`. Same pattern as `auth/service.py` refresh token expiry.
- **`TokenExpiredError` reused**: `accept_transfer` raises `auth.exceptions.TokenExpiredError` for expired transfers — semantically correct and avoids a new exception class.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added `from __future__ import annotations` to service.py**
- **Found during:** Task 1 verification
- **Issue:** `bool | None` type union syntax raises `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` at import time on Python 3.9.6 runtime
- **Fix:** Added `from __future__ import annotations` at top of `service.py` — defers annotation evaluation, enabling modern union syntax on Python 3.9
- **Files modified:** `backend/src/wxcode_adm/tenants/service.py`
- **Verification:** Import verified: `Member management service OK`
- **Committed in:** `f82942f` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug)
**Impact on plan:** Auto-fix essential for Python 3.9 compatibility. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Member management and ownership transfer complete; RBAC administrative surface is now functional
- Plan 03-05 (invitation service: send, accept, reject) is the final piece to complete the multi-tenancy phase
- All existing tests pass (21/21)

---
*Phase: 03-multi-tenancy-and-rbac*
*Completed: 2026-02-23*
