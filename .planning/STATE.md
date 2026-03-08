# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-06)

**Core value:** Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.
**Current focus:** v3.0 WXCODE Engine Integration — planned, not yet started.

## Current Position

Phase: v3.0 Phase 23 (Admin UI Claude Management) — COMPLETE
Plan: 71 plans complete (38 v1.0 + 20 v2.0 + 13 v3.0), Phase 23 done
Status: v3.0 IN PROGRESS — Phase 23 COMPLETE (6 of 6 plans done)
Last activity: 2026-03-08 — 23-06 WXCODE Provisioning config endpoint + UI section

Progress: [████████████████████████████████] 100% (v1.0+v2.0) + v3.0 started

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 38
- Average duration: 5 min
- Total execution time: ~3.2 hours
- Timeline: 11 days (2026-02-22 → 2026-03-04)

**Velocity (v2.0):**
- Total plans completed: 20
- Average duration: 2 min
- Total execution time: ~0.7 hours
- Timeline: 3 days (2026-03-04 → 2026-03-06)

**Velocity (v3.0):**
- Plans completed: 14 (20-01, 20-02, 21-01, 22-01, 22-02, 23-01, 23-02, 23-03, 23-04, 23-05, 23-06 + gap closure plans including 23-03 backend re-do)
- Average duration: 2-11 min
- Phase 20 complete, Phase 21 complete, Phase 22 complete, Phase 23 complete (6 of 6 + gap closures)

**Combined:**
- 66+ plans executed across 23 phases
- Backend: ~20,700 LOC Python, 175 tests passing (+14 from dual quota field tests)
- Frontend: ~10,765 LOC TypeScript/React, 53 source files
- Timeline: 14 days total (2026-02-22 → 2026-03-08)

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

**20-01 (Crypto Service):**
- Lazy _get_fernet() helper reads key per call — enables test monkeypatching without module-level state
- SHA-256 passphrase derivation — any string works as WXCODE_ENCRYPTION_KEY, no Fernet format requirement for dev
- Dev default "change-me-in-production" — obvious sentinel, not a hardcoded fake Fernet key

**20-02 (Tenant Model Extension):**
- Plain String (not enum) for status field — consistent with MemberRole native_enum=False pattern, avoids PostgreSQL CREATE TYPE issues
- String(2048) for claude_oauth_token — Fernet-encrypted tokens are longer than plaintext OAuth tokens
- claude_monthly_token_budget nullable (null = unlimited) — avoids sentinel integer value ambiguity
- server_default on non-nullable migration columns — existing rows get defaults without data migration

**21-01 (Plan Limits Extension):**
- Limit fields not wired into Stripe re-sync — wxcode-only operational limits, not billing amounts
- ge=1 validation on limit fields — zero limits are operationally invalid
- Defaults consistent between model default= and migration server_default= (5, 20, 10)

**22-01 (Claude Provisioning API):**
- Budget=0 in API means unlimited (NULL in DB); None means "no change" — avoids ambiguity
- Claude OAuth token value never written to logs or audit details — only reason and tenant_id recorded
- AdminActionRequest reused for DELETE /claude-token body — shared semantics for reason field

**22-02 (wxcode-config endpoint + integration tests):**
- tenant-mismatch-404: wxcode-config validates path tenant_id vs X-Tenant-ID to prevent cross-tenant reads (404, not 403)
- max_concurrent_sessions: no 'claude_' prefix in wxcode-config response, matching ROADMAP spec
- httpx-delete-body: Use c.request('DELETE', url, content=json.dumps(...)) for DELETE with body in tests

**23-01 (Admin UI WXCODE Integration — hooks + tenant detail page):**
- wxcodeStatusBadge as separate function from statusBadge — handles wxcode lifecycle (pending_setup/active/suspended/cancelled) vs legacy is_suspended/is_deleted booleans
- Token entry uses type=password for shoulder-surfing prevention; has_claude_token display always shows masked ****-****-****
- Config form sends partial PATCH — only non-empty fields included; 0 for budget maps to unlimited (NULL in DB)

**23-02 (Plans management page + nav links):**
- Array response for plans (not paginated) — backend returns PlanResponse[] directly, no wrapper object
- Partial PATCH compares edit field strings vs original plan string values — only sends changed fields
- Plans nav link placed between Tenants and Users — logical hierarchy Dashboard > Tenants > Plans > Users > Audit Logs

**23-04 (Admin session persistence + plan inactivate/delete):**
- Refresh token only in localStorage (not access token) — access token short-lived, stays in memory for XSS safety
- Async session restore on mount — isLoading=true until refreshAdminTokens resolves, preventing redirect flash to /admin/login
- PLAN_IN_USE guard counts all TenantSubscription references (not filtered by status) — prevents orphaned subscription records

**23-06 (WXCODE Provisioning config — gap closure):**
- WxcodeConfigUpdateRequest uses at-least-one-field model_validator — consistent with ClaudeConfigUpdateRequest pattern
- WXCODE Provisioning section visible only for pending_setup tenants — prevents confusing display in other states
- database_name displays amber "Not configured" warning when null — direct visual cue that activation will fail
- neo4j_enabled uses string state with "no change" option — prevents accidental boolean overwrites
- [Phase 23-03]: token_quota_5h used as enforcement field in _enforce_token_quota (tighter 5h window = primary constraint)
- [Phase 23-03]: Data migration copies existing values to BOTH new columns to preserve prior data in migration 010
- [Phase 23]: token_quota fields in billing/page.tsx (tenant-facing) left untouched — out of scope for plan 23-05; different API endpoint and interface

### Roadmap Evolution

- Phase 9 inserted: MFA-wxcode redirect fix (gap closure from v1.0 audit)
- Phase 11 inserted: Billing integration fixes (gap closure from v1.0 audit — INT-01, INT-02)
- Phase 18 added: Super-Admin Enhanced (MRR dashboard, audit log, tenant detail, force reset)
- Phase 19 added: UI Polish and Tech Debt Cleanup (gap closure from v2.0 audit)

### Pending Todos

None.

### Blockers/Concerns

- Phase 10 (API Key Management) still pending — PLAT-01 and PLAT-02 not implemented. Carry-over to next milestone.

## Session Continuity

Last session: 2026-03-08
Stopped at: Completed 23-05-PLAN.md (frontend dual budget/quota fields: hook interfaces + tenant detail + plans page)
Resume file: None — all 6 plans in phase 23 now complete
