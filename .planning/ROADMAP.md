# Roadmap: WXCODE ADM

## Milestones

- ✅ **v1.0 Backend API** — Phases 1-11 (shipped 2026-03-04)
- ✅ **v2.0 Frontend UI** — Phases 12-19 (shipped 2026-03-06)
- 🔲 **v3.0 WXCODE Engine Integration** — Phases 20-25 (planned)

## Phases

<details>
<summary>✅ v1.0 Backend API (Phases 1-11) — SHIPPED 2026-03-04</summary>

- [x] Phase 1: Foundation (4/4 plans) — completed 2026-02-22
- [x] Phase 2: Auth Core (5/5 plans) — completed 2026-02-23
- [x] Phase 3: Multi-Tenancy and RBAC (5/5 plans) — completed 2026-02-23
- [x] Phase 4: Billing Core (5/5 plans) — completed 2026-02-24
- [x] Phase 5: Platform Security (4/4 plans) — completed 2026-02-24
- [x] Phase 6: OAuth and MFA (5/5 plans) — completed 2026-02-24
- [x] Phase 7: User Account (4/4 plans) — completed 2026-02-25
- [x] Phase 8: Super-Admin (4/4 plans) — completed 2026-02-26
- [x] Phase 9: MFA-wxcode Redirect Fix (1/1 plan) — completed 2026-02-28
- [ ] Phase 10: API Key Management (0/1 plan) — **PENDING** (deferred: PLAT-01, PLAT-02)
- [x] Phase 11: Billing Integration Fixes (1/1 plan) — completed 2026-03-04

Full details: `milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v2.0 Frontend UI (Phases 12-19) — SHIPPED 2026-03-06</summary>

- [x] Phase 12: Design System Foundation (3/3 plans) — completed 2026-03-04
- [x] Phase 13: Auth Flows UI (4/4 plans) — completed 2026-03-04
- [x] Phase 14: User Account UI (2/2 plans) — completed 2026-03-05
- [x] Phase 15: Tenant Management UI (3/3 plans) — completed 2026-03-05
- [x] Phase 16: Billing UI (2/2 plans) — completed 2026-03-05
- [x] Phase 17: Super-Admin UI (3/3 plans) — completed 2026-03-05
- [x] Phase 18: Super-Admin Enhanced (2/2 plans) — completed 2026-03-06
- [x] Phase 19: UI Polish and Tech Debt Cleanup (1/1 plan) — completed 2026-03-06

Full details: `milestones/v2.0-ROADMAP.md`

</details>

<details>
<summary>🔲 v3.0 WXCODE Engine Integration (Phases 20-25) — PLANNED</summary>

- [x] Phase 20: Crypto Service + Tenant Model Extension (2 plans) (completed 2026-03-07)
  - [ ] 20-01-PLAN.md — Fernet crypto service + encryption key config
  - [ ] 20-02-PLAN.md — Tenant model extension + migration 008 + tests
- [x] Phase 21: Plan Limits Extension (1 plan) (completed 2026-03-07)
  - [ ] 21-01-PLAN.md — Plan model limits + migration 009 + schemas + tests
- [x] Phase 22: Claude Provisioning API (2 plans) (completed 2026-03-07)
  - [ ] 22-01-PLAN.md — Admin provisioning endpoints (schemas + service + 4 admin routes)
  - [ ] 22-02-PLAN.md — wxcode-config endpoint + integration tests
- [x] Phase 23: Admin UI — Claude Management (6 plans) (UAT gap closure in progress) (completed 2026-03-08)
  - [x] 23-01-PLAN.md — API hooks + tenant detail WXCODE Integration section
  - [x] 23-02-PLAN.md — Plan management page with wxcode limits + admin nav update
  - [ ] 23-03-PLAN.md — Backend: split budget/quota to dual 5h + weekly fields
  - [ ] 23-04-PLAN.md — Session persistence + plan inactivate/delete fixes
  - [ ] 23-05-PLAN.md — Frontend: dual budget/quota fields in hooks + UI pages
  - [ ] 23-06-PLAN.md — WXCODE provisioning endpoint + tenant detail UI section
- [x] Phase 24: CORS Fix + Integration Contract (2 plans) (completed 2026-03-09)
  - [ ] 24-01-PLAN.md — CORS production fix + dynamic tenant wxcode_url origins + tests
  - [ ] 24-02-PLAN.md — Integration health endpoint + contract documentation + tests
- [ ] Phase 25: wxcode-config Plan Limits (1 plan) — **Gap Closure** (MISSING-01, FLOW-BREAK-01)
  - Goal: Expose plan limits (max_projects, max_output_projects, max_storage_gb, token_quota_5h, token_quota_weekly) in GET /tenants/{id}/wxcode-config via TenantSubscription → Plan join + update INTEGRATION-CONTRACT.md
  Plans:
  - [ ] 25-01-PLAN.md — Add plan_limits to wxcode-config endpoint + update integration contract

Full details: `milestones/v3.0-ROADMAP.md`

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 4/4 | Complete | 2026-02-22 |
| 2. Auth Core | v1.0 | 5/5 | Complete | 2026-02-23 |
| 3. Multi-Tenancy and RBAC | v1.0 | 5/5 | Complete | 2026-02-23 |
| 4. Billing Core | v1.0 | 5/5 | Complete | 2026-02-24 |
| 5. Platform Security | v1.0 | 4/4 | Complete | 2026-02-24 |
| 6. OAuth and MFA | v1.0 | 5/5 | Complete | 2026-02-24 |
| 7. User Account | v1.0 | 4/4 | Complete | 2026-02-25 |
| 8. Super-Admin | v1.0 | 4/4 | Complete | 2026-02-26 |
| 9. MFA-wxcode Redirect Fix | v1.0 | 1/1 | Complete | 2026-02-28 |
| 10. API Key Management | v1.0 | 0/1 | Pending | - |
| 11. Billing Integration Fixes | v1.0 | 1/1 | Complete | 2026-03-04 |
| 12. Design System Foundation | v2.0 | 3/3 | Complete | 2026-03-04 |
| 13. Auth Flows UI | v2.0 | 4/4 | Complete | 2026-03-04 |
| 14. User Account UI | v2.0 | 2/2 | Complete | 2026-03-05 |
| 15. Tenant Management UI | v2.0 | 3/3 | Complete | 2026-03-05 |
| 16. Billing UI | v2.0 | 2/2 | Complete | 2026-03-05 |
| 17. Super-Admin UI | v2.0 | 3/3 | Complete | 2026-03-05 |
| 18. Super-Admin Enhanced | v2.0 | 2/2 | Complete | 2026-03-06 |
| 19. UI Polish and Tech Debt Cleanup | v2.0 | 1/1 | Complete | 2026-03-06 |
| 20. Crypto Service + Tenant Model Extension | v3.0 | 2/2 | Complete | 2026-03-07 |
| 21. Plan Limits Extension | v3.0 | 1/1 | Complete | 2026-03-07 |
| 22. Claude Provisioning API | v3.0 | 2/2 | Complete | 2026-03-07 |
| 23. Admin UI — Claude Management | v3.0 | 6/6 | Complete | 2026-03-08 |
| 24. CORS Fix + Integration Contract | v3.0 | 2/2 | Complete | 2026-03-09 |
| 25. wxcode-config Plan Limits | v3.0 | 0/1 | Not started | - |
