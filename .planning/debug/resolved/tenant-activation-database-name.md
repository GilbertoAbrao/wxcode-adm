---
status: resolved
trigger: "Tenant must have a database_name configured before activation - UI missing database_name field"
created: 2026-03-08T00:00:00Z
updated: 2026-03-08T18:30:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: CONFIRMED — No backend endpoint exists to set database_name, and the UI has no field for it anywhere
test: Searched all admin router endpoints, admin service functions, and frontend UI components
expecting: Confirmed — complete gap in the admin workflow
next_action: COMPLETE — return diagnosis

## Symptoms

expected: User can configure database_name and then activate tenant
actual: Error "Tenant must have a database_name configured before activation" with no UI way to set it
errors: "Tenant must have a database_name configured before activation"
reproduction: Navigate to pending_setup tenant, click Activate Tenant
started: unknown / always broken for this workflow

## Eliminated

## Evidence

- timestamp: 2026-03-08T00:01:00Z
  checked: backend/src/wxcode_adm/admin/service.py activate_tenant() lines 1145-1205
  found: Hard guard at line 1182 — if tenant.database_name is None: raise ConflictError(error_code="MISSING_DATABASE_NAME", message="Tenant must have a database_name configured before activation")
  implication: Activation is impossible unless database_name is non-null on the Tenant row

- timestamp: 2026-03-08T00:02:00Z
  checked: backend/src/wxcode_adm/admin/router.py — all PATCH/PUT/POST endpoints for tenants
  found: Only three tenant mutation endpoints exist: /suspend, /reactivate, /delete (soft), /claude-token (PUT/DELETE), /claude-config (PATCH), /activate (POST). There is NO endpoint to set database_name, default_target_stack, or neo4j_enabled.
  implication: There is no backend API at all for setting database_name — the field can only be set via direct DB access

- timestamp: 2026-03-08T00:03:00Z
  checked: frontend/src/app/admin/tenants/[tenantId]/page.tsx — all form state and UI sections
  found: The page has forms for: Claude token (set/revoke), Claude config (model/sessions/budget), and Activate (reason only). No form or field for database_name anywhere. The WXCODE Integration card shows current database_name only in the response schema — but it is NOT displayed in the UI and not editable.
  implication: The UI cannot set database_name at all — neither before nor after activation attempt

- timestamp: 2026-03-08T00:04:00Z
  checked: frontend/src/hooks/useAdminTenants.ts — all mutation hooks
  found: Hooks cover: suspend, reactivate, set-claude-token, revoke-claude-token, update-claude-config, activate. No hook for updating database_name or any other wxcode provisioning field (database_name, default_target_stack, neo4j_enabled, wxcode_url).
  implication: Even if a backend endpoint existed, the frontend has no hook wired up to call it

- timestamp: 2026-03-08T00:05:00Z
  checked: backend/src/wxcode_adm/tenants/models.py lines 130-149
  found: database_name: String(100), nullable=True, default=None. Also present: default_target_stack (default="fastapi-jinja2"), neo4j_enabled (default=True), status (default="pending_setup"). All these are wxcode provisioning fields that belong to the same Phase 20 integration card.
  implication: database_name is the only nullable field without a default that blocks activation; default_target_stack and neo4j_enabled have safe defaults

- timestamp: 2026-03-08T00:06:00Z
  checked: frontend/src/app/admin/tenants/[tenantId]/page.tsx lines 682-743 — Activate Tenant subsection
  found: The activate section shows a hint text "Requires database_name to be configured" (line 701) but provides NO mechanism to set it. The form only collects a reason string.
  implication: The UI acknowledges the requirement but provides no solution — a dead-end UX

## Resolution

root_cause: |
  Two-layer gap — missing backend endpoint AND missing frontend UI:

  1. BACKEND: There is no admin API endpoint to set `database_name` (or the related wxcode provisioning
     fields: `default_target_stack`, `neo4j_enabled`). The only way to set `database_name` today is
     via direct database manipulation. The `activate_tenant` service function at line 1182 of
     `backend/src/wxcode_adm/admin/service.py` hard-blocks activation when `database_name IS NULL`,
     raising a 409 ConflictError with code "MISSING_DATABASE_NAME".

  2. FRONTEND: The tenant detail page (`frontend/src/app/admin/tenants/[tenantId]/page.tsx`) displays
     the current `database_name` value from the API response (it's in the TenantDetailResponse
     TypeScript interface at line 59 of useAdminTenants.ts) but never renders it in the UI, and
     has no form field or edit affordance for it. The Activate Tenant section (lines 700-701) even
     displays "Requires database_name to be configured" as a hint but offers no way to actually
     configure it.

  The result: the admin clicks "Activate", sees the error, and has no path forward inside the UI.

fix:
verification:
files_changed: []
