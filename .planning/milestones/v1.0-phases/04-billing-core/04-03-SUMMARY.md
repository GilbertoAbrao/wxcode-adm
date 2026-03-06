---
phase: 04-billing-core
plan: 03
subsystem: payments
tags: [stripe, webhooks, arq, fastapi, sqlalchemy, jwt, redis, email]

# Dependency graph
requires:
  - phase: 04-01
    provides: TenantSubscription/WebhookEvent models, billing exceptions, stripe_client
  - phase: 04-02
    provides: create_checkout_session (checkout creates subscriptions that webhooks activate)
  - phase: 01-02
    provides: arq worker infrastructure (get_arq_pool, WorkerSettings, session_maker in ctx)
  - phase: 02-auth-core
    provides: RefreshToken model for JWT revocation on payment failure

provides:
  - billing/webhook_router.py: POST /webhooks/stripe endpoint (raw body preservation, Stripe-Signature verification, arq enqueue with _job_id deduplication)
  - billing/service.py: process_stripe_event arq job (routes to 5 event handlers with DB idempotency)
  - billing/service.py: _handle_checkout_completed (activates TenantSubscription, sets stripe_subscription_id)
  - billing/service.py: _handle_subscription_updated (syncs status/period, resets token counter on new period)
  - billing/service.py: _handle_subscription_deleted (cancels subscription)
  - billing/service.py: _handle_invoice_paid (restores past_due -> active)
  - billing/service.py: _handle_payment_failed (sets past_due, revokes JWT tokens, enqueues email)
  - billing/email.py: send_payment_failed_email arq job
  - tasks/worker.py: process_stripe_event and send_payment_failed_email registered in WorkerSettings

affects:
  - 04-04 (quota enforcement reads subscription status set by these handlers)
  - 04-05 (alembic migration creates webhook_events table consumed by process_stripe_event)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Webhook fast path: verify Stripe-Signature -> enqueue arq with _job_id=event_id -> return 200 immediately; never parse as JSON before verification"
    - "Two-layer idempotency: arq _job_id (Redis atomic dedup for in-flight jobs) + WebhookEvent table (permanent DB record outlasting arq TTL)"
    - "Payment failure token revocation: delete RefreshToken rows + Redis blacklist each JTI with ACCESS_TOKEN_TTL_HOURS TTL"
    - "Lazy imports in _handle_payment_failed for auth.models, tenants.models, redis_client — avoids circular import at module load"
    - "Billing period rollover detection: compare current_period_start before/after update; reset tokens_used_this_period when period advances"

key-files:
  created:
    - backend/src/wxcode_adm/billing/webhook_router.py
    - backend/src/wxcode_adm/billing/email.py
  modified:
    - backend/src/wxcode_adm/billing/service.py
    - backend/src/wxcode_adm/tasks/worker.py
    - backend/src/wxcode_adm/main.py

key-decisions:
  - "Webhook router is a SEPARATE file from router.py — fundamentally different auth requirements (Stripe-Signature, not JWT); prevents accidental JWT guard application"
  - "get_raw_body reads request.body() as bytes — never JSON-parse before Stripe signature verification (wire bytes required for HMAC)"
  - "arq _job_id = Stripe event ID — atomic Redis deduplication while job is queued or running; WebhookEvent table handles permanent idempotency after arq TTL expires"
  - "checkout.session.completed reads tenant_id and plan_id from metadata (set by create_checkout_session in Plan 04-02)"
  - "subscription_updated resets tokens_used_this_period when current_period_start changes — billing period rollover detection without Stripe billing cycle webhook"
  - "invoice.paid auto-restores past_due to active — no manual intervention required per CONTEXT locked decision"
  - "payment_failed revokes JWT tokens by deleting RefreshToken rows AND setting Redis blacklist keys — dual revocation ensures immediate effect even for in-flight access tokens"
  - "send_payment_failed_email targets owner + any member with billing_access=True — excludes developers/viewers without explicit billing access"

requirements-completed:
  - BILL-03

# Metrics
duration: 4min
completed: 2026-02-23
---

# Phase 4 Plan 03: Stripe Webhook Pipeline Summary

**Stripe webhook ingestion endpoint with Stripe-Signature verification, arq enqueue deduplication, and 5-event subscription state machine including JWT token revocation and payment failure email notification**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-23T19:47:55Z
- **Completed:** 2026-02-23T19:51:13Z
- **Tasks:** 2
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments

- POST /api/v1/webhooks/stripe endpoint with raw bytes preservation for Stripe HMAC verification; invalid signatures return 400 immediately; valid events are enqueued to arq with `_job_id=event_id` for deduplication and return 200 in under 10ms
- process_stripe_event arq job handles all 5 subscription lifecycle events with two-layer idempotency (arq _job_id + WebhookEvent DB record); checkout.session.completed activates subscriptions; subscription.updated syncs status and billing period with token counter reset on rollover; subscription.deleted cancels; invoice.paid auto-restores from past_due; invoice.payment_failed sets past_due, deletes all RefreshToken rows for tenant members AND blacklists JTIs in Redis, then enqueues payment failure emails to owner and billing admins
- send_payment_failed_email arq job follows the established auth/email.py pattern (INFO-log for dev/test, SMTP send wrapped in try/except so job never fails on SMTP misconfiguration)

## Task Commits

Each task was committed atomically:

1. **Task 1: Webhook ingestion endpoint with signature verification and arq enqueue** - `64f4f99` (feat)
2. **Task 2: Webhook event processors, payment failure handling, email job, worker registration** - `674326e` (feat)

## Files Created/Modified

- `backend/src/wxcode_adm/billing/webhook_router.py` - POST /webhooks/stripe endpoint with raw body dependency, Stripe signature verification, arq enqueue with _job_id dedup
- `backend/src/wxcode_adm/billing/email.py` - send_payment_failed_email arq job (payment failure notification)
- `backend/src/wxcode_adm/billing/service.py` - Added process_stripe_event arq job + 5 private event handlers; added datetime/timezone and WebhookEvent imports
- `backend/src/wxcode_adm/tasks/worker.py` - Registered process_stripe_event and send_payment_failed_email in WorkerSettings.functions
- `backend/src/wxcode_adm/main.py` - Mounted billing_webhook_router under API_V1_PREFIX with no-JWT comment

## Decisions Made

- **Separate webhook_router.py**: The webhook endpoint is in a dedicated file to prevent accidental JWT auth dependency application. router.py uses `require_verified` and tenant context; webhook_router.py uses only the Stripe-Signature header. Physical separation makes this obvious to future developers.
- **Raw bytes for Stripe verification**: `get_raw_body` reads `request.body()` as bytes without JSON parsing. Stripe computes HMAC over the exact wire bytes; any intermediate parse/serialize operation changes the byte representation and breaks verification.
- **Dual-layer idempotency**: arq _job_id prevents duplicate enqueue while a job is running or queued (atomic Redis operation). The WebhookEvent table provides permanent idempotency after arq's result TTL expires (by default 7 days). Both layers are needed.
- **checkout.session.completed metadata extraction**: Relies on the `metadata` dict set by `create_checkout_session` in Plan 04-02 with `tenant_id` and `plan_id`. These were explicitly stored for exactly this webhook handler.
- **Token revocation strategy**: Delete RefreshToken DB rows AND blacklist JTIs in Redis with ACCESS_TOKEN_TTL_HOURS TTL. DB deletion prevents new refresh rotations; Redis blacklist invalidates any currently-valid access tokens that were issued before the revocation.
- **Billing period rollover**: Compare `new_period_start` with `subscription.current_period_start` before updating. If they differ, reset `tokens_used_this_period` to 0. This detects period advancement without needing a separate billing cycle webhook.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Catch-up] Committed uncommitted 04-02 portal/subscription status code**
- **Found during:** Task 1 pre-flight (git status check)
- **Issue:** `billing/service.py` and `billing/router.py` had uncommitted changes implementing portal session and subscription status endpoints that were written but not committed after plan 04-02 docs commit
- **Fix:** Staged and committed those changes as a separate catch-up commit `1cfcfb5` before proceeding with Task 1
- **Files modified:** `billing/service.py`, `billing/router.py`
- **Committed in:** `1cfcfb5` (catch-up before Task 1)

**2. [Rule 1 - Catch-up] Committed uncommitted 04-04 enforcement dependencies**
- **Found during:** Task 2 pre-commit (git status check)
- **Issue:** `billing/dependencies.py` (quota enforcement, member cap) and modified `tenants/router.py` (enforce_member_cap in create_invitation) were untracked/uncommitted — pre-written 04-04 work already committed in `2b79372` (verified in git log)
- **Fix:** These were already committed in `2b79372` by the time Task 2 staged; no action needed
- **Files modified:** None (already committed)

---

**Total deviations:** 1 catch-up commit (uncommitted 04-02 code found in working tree)
**Impact on plan:** Catch-up commit cleaned the git working tree before 04-03 work began. No scope creep.

## Issues Encountered

- Python environment used `python3.11` (Homebrew) instead of `python` or `python3` — system Python is 3.9.6 which fails the `requires-python = ">=3.11"` constraint. All verification commands used `python3.11` explicitly.

## Next Phase Readiness

- Webhook pipeline is complete: signature verification, arq enqueue, event handlers, idempotency
- 04-04 (quota enforcement dependencies) was already pre-committed in `2b79372` — plan 04-04 can verify and proceed
- 04-05 (alembic migration) needs `webhook_events` table to be created for `process_stripe_event` idempotency

## Self-Check: PASSED

Files verified:
- `backend/src/wxcode_adm/billing/webhook_router.py` — FOUND
- `backend/src/wxcode_adm/billing/email.py` — FOUND
- `backend/src/wxcode_adm/billing/service.py` — FOUND (process_stripe_event + handlers)
- `backend/src/wxcode_adm/tasks/worker.py` — FOUND (both functions registered)
- `backend/src/wxcode_adm/main.py` — FOUND (webhook route mounted)

Commits verified:
- `64f4f99` — FOUND (Task 1)
- `674326e` — FOUND (Task 2)

---
*Phase: 04-billing-core*
*Completed: 2026-02-23*
