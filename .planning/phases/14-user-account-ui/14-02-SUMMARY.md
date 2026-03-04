---
phase: 14-user-account-ui
plan: 02
subsystem: ui
tags: [react, tanstack-query, react-hook-form, zod, typescript, next-js, password-change, sessions]

# Dependency graph
requires:
  - phase: 14-01
    provides: useChangePassword, useUserSessions, useRevokeSession hooks; /account page with ProfileSection and placeholder sections
  - phase: 13-auth-flows-ui
    provides: apiClient (with ApiError.status), GlowButton, GlowInput, LoadingSkeleton, ErrorState
  - phase: 12-design-system
    provides: AppShell with sidebar, Obsidian Studio dark theme
  - phase: 07-user-account
    provides: POST /users/me/change-password, GET /users/me/sessions, DELETE /users/me/sessions/{id}
provides:
  - changePasswordSchema with current_password, new_password (reuses passwordSchema), confirm_password + match refinement
  - ChangePasswordFormData type alias
  - /account page password change section: current/new/confirm fields with show/hide toggles, 400-aware error message, 3s success feedback
  - /account page sessions section: device info + IP + relative time, Current badge, per-session Revoke button

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "400 HTTP status check on ApiError for contextual inline error messages (not generic fallback)"
    - "revokeSessionMutation.variables === session.id pattern for per-row loading state in a list"
    - "formatRelativeTime() inline helper — avoids date-fns dependency for simple relative timestamps"

key-files:
  created: []
  modified:
    - frontend/src/lib/validations.ts
    - frontend/src/app/(app)/account/page.tsx

key-decisions:
  - "Password change error handling checks ApiError.status === 400 specifically to show 'Current password is incorrect' rather than a generic error — differentiates auth failure from server error"
  - "showCurrentPassword and showNewPassword are separate state variables — confirm_password shares showNewPassword to avoid adding a third toggle (confirm is same 'new' password flow)"
  - "Sessions section renders inside AccountPage (not a sub-component) to keep all state at one level per plan spec: single use-client component, no splits"

requirements-completed: [UAI-02, UAI-03]

# Metrics
duration: 1min
completed: 2026-03-04
---

# Phase 14 Plan 02: User Account UI (Password + Sessions) Summary

**Password change form with show/hide toggles and 400-aware error handling, plus active sessions list with per-session revocation — completing the /account page**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-04T23:20:49Z
- **Completed:** 2026-03-04T23:21:49Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `changePasswordSchema` to `validations.ts` — reuses existing `passwordSchema` for `new_password`, adds `current_password` required field, and `.refine()` match check on `confirm_password`
- Completed the `/account` page password section: three GlowInput fields with show/hide password toggles (separate state for current vs new), inline API error with 400-specific message "Current password is incorrect", and 3-second success feedback
- Completed the `/account` page sessions section: per-session rows showing device info, IP address, and `formatRelativeTime()` relative timestamp; current session shows "Current" badge and hides the Revoke button; Revoke button shows per-row loading state using `revokeSessionMutation.variables === session.id`
- `pnpm build` passes with zero TypeScript or compilation errors; `/account` route in build output at 403 lines

## Task Commits

Each task was committed atomically:

1. **Task 1: Add changePasswordSchema to validations.ts** - `3bbd4c3` (feat)
2. **Task 2: Add password change and sessions sections to /account page** - `30edf26` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `frontend/src/lib/validations.ts` — Added `changePasswordSchema` and `ChangePasswordFormData` type alias (12 lines added)
- `frontend/src/app/(app)/account/page.tsx` — Replaced placeholder sections with full password change form and sessions list (226 → 403 lines, +194/-17 diff)

## Decisions Made

- **400-specific error message:** `ApiError.status === 400` produces "Current password is incorrect" while other errors fall back to `error.message` — avoids showing a generic "wrong password" message for server-side 5xx failures
- **Shared showNewPassword toggle for confirm field:** `confirm_password` uses the same `showNewPassword` state as `new_password` — adding a third toggle would be redundant since users enter the same value in both fields
- **Sessions rendered in AccountPage root:** Per plan spec, no sub-components — all session state (`useUserSessions`, `useRevokeSession`) lives at the top-level page component alongside the password state

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 14 complete — all three /account sections (profile, password, sessions) fully implemented
- Requirements UAI-01, UAI-02, UAI-03 all satisfied
- No backend changes required — all endpoints already live at localhost:8040 (Phase 7)

---
*Phase: 14-user-account-ui*
*Completed: 2026-03-04*
