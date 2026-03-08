# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-06)

**Core value:** Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.
**Current focus:** v3.0 WXCODE Engine Integration — planned, not yet started.

## Current Position

Phase: v3.0 Phase 23 (Admin UI Claude Management) — IN PROGRESS
Plan: 64 plans complete (38 v1.0 + 20 v2.0 + 6 v3.0), Plan 23-01 done
Status: v3.0 IN PROGRESS — Phase 23 IN PROGRESS (1 of 2 plans done)
Last activity: 2026-03-08 — 23-01 WXCODE Integration UI (hooks + tenant detail WXCODE card)

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
- Plans completed: 6 (20-01, 20-02, 21-01, 22-01, 22-02, 23-01)
- Average duration: 2-4 min
- Phase 20 complete, Phase 21 complete, Phase 22 complete, Phase 23 in progress

**Combined:**
- 64 plans executed across 23 phases
- Backend: ~20,600 LOC Python, 161 tests passing
- Frontend: 9,612 LOC TypeScript/React (+438 LOC from Phase 23-01), 51 source files
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
Stopped at: Completed 23-01-PLAN.md (WXCODE Integration UI: 4 mutation hooks + tenant detail WXCODE card)
Resume file: None — Phase 23 plan 23-02 is next
