---
phase: 04-billing-core
plan: 04
subsystem: payments
tags: [stripe, billing, fastapi, sqlalchemy, quota, enforcement, dependencies]

# Dependency graph
requires:
  - phase: 04-01
    provides: Plan/TenantSubscription models, billing exceptions (PaymentRequiredError, QuotaExceededError, MemberLimitError)
  - phase: 04-02
    provides: create_portal_session, get_subscription_status in service.py; require_billing_access; portal/subscription endpoints; SubscriptionResponse schema

provides:
  - billing/dependencies.py: _enforce_active_subscription (pure sync helper, directly testable)
  - billing/dependencies.py: _enforce_token_quota (pure sync helper, directly testable)
  - billing/dependencies.py: require_active_subscription (FastAPI Depends — blocks PAST_DUE/CANCELED)
  - billing/dependencies.py: check_token_quota (FastAPI Depends — free tier quota + X-Quota-Warning headers)
  - billing/dependencies.py: check_member_cap (FastAPI Depends — plan member cap enforcement)
  - billing/dependencies.py: enforce_member_cap (standalone async utility for direct calls)
  - tenants/router.py: create_invitation now enforces plan member cap via enforce_member_cap

affects:
  - 04-05 (integration tests will call _enforce_active_subscription and _enforce_token_quota directly)
  - wxcode engine proxy endpoints (will use require_active_subscription and check_token_quota)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Private sync helpers pattern: _enforce_active_subscription and _enforce_token_quota contain pure enforcement logic, called by both FastAPI deps and tests directly"
    - "Lazy import in endpoint handler: enforce_member_cap imported inside create_invitation body to avoid circular import (billing.deps -> tenants.deps -> tenants.models; tenants.router -> billing.deps would be fine, but lazy import is defensive)"
    - "Response header injection from Depends: FastAPI injects Response into check_token_quota via parameter, allows setting X-Quota-Warning headers without modifying endpoint signature"
    - "Overage billing never blocks: _enforce_token_quota only raises for monthly_fee_cents==0 plans — paid customers are never interrupted regardless of token usage"

key-files:
  created:
    - backend/src/wxcode_adm/billing/dependencies.py
  modified:
    - backend/src/wxcode_adm/tenants/router.py

key-decisions:
  - "Private sync helpers _enforce_active_subscription and _enforce_token_quota are pure synchronous functions with no DB calls — Plan 05 tests call them directly without FastAPI Depends wiring"
  - "enforce_member_cap is a standalone async function (not a FastAPI dependency) — avoids double tenant-context resolution since require_role already resolves context in create_invitation"
  - "Lazy import of enforce_member_cap inside create_invitation handler body — defensive pattern matching auto_join_pending_invitations and create_workspace precedents"
  - "check_token_quota chains on require_active_subscription — quota check only runs if subscription is active (no point checking quota for canceled/past_due tenants)"
  - "X-Quota-Warning at 80% uses QUOTA_WARNING_80PCT value, at 100% uses QUOTA_REACHED — two separate thresholds per CONTEXT.md spec"

patterns-established:
  - "Pure sync helpers for enforcement logic: makes integration testing straightforward without FastAPI test client overhead"
  - "Dependency chaining: check_token_quota -> require_active_subscription -> get_tenant_context — explicit dependency hierarchy"

requirements-completed:
  - BILL-04
  - BILL-05

# Metrics
duration: 4min
completed: 2026-02-23
---

# Phase 4 Plan 04: Portal, Subscription Status, and Plan Enforcement Summary

**Stripe Customer Portal access and three reusable FastAPI enforcement dependencies (active subscription, token quota, member cap) with private sync helpers for direct test-time assertion**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-23T19:46:22Z
- **Completed:** 2026-02-23T19:50:54Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Task 1 (POST /billing/portal + GET /billing/subscription) was already committed in a prior session as commit `1cfcfb5` — recognized as complete and verified without re-doing work
- Created `billing/dependencies.py` with 6 functions: 2 pure sync helpers (`_enforce_active_subscription`, `_enforce_token_quota`) for direct testability, 3 FastAPI dependencies (`require_active_subscription`, `check_token_quota`, `check_member_cap`), and 1 standalone utility (`enforce_member_cap`)
- Wired `enforce_member_cap` into the invitation creation endpoint (`POST /api/v1/tenants/current/invitations`) via lazy import — member cap is now enforced before any invitation is created
- `check_token_quota` sets `X-Quota-Warning` and `X-Quota-Usage` response headers at 80% and 100% usage — paid plans are never blocked (overage billing), free tier is hard-blocked at quota

## Task Commits

Each task was committed atomically:

1. **Task 1: Customer Portal session + subscription status API** - `1cfcfb5` (feat) — previously committed
2. **Task 2: Plan enforcement dependencies** - `2b79372` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/src/wxcode_adm/billing/dependencies.py` — All plan enforcement logic: active subscription check, token quota enforcement (with warning headers), member cap check, and private sync helpers for direct test use
- `backend/src/wxcode_adm/tenants/router.py` — Added `enforce_member_cap` call in `create_invitation` with lazy import to prevent circular imports

## Decisions Made

- Private sync helpers pattern: `_enforce_active_subscription` and `_enforce_token_quota` are pure synchronous functions that contain the enforcement logic. Plan 05 tests call them directly without FastAPI Depends — no test client overhead for unit-level assertion
- `enforce_member_cap` as a standalone function (not a FastAPI Depends): `require_role` in `create_invitation` already resolves tenant context; making it a second Depends would double-resolve the context. Direct call with `(db, tenant.id)` is cleaner
- Lazy import of `enforce_member_cap` inside handler body — matches the established `auto_join_pending_invitations` and `create_workspace` patterns from Phases 2 and 4

## Deviations from Plan

None - plan executed exactly as written.

Task 1 (portal/subscription endpoints) was found already committed from a prior partial session. The code was verified as correct and complete per plan spec without re-implementing.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `billing/dependencies.py` is ready for Plan 05 integration tests (`_enforce_active_subscription` and `_enforce_token_quota` importable and callable without FastAPI wiring)
- `require_active_subscription` and `check_token_quota` ready to wire into wxcode engine proxy endpoints in Phase 5 or beyond
- Member cap enforcement active in invitation flow — inviting past plan limit now returns HTTP 402

---
*Phase: 04-billing-core*
*Completed: 2026-02-23*
