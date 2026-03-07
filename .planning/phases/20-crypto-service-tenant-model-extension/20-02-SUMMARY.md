---
phase: 20-crypto-service-tenant-model-extension
plan: "02"
subsystem: database
tags: [sqlalchemy, alembic, tenant, migration, encryption, fernet]

# Dependency graph
requires:
  - phase: 20-crypto-service-tenant-model-extension
    plan: "01"
    provides: encrypt_value/decrypt_value from crypto.py for token storage test

provides:
  - Extended Tenant SQLAlchemy model with 8 new Phase 20 fields
  - Alembic migration 008 adding all 8 columns to tenants table with server_defaults
  - 6 integration tests verifying defaults, custom values, encrypted token round-trip, status values

affects:
  - 21-wxcode-tenant-provisioning (will read/write database_name, status, neo4j_enabled)
  - 22-claude-oauth (will store encrypted claude_oauth_token, read claude_default_model)
  - 23-session-management (will read claude_max_concurrent_sessions)

# Tech tracking
tech-stack:
  added: []  # Integer already in SQLAlchemy; no new dependencies
  patterns:
    - "Plain String column for status field — avoids PostgreSQL native enum issues (consistent with MemberRole native_enum=False)"
    - "server_default on non-nullable columns — existing rows get correct defaults without data migration"
    - "Nullable columns have no server_default — null is the correct initial value"

key-files:
  created:
    - backend/alembic/versions/008_add_claude_wxcode_tenant_fields.py
    - backend/tests/test_tenant_model_extension.py
  modified:
    - backend/src/wxcode_adm/tenants/models.py

key-decisions:
  - "Plain String (not enum) for status field — consistent with MemberRole native_enum=False pattern, avoids PostgreSQL CREATE TYPE issues"
  - "String(2048) for claude_oauth_token — Fernet-encrypted tokens are longer than plaintext OAuth tokens"
  - "claude_monthly_token_budget is nullable (null = unlimited) — avoids integer sentinel value ambiguity"
  - "server_default for non-nullable columns in migration 008 — existing rows get defaults without a data migration step"

patterns-established:
  - "Migration pattern: op.add_column with server_default for non-nullable additions, no server_default for nullable ones"
  - "Tenant model Phase comment blocks: # Phase N: description (added by migration NNN)"

requirements-completed:
  - ENG-02
  - ENG-03

# Metrics
duration: 3min
completed: "2026-03-07"
---

# Phase 20 Plan 02: Tenant Model Extension Summary

**Extended Tenant SQLAlchemy model with 8 Claude+wxcode fields, Alembic migration 008 with server_defaults, and 6 passing integration tests including encrypted token round-trip**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-07T17:12:57Z
- **Completed:** 2026-03-07T17:15:43Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added 8 new fields to `Tenant` model: `claude_oauth_token` (nullable String(2048) for Fernet-encrypted values), `claude_default_model` (default "sonnet"), `claude_max_concurrent_sessions` (default 3), `claude_monthly_token_budget` (nullable), `database_name` (nullable), `default_target_stack` (default "fastapi-jinja2"), `neo4j_enabled` (default True), `status` (default "pending_setup")
- Created Alembic migration 008 with `down_revision="007"`, 8 `op.add_column` calls with `server_default` on non-nullable columns so existing rows receive correct defaults without data migration
- 6 integration tests all pass: default field verification, encrypted token round-trip via `encrypt_value`/`decrypt_value`, all 4 valid status values, custom Claude config, database_name pattern

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend Tenant model with Claude and wxcode fields** - `8eefdbd` (feat)
2. **Task 2: Create Alembic migration 008 and write tests for new fields** - `ac9344b` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified

- `backend/src/wxcode_adm/tenants/models.py` - Added Integer to imports; 8 new Phase 20 fields with correct types, defaults, and nullability under "# Phase 20: Claude and wxcode integration fields" comment block
- `backend/alembic/versions/008_add_claude_wxcode_tenant_fields.py` - Alembic migration adding all 8 columns; revision="008", down_revision="007"; server_default on claude_default_model, claude_max_concurrent_sessions, default_target_stack, neo4j_enabled, status
- `backend/tests/test_tenant_model_extension.py` - 6 integration tests using test_db fixture; covers Claude defaults, wxcode defaults, encrypted token round-trip, all valid status values, custom config, database_name pattern

## Decisions Made

- **Plain String for status:** Using `String(20)` not `Enum` for the status column, consistent with the project's `native_enum=False` pattern documented in RESEARCH.md. Valid values (pending_setup, active, suspended, cancelled) are enforced at service/API layer.
- **String(2048) for oauth token:** Fernet-encrypted tokens are base64url-encoded and significantly longer than the original plaintext token. 2048 chars accommodates current and future token sizes.
- **Nullable = unlimited for token budget:** `claude_monthly_token_budget=None` means unlimited — avoids choosing a sentinel integer (0? -1? max_int?) that could cause logic errors.
- **server_default vs no server_default:** Non-nullable columns get `server_default` so ALTER TABLE succeeds on non-empty tables. Nullable columns omit `server_default` since NULL is the correct initial state.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Pre-existing test failures in `test_platform_security.py` (3 audit log query tests + 1 rate limit flake) are not caused by this plan's changes - confirmed by running those tests against the pre-change codebase (same failures).

## User Setup Required

None - no external service configuration required. The existing `WXCODE_ENCRYPTION_KEY` setting (added in plan 20-01) is used for `claude_oauth_token` encryption.

## Next Phase Readiness

- Tenant model now has all fields needed for wxcode engine integration phases (21+)
- Migration 008 is ready to run: `PYTHONPATH=src alembic upgrade head`
- `claude_oauth_token` field accepts Fernet-encrypted values from `encrypt_value()` (plan 20-01)
- `status` field starts as "pending_setup" — Phase 21 (provisioning) will transition it to "active"

---
*Phase: 20-crypto-service-tenant-model-extension*
*Completed: 2026-03-07*

## Self-Check: PASSED

- backend/src/wxcode_adm/tenants/models.py: FOUND
- backend/alembic/versions/008_add_claude_wxcode_tenant_fields.py: FOUND
- backend/tests/test_tenant_model_extension.py: FOUND
- .planning/phases/20-crypto-service-tenant-model-extension/20-02-SUMMARY.md: FOUND
- Commit 8eefdbd (feat: extend Tenant model): FOUND
- Commit ac9344b (feat: migration 008 + tests): FOUND
