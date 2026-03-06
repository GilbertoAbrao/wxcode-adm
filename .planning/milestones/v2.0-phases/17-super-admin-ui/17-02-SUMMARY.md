---
phase: 17-super-admin-ui
plan: "02"
subsystem: ui
tags: [react, nextjs, typescript, tanstack-query, admin-tenants, pagination, inline-action]

# Dependency graph
requires:
  - phase: 17-01
    provides: adminApiClient, AdminAuthProvider, useAdminAuthContext — admin auth isolation
  - phase: 08-super-admin
    provides: backend GET /admin/tenants, POST /admin/tenants/{id}/suspend, POST /admin/tenants/{id}/reactivate

provides:
  - useAdminTenants query hook with URLSearchParams-based param building and per-filter cache keying
  - useSuspendTenant mutation hook (POST /admin/tenants/{id}/suspend) with query invalidation
  - useReactivateTenant mutation hook (POST /admin/tenants/{id}/reactivate) with query invalidation
  - /admin/tenants page with paginated tenant table, plan/status filters, inline moderation actions, pagination

affects: [17-03-super-admin-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ADMIN_TENANT_KEYS.list(params) cache keying — query key includes all filter params so each filter combination is separately cached"
    - "URLSearchParams-based endpoint building — null/undefined/empty params are skipped so clean URL is sent to backend"
    - "Inline action row pattern — actionTenant: {id, action} state replaces modal; confirmation row rendered as <tr> below the target row"
    - "Filter onChange resets page to 0 — prevents stale pagination after filter change"

key-files:
  created:
    - frontend/src/hooks/useAdminTenants.ts
    - frontend/src/app/admin/tenants/page.tsx
  modified: []

key-decisions:
  - "ADMIN_TENANT_KEYS.list(params) includes all params in query key — each filter combination gets its own cache entry; invalidateQueries({ queryKey: ['admin', 'tenants'] }) invalidates all at once on mutation"
  - "URLSearchParams skips null/undefined/empty string values — avoids sending ?plan_slug= to backend when filter is cleared"
  - "ActionRow rendered as a <tr> sibling in the same table body — follows inline confirmation pattern from team/page.tsx (confirmRemove) instead of a modal"
  - "AdminNav lives in the page file (not a shared layout) — simple enough to inline for plan scope; can be extracted in 17-03 if needed"
  - "logout() called directly from useAdminAuthContext — AdminAuthProvider handles token clearing and redirect to /admin/login"

patterns-established:
  - "Admin tenant moderation: inline reason-required confirmation row pattern for irreversible actions"
  - "Admin pagination: page * limit offset pattern with Previous/Next GlowButton ghost variant"

requirements-completed: [SAI-02]

# Metrics
duration: 2min
completed: 2026-03-05
---

# Phase 17 Plan 02: Admin Tenant Management UI Summary

**Paginated tenant list with plan/status filters, inline suspend/reactivate reason-confirmation flow, and Previous/Next pagination using adminApiClient hooks**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-05T21:42:55Z
- **Completed:** 2026-03-05T21:44:50Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `useAdminTenants` query hook: GET /admin/tenants with URLSearchParams-based query building; null/empty params skipped; staleTime 30s; query key includes all params for per-filter caching
- `useSuspendTenant` mutation: POST /admin/tenants/{id}/suspend + invalidateQueries on success
- `useReactivateTenant` mutation: POST /admin/tenants/{id}/reactivate + invalidateQueries on success
- `/admin/tenants` page: 7-column table (name, slug, plan, status, members, created, actions) with status badges (emerald/amber/rose)
- Plan slug GlowInput filter + status dropdown (All/Active/Suspended/Deleted) — both reset pagination
- Inline action row: clicking Suspend/Reactivate renders a reason-input `<tr>` below the target row; Confirm disabled until reason entered
- Pagination: page/limit state, "Showing X–Y of Z tenants" summary, Previous/Next GlowButton ghost
- Admin nav bar with active Tenants link (cyan-400 underline), Users link, Logout button
- Loading skeleton, ErrorState with retry, EmptyState for empty result sets

## Task Commits

Each task was committed atomically:

1. **Task 1: Create useAdminTenants hooks for tenant list and moderation actions** — `ecdafbf` (feat)
2. **Task 2: Create admin tenants page with table, filters, pagination, and moderation actions** — `3cdd62e` (feat)

## Files Created/Modified

- `frontend/src/hooks/useAdminTenants.ts` — TanStack Query hooks: useAdminTenants, useSuspendTenant, useReactivateTenant; TypeScript interfaces TenantListItem, TenantListResponse, AdminActionRequest
- `frontend/src/app/admin/tenants/page.tsx` — Admin tenant management page (503 lines): table with inline action rows, filter bar, pagination, AdminNav, loading/error/empty states

## Decisions Made

- Query key includes all filter params so each unique filter combination is independently cached; `invalidateQueries({ queryKey: ['admin', 'tenants'] })` invalidates all cached pages and filter combinations at once after any mutation
- URLSearchParams building skips null/undefined/empty-string values — avoids noisy `?plan_slug=&status=` query strings in API calls
- Inline action row rendered as `<tr>` inside the same `<tbody>` — follows the confirmRemove inline pattern from team/page.tsx instead of a modal
- AdminNav is co-located in the page file for plan scope; can be extracted to a shared component if 17-03 or 17-04 require it
- Filter changes reset `page` to 0 to prevent showing "Showing 21-40" after filtering to a result set with fewer than 21 items

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- /admin/tenants page live — paginated tenant table, filter by plan slug + status, suspend/reactivate with reason
- AdminNav includes /admin/users link — ready for Plan 17-03 (User Management UI)
- useAdminTenants pattern established — 17-03 useAdminUsers hooks can follow the same structure

---
*Phase: 17-super-admin-ui*
*Completed: 2026-03-05*
