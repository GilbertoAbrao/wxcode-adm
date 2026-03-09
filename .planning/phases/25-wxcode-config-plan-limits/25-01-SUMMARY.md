---
phase: 25-wxcode-config-plan-limits
plan: 01
subsystem: api
tags: [sqlalchemy, fastapi, billing, plan-limits, integration-contract]

# Dependency graph
requires:
  - phase: 22-claude-provisioning-api
    provides: wxcode-config endpoint (GET /tenants/{id}/wxcode-config)
  - phase: 21-plan-limits-extension
    provides: Plan model with max_projects, max_output_projects, max_storage_gb, token_quota_5h, token_quota_weekly fields
provides:
  - plan_limits object in wxcode-config response with 5 operational limit fields
  - null plan_limits when tenant has no subscription
  - INTEGRATION-CONTRACT.md v0.2.0 documenting plan_limits
affects: wxcode-engine, integration-contract, billing

# Tech tracking
tech-stack:
  added: []
  patterns:
    - TenantSubscription loaded via select + where tenant_id; plan auto-loaded via lazy="joined" relationship
    - Conditional plan_limits dict — None when no subscription, 5-field dict when plan exists

key-files:
  created: []
  modified:
    - backend/src/wxcode_adm/tenants/router.py
    - backend/tests/test_claude_provisioning.py
    - docs/INTEGRATION-CONTRACT.md

key-decisions:
  - "TenantSubscription query uses select + where pattern (not relationship eager load) — consistent with existing admin endpoints in router.py"
  - "plan_limits=null when no subscription — wxcode engine must handle null gracefully (no limits enforced for unsubscribed tenants)"
  - "plan is auto-loaded via lazy=joined on TenantSubscription — no separate Plan query needed"

patterns-established:
  - "Plan limits exposed via TenantSubscription -> Plan join in wxcode-config endpoint"
  - "Test for no-subscription case: create tenant directly in DB without onboarding (bypasses bootstrap_free_subscription)"

requirements-completed: [MISSING-01, FLOW-BREAK-01]

# Metrics
duration: 1min
completed: 2026-03-09
---

# Phase 25 Plan 01: wxcode-config Plan Limits Summary

**Plan limits (max_projects, max_output_projects, max_storage_gb, token_quota_5h, token_quota_weekly) exposed in wxcode-config endpoint via TenantSubscription -> Plan join; INTEGRATION-CONTRACT.md bumped to v0.2.0**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-09T15:49:12Z
- **Completed:** 2026-03-09T15:50:36Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Modified `get_wxcode_config` to query TenantSubscription and return `plan_limits` dict with 5 operational limit fields
- Returns `plan_limits=null` when tenant has no subscription (graceful for unsubscribed tenants)
- Added 2 new tests: `test_wxcode_config_plan_limits_with_subscription` and `test_wxcode_config_plan_limits_no_subscription`; all 16 provisioning tests pass
- Updated INTEGRATION-CONTRACT.md Section 4 with plan_limits in JSON example and field table; version bumped 0.1.0 → 0.2.0
- Closed MISSING-01 (plan limits not exposed) and FLOW-BREAK-01 (wxcode engine cannot get plan limits from wxcode-adm)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add plan limits to wxcode-config endpoint + tests** - `aec6c04` (feat)
2. **Task 2: Update INTEGRATION-CONTRACT.md with plan_limits documentation** - `582f9c5` (docs)

**Plan metadata:** (docs: complete plan — see final commit)

## Files Created/Modified
- `backend/src/wxcode_adm/tenants/router.py` - Added TenantSubscription import, subscription query, plan_limits dict, added plan_limits to return dict
- `backend/tests/test_claude_provisioning.py` - Added 2 new plan_limits tests, updated developer_access test to assert plan_limits key present
- `docs/INTEGRATION-CONTRACT.md` - Added plan_limits to Section 4 JSON example and field table, bumped version to 0.2.0

## Decisions Made
- TenantSubscription query uses `select + where` pattern consistent with other admin endpoints in router.py, rather than preloading via relationship
- `plan_limits=null` when no subscription — wxcode engine must handle null gracefully; this is the correct semantic for unsubscribed/pending tenants
- `lazy="joined"` on `TenantSubscription.plan` means no separate Plan query needed once subscription is loaded

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- wxcode engine can now read tenant plan limits from GET /tenants/{id}/wxcode-config
- Phase 25 plan 01 complete — all gaps MISSING-01 and FLOW-BREAK-01 are closed
- No blockers for downstream phases

## Self-Check: PASSED

All files verified present. All task commits verified in git log.

---
*Phase: 25-wxcode-config-plan-limits*
*Completed: 2026-03-09*
