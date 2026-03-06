---
phase: 19-ui-polish-and-tech-debt-cleanup
plan: 01
subsystem: frontend
tags: [ui-polish, tech-debt, navigation, dashboard, admin-auth, imports]
dependency_graph:
  requires: []
  provides:
    - Sidebar without dead /settings link
    - Live tenant dashboard with real API data
    - Admin post-login redirect to /admin/dashboard
    - Normalized barrel imports in admin pages
  affects:
    - frontend/src/components/layout/Sidebar.tsx
    - frontend/src/app/(app)/page.tsx
    - frontend/src/app/admin/login/page.tsx
    - frontend/src/providers/admin-auth-provider.tsx
    - frontend/src/app/admin/users/page.tsx
tech_stack:
  added: []
  patterns:
    - Live data dashboard via useMyTenants + useSubscription + useTenantMembers + useAuthContext
    - Barrel imports from @/components/ui for all design system components
key_files:
  created: []
  modified:
    - frontend/src/components/layout/Sidebar.tsx
    - frontend/src/app/(app)/page.tsx
    - frontend/src/app/admin/login/page.tsx
    - frontend/src/providers/admin-auth-provider.tsx
    - frontend/src/app/admin/users/page.tsx
decisions:
  - "[19-01]: Sidebar bottom section retains avatar A-badge but removes Settings gear icon and /settings link entirely — no settings page exists"
  - "[19-01]: Dashboard page uses useMyTenants().data?.tenants[0] to extract tenantId; all tenant-scoped hooks gated on enabled: !!tenantId"
  - "[19-01]: StatCard shows SkeletonCard during loading — uses isLoading boolean from each hook independently per card"
  - "[19-01]: Admin post-login redirect changed from /admin/tenants to /admin/dashboard in both admin/login/page.tsx and admin-auth-provider.tsx"
  - "[19-01]: admin/users/page.tsx and admin/login/page.tsx now use single barrel import from @/components/ui — consistent with all other pages"
metrics:
  duration: "2 min"
  completed_date: "2026-03-06"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 5
---

# Phase 19 Plan 01: UI Polish and Tech Debt Cleanup (Part 1) Summary

**One-liner:** Remove dead /settings sidebar link, replace static placeholder dashboard with live tenant/subscription/member data via TanStack hooks, and fix admin login redirect to /admin/dashboard with normalized barrel imports.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Remove dead settings link and replace static dashboard with live data | b846fac | Sidebar.tsx, (app)/page.tsx |
| 2 | Fix admin post-login redirect and normalize barrel imports | caa8d75 | admin/login/page.tsx, admin-auth-provider.tsx, admin/users/page.tsx |

## What Was Built

### Task 1: Sidebar + Live Dashboard

**Sidebar.tsx:**
- Removed `Settings` icon import from lucide-react
- Removed the `<Link href="/settings">` block from the bottom section
- Kept the avatar A-badge in the bottom section (border-t div preserved)
- No /settings navigation entry remains anywhere in the file

**page.tsx (Dashboard):**
- Replaced static placeholder with live data dashboard using four hooks:
  - `useMyTenants()` — tenant name and slug
  - `useSubscription(tenantId)` — plan name, status, renewal date
  - `useTenantMembers(tenantId)` — member count
  - `useAuthContext()` — user display_name for welcome greeting
- Four `StatCard` components with icons (Building2, CreditCard, Users, CalendarClock)
- Welcome section: "Welcome back, {displayName}" heading + description
- Empty state for users with no tenants
- `SkeletonCard` loading state per card (independent per hook)
- Removed "Get Started" GlowButton (no action was wired)

### Task 2: Admin Redirect + Import Normalization

**admin/login/page.tsx:**
- `router.push("/admin/tenants")` changed to `router.push("/admin/dashboard")`
- Docstring updated to reflect new redirect target
- Imports consolidated: `GlowButton` + `GlowInput` now from `@/components/ui` barrel

**admin-auth-provider.tsx:**
- `router.push("/admin/tenants")` changed to `router.push("/admin/dashboard")` in the route protection effect
- Docstring updated: "redirect to /admin/tenants" → "redirect to /admin/dashboard"

**admin/users/page.tsx:**
- Five individual path imports replaced with single barrel import:
  ```tsx
  import {
    GlowButton,
    GlowInput,
    SkeletonList,
    SkeletonTable,
    ErrorState,
    EmptyState,
  } from "@/components/ui";
  ```

## Verification Results

All 6 verification checks passed:
1. Next.js build: compiled successfully (18/18 static pages)
2. No `/settings` in Sidebar.tsx — PASS
3. `useMyTenants` in (app)/page.tsx — PASS (2 matches)
4. No `/admin/tenants` in admin/login/page.tsx or admin-auth-provider.tsx — PASS
5. No individual path imports (`@/components/ui/...`) in admin/users/page.tsx — PASS
6. Barrel import (`@/components/ui`) present in admin/users/page.tsx — PASS

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

Files verified:
- FOUND: frontend/src/components/layout/Sidebar.tsx
- FOUND: frontend/src/app/(app)/page.tsx
- FOUND: frontend/src/app/admin/login/page.tsx
- FOUND: frontend/src/providers/admin-auth-provider.tsx
- FOUND: frontend/src/app/admin/users/page.tsx

Commits verified:
- FOUND: b846fac (feat(19-01): remove dead settings link and replace static dashboard with live data)
- FOUND: caa8d75 (fix(19-01): fix admin post-login redirect to /admin/dashboard and normalize barrel imports)
