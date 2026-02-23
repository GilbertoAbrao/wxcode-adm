---
phase: 03-multi-tenancy-and-rbac
plan: 03
subsystem: api
tags: [itsdangerous, arq, fastapi, sqlalchemy, invitations, rbac]

# Dependency graph
requires:
  - phase: 03-02
    provides: "Tenant, TenantMembership, Invitation models; invitation_serializer pre-wired in service.py; require_role dependency"
provides:
  - "Invitation flow with two distinct paths: existing users accept via POST /invitations/accept, new users auto-joined at email verification"
  - "invite_user, accept_invitation, auto_join_pending_invitations, list_invitations, cancel_invitation in tenants/service.py"
  - "generate_invitation_token, verify_invitation_token (itsdangerous, 7-day expiry) in tenants/service.py"
  - "send_invitation_email arq job in tenants/email.py"
  - "Invitation endpoints: POST/GET/DELETE /api/v1/tenants/current/invitations (Admin+)"
  - "POST /api/v1/invitations/accept endpoint (existing user flow, no X-Tenant-ID needed)"
  - "invitation_router mounted in main.py at /api/v1/invitations"
  - "send_invitation_email registered in WorkerSettings.functions"
  - "verify_email in auth/service.py calls auto_join_pending_invitations (new user flow)"
affects: [03-04, 03-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-path invitation flow: existing users call POST /invitations/accept; new users auto-join at email verification (locked decision from CONTEXT.md)"
    - "Fault-tolerant auto_join_pending_invitations: never raises, wraps each loop iteration in try/except"
    - "Lazy import inside verify_email to avoid circular import (auth.service -> tenants.service -> auth.models)"
    - "Separate invitation_router (not under /tenants/current) because accepting user may have no tenant context"

key-files:
  created:
    - backend/src/wxcode_adm/tenants/email.py
  modified:
    - backend/src/wxcode_adm/tenants/service.py
    - backend/src/wxcode_adm/tenants/router.py
    - backend/src/wxcode_adm/tasks/worker.py
    - backend/src/wxcode_adm/auth/service.py
    - backend/src/wxcode_adm/main.py

key-decisions:
  - "auto_join_pending_invitations uses lazy import inside verify_email to avoid circular import (auth.service imports tenants.service which imports auth.models)"
  - "invitation_router mounted separately (not under /tenants/current) — accepting user may have no existing tenant membership"
  - "auto_join_pending_invitations is fault-tolerant: individual failures wrapped in try/except, logged as warnings, skipped — email verification always succeeds"
  - "invite_user accepts redis parameter for forward compatibility, but uses get_arq_pool() directly for arq job enqueue"

patterns-established:
  - "Pattern: Two-path invitation (existing users: explicit accept; new users: auto-join at verify_email)"
  - "Pattern: Fault-tolerant hook functions that run inside critical paths — wrap body in try/except, log warnings, never raise"
  - "Pattern: Lazy import inside async function to avoid circular import at module load time"
  - "Pattern: arq job functions mirror auth/email.py pattern — log link at INFO for dev, wrap SMTP in try/except"

requirements-completed:
  - TNNT-03
  - TNNT-04

# Metrics
duration: 7min
completed: 2026-02-23
---

# Phase 03 Plan 03: Invitation Flow Summary

**Two-path tenant invitation system: existing users accept via signed token endpoint, new users auto-joined at email verification using itsdangerous tokens (7-day expiry) and arq email job**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-23T15:42:36Z
- **Completed:** 2026-02-23T15:49:32Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Invitation service with create/accept/auto-join/list/cancel functions and itsdangerous token helpers
- Three invitation endpoints (POST/GET/DELETE) under /tenants/current (Admin+) plus separate /invitations/accept for existing users
- auto_join_pending_invitations hooked into verify_email via lazy import; new users seamlessly join pending tenants after email verification with no extra step

## Task Commits

Each task was committed atomically:

1. **Task 1: Invitation service logic, auto-join function, and email job** - `6efa155` (feat)
2. **Task 2: Invitation router endpoints, worker registration, and verify_email auto-join hook** - `aa48f0a` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/src/wxcode_adm/tenants/service.py` - Added generate_invitation_token, verify_invitation_token, invite_user, accept_invitation, auto_join_pending_invitations, list_invitations, cancel_invitation; updated imports
- `backend/src/wxcode_adm/tenants/email.py` - Created; send_invitation_email arq job function
- `backend/src/wxcode_adm/tenants/router.py` - Added POST/GET/DELETE /current/invitations endpoints and invitation_router with /accept endpoint
- `backend/src/wxcode_adm/tasks/worker.py` - Added send_invitation_email import and to WorkerSettings.functions
- `backend/src/wxcode_adm/auth/service.py` - Added auto_join_pending_invitations lazy import + call inside verify_email
- `backend/src/wxcode_adm/main.py` - Imported and mounted invitation_router at /api/v1/invitations

## Decisions Made

- **Lazy import in verify_email**: `from wxcode_adm.tenants.service import auto_join_pending_invitations` inside verify_email body to avoid circular import at module load time (auth.service -> tenants.service -> auth.models chain)
- **Separate invitation_router**: Mounted at /api/v1/invitations, not under /tenants/current, because the accepting user may not yet be a member of the target tenant
- **Fault-tolerant auto_join**: Wraps each loop iteration in try/except with warning log and continue — email verification always succeeds even if auto-join fails for a specific invitation
- **invite_user defense in depth**: Role guard (ADMIN+) inside service layer in addition to router's require_role dependency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] service.py was expanded since plan was written — had to merge invitation imports carefully**
- **Found during:** Task 1 (service.py already had member management + ownership transfer from Plan 03-02)
- **Issue:** Plan 03-03 was written expecting the original small service.py; Plan 03-02 had expanded it with change_role, remove_member, leave_tenant, initiate_transfer, accept_transfer, get_pending_transfer
- **Fix:** Added new imports incrementally (hashlib, logging, Redis, itsdangerous.exc, AlreadyMemberError, InvitationAlreadyExistsError, InvalidTokenError, Invitation, get_arq_pool) and appended invitation functions at end of existing file
- **Files modified:** backend/src/wxcode_adm/tenants/service.py
- **Verification:** All 21 existing tests pass; import check passes
- **Committed in:** 6efa155 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - integration with expanded service.py)
**Impact on plan:** Minor integration challenge; no scope change or architectural deviation.

## Issues Encountered

None after handling the expanded service.py from Plan 03-02.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Invitation flow complete (create, accept, auto-join, list, cancel)
- Two distinct paths implemented per CONTEXT.md locked decision
- All 21 existing tests pass without regression
- Plan 03-04 (ownership transfer + remaining member management) can proceed
- Plan 03-05 can proceed

## Self-Check: PASSED

- tenants/email.py: FOUND
- tenants/service.py: FOUND
- 03-03-SUMMARY.md: FOUND
- Commit 6efa155: FOUND
- Commit aa48f0a: FOUND

---
*Phase: 03-multi-tenancy-and-rbac*
*Completed: 2026-02-23*
