---
phase: 17-super-admin-ui
plan: "01"
subsystem: ui
tags: [react, nextjs, typescript, tanstack-query, zod, react-hook-form, admin-auth, jwt]

# Dependency graph
requires:
  - phase: 13-auth-flows-ui
    provides: auth.ts, api-client.ts, auth-provider.tsx patterns for token isolation
  - phase: 08-super-admin
    provides: backend admin auth endpoints (POST /admin/login, /admin/refresh, /admin/logout)

provides:
  - Isolated admin token store (admin-auth.ts) separate from tenant user auth
  - adminApiClient fetch wrapper with admin token injection and silent refresh
  - useAdminLogin / useAdminLogout TanStack Query mutations
  - AdminAuthProvider with route protection for /admin/* paths
  - Admin segment layout (frontend/src/app/admin/layout.tsx)
  - Admin login page at /admin/login with email/password form

affects: [17-02-super-admin-ui, 17-03-super-admin-ui, 17-04-super-admin-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Isolated admin auth store: module-scoped _adminAccessToken/_adminRefreshToken separate from user _accessToken/_refreshToken"
    - "adminApiClient mirrors apiClient but imports from admin-auth.ts — admin and user auth are never mixed"
    - "Admin route protection via AdminAuthProvider (not Next.js middleware) — same client-side useEffect pattern as AuthProvider"
    - "PUBLIC_PATHS in auth-provider.tsx includes /admin — tenant AuthProvider does not intercept admin routes"
    - "Admin layout is a real URL segment (/admin) not a route group — AdminAuthProvider wraps the segment only"

key-files:
  created:
    - frontend/src/lib/admin-auth.ts
    - frontend/src/lib/admin-api-client.ts
    - frontend/src/hooks/useAdminAuth.ts
    - frontend/src/providers/admin-auth-provider.tsx
    - frontend/src/app/admin/layout.tsx
    - frontend/src/app/admin/login/page.tsx
  modified:
    - frontend/src/providers/auth-provider.tsx

key-decisions:
  - "Admin token store uses separate module-scoped variables (_adminAccessToken, _adminRefreshToken) — never shared with user token variables from auth.ts"
  - "adminApiClient imports from admin-auth.ts (not auth.ts) and implements a local parseErrorBody copy — reuses ApiError class from api-client.ts"
  - "AdminAuthProvider does not fetch /users/me on mount (no admin profile endpoint) — just checks isAdminAuthenticated() for in-memory token"
  - "admin/layout.tsx is a real segment layout (not a route group) so /admin appears in URLs; AdminAuthProvider wraps only this segment"
  - "/admin added to PUBLIC_PATHS in auth-provider.tsx so the tenant AuthProvider never redirects admin paths to /login"
  - "Admin login page has no Forgot password / Create account links — admin accounts are seeded, not self-service"

patterns-established:
  - "Dual auth isolation: tenant auth (auth.ts + api-client.ts + auth-provider.tsx) and admin auth (admin-auth.ts + admin-api-client.ts + admin-auth-provider.tsx) are completely separate"
  - "Admin segment layout pattern: app/admin/layout.tsx wraps with AdminAuthProvider; sub-pages use useAdminAuthContext"

requirements-completed: [SAI-01]

# Metrics
duration: 2min
completed: 2026-03-05
---

# Phase 17 Plan 01: Super-Admin UI Foundation Summary

**Isolated admin auth with in-memory token store, adminApiClient, AdminAuthProvider route protection, and /admin/login page using react-hook-form + zod**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-05T21:37:15Z
- **Completed:** 2026-03-05T21:39:48Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Isolated admin auth module (admin-auth.ts) with separate in-memory token variables that never touch the user auth store
- adminApiClient with admin token injection, silent refresh on 401, and retry — mirrors apiClient but routes through admin-auth.ts
- AdminAuthProvider with useEffect route protection: unauthenticated /admin/* redirects to /admin/login; authenticated admin on /admin/login redirects to /admin/tenants
- Admin login page at /admin/login with GlowInput + react-hook-form + zod, contextual error messages (401/403), and "Back to app" escape link
- Tenant AuthProvider updated to treat /admin/* as public — no route conflict between the two auth systems

## Task Commits

Each task was committed atomically:

1. **Task 1: Create admin auth module, admin API client, and admin auth hooks** - `37865dd` (feat)
2. **Task 2: Create AdminAuthProvider, admin layout, and admin login page** - `ca1abd6` (feat)

## Files Created/Modified

- `frontend/src/lib/admin-auth.ts` - In-memory admin token store with 6 exports: getAdminAccessToken, getAdminRefreshToken, setAdminTokens, clearAdminTokens, isAdminAuthenticated, refreshAdminTokens
- `frontend/src/lib/admin-api-client.ts` - Typed fetch wrapper for admin endpoints with token injection, 401 refresh retry, local parseErrorBody helper; reuses ApiError from api-client.ts
- `frontend/src/hooks/useAdminAuth.ts` - useAdminLogin (skipAuth: true) and useAdminLogout TanStack Query mutations
- `frontend/src/providers/admin-auth-provider.tsx` - AdminAuthProvider with route protection, login/logout handlers, useAdminAuthContext hook
- `frontend/src/app/admin/layout.tsx` - Admin segment layout wrapping children with AdminAuthProvider and wxCode logo header
- `frontend/src/app/admin/login/page.tsx` - Admin login form (email + password, show/hide toggle, contextual API errors, "Back to app" link)
- `frontend/src/providers/auth-provider.tsx` - Added "/admin" to PUBLIC_PATHS so tenant AuthProvider ignores /admin/* paths

## Decisions Made

- Admin token store uses completely separate module-scoped variables from user auth — admin login has zero effect on user session and vice versa
- adminApiClient implements a local copy of parseErrorBody (not exported from api-client.ts) and reuses the ApiError class via import
- AdminAuthProvider uses isAdminAuthenticated() check (not a /profile API call) on mount — there is no admin /me endpoint
- Admin layout is a real URL segment (app/admin/layout.tsx), not a route group, so /admin appears in browser URLs and AdminAuthProvider wraps only admin pages
- /admin added to PUBLIC_PATHS in auth-provider.tsx to prevent the tenant AuthProvider from intercepting admin navigation and redirecting to /login

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Admin auth foundation complete — /admin/login page renders and calls POST /api/v1/admin/login
- AdminAuthProvider route protection active — unauthenticated /admin/tenants redirects to /admin/login
- Ready for Plan 17-02: Admin Tenant Management (tenant list + detail + suspend/reactivate/delete)

---
*Phase: 17-super-admin-ui*
*Completed: 2026-03-05*
