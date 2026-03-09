---
phase: 23-admin-ui-claude-management
plan: "06"
subsystem: ui
tags: [react, tanstack-query, fastapi, pydantic, admin]

# Dependency graph
requires:
  - phase: 23-admin-ui-claude-management
    provides: Tenant detail page with Claude provisioning UI (23-01)
  - phase: 22
    provides: activate_tenant service with database_name precondition check
provides:
  - PATCH /admin/tenants/{id}/wxcode-config endpoint for setting database_name, default_target_stack, neo4j_enabled
  - WxcodeConfigUpdateRequest schema with at-least-one-field validation
  - update_wxcode_config service function with audit logging
  - useUpdateWxcodeConfig React mutation hook
  - WXCODE Provisioning section in tenant detail page (visible for pending_setup tenants)
affects: [tenant-activation, wxcode-provisioning, admin-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Partial PATCH pattern: all fields optional, at-least-one-field validator blocks empty payloads
    - Provisioning gate pattern: configure database_name before activation, UI section visible only for pending_setup

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/admin/schemas.py
    - backend/src/wxcode_adm/admin/service.py
    - backend/src/wxcode_adm/admin/router.py
    - frontend/src/hooks/useAdminTenants.ts
    - frontend/src/app/admin/tenants/[tenantId]/page.tsx

key-decisions:
  - "WxcodeConfigUpdateRequest uses at-least-one-field model_validator — rejects all-None payloads, consistent with ClaudeConfigUpdateRequest pattern"
  - "WXCODE Provisioning section visible only when tenant.status === pending_setup — avoids confusing display for active/suspended tenants"
  - "database_name display shows amber warning when not configured — visual cue that activation will fail without it"
  - "Form uses string state for neo4j_enabled ('true'/'false'/'') — empty string means no change, avoids three-way boolean state"

patterns-established:
  - "Provisioning gate pattern: UI section with current-values display + inline edit form, collapsed by default"
  - "Three-option select for boolean fields: no-change option prevents accidental overwrites"

requirements-completed: [UI-ACTIVATE, UI-CONFIG]

# Metrics
duration: 4min
completed: 2026-03-08
---

# Phase 23 Plan 06: WXCODE Provisioning Config Summary

**PATCH /admin/tenants/{id}/wxcode-config endpoint + WXCODE Provisioning UI section unblocking tenant activation by providing a path to configure database_name**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-08T16:10:52Z
- **Completed:** 2026-03-08T16:15:40Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- New PATCH /admin/tenants/{id}/wxcode-config endpoint accepts database_name, default_target_stack, neo4j_enabled (any subset)
- update_wxcode_config service function updates tenant fields with full audit logging via write_audit
- useUpdateWxcodeConfig mutation hook in useAdminTenants.ts using adminApiClient
- WXCODE Provisioning section on tenant detail page (pending_setup tenants only) — shows current values and inline edit form with database_name, target stack, and neo4j_enabled toggle

## Task Commits

Each task was committed atomically:

1. **Task 1: Add wxcode-config PATCH endpoint (schema + service + router)** - `49eefaa` (feat)
2. **Task 2: Add useUpdateWxcodeConfig hook and WXCODE Provisioning UI section** - `a817597` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `backend/src/wxcode_adm/admin/schemas.py` - Added WxcodeConfigUpdateRequest schema with at-least-one-field validation
- `backend/src/wxcode_adm/admin/service.py` - Added update_wxcode_config service function with audit logging
- `backend/src/wxcode_adm/admin/router.py` - Added PATCH /admin/tenants/{tenant_id}/wxcode-config endpoint + WxcodeConfigUpdateRequest import
- `frontend/src/hooks/useAdminTenants.ts` - Added WxcodeConfigUpdate interface and useUpdateWxcodeConfig mutation hook
- `frontend/src/app/admin/tenants/[tenantId]/page.tsx` - Added Database icon import, provisioning form state, handleUpdateProvisioning handler, WXCODE Provisioning UI section

## Decisions Made
- WxcodeConfigUpdateRequest uses at-least-one-field model_validator — consistent with ClaudeConfigUpdateRequest pattern
- WXCODE Provisioning section visible only for pending_setup tenants — prevents confusing display in other states
- database_name shows amber "Not configured" warning when null — direct visual cue that activation will fail
- neo4j_enabled uses string state with "no change" option — prevents accidental boolean overwrites

## Deviations from Plan

None — plan executed exactly as written. Linter auto-modified budget field names (`claude_monthly_token_budget` → `claude_5h_token_budget`/`claude_weekly_token_budget`) in router.py and service.py to match actual model fields, which is correct and intentional.

## Issues Encountered
- System Python (3.9) failed to import modules due to `str | None` syntax requiring Python 3.10+. Used `/opt/homebrew/bin/python3.11` for all verification. Project uses `requires-python = ">=3.11"` so this is expected.
- Pre-existing test failures: all tests in the suite fail with `TypeError: 'token_quota' is an invalid keyword argument for Plan`. This predates this plan (conftest.py uses `token_quota=10000` but Plan model has `token_quota_5h`/`token_quota_weekly`). Documented in deferred items — out of scope.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- Admin can now set database_name before activating a tenant — the full activation flow is unblocked
- Gap closure complete: UI-ACTIVATE and UI-CONFIG requirements fulfilled
- Pre-existing test suite failure (token_quota field mismatch in conftest.py) should be addressed in a future cleanup plan

## Self-Check: PASSED

All created/modified files verified present. All commits verified in git log.
- `backend/src/wxcode_adm/admin/schemas.py`: FOUND
- `backend/src/wxcode_adm/admin/service.py`: FOUND
- `backend/src/wxcode_adm/admin/router.py`: FOUND
- `frontend/src/hooks/useAdminTenants.ts`: FOUND
- `frontend/src/app/admin/tenants/[tenantId]/page.tsx`: FOUND
- Commit `49eefaa`: FOUND
- Commit `a817597`: FOUND

---
*Phase: 23-admin-ui-claude-management*
*Completed: 2026-03-08*
