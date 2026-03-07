---
phase: 22-claude-provisioning-api
plan: "02"
subsystem: tenant-provisioning
tags: [tenants, wxcode-config, integration-tests, provisioning, audit]
dependency_graph:
  requires:
    - 22-01-SUMMARY.md  # admin provisioning endpoints (PUT/DELETE/PATCH/POST)
    - 20-02-SUMMARY.md  # tenant model fields (database_name, claude_*, status, etc.)
  provides:
    - GET /tenants/{tenant_id}/wxcode-config endpoint on tenants router
    - 14 integration tests covering all 5 Phase 22 provisioning endpoints
  affects:
    - backend/src/wxcode_adm/tenants/router.py
    - backend/tests/test_claude_provisioning.py
tech_stack:
  added: []
  patterns:
    - Tenant mismatch protection (path tenant_id vs X-Tenant-ID context comparison)
    - require_role(MemberRole.DEVELOPER) for tenant-scoped engine endpoint
    - c.request('DELETE', ..., content=...) for DELETE endpoints with bodies in httpx
    - Direct DB seeding for test isolation (no HTTP flow for tenant creation)
key_files:
  created:
    - backend/tests/test_claude_provisioning.py
  modified:
    - backend/src/wxcode_adm/tenants/router.py
decisions:
  - tenant-mismatch-404: GET wxcode-config validates that path tenant_id matches X-Tenant-ID context — returns 404 (not 403) on mismatch to prevent tenant enumeration
  - max_concurrent_sessions-no-prefix: Response field named 'max_concurrent_sessions' (no 'claude_' prefix) matching ROADMAP deliverable spec, even though DB column is claude_max_concurrent_sessions
  - httpx-delete-body: httpx AsyncClient.delete() doesn't support body kwargs in the pinned version; use c.request('DELETE', url, content=json.dumps(...)) for DELETE endpoints with request bodies
metrics:
  duration: "4 min"
  completed: "2026-03-07"
  tasks_completed: 2
  files_modified: 2
  commits: 2
---

# Phase 22 Plan 02: wxcode-config Endpoint + Integration Tests Summary

**One-liner:** GET /tenants/{id}/wxcode-config endpoint (DEVELOPER+ role, no token returned) + 14 integration tests covering all 5 Phase 22 provisioning endpoints end-to-end.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add GET /tenants/{id}/wxcode-config endpoint | 0890e45 | tenants/router.py |
| 2 | Add 14 integration tests for all 5 provisioning endpoints | 52f009f | tests/test_claude_provisioning.py |

## What Was Built

### Endpoint (tenants/router.py)

New endpoint added under `# Phase 22: wxcode engine config endpoint` section:

`GET /api/v1/tenants/{tenant_id}/wxcode-config`

- Requires DEVELOPER+ role via `require_role(MemberRole.DEVELOPER)` dependency
- Validates `tenant.id == tenant_id` path param (mismatch → 404 TENANT_MISMATCH)
- Returns: `tenant_id`, `database_name`, `default_target_stack`, `neo4j_enabled`, `claude_default_model`, `max_concurrent_sessions`
- Explicitly excludes `claude_oauth_token` — token never leaves wxcode-adm
- Field name `max_concurrent_sessions` (no `claude_` prefix) matches ROADMAP spec

Security design: The X-Tenant-ID header resolves the tenant context through `require_role`. The path `tenant_id` is then compared to the resolved tenant's ID. This prevents a DEVELOPER in tenant A from reading config of tenant B by guessing UUIDs (cross-tenant read prevention).

### Integration Tests (tests/test_claude_provisioning.py) — 721 lines, 14 tests

**Admin endpoints (super-admin token):**

1. `test_set_claude_token_success` — PUT sets encrypted token; `has_claude_token=True`; raw token not in response
2. `test_set_claude_token_not_found` — PUT with random UUID returns 404
3. `test_revoke_claude_token_success` — DELETE revokes token; `has_claude_token=False`
4. `test_revoke_claude_token_no_token` — DELETE with no existing token returns 409 `NO_TOKEN`
5. `test_update_claude_config_partial` — PATCH single field; others unchanged
6. `test_update_claude_config_all_fields` — PATCH all 3 fields; all updated
7. `test_update_claude_config_empty_rejected` — PATCH with `{}` returns 422
8. `test_activate_tenant_success` — POST activate; status transitions to `active`
9. `test_activate_tenant_wrong_status` — POST on `active` tenant returns 409 `INVALID_STATUS`
10. `test_activate_tenant_no_database_name` — POST without `database_name` returns 409 `MISSING_DATABASE_NAME`
11. `test_wxcode_config_developer_access` — OWNER (level 4) accesses config; all fields present; token absent
12. `test_wxcode_config_viewer_denied` — VIEWER (level 1) returns 403
13. `test_wxcode_config_tenant_mismatch` — OWNER of tenant A + path of tenant B returns 404
14. `test_provisioning_audit_trail` — set_token + update_config + activate all in audit log; token never in details

**Helpers:**
- `_seed_super_admin` / `_admin_login` — super-admin test flow
- `_signup_verify_login` — regular user signup/verify/login
- `_create_tenant_in_db` — direct DB tenant creation for test isolation

## Verification

- `GET /tenants/{tenant_id}/wxcode-config` registered on tenants router
- All 14 new tests pass
- All 161 existing tests pass (147 + 14 new); pre-existing `test_rate_limit_response_includes_retry_after` failure unchanged (out of scope)
- Token value never appears in any response or audit log

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] httpx AsyncClient.delete() does not accept body parameters**

- **Found during:** Task 2
- **Issue:** The plan specified `c.delete(url, json={"reason": ...})` but this version of httpx AsyncClient's `delete()` method does not accept `json` or `content` kwargs
- **Fix:** Used `c.request("DELETE", url, content=json.dumps(...), headers={..., "Content-Type": "application/json"})` which works correctly
- **Files modified:** `backend/tests/test_claude_provisioning.py`
- **Commit:** 52f009f

## Deferred Items

Pre-existing test failure `test_rate_limit_response_includes_retry_after` in `tests/test_platform_security.py` — caused by uncommitted change `headers_enabled=False` in `backend/src/wxcode_adm/common/rate_limit.py`. Out of scope for this plan (documented in 22-01-SUMMARY.md).

## Self-Check: PASSED
