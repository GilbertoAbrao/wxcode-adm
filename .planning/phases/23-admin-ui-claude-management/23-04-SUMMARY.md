---
phase: 23-admin-ui-claude-management
plan: "04"
subsystem: ui
tags: [react, nextjs, typescript, localStorage, session-persistence, admin-auth]

# Dependency graph
requires:
  - phase: 23-admin-ui-claude-management
    provides: Admin auth infrastructure (admin-auth.ts, AdminAuthProvider, plans page with useAdminPlans hooks)

provides:
  - localStorage persistence for admin refresh token and email across page refresh
  - Session restore on mount via refreshAdminTokens() reading from localStorage
  - Plan Inactivate/Activate toggle button in plans table Actions column
  - Backend TenantSubscription guard in delete_plan (PLAN_IN_USE ConflictError)

affects:
  - 23-05-PLAN.md
  - 23-06-PLAN.md

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Refresh token in localStorage, access token in memory only (standard security split)
    - Async session restore on mount with cancelled flag for cleanup
    - Partial PATCH toggle using existing useMutation hook

key-files:
  created: []
  modified:
    - frontend/src/lib/admin-auth.ts
    - frontend/src/providers/admin-auth-provider.tsx
    - frontend/src/app/admin/plans/page.tsx
    - backend/src/wxcode_adm/billing/service.py

key-decisions:
  - "Refresh token only in localStorage (not access token) — access token short-lived, stays in memory only"
  - "Session restore is async (refreshAdminTokens call) — isLoading=true until restore resolves, preventing redirect flash"
  - "Inactivate toggle uses existing useUpdatePlan with is_active: !plan.is_active — no new API or mutation needed"
  - "PLAN_IN_USE guard uses func.count(TenantSubscription.id) — counts all subscriptions, not just active ones"

patterns-established:
  - "Admin session restore pattern: mount useEffect -> refreshAdminTokens() -> setIsLoading(false)"
  - "Plan status toggle: mutateAsync with is_active: !plan.is_active, surface errors via window.alert"

requirements-completed: [UI-TOKEN, UI-STATUS]

# Metrics
duration: 5min
completed: 2026-03-08
---

# Phase 23 Plan 04: Session Persistence + Plan Inactivate Toggle Summary

**Admin session survives page refresh via localStorage refresh token; plans now have Inactivate/Activate toggle and backend delete guard against tenant-in-use plans.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-08T16:10:31Z
- **Completed:** 2026-03-08T16:15:11Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Admin refresh token persisted to localStorage on login, cleared on logout
- Page refresh no longer forces re-login — AdminAuthProvider restores session from localStorage on mount
- Plans table has Inactivate/Activate toggle in Actions column (amber for inactivate, emerald for activate)
- Backend delete_plan now checks TenantSubscription count before soft-deleting, raising ConflictError PLAN_IN_USE if any tenants reference the plan

## Task Commits

Each task was committed atomically:

1. **Task 1: Add localStorage persistence for admin session** - `79f01b4` (feat)
2. **Task 2: Add plan inactivate toggle and fix delete with tenant guard** - `f85091b` (feat)

**Plan metadata:** (to be committed)

## Files Created/Modified
- `frontend/src/lib/admin-auth.ts` - Added ADMIN_REFRESH_KEY/ADMIN_EMAIL_KEY constants, localStorage writes in setAdminTokens/clearAdminTokens, new setAdminEmail/getStoredAdminEmail functions, localStorage fallback in refreshAdminTokens
- `frontend/src/providers/admin-auth-provider.tsx` - Mount useEffect replaced with async restoreSession(), imports refreshAdminTokens/persistAdminEmail/getStoredAdminEmail, login callback persists email
- `frontend/src/app/admin/plans/page.tsx` - Added Inactivate/Activate toggle button before Edit button in Actions column
- `backend/src/wxcode_adm/billing/service.py` - Added func import, TenantSubscription count check in delete_plan before soft-delete

## Decisions Made
- Refresh token only in localStorage (not access token) — access token short-lived, stays in memory for XSS safety
- Session restore is async — isLoading stays true until refreshAdminTokens resolves, preventing redirect flash to /admin/login
- Inactivate toggle reuses existing useUpdatePlan hook with is_active: !plan.is_active — no new API endpoint needed
- PLAN_IN_USE guard counts all TenantSubscription references (not filtered by status) — prevents orphaned subscription records

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Git stash pop conflict during baseline test check reverted service.py and plans/page.tsx — re-applied both changes manually. No impact on final result.
- Backend billing tests all fail with `TypeError: 'token_quota' is an invalid keyword argument for Plan` — this is a pre-existing mismatch from Phase 23-03 (model migrated to token_quota_5h/token_quota_weekly but test fixtures still use token_quota). Out of scope for this plan, logged to deferred items.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Admin session persistence complete — UAT issue AUTH-PERSIST-01 resolved
- Plans inactivate/delete flow complete — UAT issues PLAN-TOGGLE-01 and PLAN-DELETE-01 resolved
- Remaining UAT gaps: 23-05 (rate limit headers) and 23-06 (other gaps) can proceed independently

## Self-Check: PASSED

- frontend/src/lib/admin-auth.ts: FOUND
- frontend/src/providers/admin-auth-provider.tsx: FOUND
- frontend/src/app/admin/plans/page.tsx: FOUND
- backend/src/wxcode_adm/billing/service.py: FOUND
- 23-04-SUMMARY.md: FOUND
- Commit 79f01b4: FOUND
- Commit f85091b: FOUND

---
*Phase: 23-admin-ui-claude-management*
*Completed: 2026-03-08*
