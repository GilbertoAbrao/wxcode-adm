---
status: diagnosed
trigger: "Replace single monthly budget with 5-hour-window budget + weekly budget across tenant detail and plans page"
created: 2026-03-08T15:29:55Z
updated: 2026-03-08T15:30:00Z
---

## Current Focus

hypothesis: confirmed — a single `claude_monthly_token_budget` field exists on the
  Tenant model and a single `token_quota` field exists on the Plan model; both need
  to be split into two budget fields each.
test: full chain audit from DB model → migration → schema → API → frontend hook → UI page
expecting: complete map of every file that must change
next_action: return diagnosis to caller

## Symptoms

expected: TWO budget fields on tenant detail card (5-hour-window budget + weekly budget)
          TWO quota columns on plans page table (5-hour-window quota + weekly quota)
actual: ONE field — "Monthly Budget" on tenant card; ONE column — "Token Quota" on plans table
errors: none (UI renders, just with wrong field semantics)
reproduction: visit /admin/tenants/{id} → WXCODE Integration card; visit /admin/plans
started: never had dual fields — single-field design from Phase 20/21

## Eliminated

- hypothesis: bug introduced by a recent commit
  evidence: feature was always single-field by design (migration 008 / 009 explicitly add only one budget column each)
  timestamp: 2026-03-08T15:30:00Z

## Evidence

- timestamp: 2026-03-08T15:30:00Z
  checked: backend/src/wxcode_adm/tenants/models.py — Tenant model
  found: |
    Line 125-129: `claude_monthly_token_budget: Mapped[Optional[int]]`
    No `claude_5h_token_budget` or `claude_weekly_token_budget` field.
  implication: DB model has one budget column; needs two new columns + old one removed

- timestamp: 2026-03-08T15:30:00Z
  checked: backend/src/wxcode_adm/billing/models.py — Plan model
  found: |
    Line 94-97: `token_quota: Mapped[int]`
    No `token_quota_5h` or `token_quota_weekly` field.
  implication: Plan model has one quota column; needs two new columns + old one removed

- timestamp: 2026-03-08T15:30:00Z
  checked: backend/alembic/versions/008_add_claude_wxcode_tenant_fields.py
  found: Migration 008 adds `claude_monthly_token_budget` (nullable Integer).
  implication: A new migration 010 must ADD two new budget columns and DROP the old one.

- timestamp: 2026-03-08T15:30:00Z
  checked: backend/alembic/versions/009_add_plan_limits_fields.py
  found: Migration 009 adds max_projects, max_output_projects, max_storage_gb — NOT the quota split.
  implication: A new migration 010 must also ADD two quota columns to plans and DROP token_quota.

- timestamp: 2026-03-08T15:30:00Z
  checked: backend/src/wxcode_adm/admin/schemas.py — TenantDetailResponse + ClaudeConfigUpdateRequest
  found: |
    Line 109: `claude_monthly_token_budget: int | None`
    Line 257: `claude_monthly_token_budget: int | None = Field(default=None, ge=0)` in ClaudeConfigUpdateRequest
    model_validator on line 259-271 references only `claude_monthly_token_budget` in guard
  implication: Both the response schema and update request schema must swap the single field for two fields

- timestamp: 2026-03-08T15:30:00Z
  checked: backend/src/wxcode_adm/billing/schemas.py — PlanResponse, CreatePlanRequest, UpdatePlanRequest
  found: |
    Line 23: `token_quota: int = Field(ge=0)` in CreatePlanRequest
    Line 36: `token_quota: Optional[int]` in UpdatePlanRequest
    Line 54: `token_quota: int` in PlanResponse
  implication: All three billing schemas need the single quota replaced with two quota fields

- timestamp: 2026-03-08T15:30:00Z
  checked: backend/src/wxcode_adm/admin/service.py (grep output)
  found: |
    Line 400: `"claude_monthly_token_budget": tenant.claude_monthly_token_budget` — in get_tenant_detail dict
    Line 1083: `claude_monthly_token_budget: int | None` — update_claude_config signature
    Line 1121-1125: budget set logic reads/writes `tenant.claude_monthly_token_budget`
    Line 1129/1137: audit log records field by name
  implication: admin/service.py needs two separate budget params and two separate assignment blocks

- timestamp: 2026-03-08T15:30:00Z
  checked: frontend/src/hooks/useAdminTenants.ts — TenantDetailResponse interface + ClaudeConfigUpdate
  found: |
    Line 64: `claude_monthly_token_budget: number | null`
    Line 254: `claude_monthly_token_budget?: number` in ClaudeConfigUpdate interface
  implication: Both TS interfaces need the single field replaced with two fields

- timestamp: 2026-03-08T15:30:00Z
  checked: frontend/src/hooks/useAdminPlans.ts — PlanResponse, CreatePlanData, UpdatePlanData
  found: |
    Line 27: `token_quota: number` in PlanResponse
    Line 43: `token_quota: number` in CreatePlanData
    Line 52: `token_quota?: number` in UpdatePlanData
  implication: All three TS interfaces need the single quota replaced with two quota fields

- timestamp: 2026-03-08T15:30:00Z
  checked: frontend/src/app/admin/tenants/[tenantId]/page.tsx — WXCODE Integration card
  found: |
    Line 614-619: display section renders "Monthly Budget" label from `tenant.claude_monthly_token_budget`
    Line 154-156: state vars are `configBudget: string` (one state var)
    Line 226-239: handleUpdateConfig builds payload with `claude_monthly_token_budget`
    Line 641-652: single GlowInput "Monthly Budget (0 = unlimited)"
  implication: Must change display labels, add a second state variable + input, update payload builder

- timestamp: 2026-03-08T15:30:00Z
  checked: frontend/src/app/admin/plans/page.tsx — Plans page table + forms
  found: |
    Line 502-503: table header "Token Quota"
    Line 537-539: table cell renders `plan.token_quota.toLocaleString()`
    Line 395-400: create form has single "Token Quota" GlowInput bound to `createQuota`
    Line 619-626: edit form has single "Token Quota" GlowInput bound to `editQuota`
    Line 140: useEffect pre-populates `editQuota` from `editingPlan.token_quota`
    Lines 173/221: handleCreate/handleUpdate reference `token_quota`
  implication: Table header + cell, create form, edit form, state vars, handlers all need doubling

## Resolution

root_cause: |
  The system was designed with a single "monthly" budget concept at both layers:
  - Tenant layer: `claude_monthly_token_budget` (one DB column)
  - Plan layer: `token_quota` (one DB column)

  The desired design replaces these with two separate time-window budgets:
  - 5-hour rolling window budget: `claude_5h_token_budget` / `token_quota_5h`
  - Weekly budget: `claude_weekly_token_budget` / `token_quota_weekly`

  The change must propagate through all six layers consistently.

fix: not applied (diagnose-only mode)

verification: not applied

files_changed: []
