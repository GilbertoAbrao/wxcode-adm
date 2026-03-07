---
phase: 21-plan-limits-extension
plan: 01
subsystem: payments
tags: [sqlalchemy, alembic, pydantic, billing, plan-limits, wxcode]

# Dependency graph
requires:
  - phase: 20-crypto-service-tenant-extension
    provides: Tenant model extension pattern, migration 008 with server_default pattern
  - phase: 4-billing
    provides: Plan model, billing schemas, service layer, test helpers
provides:
  - Plan model with max_projects (default 5), max_output_projects (default 20), max_storage_gb (default 10)
  - Migration 009 adding 3 columns to plans table with server_default for existing rows
  - CreatePlanRequest, UpdatePlanRequest, PlanResponse updated with limit fields
  - create_plan and update_plan service functions handle new fields
  - 3 integration tests covering plan CRUD with limit fields
affects:
  - phase-23-admin-ui-claude-management (plan form needs these fields)
  - wxcode-engine (per-tenant limit enforcement)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - server_default on non-nullable migration columns — existing rows get defaults without data migration
    - Partial update pattern: if body.field is not None: plan.field = body.field

key-files:
  created:
    - backend/alembic/versions/009_add_plan_limits_fields.py
  modified:
    - backend/src/wxcode_adm/billing/models.py
    - backend/src/wxcode_adm/billing/schemas.py
    - backend/src/wxcode_adm/billing/service.py
    - backend/tests/test_billing.py

key-decisions:
  - "max_projects default 5, max_output_projects default 20, max_storage_gb default 10 — same in model default and migration server_default"
  - "Limit fields not included in Stripe price re-sync logic — they are wxcode-only operational limits, not billing amounts"
  - "ge=1 validation on CreatePlanRequest/UpdatePlanRequest limit fields — zero limits are operationally invalid"

patterns-established:
  - "Limit fields follow exact mapped_column() pattern from member_cap — Integer, nullable=False, default=N"
  - "UpdatePlanRequest partial update: new limit fields use Optional[int] = Field(default=None, ge=1)"
  - "Migration 009: server_default=sa.text('N') ensures existing plan rows receive defaults without data migration"

requirements-completed: [PLAN-LIMITS-01, PLAN-LIMITS-02, PLAN-LIMITS-03, PLAN-LIMITS-04, PLAN-LIMITS-05]

# Metrics
duration: 3min
completed: 2026-03-07
---

# Phase 21 Plan 01: Plan Limits Extension Summary

**Plan model extended with max_projects/max_output_projects/max_storage_gb integer fields, migration 009 with server_default, updated billing schemas and service, 3 new passing tests**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-07T20:08:32Z
- **Completed:** 2026-03-07T20:11:08Z
- **Tasks:** 2
- **Files modified:** 4 (+ 1 created)

## Accomplishments

- Plan SQLAlchemy model has 3 new integer limit fields (max_projects=5, max_output_projects=20, max_storage_gb=10 defaults)
- Alembic migration 009 adds columns with server_default so existing plan rows get defaults automatically
- All three Pydantic schemas (CreatePlanRequest, UpdatePlanRequest, PlanResponse) updated with limit fields
- create_plan() passes new fields to Plan constructor; update_plan() applies non-None fields selectively
- 23 total billing tests pass (20 existing + 3 new), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Plan limit fields, migration 009, update schemas and service** - `ffb28aa` (feat)
2. **Task 2: Add tests for plan limits CRUD** - `8e3d656` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/billing/models.py` - Added max_projects, max_output_projects, max_storage_gb mapped columns
- `backend/src/wxcode_adm/billing/schemas.py` - Updated all 3 schema classes with new limit fields
- `backend/src/wxcode_adm/billing/service.py` - create_plan and update_plan handle new fields
- `backend/alembic/versions/009_add_plan_limits_fields.py` - Migration 009 (008->009, 3 columns with server_default)
- `backend/tests/test_billing.py` - 3 new tests: explicit limits, defaults, partial update

## Decisions Made

- Limit fields not wired into Stripe price re-sync — they are wxcode-only operational limits, not billing amounts. This keeps the service clean and avoids unnecessary Stripe API calls.
- ge=1 validation on limit fields (not ge=0) — zero limits are operationally invalid; a plan must allow at least 1 project/output/GB.
- Defaults match between SQLAlchemy model default= and migration server_default= for consistency.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — straightforward field extension following established patterns from Phase 20 (migration 008) and the existing member_cap field.

## User Setup Required

None - no external service configuration required. Migration 009 will be applied automatically by the deployment process.

## Next Phase Readiness

- Plan model limit fields are ready for Phase 23 Admin UI (Claude Management) to surface in the plan form
- wxcode engine can read these fields from the Plan via TenantSubscription to enforce per-tenant limits
- No additional backend work needed for these 3 fields — CRUD is complete end-to-end

---
*Phase: 21-plan-limits-extension*
*Completed: 2026-03-07*

## Self-Check: PASSED

All files found, all commits verified.
- ffb28aa: feat(21-01): add max_projects, max_output_projects, max_storage_gb to Plan
- 8e3d656: feat(21-01): add tests for plan limits CRUD
