---
phase: 23-admin-ui-claude-management
plan: "02"
subsystem: frontend-admin
tags: [admin-ui, plans, billing, navigation, tanstack-query]
dependency_graph:
  requires: [23-01, 21-01, 22-01]
  provides: [admin-plans-page, admin-plan-hooks, admin-nav-plans-link]
  affects: [admin-billing-plans-endpoint]
tech_stack:
  added: []
  patterns:
    - TanStack Query hooks for non-paginated list endpoint (array response)
    - Inline edit row pattern in table (expanded td with colSpan)
    - Auto-slug generation from name field
    - Partial PATCH payload (diff against original values)
key_files:
  created:
    - frontend/src/hooks/useAdminPlans.ts
    - frontend/src/app/admin/plans/page.tsx
  modified:
    - frontend/src/app/admin/tenants/page.tsx
    - frontend/src/app/admin/tenants/[tenantId]/page.tsx
    - frontend/src/app/admin/users/page.tsx
    - frontend/src/app/admin/dashboard/page.tsx
    - frontend/src/app/admin/audit-logs/page.tsx
decisions:
  - Array response (not paginated) for plans — backend returns PlanResponse[] directly, no TenantListResponse wrapper
  - Partial PATCH compares edit field strings vs original plan values — only sends changed fields in payload
  - Delete confirmed via window.confirm + window.alert for errors — simple UX for an infrequent admin action
  - Plans nav link added between Tenants and Users — preserves logical hierarchy Dashboard > Tenants > Plans > Users > Audit Logs
  - Admin layout wrapper handles max-w-7xl; plans page uses same min-h-screen bg-zinc-950 pattern as tenants/dashboard pages
metrics:
  duration: "3 min"
  completed: 2026-03-08
  tasks_completed: 2
  files_created: 2
  files_modified: 5
---

# Phase 23 Plan 02: Plans Management Page + Admin Nav — Summary

**One-liner:** Plans CRUD page with wxcode limit columns (max_projects, max_output_projects, max_storage_gb) and Plans nav link added to all 5 existing admin pages.

## What Was Built

### Task 1: useAdminPlans hooks file (commit 16ff31d)

New file `frontend/src/hooks/useAdminPlans.ts` — TanStack Query hooks for admin billing plan management.

**Exports:**
- `PlanResponse` — TypeScript interface matching `billing/schemas.py:PlanResponse`
- `CreatePlanData` — interface for plan creation payload
- `UpdatePlanData` — interface for partial plan update payload
- `ADMIN_PLAN_KEYS` — query key factory (`list()`, `detail(planId)`)
- `useAdminPlans()` — query hook: `GET /admin/billing/plans` → `PlanResponse[]`, staleTime 30s
- `useCreatePlan()` — mutation: `POST /admin/billing/plans`
- `useUpdatePlan()` — mutation: `PATCH /admin/billing/plans/:plan_id`
- `useDeletePlan()` — mutation: `DELETE /admin/billing/plans/:plan_id`

All hooks follow exact pattern from `useAdminTenants.ts`: `adminApiClient`, `useMutation` + `useQueryClient`, `onSuccess` with `invalidateQueries({ queryKey: ["admin", "plans"] })`.

### Task 2: Plans page and nav updates (commit 82d5cc5)

**New file** `frontend/src/app/admin/plans/page.tsx` (723 lines):

- AdminNav component with Plans link highlighted (cyan-400 with border-b-2)
- 9-column table: Name, Slug, Fee/mo, Token Quota, Max Projects, Max Output, Storage (GB), Status, Actions
- Create form above table (collapsible) with all fields + auto-slug from name + sensible defaults (max_projects=5, max_output_projects=20, max_storage_gb=10)
- Inline edit form as expanded `<tr>` row with `colSpan={9}`, pre-populated from current plan values, sends only changed fields via partial PATCH
- Delete button only visible for inactive plans, gated by `window.confirm`
- Loading/Error/Empty states matching tenants/page.tsx patterns
- Plan count summary footer

**5 admin pages updated** — Plans link added between Tenants and Users in each AdminNav:
- `dashboard/page.tsx`
- `tenants/page.tsx`
- `tenants/[tenantId]/page.tsx`
- `users/page.tsx`
- `audit-logs/page.tsx`

## Verification Results

1. `npx tsc --noEmit` — zero errors
2. `npx next build` — succeeds, `/admin/plans` route listed as static
3. `useAdminPlans.ts` exports 4 hooks (useAdminPlans, useCreatePlan, useUpdatePlan, useDeletePlan)
4. `/admin/plans/page.tsx` exists (723 lines) with max_projects, max_output_projects, max_storage_gb columns
5. All 6 admin pages have Plans link in nav (5 existing + 1 new)
6. Create form has max_projects (default 5), max_output_projects (default 20), max_storage_gb (default 10)
7. Edit form allows updating all wxcode limit fields

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- FOUND: `frontend/src/hooks/useAdminPlans.ts`
- FOUND: `frontend/src/app/admin/plans/page.tsx`
- FOUND: commit `16ff31d` (Task 1)
- FOUND: commit `82d5cc5` (Task 2)
