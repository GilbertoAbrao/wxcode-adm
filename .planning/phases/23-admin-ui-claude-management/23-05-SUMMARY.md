---
phase: 23-admin-ui-claude-management
plan: "05"
subsystem: ui
tags: [react, typescript, nextjs, tanstack-query, admin-ui, dual-budget]

# Dependency graph
requires:
  - phase: 23-03
    provides: "Backend dual budget/quota fields: claude_5h_token_budget + claude_weekly_token_budget on tenants, token_quota_5h + token_quota_weekly on plans"
provides:
  - "Frontend hook interfaces updated to match backend dual-field schema"
  - "Tenant detail page displays and edits 5h + weekly budget fields"
  - "Plans page displays dual quota columns and create/edit forms with dual quota inputs"
affects: [23-06, uat-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-state pattern: one React state per API field (configBudget5h + configBudgetWeekly instead of single configBudget)"
    - "Partial PATCH independence: each field compared and sent independently in edit form diff logic"

key-files:
  created: []
  modified:
    - frontend/src/hooks/useAdminTenants.ts
    - frontend/src/hooks/useAdminPlans.ts
    - frontend/src/app/admin/tenants/[tenantId]/page.tsx
    - frontend/src/app/admin/plans/page.tsx

key-decisions:
  - "token_quota fields in billing/page.tsx (tenant-facing) left untouched — uses separate useBilling hook and /billing/subscription endpoint, not the admin billing API; out of scope for this plan"
  - "Create plan form: quota fields default to 0 when empty (parseInt fallback) — removed mandatory quota validation since 0 is a valid starting quota"

patterns-established:
  - "Admin hook interfaces always mirror backend schemas exactly (field names, types, nullable annotations)"

requirements-completed: [UI-CONFIG, UI-HOOKS]

# Metrics
duration: 3min
completed: 2026-03-08
---

# Phase 23 Plan 05: Frontend Dual Budget/Quota Fields Summary

**TypeScript hook interfaces and admin UI pages updated for dual time-window budget (5h + weekly) and quota fields, closing UAT gaps 1 and 7**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-08T16:26:07Z
- **Completed:** 2026-03-08T16:29:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Updated `TenantDetailResponse` and `ClaudeConfigUpdate` interfaces in `useAdminTenants.ts` to use `claude_5h_token_budget` + `claude_weekly_token_budget` (replacing `claude_monthly_token_budget`)
- Updated `PlanResponse`, `CreatePlanData`, `UpdatePlanData` in `useAdminPlans.ts` to use `token_quota_5h` + `token_quota_weekly` (replacing `token_quota`)
- Tenant detail WXCODE Integration card now shows "5h Budget" and "Weekly Budget" displays and two separate edit inputs
- Plans table now has "Quota 5h" and "Quota Weekly" columns; create/edit forms have dual quota inputs with independent PATCH diff logic
- TypeScript compiles with zero errors; Next.js production build succeeds

## Task Commits

Each task was committed atomically:

1. **Task 1: Update hooks interfaces for dual budget/quota fields** - `ada4bda` (feat)
2. **Task 2: Update tenant detail and plans pages for dual fields** - `8ff3b96` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `frontend/src/hooks/useAdminTenants.ts` - TenantDetailResponse and ClaudeConfigUpdate interfaces updated for dual budget fields
- `frontend/src/hooks/useAdminPlans.ts` - PlanResponse, CreatePlanData, UpdatePlanData updated for dual quota fields
- `frontend/src/app/admin/tenants/[tenantId]/page.tsx` - 5h Budget + Weekly Budget display and edit form; configBudget5h + configBudgetWeekly state variables
- `frontend/src/app/admin/plans/page.tsx` - Quota 5h + Quota Weekly columns; dual create/edit quota inputs; colSpan updated from 9 to 10

## Decisions Made

- `token_quota` references in `frontend/src/app/(app)/billing/page.tsx` and `frontend/src/hooks/useBilling.ts` left untouched — these are tenant-facing billing pages using a separate `/billing/subscription` endpoint with a different `PlanInfo` interface. Out of scope for this plan.
- Create plan form quota fields now default to `parseInt(...) || 0` — removed mandatory quota field validation since 0 is semantically valid (quota-unlimited intent set at plan level)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all changes applied cleanly. `token_quota` in billing pages was identified as a pre-existing out-of-scope reference (different subsystem, different API).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All frontend admin UI now uses dual budget/quota fields matching the backend schema from Phase 23-03
- UAT gap 1 (Tenant detail shows single monthly budget) and UAT gap 7 (Plans table shows single quota column) are fully closed
- No blockers

---
*Phase: 23-admin-ui-claude-management*
*Completed: 2026-03-08*
