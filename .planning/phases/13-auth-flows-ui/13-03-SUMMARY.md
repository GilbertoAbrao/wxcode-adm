---
phase: 13-auth-flows-ui
plan: 03
subsystem: auth
tags: [react, tanstack-query, zod, react-hook-form, next.js, typescript, otp, suspense]

# Dependency graph
requires:
  - phase: 13-auth-flows-ui
    provides: useVerifyEmail, useResendVerification, useForgotPassword, useResetPassword hooks; verifyEmailSchema, forgotPasswordSchema, resetPasswordSchema from validations.ts; GlowButton, GlowInput components; (auth) layout
provides:
  - Email verification page (/verify-email) with 6-digit OTP input, resend with 60s cooldown, redirects to /onboarding
  - Forgot password page (/forgot-password) with email input and enumeration-safe success state
  - Password reset confirmation page (/reset-password) with new password + confirm match validation
affects:
  - 13-04-PLAN.md (onboarding page — next in auth flow sequence)
  - Login page shows 403 error with link to /verify-email for unverified users

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Suspense wrapper pattern for useSearchParams() — inner component reads params, outer default export wraps in <Suspense fallback={null}>
    - Enumeration-safe success message for forgot-password (always shows success regardless of email existence)
    - setInterval countdown timer in useEffect for resend cooldown with cleanup

key-files:
  created:
    - frontend/src/app/(auth)/verify-email/page.tsx
    - frontend/src/app/(auth)/forgot-password/page.tsx
    - frontend/src/app/(auth)/reset-password/page.tsx
  modified: []

key-decisions:
  - "Suspense wrapper pattern required for all pages using useSearchParams() in Next.js App Router — inner component reads params, page default export wraps in Suspense. Applied consistently across verify-email, reset-password, and mfa-verify."
  - "Enumeration-safe forgot-password: always shows success state after submit regardless of whether email exists — prevents user enumeration attacks"
  - "reset-password shows inline error state (not redirect) when token is missing — gives user a clear recovery path via link to /forgot-password"

patterns-established:
  - "Pattern: Pages using useSearchParams() split into inner content component + Suspense-wrapped page export"
  - "Pattern: Resend cooldown — setInterval with cleanup, state-managed countdown, button disabled during cooldown"
  - "Pattern: Enumeration-safe success state — replace form with message after submit, never reveal whether email exists"

requirements-completed: [AUI-03, AUI-04]

# Metrics
duration: 4min
completed: 2026-03-04
---

# Phase 13 Plan 03: Email Verification, Forgot Password, Reset Password Summary

**Three secondary auth flow pages: OTP email verification with 60s resend cooldown, enumeration-safe forgot-password, and token-based password reset with match validation**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-04T22:48:41Z
- **Completed:** 2026-03-04T22:52:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Email verification page (`/verify-email`) reads `?email=` param, shows 6-digit OTP input with KeyRound icon, submits to `/auth/verify-email`, redirects to `/onboarding` on success, resend button with 60-second countdown timer and "New code sent!" feedback
- Forgot password page (`/forgot-password`) accepts email, calls `/auth/forgot-password`, shows enumeration-safe success message (never reveals if email exists), "Back to Login" link in footer and success state
- Password reset page (`/reset-password`) reads `?token=` param, shows inline error with recovery link if missing, new password + confirm password with zod refine validation ("Passwords do not match"), password visibility toggle, calls `/auth/reset-password`, redirects to `/login?reset=success` on success

## Task Commits

Each task was committed atomically:

1. **Task 1: Create email verification page with OTP input** - `98af771` (feat) — committed as part of 13-02 Suspense fix that pre-built this page
2. **Task 2: Create forgot password and reset password pages** - `6620b19` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `frontend/src/app/(auth)/verify-email/page.tsx` — 6-digit OTP input, resend with 60s cooldown, Suspense wrapper for useSearchParams
- `frontend/src/app/(auth)/forgot-password/page.tsx` — email form, enumeration-safe success state, ArrowLeft footer link
- `frontend/src/app/(auth)/reset-password/page.tsx` — new_password + confirm_password with zod refine, password visibility toggle, Suspense wrapper

## Decisions Made

- **Suspense wrapper pattern** — Next.js App Router requires `useSearchParams()` to be inside a Suspense boundary during static generation. All pages using search params (verify-email, reset-password) use the inner-component + Suspense-wrapped export pattern consistently.
- **Enumeration-safe forgot-password** — Always shows success state regardless of whether the email exists. This prevents user enumeration: an attacker cannot determine valid accounts by observing success/failure.
- **Inline error state for missing token** — reset-password shows a card with an error message and link to `/forgot-password` rather than silently redirecting. This provides a better user experience when navigating directly to the URL.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Suspense boundary required for useSearchParams() in verify-email page**
- **Found during:** Task 1 (verify-email page creation)
- **Issue:** Next.js 16 App Router requires `useSearchParams()` to be wrapped in a Suspense boundary for static generation. Without this, the production build fails with "useSearchParams() should be wrapped in a suspense boundary".
- **Fix:** Split page into inner `VerifyEmailContent` component that reads search params, and outer `VerifyEmailPage` default export that wraps in `<Suspense fallback={null}>`. Same pattern applied to reset-password page.
- **Files modified:** `frontend/src/app/(auth)/verify-email/page.tsx`, `frontend/src/app/(auth)/reset-password/page.tsx`
- **Verification:** `pnpm build` passes with all 9 routes in output including `/verify-email`, `/forgot-password`, `/reset-password`
- **Committed in:** `98af771` (part of Task 1 — pre-built in 13-02 as blocking fix), `6620b19` (Task 2)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Required fix for production build correctness. No scope creep. The Suspense pattern is now established as a project convention.

## Issues Encountered

- verify-email page was already fully implemented and committed (98af771) during 13-02 execution as a Rule 3 fix to unblock the build at that time. Task 1 was effectively pre-completed — verified content matched plan requirements exactly (206 lines, correct hooks, OTP input, cooldown, redirect logic).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All secondary auth flows complete: email verification, forgot password, password reset
- `/login?reset=success` query param is set but login page doesn't yet show a success banner — this is acceptable for MVP
- Ready for Phase 13-04: MFA verify page and onboarding workspace creation page

---
*Phase: 13-auth-flows-ui*
*Completed: 2026-03-04*
