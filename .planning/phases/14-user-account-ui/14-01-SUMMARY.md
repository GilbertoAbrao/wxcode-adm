---
phase: 14-user-account-ui
plan: 01
subsystem: ui
tags: [react, tanstack-query, react-hook-form, zod, typescript, next-js]

# Dependency graph
requires:
  - phase: 13-auth-flows-ui
    provides: apiClient, auth token management (getAccessToken, API_BASE), GlowButton, GlowInput, LoadingSkeleton, ErrorState
  - phase: 12-design-system
    provides: AppShell with sidebar, Obsidian Studio dark theme, ui component barrel export
  - phase: 07-user-account
    provides: backend endpoints GET/PATCH /users/me, POST /users/me/avatar, POST /users/me/change-password, GET/DELETE /users/me/sessions
provides:
  - useCurrentUser hook (GET /users/me, 30s staleTime)
  - useUpdateProfile hook (PATCH /users/me, invalidates user/me)
  - useUploadAvatar hook (POST /users/me/avatar, direct fetch for multipart)
  - useChangePassword hook (POST /users/me/change-password)
  - useUserSessions hook (GET /users/me/sessions, 10s staleTime)
  - useRevokeSession hook (DELETE /users/me/sessions/{id})
  - useRevokeAllSessions hook (DELETE /users/me/sessions)
  - /account page with Profile section (avatar display/upload + display name edit)
  - Placeholder Password and Sessions sections (for Plan 14-02)
affects:
  - 14-02 (Password and Sessions sections use hooks from useUserAccount.ts)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Direct fetch for multipart uploads — bypass apiClient Content-Type to let browser set multipart boundary"
    - "useEffect with reset() pattern for react-hook-form pre-population from async query data"
    - "2-second showSaved state feedback pattern for save confirmations without navigation"

key-files:
  created:
    - frontend/src/hooks/useUserAccount.ts
    - frontend/src/app/(app)/account/page.tsx
  modified: []

key-decisions:
  - "Avatar upload uses direct fetch (not apiClient) because apiClient always sets Content-Type: application/json which breaks multipart/form-data boundary; direct fetch with only Authorization header lets browser set correct Content-Type"
  - "Account page split into ProfileSection component (inline) + AccountPage root — keeps form state encapsulated near its hooks"
  - "Password and Sessions sections stubbed as placeholder divs with TODO comments rather than omitted — maintains page structure for Plan 14-02"

patterns-established:
  - "useEffect([user?.field, reset]) pattern: pre-populate react-hook-form from TanStack Query data by tracking specific field as dependency"
  - "showSaved boolean state + setTimeout(2000) for transient success feedback — no toast library needed"

requirements-completed: [UAI-01]

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 14 Plan 01: User Account UI Summary

**TanStack Query hooks for all user account endpoints plus /account page with avatar upload and display name inline editing**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-04T02:37:17Z
- **Completed:** 2026-03-04T02:39:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created `useUserAccount.ts` with 7 exported hooks covering the full user account API surface (profile read/update, avatar upload, password change, session list/revoke)
- Built `/account` page rendering inside the AppShell (sidebar visible) with a Profile section: avatar display with initials fallback, click-to-upload file input, and display name form with zod validation
- Avatar upload correctly uses direct fetch to avoid apiClient's forced `Content-Type: application/json` header — multipart boundary set by browser automatically

## Task Commits

Each task was committed atomically:

1. **Task 1: Create useUserAccount.ts with profile and avatar hooks** - `4e8b082` (feat)
2. **Task 2: Create /account page with profile section** - `8272589` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `frontend/src/hooks/useUserAccount.ts` - 7 TanStack Query hooks for user account API: useCurrentUser, useUpdateProfile, useUploadAvatar, useChangePassword, useUserSessions, useRevokeSession, useRevokeAllSessions
- `frontend/src/app/(app)/account/page.tsx` - Account settings page (226 lines) with Profile section: avatar display/upload, display name form with react-hook-form + zod, loading/error states

## Decisions Made
- **Avatar upload via direct fetch:** apiClient always prepends `Content-Type: application/json` to all requests; multipart uploads require the browser to set `Content-Type: multipart/form-data; boundary=...` automatically. Using direct fetch with only the `Authorization` header solves this cleanly without modifying apiClient.
- **ProfileSection as inline component:** Keeps avatar and form state (fileInputRef, showSaved, form register) co-located and encapsulated within the page file rather than creating a separate component file — appropriate for plan scope.
- **Placeholder sections stubbed:** Password and Sessions sections are rendered as visible placeholder cards rather than omitted, maintaining the intended 3-section page structure that Plan 14-02 will populate.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `useUserAccount.ts` exports `useChangePassword`, `useUserSessions`, `useRevokeSession`, `useRevokeAllSessions` — all ready for Plan 14-02 to implement the Password and Sessions sections
- `/account` page structure already has placeholder sections at the correct positions for Plan 14-02 to fill in
- No backend changes required — all endpoints already live at localhost:8040 (Phase 7)

---
*Phase: 14-user-account-ui*
*Completed: 2026-03-04*
