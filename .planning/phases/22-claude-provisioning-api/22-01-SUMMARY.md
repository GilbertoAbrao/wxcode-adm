---
phase: 22-claude-provisioning-api
plan: "01"
subsystem: admin-provisioning
tags: [admin, provisioning, claude, encryption, audit]
dependency_graph:
  requires:
    - 20-01-SUMMARY.md  # crypto service (encrypt_value)
    - 20-02-SUMMARY.md  # tenant model Phase 20 fields
  provides:
    - 4 admin provisioning endpoints on admin_router
    - ClaudeTokenRequest, ClaudeConfigUpdateRequest, ActivateTenantRequest schemas
    - set_claude_token, revoke_claude_token, update_claude_config, activate_tenant service functions
    - TenantDetailResponse extended with Claude/wxcode fields
  affects:
    - backend/src/wxcode_adm/admin/schemas.py
    - backend/src/wxcode_adm/admin/service.py
    - backend/src/wxcode_adm/admin/router.py
tech_stack:
  added: []
  patterns:
    - Fernet encryption via encrypt_value before token storage
    - Partial update pattern (only non-None fields applied)
    - ConflictError for invalid state transitions
    - Audit trail on all provisioning operations
key_files:
  created: []
  modified:
    - backend/src/wxcode_adm/admin/schemas.py
    - backend/src/wxcode_adm/admin/service.py
    - backend/src/wxcode_adm/admin/router.py
decisions:
  - 0-budget-means-unlimited: claude_monthly_token_budget=0 in API means set to NULL in DB (unlimited); None means "no change" — avoids ambiguity between "no change" and "set to unlimited"
  - token-never-logged: Claude OAuth token value is never written to logs or audit details — only the reason and tenant_id are recorded
  - AdminActionRequest-for-DELETE-body: DELETE /claude-token reuses existing AdminActionRequest instead of new schema — reason field is shared semantics
metrics:
  duration: "4 min"
  completed: "2026-03-07"
  tasks_completed: 3
  files_modified: 3
  commits: 3
---

# Phase 22 Plan 01: Claude Provisioning API Summary

**One-liner:** 4 admin provisioning endpoints (PUT/DELETE claude-token, PATCH claude-config, POST activate) with Fernet encryption, audit logging, and extended TenantDetailResponse.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add provisioning schemas and extend TenantDetailResponse | e78f680 | admin/schemas.py |
| 2 | Add provisioning service functions | 85df1b8 | admin/service.py |
| 3 | Add 4 admin provisioning endpoints to router | 9bd155e | admin/router.py |

## What Was Built

### Schemas (admin/schemas.py)

Three new request schemas:
- `ClaudeTokenRequest` — `token` (1-4096 chars) + `reason` (1-500 chars)
- `ClaudeConfigUpdateRequest` — optional `claude_default_model`, `claude_max_concurrent_sessions` (1-100), `claude_monthly_token_budget` (>=0); model_validator rejects all-None payloads
- `ActivateTenantRequest` — `reason` (1-500 chars)

`TenantDetailResponse` extended with 8 Phase 20 fields: `status`, `database_name`, `default_target_stack`, `neo4j_enabled`, `claude_default_model`, `claude_max_concurrent_sessions`, `claude_monthly_token_budget`, `has_claude_token`. Raw `claude_oauth_token` never exposed.

### Service Functions (admin/service.py)

Four new service functions following the suspend_tenant pattern:

1. **set_claude_token** — Fernet-encrypts plaintext token, stores encrypted value, audits with reason only (no token value)
2. **revoke_claude_token** — Clears token, raises `ConflictError(NO_TOKEN)` if no token exists
3. **update_claude_config** — Partial update; budget=0 maps to NULL in DB (unlimited); records only changed fields in audit
4. **activate_tenant** — Validates `status == "pending_setup"` and `database_name is not None`, transitions to `active`

`get_tenant_detail` updated to return 8 Phase 20 fields including computed `has_claude_token`.

### Endpoints (admin/router.py)

Four new endpoints auto-registered under `/api/v1/admin/` prefix:
- `PUT /admin/tenants/{tenant_id}/claude-token`
- `DELETE /admin/tenants/{tenant_id}/claude-token`
- `PATCH /admin/tenants/{tenant_id}/claude-config`
- `POST /admin/tenants/{tenant_id}/activate`

All require `require_admin` dependency (super-admin auth).

## Verification

All imports resolve. 147 tests pass (pre-existing `test_rate_limit_response_includes_retry_after` unrelated failure — caused by uncommitted `headers_enabled=False` in `rate_limit.py` that predates this plan).

## Deviations from Plan

None — plan executed exactly as written.

## Deferred Items

Pre-existing test failure `test_rate_limit_response_includes_retry_after` in `tests/test_platform_security.py` — caused by uncommitted change `headers_enabled=False` in `backend/src/wxcode_adm/common/rate_limit.py`. Out of scope for this plan.

## Self-Check: PASSED
