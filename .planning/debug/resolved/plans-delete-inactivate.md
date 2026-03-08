---
status: resolved
trigger: "Test 8: Missing delete button on plans page. Test 10: No way to inactivate a plan."
created: 2026-03-08T00:00:00Z
updated: 2026-03-08T18:30:00Z
---

## Current Focus

hypothesis: Delete button is gated on `!plan.is_active`, making it invisible for active plans. Inactivate toggle is absent from the edit form and the actions column.
test: Read all relevant files — page.tsx, hooks, backend model/service/router/schema.
expecting: Confirmed by direct code inspection.
next_action: Return structured diagnosis.

## Symptoms

expected: User can delete a plan and toggle a plan active/inactive from the Plans page.
actual:
  - Delete button only renders when `plan.is_active === false` (line 570 of page.tsx)
  - No activate/inactivate toggle button exists anywhere in the UI
errors: No runtime errors — purely missing UI affordances.
reproduction:
  - Visit /admin/plans — all active plans show only an "Edit" button, no "Delete"
  - Open edit form for any plan — no is_active checkbox or toggle is rendered
started: Always (features were never implemented)

## Eliminated

- hypothesis: Delete hook `useDeletePlan` is missing or broken
  evidence: Hook exists and calls DELETE /admin/billing/plans/{plan_id} correctly (useAdminPlans.ts lines 146-157)
  timestamp: 2026-03-08T00:00:00Z

- hypothesis: Backend DELETE endpoint missing tenant-in-use validation
  evidence: Confirmed — `service.delete_plan` (service.py lines 251-281) does NO check for active TenantSubscription records referencing the plan before soft-deleting it. The only guard is a soft-delete (is_active=False) rather than a hard delete, which avoids FK violations but allows deactivating plans that tenants are currently subscribed to.
  timestamp: 2026-03-08T00:00:00Z

- hypothesis: Plan model lacks is_active field
  evidence: `is_active: Mapped[bool]` exists on Plan model (models.py line 123). Also present in PlanResponse schema (schemas.py line 60), UpdatePlanRequest schema (schemas.py line 42), and PlanResponse TypeScript interface (useAdminPlans.ts line 33).
  timestamp: 2026-03-08T00:00:00Z

- hypothesis: update_plan service ignores is_active field
  evidence: service.py lines 192-193 handle `body.is_active` correctly — if not None, it is applied to the plan. The PATCH endpoint can already toggle is_active.
  timestamp: 2026-03-08T00:00:00Z

## Evidence

- timestamp: 2026-03-08T00:00:00Z
  checked: frontend/src/app/admin/plans/page.tsx lines 570-580
  found: Delete button wrapped in `{!plan.is_active && ( ... )}` — only renders for INACTIVE plans
  implication: Active plans never show the Delete button; since all new plans are created active, users can never delete them

- timestamp: 2026-03-08T00:00:00Z
  checked: frontend/src/app/admin/plans/page.tsx inline edit form (lines 586-703)
  found: Edit form renders inputs for name, fee, quota, overage, member_cap, max_projects, max_output_projects, max_storage_gb — but NO is_active toggle
  implication: There is no UI mechanism to set is_active=false, making the Delete button permanently hidden

- timestamp: 2026-03-08T00:00:00Z
  checked: frontend/src/hooks/useAdminPlans.ts UpdatePlanData interface (lines 50-60)
  found: `is_active?: boolean` is present in the TypeScript interface
  implication: The hook layer already supports toggling is_active — only the page UI is missing it

- timestamp: 2026-03-08T00:00:00Z
  checked: backend/src/wxcode_adm/billing/service.py delete_plan (lines 251-281)
  found: No query for TenantSubscription records referencing this plan_id before soft-deleting
  implication: Admin can soft-delete a plan that active tenants are currently subscribed to, causing data integrity risk

- timestamp: 2026-03-08T00:00:00Z
  checked: backend/src/wxcode_adm/billing/schemas.py UpdatePlanRequest (lines 31-42)
  found: `is_active: Optional[bool] = None` is in UpdatePlanRequest — PATCH endpoint supports toggling
  implication: Backend already handles activate/deactivate via PATCH; only the UI toggle is missing

- timestamp: 2026-03-08T00:00:00Z
  checked: backend/src/wxcode_adm/billing/models.py TenantSubscription (lines 133-188)
  found: TenantSubscription.plan_id is a ForeignKey to plans.id with NO ondelete cascade — hard delete is impossible, soft-delete is the only path. The FK has no ondelete= argument, defaulting to RESTRICT.
  implication: Hard delete of a plan with active subscriptions would fail at DB level; soft-delete (is_active=False) goes through without validation

## Resolution

root_cause: |
  Three interconnected problems:

  1. DELETE BUTTON HIDDEN (Test 8, UI): The delete button in page.tsx line 570 is gated on
     `{!plan.is_active && ...}` — it ONLY appears for already-inactive plans. Since all plans
     start active and there is no way to inactivate them from the UI, the delete button is
     effectively unreachable. The guard's intent was likely "you must inactivate first, then
     delete", but the inactivate step was never built.

  2. INACTIVATE TOGGLE MISSING (Test 10, UI): The edit form (page.tsx lines 603-673) and the
     handleUpdate function do not include an is_active field. The hook (useAdminPlans.ts line 59)
     and backend schema (schemas.py line 42) both support is_active in PATCH, but the UI never
     sends it. There is no standalone toggle button in the Actions column either.

  3. NO TENANT-IN-USE VALIDATION (Test 8, Backend): service.delete_plan (service.py line 265)
     sets is_active=False without first checking whether any TenantSubscription records have
     plan_id = this plan's ID and status not in (CANCELED). An admin can deactivate a plan that
     active tenants are currently on, which would break their checkout/quota flows.

fix: (not applied — diagnose-only mode)
verification: (not applied)
files_changed: []
