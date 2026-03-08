---
status: diagnosed
phase: 23-admin-ui-claude-management
source: [23-01-SUMMARY.md, 23-02-SUMMARY.md]
started: 2026-03-08T15:00:00Z
updated: 2026-03-08T15:20:00Z
---

## Current Test

[testing complete]

## Tests

### 1. WXCODE Integration Card on Tenant Detail
expected: On the tenant detail page (/admin/tenants/{id}), a full-width "WXCODE Integration" card is visible below existing tenant info. It shows a wxcode status badge (pending_setup/active/suspended/cancelled), Claude token status (masked as ****-****-**** if set, or "Not set"), and current config values (model, max sessions, monthly budget).
result: issue
reported: "Monthly Budget precisa ser substituido por 5-hour-window budget e por weekly budget"
severity: major

### 2. Set Claude Token
expected: In the WXCODE Integration card, clicking "Set Token" (or "Update Token") reveals a password-type input field and a submit button. After entering a token value and submitting, the token status updates to show ****-****-**** (masked). The input field is hidden after successful submission.
result: pass

### 3. Revoke Claude Token
expected: When a token is set, a "Revoke" button is available. Clicking it shows a reason input. After submitting with a reason, the token status changes back to "Not set" and the revoke form disappears.
result: issue
reported: "quando refresh a pagina sou obrigado a fazer novo login, isso nao pode acontecer"
severity: major

### 4. Update Claude Config
expected: The WXCODE Integration card has an editable config section. Clicking "Edit" reveals form fields for default model, max concurrent sessions, and monthly token budget. Changing values and submitting only sends modified fields. Setting budget to 0 means unlimited. Form resets after successful save.
result: pass

### 5. Activate Tenant (pending_setup only)
expected: When a tenant has status "pending_setup", an "Activate Tenant" section is visible at the bottom of the WXCODE Integration card. Clicking activate changes the tenant status to "active". This section is NOT visible for tenants with other statuses (active, suspended, cancelled).
result: issue
reported: "Tomei essa mensagem ao clicar em activate: Tenant must have a database_name configured before activation"
severity: major

### 6. Plans Link in Admin Navigation
expected: All admin pages (Dashboard, Tenants, Tenant Detail, Users, Audit Logs) show a "Plans" link in the top navigation bar, positioned between "Tenants" and "Users". Clicking it navigates to /admin/plans.
result: pass

### 7. Plans Page — List All Plans
expected: The /admin/plans page shows a table with 9 columns: Name, Slug, Fee/mo, Token Quota, Max Projects, Max Output, Storage (GB), Status, Actions. All existing billing plans are listed. A plan count summary appears at the bottom.
result: issue
reported: "O token quota deve ser por 5-hour-window e weekly"
severity: major

### 8. Create a New Plan
expected: Above the plans table, a "Create Plan" button expands a form. The form has fields for name, slug (auto-generated from name), monthly fee, token quota, max projects (default 5), max output projects (default 20), max storage GB (default 10), and active status. Submitting creates the plan and it appears in the table.
result: issue
reported: "faltou botao para excluir planos, essa exclusao deve validar se não há nenhum tenant usando o plano a ser excluido"
severity: major

### 9. Edit a Plan Inline
expected: Clicking "Edit" on a plan row expands an inline edit form below the row (colSpan covering all columns). Fields are pre-populated with current values. Changing some fields and saving only sends the modified fields. The row collapses after successful update.
result: pass

### 10. Delete an Inactive Plan
expected: The "Delete" button is only visible for inactive plans. Clicking it shows a browser confirmation dialog. Confirming deletes the plan from the table. Active plans do not show a delete button.
result: issue
reported: "I can't find how to inactivate a plan."
severity: major

## Summary

total: 10
passed: 4
issues: 6
pending: 0
skipped: 0

## Gaps

- truth: "WXCODE Integration card shows budget config per time window"
  status: failed
  reason: "User reported: Monthly Budget precisa ser substituido por 5-hour-window budget e por weekly budget"
  severity: major
  test: 1
  root_cause: "Single claude_monthly_token_budget field exists at every layer (model, migration, schema, API, UI). Needs splitting into claude_5h_token_budget + claude_weekly_token_budget across the full stack."
  artifacts:
    - path: "backend/src/wxcode_adm/tenants/models.py"
      issue: "claude_monthly_token_budget is single field, needs two"
    - path: "backend/src/wxcode_adm/admin/schemas.py"
      issue: "TenantDetailResponse and ClaudeConfigUpdateRequest have single budget field"
    - path: "backend/src/wxcode_adm/admin/service.py"
      issue: "get_tenant_detail and update_claude_config use single budget field"
    - path: "frontend/src/hooks/useAdminTenants.ts"
      issue: "TenantDetailResponse and ClaudeConfigUpdate have single budget field"
    - path: "frontend/src/app/admin/tenants/[tenantId]/page.tsx"
      issue: "Single configBudget state var and single budget display/input"
  missing:
    - "Replace claude_monthly_token_budget with claude_5h_token_budget + claude_weekly_token_budget in tenant model"
    - "New alembic migration to add two columns and drop old one"
    - "Update admin schemas, service, and frontend to use two budget fields"
  debug_session: ".planning/debug/budget-fields-single-to-dual.md"

- truth: "Page refresh preserves authentication session"
  status: failed
  reason: "User reported: quando refresh a pagina sou obrigado a fazer novo login, isso nao pode acontecer"
  severity: major
  test: 3
  root_cause: "Admin tokens stored exclusively in JS module-scoped variables (_adminAccessToken/_adminRefreshToken in admin-auth.ts). Page reload reinitializes modules to null. AdminAuthProvider mount effect has no session restore logic."
  artifacts:
    - path: "frontend/src/lib/admin-auth.ts"
      issue: "Tokens in module-scoped let variables, lost on reload"
    - path: "frontend/src/providers/admin-auth-provider.tsx"
      issue: "Mount useEffect has no session restore, just setIsLoading(false)"
    - path: "frontend/src/app/admin/login/page.tsx"
      issue: "Login success only writes to in-memory store"
  missing:
    - "Persist admin refresh token to localStorage on login"
    - "Add session restore in AdminAuthProvider mount: read localStorage, call refreshAdminTokens(), set auth state"
    - "Clear localStorage on logout in clearAdminTokens()"
  debug_session: ".planning/debug/auth-session-persistence.md"

- truth: "Activate tenant changes status to active"
  status: failed
  reason: "User reported: Tomei essa mensagem ao clicar em activate: Tenant must have a database_name configured before activation"
  severity: major
  test: 5
  root_cause: "activate_tenant service requires database_name to be set, but no API endpoint or UI exists to set database_name (or default_target_stack, neo4j_enabled). These wxcode provisioning fields have no admin management path."
  artifacts:
    - path: "backend/src/wxcode_adm/admin/service.py"
      issue: "activate_tenant checks database_name is not null but no endpoint to set it"
    - path: "backend/src/wxcode_adm/admin/router.py"
      issue: "No PATCH endpoint for wxcode provisioning fields"
    - path: "frontend/src/app/admin/tenants/[tenantId]/page.tsx"
      issue: "No UI for database_name/default_target_stack/neo4j_enabled"
  missing:
    - "New backend schema WxcodeConfigUpdateRequest with database_name, default_target_stack, neo4j_enabled"
    - "New service function update_wxcode_config and PATCH endpoint"
    - "New useUpdateWxcodeConfig mutation hook"
    - "New WXCODE Provisioning subsection in tenant detail card with editable fields"
  debug_session: ".planning/debug/tenant-activation-database-name.md"

- truth: "Plans table shows token quota per time window"
  status: failed
  reason: "User reported: O token quota deve ser por 5-hour-window e weekly"
  severity: major
  test: 7
  root_cause: "Single token_quota field in Plan model. Needs splitting into token_quota_5h + token_quota_weekly across model, migration, schemas, hooks, and plans page."
  artifacts:
    - path: "backend/src/wxcode_adm/billing/models.py"
      issue: "Single token_quota field"
    - path: "backend/src/wxcode_adm/billing/schemas.py"
      issue: "token_quota in CreatePlanRequest, UpdatePlanRequest, PlanResponse"
    - path: "frontend/src/hooks/useAdminPlans.ts"
      issue: "token_quota in PlanResponse, CreatePlanData, UpdatePlanData"
    - path: "frontend/src/app/admin/plans/page.tsx"
      issue: "Single Token Quota column, single create/edit input"
  missing:
    - "Replace token_quota with token_quota_5h + token_quota_weekly in Plan model"
    - "New alembic migration for plan token quota columns"
    - "Update billing schemas, hooks, and plans page for two quota fields"
  debug_session: ".planning/debug/budget-fields-single-to-dual.md"

- truth: "Plans page has delete button with tenant validation"
  status: failed
  reason: "User reported: faltou botao para excluir planos, essa exclusao deve validar se não há nenhum tenant usando o plano a ser excluido"
  severity: major
  test: 8
  root_cause: "Delete button gated by !plan.is_active (line 570 of plans page) — permanently hidden because no way to inactivate. Backend delete_plan has no TenantSubscription check before soft-delete."
  artifacts:
    - path: "frontend/src/app/admin/plans/page.tsx"
      issue: "Delete button hidden behind impossible condition; no inactivate toggle"
    - path: "backend/src/wxcode_adm/billing/service.py"
      issue: "delete_plan has no tenant-in-use guard"
  missing:
    - "Add Activate/Inactivate toggle button in Actions column"
    - "Add TenantSubscription check in delete_plan before soft-delete"
  debug_session: ".planning/debug/plans-delete-inactivate.md"

- truth: "Plans can be inactivated and only inactive plans can be deleted"
  status: failed
  reason: "User reported: I can't find how to inactivate a plan."
  severity: major
  test: 10
  root_cause: "Edit form renders 8 fields but no is_active toggle. Backend and hooks already support is_active updates — only the UI control is missing."
  artifacts:
    - path: "frontend/src/app/admin/plans/page.tsx"
      issue: "No is_active toggle in Actions column or edit form"
  missing:
    - "Add Activate/Inactivate toggle button in Actions column using useUpdatePlan with { is_active: !plan.is_active }"
  debug_session: ".planning/debug/plans-delete-inactivate.md"
