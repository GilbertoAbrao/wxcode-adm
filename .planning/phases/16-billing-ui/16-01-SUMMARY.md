---
phase: 16-billing-ui
plan: 01
subsystem: ui
tags: [react, tanstack-query, billing, stripe, nextjs]

# Dependency graph
requires:
  - phase: 15-tenant-management-ui
    provides: useMyTenants hook, tenantHeaders pattern, page layout conventions
  - phase: 12-design-system
    provides: GlowButton, LoadingSkeleton, ErrorState, EmptyState, design tokens

provides:
  - TanStack Query hooks for all billing endpoints (useBilling.ts)
  - /billing page with subscription display and plan catalog grid
  - Typed interfaces for BillingPlan, Subscription, CheckoutResponse, PortalResponse

affects: [16-02-plan, stripe-checkout-wiring, portal-redirect-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - TanStack Query billing hooks with tenantHeaders injection (same as useTenant.ts)
    - Placeholder onClick handlers with Plan 16-02 comments for Stripe wiring
    - PlanCard sub-component co-located in billing/page.tsx for plan state access
    - formatCents/formatDate/statusBadge helper functions inline in page file

key-files:
  created:
    - frontend/src/hooks/useBilling.ts
    - frontend/src/app/(app)/billing/page.tsx
  modified: []

key-decisions:
  - "useQueryClient included in useCreateCheckout and useCreatePortal imports for Plan 16-02 readiness (polling after Stripe return)"
  - "PlanCard rendered as inline sub-component in billing/page.tsx — keeps subscription state accessible without prop drilling via context"
  - "Manage Billing GlowButton only shown for active/past_due status — trialing excluded as portal may not apply"
  - "Member cap -1 treated as Unlimited members; 0 treated as 1 member fallback"

patterns-established:
  - "Billing hooks: usePlans() requires no tenant header (any auth user); subscription/checkout/portal require X-Tenant-ID"
  - "Plan card CTA logic: isCurrent -> disabled badge; hasBillingAccess -> active button; else -> descriptive text"

requirements-completed: [BUI-01, BUI-02]

# Metrics
duration: 1min
completed: 2026-03-05
---

# Phase 16 Plan 01: Billing UI — Hooks and Page Summary

**TanStack Query billing hooks (usePlans, useSubscription, useCreateCheckout, useCreatePortal) and /billing page with subscription card, status badges, token usage bar, and responsive plan catalog grid**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-03-05T17:51:07Z
- **Completed:** 2026-03-05T17:52:58Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `useBilling.ts` with 4 typed TanStack Query hooks matching backend billing API schemas
- Created `/billing` page (387 lines) with Current Plan section (status badge, renewal date, token usage bar) and Available Plans grid
- Plan cards highlight current plan with cyan-400 border, show contextual CTAs (Subscribe/Upgrade for billing users, descriptive text for others)
- Placeholder `onClick` handlers documented with `// Plan 16-02: wire useCreateCheckout/useCreatePortal` comments

## Task Commits

Each task was committed atomically:

1. **Task 1: Create useBilling.ts with TanStack Query hooks** - `b364dfc` (feat)
2. **Task 2: Create /billing page with subscription display and plan catalog** - `8db86dd` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `frontend/src/hooks/useBilling.ts` — 4 billing hooks + TypeScript interfaces; tenantHeaders helper; useQueryClient included for Plan 16-02 readiness
- `frontend/src/app/(app)/billing/page.tsx` — Full billing page with Current Plan section, token usage bar, Available Plans grid, PlanCard sub-component, helper functions (formatCents, formatDate, statusBadge)

## Decisions Made

- `useQueryClient` included in mutation hooks even though neither hook invalidates queries yet — Plan 16-02 will need it for post-Stripe-return polling
- `PlanCard` co-located as inline sub-component in page.tsx rather than a separate file — plan state (subscription, hasBillingAccess) accessed directly without extra prop indirection
- `Manage Billing` button shown only for `active` and `past_due` statuses — `trialing` excluded since Stripe portal behavior may differ
- Member cap `0` treated as "1 member" fallback (edge case); `-1` treated as "Unlimited"

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — TypeScript compilation clean on first attempt, build succeeded immediately.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `useBilling.ts` hooks are ready for Plan 16-02 to wire Stripe Checkout and Portal redirects
- `/billing` page placeholder `onClick` handlers already marked with `// Plan 16-02:` comments for easy discovery
- `useCreateCheckout` and `useCreatePortal` are instantiated but unused in Plan 16-01 — Plan 16-02 will call `mutateAsync` on those references
- Sidebar already has `/billing` nav item with CreditCard icon (from Phase 12-03)

## Self-Check: PASSED

- `frontend/src/hooks/useBilling.ts` — FOUND
- `frontend/src/app/(app)/billing/page.tsx` — FOUND
- `.planning/phases/16-billing-ui/16-01-SUMMARY.md` — FOUND
- Commit `b364dfc` (Task 1) — FOUND
- Commit `8db86dd` (Task 2) — FOUND

---
*Phase: 16-billing-ui*
*Completed: 2026-03-05*
