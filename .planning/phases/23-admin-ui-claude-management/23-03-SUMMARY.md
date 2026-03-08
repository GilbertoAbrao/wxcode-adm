---
phase: 23-admin-ui-claude-management
plan: "03"
subsystem: database
tags: [sqlalchemy, alembic, pydantic, postgresql, migration, billing, claude]

# Dependency graph
requires:
  - phase: 20-tenant-model-extension
    provides: claude_monthly_token_budget on Tenant model
  - phase: 21-plan-limits-extension
    provides: Plan model with token_quota field
  - phase: 22-claude-provisioning-api
    provides: update_claude_config endpoint and service

provides:
  - Dual budget fields on Tenant (claude_5h_token_budget + claude_weekly_token_budget)
  - Dual quota fields on Plan (token_quota_5h + token_quota_weekly)
  - Migration 010 with data preservation
  - All backend schemas and services use dual fields
  - Updated tests (161 tests pass)

affects:
  - 23-05 (frontend plan config UI needs dual fields)
  - billing/dependencies (quota enforcement uses token_quota_5h)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual time-window quota fields: 5h window + weekly window instead of monthly"
    - "Data migration with UPDATE before DROP (preserving existing values)"
    - "0 = unlimited in API, stored as NULL in DB (same pattern as before)"

key-files:
  created:
    - backend/alembic/versions/010_split_budget_quota_dual_fields.py
  modified:
    - backend/src/wxcode_adm/tenants/models.py
    - backend/src/wxcode_adm/billing/models.py
    - backend/src/wxcode_adm/admin/schemas.py
    - backend/src/wxcode_adm/billing/schemas.py
    - backend/src/wxcode_adm/admin/service.py
    - backend/src/wxcode_adm/admin/router.py
    - backend/src/wxcode_adm/billing/service.py
    - backend/src/wxcode_adm/billing/dependencies.py
    - backend/tests/conftest.py
    - backend/tests/test_billing.py
    - backend/tests/test_claude_provisioning.py
    - backend/tests/test_tenant_model_extension.py
    - backend/tests/test_super_admin.py

key-decisions:
  - "token_quota_5h used as enforcement field in _enforce_token_quota (tighter 5h window = primary constraint)"
  - "Data migration copies existing values to BOTH new columns to preserve prior data"
  - "server_default=text('0') on plan quota columns ensures non-nullable constraint is safe for existing rows"
  - "billing/dependencies.py auto-fixed (Rule 1) to use token_quota_5h instead of removed token_quota"

requirements-completed: [UI-CONFIG, UI-STATUS]

# Metrics
duration: 11min
completed: 2026-03-08
---

# Phase 23 Plan 03: Dual Budget/Quota Fields Summary

**Replaced single monthly budget/quota fields with 5h-window + weekly-window dual fields across all backend layers: models, migration 010, schemas, services, and tests**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-08T16:11:07Z
- **Completed:** 2026-03-08T16:22:00Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- Split Tenant.claude_monthly_token_budget into claude_5h_token_budget + claude_weekly_token_budget
- Split Plan.token_quota into token_quota_5h + token_quota_weekly
- Migration 010 adds new columns, preserves existing data via UPDATE, drops old columns (with rollback support)
- All admin and billing schemas updated: TenantDetailResponse, ClaudeConfigUpdateRequest, CreatePlanRequest, UpdatePlanRequest, PlanResponse
- Admin service get_tenant_detail and update_claude_config updated with dual fields
- Billing service create_plan and update_plan updated with dual fields
- billing/dependencies.py quota enforcement updated to use token_quota_5h
- 161 tests pass (3 pre-existing audit log failures unrelated to this plan)

## Task Commits

1. **Task 1: Split model fields and create migration 010** - `abb9451` + `872b5fd` (feat)
2. **Task 2: Update all backend schemas and services for dual fields** - `e8eed24` (feat)

## Files Created/Modified
- `backend/alembic/versions/010_split_budget_quota_dual_fields.py` - Migration adding dual columns, data migration, dropping old columns
- `backend/src/wxcode_adm/tenants/models.py` - claude_5h_token_budget + claude_weekly_token_budget (both nullable)
- `backend/src/wxcode_adm/billing/models.py` - token_quota_5h + token_quota_weekly (both non-nullable)
- `backend/src/wxcode_adm/admin/schemas.py` - TenantDetailResponse and ClaudeConfigUpdateRequest updated
- `backend/src/wxcode_adm/billing/schemas.py` - CreatePlanRequest, UpdatePlanRequest, PlanResponse updated
- `backend/src/wxcode_adm/admin/service.py` - get_tenant_detail and update_claude_config updated
- `backend/src/wxcode_adm/admin/router.py` - update_claude_config endpoint passes dual fields
- `backend/src/wxcode_adm/billing/service.py` - create_plan and update_plan use dual fields
- `backend/src/wxcode_adm/billing/dependencies.py` - quota enforcement uses token_quota_5h
- `backend/tests/conftest.py` - free plan seeded with dual quota fields
- `backend/tests/test_billing.py` - all plan creation/assertion references updated
- `backend/tests/test_claude_provisioning.py` - all budget field assertions updated
- `backend/tests/test_tenant_model_extension.py` - all budget field assertions updated
- `backend/tests/test_super_admin.py` - paid plan seeded with dual quota fields

## Decisions Made
- token_quota_5h used as the enforcement field in _enforce_token_quota — the 5h window is the tighter constraint and tokens_used_this_period represents a rolling total
- Data migration copies existing claude_monthly_token_budget to both new 5h and weekly columns (safe preservation)
- server_default=text("0") on Plan quota columns lets migration run without touching existing rows

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated billing/dependencies.py to use token_quota_5h**
- **Found during:** Task 2 (Update all backend schemas and services)
- **Issue:** billing/dependencies.py _enforce_token_quota and check_token_quota used plan.token_quota which was removed from the Plan model
- **Fix:** Replaced plan.token_quota with plan.token_quota_5h in both _enforce_token_quota and check_token_quota header generation
- **Files modified:** backend/src/wxcode_adm/billing/dependencies.py
- **Verification:** 161 tests pass; token quota enforcement tests pass
- **Committed in:** e8eed24 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — Bug)
**Impact on plan:** Auto-fix essential for correctness — quota enforcement would have crashed at runtime using the removed field. No scope creep.

## Issues Encountered
- git stash during verification temporarily showed old file contents in system reminders; working tree was confirmed via grep to have correct content throughout

## User Setup Required
None - no external service configuration required. Migration 010 applied automatically via `alembic upgrade head`.

## Next Phase Readiness
- All backend layers now use dual time-window budget/quota fields
- Frontend plan (23-05) can now consume claude_5h_token_budget, claude_weekly_token_budget, token_quota_5h, token_quota_weekly from the API
- Migration 010 applied to production-equivalent DB (5.161.127.145)

---
*Phase: 23-admin-ui-claude-management*
*Completed: 2026-03-08*
