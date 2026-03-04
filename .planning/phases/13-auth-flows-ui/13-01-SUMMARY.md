---
phase: 13-auth-flows-ui
plan: 01
subsystem: auth
tags: [react, tanstack-query, zod, react-hook-form, next.js, jwt, typescript]

# Dependency graph
requires:
  - phase: 12-design-system-foundation
    provides: App shell with QueryProvider, route groups, Tailwind v4 design tokens
provides:
  - Typed fetch wrapper (apiClient) with Authorization header injection, 401 refresh/retry, ApiError
  - In-memory XSS-safe token store (getAccessToken, setTokens, clearTokens, isAuthenticated, refreshTokens)
  - AuthProvider context with user state, login/logout actions, client-side route protection
  - useAuth.ts with 9 TanStack Query mutations for all auth endpoints
  - (auth) route group layout (no sidebar, centered, wxCode logo)
  - react-hook-form, @hookform/resolvers, zod installed for form validation
affects:
  - 13-02-PLAN.md (login, signup pages use useLogin, useSignup, form infrastructure)
  - 13-03-PLAN.md (verify-email, forgot-password, reset-password use useVerifyEmail, etc.)
  - 13-04-PLAN.md (MFA verify, onboarding use useMfaVerify, useCreateWorkspace)
  - 17-super-admin-ui (uses apiClient, useAuthContext for admin data fetching)

# Tech tracking
tech-stack:
  added:
    - react-hook-form@7.71.2
    - "@hookform/resolvers@5.2.2"
    - zod@4.3.6
  patterns:
    - In-memory token storage (XSS-safe, no localStorage)
    - 401 silent refresh + retry pattern in apiClient
    - AuthProvider wraps QueryProvider children in root layout
    - skipAuth flag on public mutations (useMutation calls)
    - Client-side route protection via useEffect in AuthProvider

key-files:
  created:
    - frontend/src/lib/api-client.ts
    - frontend/src/lib/auth.ts
    - frontend/src/hooks/useAuth.ts
    - frontend/src/providers/auth-provider.tsx
    - frontend/src/app/(auth)/layout.tsx
  modified:
    - frontend/src/app/layout.tsx
    - frontend/package.json
    - frontend/pnpm-lock.yaml

key-decisions:
  - "In-memory token storage (module-scoped variables, not localStorage) — XSS-safe. Tokens lost on page reload; user re-logs in. Acceptable for SPA that redirects to wxcode after login."
  - "Client-side route protection via AuthProvider useEffect — not Next.js middleware. Middleware cannot read in-memory tokens (no cookie). Can upgrade to middleware if tokens move to httpOnly cookies."
  - "apiClient injects Authorization header from memory token; on 401 attempts silent refresh once then clears tokens"
  - "(auth) route group has no sidebar — completely separate layout from (app) group"

patterns-established:
  - "Pattern: apiClient<T>(endpoint, options) — all backend calls go through this single typed wrapper"
  - "Pattern: skipAuth: true on all public mutations (signup, login, verify, etc.)"
  - "Pattern: useAuthContext() to access user and auth actions from any client component"
  - "Pattern: AuthProvider wraps entire app inside QueryProvider for auth state availability"

requirements-completed: [AUI-01, AUI-02]

# Metrics
duration: 3min
completed: 2026-03-04
---

# Phase 13 Plan 01: Auth Flows UI Foundation Summary

**Typed API client with in-memory JWT token management, AuthProvider context, 9 TanStack Query auth mutations, (auth) route group layout without sidebar, and react-hook-form + zod installed**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-04T22:42:45Z
- **Completed:** 2026-03-04T22:45:12Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- API client (`apiClient<T>`) with typed fetch, Authorization header injection, 401 silent refresh/retry, `ApiError` class with status and errorCode
- In-memory token store (`auth.ts`) with `setTokens`, `clearTokens`, `isAuthenticated`, `refreshTokens` — XSS-safe, no localStorage
- `AuthProvider` with `AuthUser` type, context, `login`/`logout` actions, user restoration from `/users/me` on mount, client-side route protection
- `useAuth.ts` with 9 TanStack Query mutations: `useSignup`, `useLogin`, `useVerifyEmail`, `useResendVerification`, `useForgotPassword`, `useResetPassword`, `useMfaVerify`, `useCreateWorkspace`, `useLogout`
- `(auth)/layout.tsx` — centered dark layout with wxCode logo, no sidebar, used by all auth pages
- react-hook-form@7.71.2, @hookform/resolvers@5.2.2, zod@4.3.6 installed for form validation in subsequent plans

## Task Commits

Each task was committed atomically:

1. **Task 1: Install form deps, create API client and auth token management** - `b45ac66` (feat)
2. **Task 2: Create AuthProvider, useAuth hooks, auth layout, and route protection** - `f2ad688` (feat)

**Plan metadata:** (this commit) (docs: complete plan)

## Files Created/Modified

- `frontend/src/lib/api-client.ts` — Typed fetch wrapper for backend API with token injection and 401 refresh retry
- `frontend/src/lib/auth.ts` — In-memory token storage (module-scoped, XSS-safe) with refresh helper
- `frontend/src/hooks/useAuth.ts` — 9 TanStack Query mutations for all auth/onboarding endpoints
- `frontend/src/providers/auth-provider.tsx` — AuthProvider context, AuthUser type, login/logout, route protection
- `frontend/src/app/(auth)/layout.tsx` — Auth route group layout (no sidebar, centered, wxCode logo)
- `frontend/src/app/layout.tsx` — Updated to wrap children with AuthProvider inside QueryProvider
- `frontend/package.json` — Added react-hook-form, @hookform/resolvers, zod
- `frontend/pnpm-lock.yaml` — Updated lockfile

## Decisions Made

- **In-memory tokens over localStorage**: Module-scoped variables cannot be accessed by injected scripts (XSS-safe). Trade-off: tokens lost on reload. Acceptable for admin app that redirects to wxcode anyway.
- **Client-side route protection**: Next.js edge middleware cannot read in-memory tokens (they're in the JS heap, not cookies). AuthProvider `useEffect` handles redirects. Can upgrade to httpOnly cookie + middleware in a future phase.
- **skipAuth pattern**: All public auth mutations explicitly pass `skipAuth: true` to prevent token injection on unauthenticated requests.
- **(auth) route group**: Completely separate layout from `(app)` — no AppShell, no sidebar. Route group is URL-invisible (`/login` not `/(auth)/login`).

## Deviations from Plan

None — plan executed exactly as written.

(Plan noted that middleware.ts should be skipped in favor of client-side protection. This was followed as specified.)

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Self-Check: PASSED

All files verified present. Both task commits verified in git log. All artifacts meet minimum line count requirements (api-client.ts: 151, auth.ts: 86, useAuth.ts: 208, auth-provider.tsx: 186, layout.tsx: 29).

## Next Phase Readiness

- **Ready for 13-02**: Login and signup pages can use `useLogin`, `useSignup`, `useAuthContext`, react-hook-form, zod, and `(auth)/layout.tsx`
- **Ready for 13-03**: Verify email, forgot password, reset password pages have all mutations ready
- **Ready for 13-04**: MFA verify and onboarding pages have `useMfaVerify` and `useCreateWorkspace` ready
- No blockers — production build passes clean, zero TypeScript errors

---
*Phase: 13-auth-flows-ui*
*Completed: 2026-03-04*
