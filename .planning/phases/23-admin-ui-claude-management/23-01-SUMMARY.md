---
phase: 23-admin-ui-claude-management
plan: "01"
subsystem: ui
tags: [react, next.js, typescript, tanstack-query, admin, claude, wxcode]

# Dependency graph
requires:
  - phase: 22-claude-provisioning-api
    provides: "PUT/DELETE /claude-token, PATCH /claude-config, POST /activate endpoints"
  - phase: 18-super-admin-enhanced
    provides: "Admin UI framework, useAdminTenants hook, tenant detail page scaffolding"
provides:
  - "4 mutation hooks for Claude management: useSetClaudeToken, useRevokeClaudeToken, useUpdateClaudeConfig, useActivateTenant"
  - "Extended TenantDetailResponse type with Phase 20 wxcode fields"
  - "WXCODE Integration card on tenant detail page with token management, config editing, and tenant activation UI"
affects:
  - 23-02-admin-ui-claude-management

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inline form expansion: toggle button reveals GlowInput + GlowButton form in-place, cancel resets state"
    - "Conditional section visibility: tenant.status==='pending_setup' gates Activate Tenant section"
    - "Token masking: password type input for entry, ****-****-**** display when set"

key-files:
  created: []
  modified:
    - frontend/src/hooks/useAdminTenants.ts
    - frontend/src/app/admin/tenants/[tenantId]/page.tsx

key-decisions:
  - "wxcodeStatusBadge added as separate function from statusBadge — handles wxcode lifecycle statuses (pending_setup/active/suspended/cancelled) vs legacy is_suspended/is_deleted booleans"
  - "Config form sends only non-empty fields (partial PATCH) — 0 for budget means unlimited (maps to NULL in DB, consistent with 22-01 decision)"
  - "Token input uses type=password during entry to prevent shoulder-surfing; display always masked as ****-****-****"

patterns-established:
  - "Inline mutation form pattern: useState for show/values/error, mutateAsync with try/catch for ApiError, reset state on success"
  - "ClaudeConfigUpdate interface separates config payload type from mutation variables for cleaner type composition"

requirements-completed: [UI-TOKEN, UI-CONFIG, UI-ACTIVATE, UI-STATUS, UI-HOOKS]

# Metrics
duration: 2min
completed: 2026-03-08
---

# Phase 23 Plan 01: Admin UI Claude Management Summary

**WXCODE Integration card on tenant detail page with masked Claude token management, config editing, and pending_setup activation flow using 4 new TanStack Query mutation hooks**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-08T14:25:14Z
- **Completed:** 2026-03-08T14:27:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Extended `TenantDetailResponse` with 8 Phase 20 wxcode fields (status, has_claude_token, claude_default_model, claude_max_concurrent_sessions, claude_monthly_token_budget, database_name, default_target_stack, neo4j_enabled)
- Added 4 mutation hooks following existing adminApiClient + query invalidation pattern: `useSetClaudeToken`, `useRevokeClaudeToken`, `useUpdateClaudeConfig`, `useActivateTenant`
- Added full-width WXCODE Integration card to tenant detail page with status badge, Claude token section (set/update/revoke with reason), config display/edit form (model/sessions/budget), and activate section (visible only for pending_setup)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add mutation hooks and extend TenantDetailResponse type** - `06e3fd0` (feat)
2. **Task 2: Add WXCODE Integration section to tenant detail page** - `f2f89a0` (feat)

## Files Created/Modified
- `frontend/src/hooks/useAdminTenants.ts` - Extended TenantDetailResponse with Phase 20 fields; added useSetClaudeToken, useRevokeClaudeToken, useUpdateClaudeConfig, useActivateTenant, ClaudeConfigUpdate interface
- `frontend/src/app/admin/tenants/[tenantId]/page.tsx` - Added wxcodeStatusBadge(), imported 4 new hooks, added 4 form state groups, added WXCODE Integration card (744 LOC total)

## Decisions Made
- `wxcodeStatusBadge` as a new separate function alongside the existing `statusBadge` — the existing badge uses legacy `is_suspended`/`is_deleted` booleans for the page header; the WXCODE section uses the new `status` string field for wxcode-specific lifecycle
- Config form sends partial PATCH — only non-empty fields included in payload; `0` for budget maps to unlimited (NULL) in DB, consistent with Phase 22-01 decision
- Token entry uses `type="password"` to prevent shoulder-surfing during entry; when has_claude_token is true, the display always shows `****-****-****` (never reveals actual value)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 4 Claude management mutation hooks ready for use in Phase 23-02
- WXCODE Integration card fully functional — connects to all 5 Phase 22 endpoints
- TypeScript zero errors, Next.js build passing (744 LOC page)
- Phase 23-02 (integration tests or additional UI) can proceed immediately

## Self-Check: PASSED

- `frontend/src/hooks/useAdminTenants.ts` — FOUND
- `frontend/src/app/admin/tenants/[tenantId]/page.tsx` — FOUND
- `.planning/phases/23-admin-ui-claude-management/23-01-SUMMARY.md` — FOUND
- commit `06e3fd0` (Task 1) — FOUND
- commit `f2f89a0` (Task 2) — FOUND

---
*Phase: 23-admin-ui-claude-management*
*Completed: 2026-03-08*
