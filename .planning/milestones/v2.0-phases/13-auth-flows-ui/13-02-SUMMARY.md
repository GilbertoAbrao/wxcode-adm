---
phase: 13-auth-flows-ui
plan: 02
subsystem: auth
tags: [react, react-hook-form, zod, next.js, typescript, suspense]

# Dependency graph
requires:
  - phase: 13-auth-flows-ui
    plan: 01
    provides: useSignup/useLogin mutations, ApiError, AuthProvider, useAuthContext, (auth) layout, react-hook-form + zod installed

provides:
  - Shared zod validation schemas for all auth forms (validations.ts)
  - Type aliases: SignupFormData, LoginFormData, ForgotPasswordFormData, etc.
  - /signup page with email+password form, inline zod errors, redirect to /verify-email
  - /login page with MFA branching (mfa_required), wxcode redirect, normal dashboard redirect
  - 401/403-specific error messages on login (wrong password, unverified email + resend link)

affects:
  - 13-03-PLAN.md (verify-email, forgot-password, reset-password pages use validations.ts schemas)
  - 13-04-PLAN.md (onboarding workspace page uses workspaceSchema from validations.ts)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Suspense wrapper pattern for pages using useSearchParams() — inner content component + exported page wrapping it
    - Contextual API error rendering (401 vs 403 vs generic) in login form
    - Show/hide password toggle via rightIcon + onRightIconClick on GlowInput

key-files:
  created:
    - frontend/src/lib/validations.ts
    - frontend/src/app/(auth)/signup/page.tsx
    - frontend/src/app/(auth)/login/page.tsx
    - frontend/src/app/(auth)/mfa-verify/page.tsx
    - frontend/src/app/(auth)/verify-email/page.tsx
  modified: []

key-decisions:
  - "Suspense boundary required for all pages using useSearchParams() in Next.js App Router — extract to inner component, export wrapper with <Suspense fallback={null}>"
  - "Login page renders contextual error messages: 401 = wrong credentials, 403 = unverified email with direct link to /verify-email?email=..., default = error.message"
  - "mfa-setup route included in login branching (mfa_setup_required) as placeholder for Phase 13 scope boundary — the route will be built in a later phase"

patterns-established:
  - "Pattern: <Suspense fallback={null}><InnerContent /></Suspense> for any page with useSearchParams"
  - "Pattern: signupSchema/loginSchema from @/lib/validations — all auth forms use shared schemas, not inline zod"
  - "Pattern: renderApiError() function in login to handle HTTP status-specific messages"

requirements-completed: [AUI-01, AUI-02]

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 13 Plan 02: Auth Flows UI — Signup and Login Pages Summary

**Signup and login pages with react-hook-form + zod, shared validation schemas, MFA branching, wxcode redirect, and contextual 401/403 error messages using Obsidian Studio GlowInput/GlowButton components**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-04T22:47:57Z
- **Completed:** 2026-03-04T22:50:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Shared `validations.ts` with 8 zod schemas (signupSchema, loginSchema, forgotPasswordSchema, resetPasswordSchema, verifyEmailSchema, workspaceSchema, mfaCodeSchema) and type aliases — reusable by Plans 03 and 04
- Signup page at `/signup` — email+password form, inline errors, show/hide password, redirects to `/verify-email?email=...` on success
- Login page at `/login` — handles 3 response branches: MFA redirect (→ /mfa-verify), wxcode redirect (store tokens + window.location.href), normal login (store tokens + router.push "/")
- Contextual API error messages: 401 = "Invalid email or password", 403 = "Please verify your email first" with link to /verify-email
- Auto-fixed Suspense boundary issues on `mfa-verify` and `verify-email` pages (pre-existing pages that used `useSearchParams()` without Suspense)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create shared validation schemas and signup page** - `08ba2bf` (feat)
2. **Task 2: Create login page with MFA branching and wxcode redirect** - `98af771` (feat)

**Plan metadata:** (this commit) (docs: complete plan)

## Files Created/Modified

- `frontend/src/lib/validations.ts` — Shared zod schemas (82 lines): signupSchema, loginSchema, forgotPasswordSchema, resetPasswordSchema, verifyEmailSchema, workspaceSchema, mfaCodeSchema + type aliases
- `frontend/src/app/(auth)/signup/page.tsx` — Signup page (121 lines): react-hook-form + zod, GlowInput/GlowButton, show/hide password, API error, redirect to /verify-email
- `frontend/src/app/(auth)/login/page.tsx` — Login page (196 lines): 3-branch onSuccess handler, contextual error messages, links to /forgot-password and /signup
- `frontend/src/app/(auth)/mfa-verify/page.tsx` — MFA verify page (191 lines): fixed Suspense boundary around useSearchParams
- `frontend/src/app/(auth)/verify-email/page.tsx` — Verify email page (196 lines): fixed Suspense boundary around useSearchParams

## Decisions Made

- **Suspense boundary pattern**: Next.js App Router requires `useSearchParams()` to be inside a `<Suspense>` boundary during static prerendering. Applied the inner-component pattern (content component + wrapper export) to both `mfa-verify` and `verify-email` pages.
- **Contextual login errors**: 401 and 403 responses get specific user-facing messages rather than generic API error text. The 403 includes a direct link to `/verify-email?email=...` using the watched email field.
- **mfa-setup placeholder**: The `mfa_setup_required` branch in login redirects to `/mfa-setup?token=...` as a placeholder — that page is out of Phase 13 scope but the branching logic is complete.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added Suspense boundaries to mfa-verify and verify-email pages**
- **Found during:** Task 2 (login page) — production build failed with error on `/mfa-verify`
- **Issue:** `useSearchParams()` called directly in top-level page component without Suspense, causing build failure: "useSearchParams() should be wrapped in a suspense boundary at page /mfa-verify"
- **Fix:** Extracted page body to `MfaVerifyContent`/`VerifyEmailContent` inner components; exported default page wraps each in `<Suspense fallback={null}>`. Applied to both mfa-verify (which was partially fixed already) and verify-email.
- **Files modified:** `frontend/src/app/(auth)/mfa-verify/page.tsx`, `frontend/src/app/(auth)/verify-email/page.tsx`
- **Verification:** `pnpm build` passes cleanly with all 6 routes (/login, /signup, /mfa-verify, /verify-email, /, /_not-found)
- **Committed in:** `98af771` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Auto-fix necessary for production build to pass. Both affected pages are pre-existing auth pages. No scope creep — fix aligns with Next.js App Router requirements.

## Issues Encountered

None beyond the Suspense boundary fix documented above.

## User Setup Required

None — no external service configuration required.

## Self-Check: PASSED

- `frontend/src/lib/validations.ts` — FOUND (82 lines, min 20)
- `frontend/src/app/(auth)/signup/page.tsx` — FOUND (121 lines, min 60)
- `frontend/src/app/(auth)/login/page.tsx` — FOUND (196 lines, min 80)
- Task 1 commit `08ba2bf` — FOUND
- Task 2 commit `98af771` — FOUND
- Production build passes with /login and /signup routes — VERIFIED
- GlowButton and GlowInput used in both pages — VERIFIED
- Both pages link to each other (signup → /login, login → /signup) — VERIFIED
- Both pages render inside (auth) layout (no sidebar) — VERIFIED

## Next Phase Readiness

- **Ready for 13-03**: verify-email, forgot-password, reset-password pages can use `verifyEmailSchema`, `forgotPasswordSchema`, `resetPasswordSchema` from validations.ts
- **Ready for 13-04**: Onboarding workspace page can use `workspaceSchema` from validations.ts; `useMfaVerify` and `useCreateWorkspace` already available from 13-01
- No blockers — production build passes clean, all routes prerender successfully

---
*Phase: 13-auth-flows-ui*
*Completed: 2026-03-04*
