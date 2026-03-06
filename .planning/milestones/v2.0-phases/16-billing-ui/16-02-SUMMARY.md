---
phase: 16-billing-ui
plan: 02
subsystem: ui
tags: [react, tanstack-query, billing, stripe, nextjs, suspense]

# Dependency graph
requires:
  - phase: 16-billing-ui/16-01
    provides: useBilling.ts hooks, /billing page scaffold with placeholder onClick handlers
  - phase: 12-design-system
    provides: GlowButton (isLoading/loadingText props), LoadingSkeleton, design tokens

provides:
  - End-to-end Stripe Checkout redirect flow (plan card -> checkout session -> Stripe -> return)
  - Stripe Customer Portal redirect from Manage Billing button
  - Post-checkout subscription polling with 2s interval, 20s timeout
  - BILLING_QUERY_KEYS constants and refetchInterval option on useSubscription
  - Suspense boundary wrapper for useSearchParams() in /billing page

affects: [stripe-integration, billing-e2e-testing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - useSearchParams() with Suspense boundary: BillingPageContent (inner) + BillingPage (outer Suspense wrapper)
    - window.location.href for external Stripe redirects (not router.push — external domain)
    - TanStack Query refetchInterval polling: isPolling flag drives refetchInterval: 2000 | false
    - setTimeout for poll timeout (20s) with cleanup via useEffect return
    - Per-card loading state: checkoutPlanId === plan.id; disabled all cards while any checkout in progress

key-files:
  created: []
  modified:
    - frontend/src/hooks/useBilling.ts
    - frontend/src/app/(app)/billing/page.tsx

key-decisions:
  - "window.location.href used for both Stripe Checkout and Portal redirects — router.push would fail for external domains"
  - "Suspense boundary required for useSearchParams() — BillingPageContent is inner, BillingPage is exported wrapper"
  - "isPolling = !!sessionId && subscription.status === 'free' && !pollTimedOut — passed as refetchInterval option to useSubscription"
  - "Poll timeout via setTimeout in useEffect (20s), not by counting refetch cycles — simpler and deterministic"
  - "checkoutPlanId tracks which specific card is loading; anyCheckoutInProgress disables all other cards simultaneously"
  - "409 conflict -> 'You already have an active subscription'; 402 -> 'Billing setup incomplete'; default -> err.message"
  - "Success banner auto-dismisses after 5s via setTimeout in useEffect"

patterns-established:
  - "Stripe checkout: mutateAsync -> window.location.href = result.checkout_url (external redirect)"
  - "Post-checkout polling: detect session_id from URL, refetchInterval: 2000, useEffect cleans up URL on status change"
  - "Checkout error differentiation: ApiError.status 409/402 get specific messages, others use err.message"

requirements-completed: [BUI-02, BUI-03]

# Metrics
duration: 2min
completed: 2026-03-05
---

# Phase 16 Plan 02: Billing UI — Stripe Checkout and Portal Wiring Summary

**End-to-end Stripe Checkout redirect flow, Customer Portal redirect, and 2s-polling post-checkout subscription activation with Suspense boundary for useSearchParams()**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-05T17:55:37Z
- **Completed:** 2026-03-05T17:57:38Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Wired plan card Subscribe/Upgrade buttons to POST /billing/checkout with per-card loading state and external redirect via window.location.href
- Wired Manage Billing button to POST /billing/portal with loading/error state and external redirect
- Implemented post-checkout return detection: reads ?session_id= from URL, polls subscription every 2s for up to 20s until status leaves "free"
- Success banner auto-dismisses after 5s; timeout banner shows at 20s with "refresh in a moment" guidance
- Restructured page with inner BillingPageContent + outer BillingPage Suspense wrapper for useSearchParams() compliance
- Added BILLING_QUERY_KEYS constants and refetchInterval option parameter to useSubscription hook

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire Stripe Checkout redirect, Customer Portal redirect, and post-checkout polling** - `416fc78` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `frontend/src/hooks/useBilling.ts` — Added BILLING_QUERY_KEYS export, updated useSubscription to accept optional `{ refetchInterval }` option for polling support
- `frontend/src/app/(app)/billing/page.tsx` — Full Stripe wiring: Suspense boundary, handleCheckout, handlePortal, post-checkout polling, success/timeout banners, per-card loading state, contextual error messages

## Decisions Made

- `window.location.href` used for both Stripe Checkout URL and Customer Portal URL — `router.push` cannot navigate to external domains
- `Suspense` boundary required: BillingPageContent (inner component uses useSearchParams) + BillingPage (exported default wraps in `<Suspense fallback={<BillingLoadingFallback />}>`)
- `isPolling` flag computed as `!!sessionId && !checkoutComplete && !pollTimedOut` — passed directly as `refetchInterval: isPolling ? 2000 : false` to useSubscription
- Poll timeout uses `setTimeout(20_000)` in a useEffect — cleaner than counting refetch cycles and deterministic
- `checkoutPlanId` state tracks which plan card triggered checkout; all cards disabled while `checkoutPlanId !== null`
- Error differentiation: HTTP 409 = "You already have an active subscription", HTTP 402 = "Billing setup incomplete", default = `err.message`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — TypeScript compilation clean on first attempt, production build succeeded immediately.

## User Setup Required

None - no external service configuration required. Stripe keys and webhook are backend concerns already implemented in Phase 4.

## Next Phase Readiness

- Phase 16 (Billing UI) is now complete — both plans done (16-01 hooks/page + 16-02 Stripe wiring)
- Phase 17 (Super-Admin UI) can begin — depends only on Phase 12 design system per STATE.md decisions
- Full billing flow is end-to-end: subscribe, pay via Stripe, return, see updated subscription

## Self-Check: PASSED

- `frontend/src/hooks/useBilling.ts` — FOUND
- `frontend/src/app/(app)/billing/page.tsx` — FOUND
- `.planning/phases/16-billing-ui/16-02-SUMMARY.md` — FOUND
- Commit `416fc78` (Task 1) — FOUND

---
*Phase: 16-billing-ui*
*Completed: 2026-03-05*
