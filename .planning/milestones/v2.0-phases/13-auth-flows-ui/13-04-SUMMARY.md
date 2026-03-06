---
phase: 13-auth-flows-ui
plan: 04
subsystem: ui
tags: [react, nextjs, tanstack-query, react-hook-form, zod, mfa, totp, workspace]

# Dependency graph
requires:
  - phase: 13-01
    provides: "API client, auth token management, AuthProvider, useAuth hooks (useMfaVerify, useCreateWorkspace), auth layout, mfaCodeSchema, workspaceSchema in validations.ts"
provides:
  - "/mfa-verify page: TOTP input, backup code toggle, trust device checkbox, wxcode redirect handling"
  - "/onboarding page: workspace name form, POST /onboarding/workspace, redirect to dashboard"
  - "Complete auth journey: signup -> verify-email -> onboarding -> dashboard"
  - "Complete MFA journey: login -> mfa-verify -> dashboard or wxcode redirect"
affects: [14-tenant-settings-ui, 15-billing-ui, 16-user-settings-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Suspense wrapper pattern for useSearchParams() in Next.js App Router (inner form component + outer Suspense export)"
    - "Dual-mode form toggle: single form switches between TOTP (6-digit numeric) and backup code (11-char alphanumeric) inputs"
    - "max-w-md card for longer-content auth pages (workspace name), max-w-sm for narrower auth pages"

key-files:
  created:
    - "frontend/src/app/(auth)/mfa-verify/page.tsx"
    - "frontend/src/app/(auth)/onboarding/page.tsx"
  modified: []

key-decisions:
  - "Suspense boundary pattern: split each page using useSearchParams into inner content component + outer page default that wraps in <Suspense fallback={null}>. Required by Next.js App Router for static prerendering."
  - "MFA page dual-mode: single Zod mfaCodeSchema (min 6, max 11) handles both TOTP (6 digits) and backup codes (XXXXX-XXXXX format). Toggle resets form to clear stale input."
  - "Trust device stored in local state (useState), not form state — it's a side effect option, not a validated field."

patterns-established:
  - "Suspense pattern: export default wraps inner component in Suspense when useSearchParams is used"
  - "Auth page card widths: max-w-sm for short forms (login, signup, MFA), max-w-md for longer content (onboarding)"

requirements-completed: [AUI-05, AUI-06, AUI-07]

# Metrics
duration: 5min
completed: 2026-03-04
---

# Phase 13 Plan 04: MFA Verify and Workspace Onboarding Pages Summary

**MFA verify page (TOTP/backup code toggle, trust device, wxcode redirect) and workspace onboarding page (create workspace, redirect to dashboard) completing the full auth journey**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-04T22:48:37Z
- **Completed:** 2026-03-04T22:53:07Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- MFA verify page with Suspense-wrapped useSearchParams, TOTP/backup code toggle, trust device checkbox, wxcode redirect on success
- Workspace onboarding page with Building2 icon input, inline error, helper text, redirect to authenticated dashboard
- Both pages render inside (auth) layout (no sidebar), use GlowButton + GlowInput from Obsidian Studio design system
- Production build passes with all 8 routes including /mfa-verify and /onboarding

## Task Commits

Each task was committed atomically:

1. **Task 1: MFA verify page** - `98af771` (feat) — committed in plan 13-02 as pre-implementation per planner
2. **Task 2: Workspace onboarding page** - `da1963e` (feat)

**Plan metadata:** _committed with this summary_

## Files Created/Modified
- `frontend/src/app/(auth)/mfa-verify/page.tsx` - MFA verify page: ?token= param read via Suspense-wrapped useSearchParams, TOTP/backup code toggle, trust device checkbox, useMfaVerify mutation, wxcode redirect or dashboard on success (190 lines)
- `frontend/src/app/(auth)/onboarding/page.tsx` - Workspace onboarding page: workspace name input with Building2 icon, useCreateWorkspace mutation, redirects to / on success (107 lines)

## Decisions Made
- Suspense boundary required by Next.js App Router when using `useSearchParams()` in statically prerendered pages. Inner component reads params; exported default wraps it in `<Suspense fallback={null}>`. This pattern is established across all auth pages that read URL params.
- MFA page uses a single `mfaCodeSchema` (min 6, max 11 chars) to handle both TOTP (6-digit numeric) and backup codes (XXXXX-XXXXX format). Toggle resets form fields.
- Trust device is local state only — not validated by Zod, just passed as boolean to the mutation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] useSearchParams() requires Suspense boundary for Next.js build**
- **Found during:** Task 1 (MFA verify page)
- **Issue:** `useSearchParams()` called directly in page component causes static prerendering failure in Next.js 16 App Router. Build error: "useSearchParams() should be wrapped in a suspense boundary at page /mfa-verify"
- **Fix:** Refactored page into inner `MfaVerifyForm` component (uses searchParams) and outer `MfaVerifyPage` default export that wraps it in `<Suspense fallback={null}>`
- **Files modified:** `frontend/src/app/(auth)/mfa-verify/page.tsx`
- **Verification:** `pnpm build` passes, /mfa-verify appears in build output as static route
- **Committed in:** `98af771` (Task 1 commit, plan 13-02 pre-implementation)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Required fix for production build correctness. No scope creep.

## Issues Encountered
- The mfa-verify page was pre-implemented in plan 13-02 commit `98af771` with the Suspense fix already applied. No additional changes were needed to that file — the disk content matched the HEAD exactly. Task 1 was verified complete without an additional commit.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full auth journey complete: signup -> verify-email -> onboarding -> dashboard
- Full MFA journey complete: login -> mfa-verify -> dashboard/wxcode
- wxcode OAuth redirect complete: login/mfa-verify -> window.location to wxcode_redirect_url?code=...
- Ready for Phase 14 (Tenant Settings UI) and Phase 15 (Billing UI) which build on authenticated app shell

## Self-Check: PASSED

All artifacts verified:
- FOUND: frontend/src/app/(auth)/mfa-verify/page.tsx (190 lines, meets min_lines: 80)
- FOUND: frontend/src/app/(auth)/onboarding/page.tsx (107 lines, meets min_lines: 50)
- FOUND: .planning/phases/13-auth-flows-ui/13-04-SUMMARY.md
- FOUND: commit 98af771 (Task 1 — mfa-verify page, committed in 13-02)
- FOUND: commit da1963e (Task 2 — onboarding page)
- pnpm build passes with /mfa-verify and /onboarding in build output

---
*Phase: 13-auth-flows-ui*
*Completed: 2026-03-04*
