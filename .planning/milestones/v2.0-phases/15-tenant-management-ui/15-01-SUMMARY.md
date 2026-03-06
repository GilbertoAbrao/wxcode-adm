---
phase: 15-tenant-management-ui
plan: 01
subsystem: ui
tags: [react, tanstack-query, nextjs, zod, react-hook-form, tenant-management]

# Dependency graph
requires:
  - phase: 14-user-account-ui
    provides: useUserAccount.ts hook patterns, account page layout, apiClient header injection pattern
  - phase: 13-auth-flows-ui
    provides: validations.ts shared schema pattern, GlowButton/GlowInput/AnimatedList components
  - phase: 12-design-system
    provides: design system components (AnimatedList, EmptyState, ErrorState, LoadingSkeleton)
provides:
  - useTenant.ts with 8 TanStack Query hooks for all tenant management endpoints
  - /team page with member list (AnimatedList), invite form, pending invitations section
  - inviteMemberSchema and InviteMemberFormData in validations.ts
  - X-Tenant-ID header injection pattern via tenantHeaders helper
affects:
  - 15-02-PLAN.md (role change, remove member, MFA enforcement controls use same hooks)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "tenantHeaders(tenantId) helper — returns { headers: { X-Tenant-ID: tenantId } } for apiClient spread"
    - "enabled: !!tenantId pattern — TanStack Query conditional fetch before tenant context resolves"
    - "ChangeRoleVariables extends ChangeRoleRequest with user_id for dynamic URL mutation"
    - "cancelInvitationMutation.variables === invitation.id for per-row loading state (same as sessions revoke)"

key-files:
  created:
    - frontend/src/hooks/useTenant.ts
    - frontend/src/app/(app)/team/page.tsx
  modified:
    - frontend/src/lib/validations.ts

key-decisions:
  - "tenantHeaders helper encapsulates X-Tenant-ID injection — all tenant-scoped hooks use it via spread onto apiClient options"
  - "useTenantInvitations conditionally enabled on isAdminOrOwner check at page level — avoids 403 for non-admin users"
  - "Zod v4 z.enum uses message param not required_error — different from Zod v3 API"
  - "EmptyState component uses description prop not message prop — must match existing component interface"
  - "inviteMemberSchema role enum excludes owner — only admin/developer/viewer are valid invite roles per backend"

patterns-established:
  - "useTenant.ts: all tenant-scoped hooks accept tenantId: string | undefined with enabled: !!tenantId guard"
  - "Invite error differentiation: 409 = already member/invited, 402 = member limit reached, other = message passthrough"

requirements-completed: [TMI-01]

# Metrics
duration: 12min
completed: 2026-03-05
---

# Phase 15 Plan 01: Tenant Management UI - Hooks and Team Page Summary

**TanStack Query hooks for all tenant endpoints with X-Tenant-ID header injection, plus /team page with AnimatedList member list, role-gated invite form, and per-row cancel buttons for pending invitations**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-05T13:51:00Z
- **Completed:** 2026-03-05T14:03:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `useTenant.ts` with 8 typed TanStack Query hooks covering all tenant management endpoints (GET /tenants/me, members, invitations; POST invite; DELETE cancel/remove; PATCH role/mfa)
- `/team` page with full member list using AnimatedList (email, role badge with color coding, join date), invite form for Owner/Admin, pending invitations section with per-row cancel buttons
- `inviteMemberSchema` and `InviteMemberFormData` added to validations.ts for consistent form validation

## Task Commits

Each task was committed atomically:

1. **Task 1: Create useTenant.ts with TanStack Query hooks** - `e874363` (feat)
2. **Task 2: Create /team page with member list, pending invitations, and invite form** - `6822a74` (feat)

## Files Created/Modified

- `frontend/src/hooks/useTenant.ts` - 8 typed hooks: useMyTenants, useTenantMembers, useTenantInvitations, useInviteMember, useCancelInvitation, useChangeRole, useRemoveMember, useMfaEnforcement
- `frontend/src/app/(app)/team/page.tsx` - Team page with member list, invite form (Owner/Admin), pending invitations section
- `frontend/src/lib/validations.ts` - Added inviteMemberSchema (email + role enum: admin/developer/viewer) and InviteMemberFormData type

## Decisions Made

- `tenantHeaders` helper encapsulates X-Tenant-ID injection — avoids repeating header object in each mutationFn
- `useTenantInvitations` conditionally enabled only when `isAdminOrOwner` at page level — prevents 403 for developer/viewer roles
- `ChangeRoleVariables` type extends `ChangeRoleRequest` with `user_id` field to pass dynamic URL segment through single mutation variable

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] EmptyState uses `description` prop, not `message`**
- **Found during:** Task 2 (team page TypeScript build)
- **Issue:** Plan spec used `message` prop but existing EmptyState component only accepts `description`
- **Fix:** Changed `message="..."` to `description="..."` on EmptyState usage
- **Files modified:** `frontend/src/app/(app)/team/page.tsx`
- **Verification:** TypeScript compilation passes
- **Committed in:** `6822a74` (Task 2 commit)

**2. [Rule 1 - Bug] Zod v4 z.enum uses `message` param, not `required_error`**
- **Found during:** Task 2 (validations.ts TypeScript build)
- **Issue:** Plan spec used `{ required_error: "..." }` which is Zod v3 API; project uses Zod v4 where the param is `{ message: "..." }`
- **Fix:** Changed `required_error` to `message` in inviteMemberSchema role enum definition
- **Files modified:** `frontend/src/lib/validations.ts`
- **Verification:** TypeScript compilation passes, build succeeds
- **Committed in:** `6822a74` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - API mismatch bugs)
**Impact on plan:** Both fixes necessary for correct TypeScript compilation. No scope creep.

## Issues Encountered

None beyond the two auto-fixed TypeScript type mismatches documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `useTenant.ts` hooks are ready for Plan 15-02 (role change UI, remove member, MFA enforcement toggle)
- `/team` page scaffolded — Plan 15-02 can add useChangeRole and useRemoveMember controls to member rows
- All patterns established: tenantHeaders helper, enabled: !!tenantId guard, per-row loading state via `.variables === id`

## Self-Check: PASSED

- FOUND: `frontend/src/hooks/useTenant.ts`
- FOUND: `frontend/src/app/(app)/team/page.tsx`
- FOUND: `.planning/phases/15-tenant-management-ui/15-01-SUMMARY.md`
- FOUND: commit `e874363` (Task 1)
- FOUND: commit `6822a74` (Task 2)

---
*Phase: 15-tenant-management-ui*
*Completed: 2026-03-05*
