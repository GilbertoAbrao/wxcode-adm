# Phase 11: Billing Integration Fixes - Research

**Researched:** 2026-03-02
**Domain:** Python / FastAPI / SQLAlchemy / Redis — surgical bug fixes in existing billing service and router
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BILL-01 | Super-admin can CRUD billing plans (synced with Stripe) | INT-02 fix ensures billing admin CRUD uses `require_admin` (admin-audience JWT), fully isolating plan management to admin-only tokens |
| BILL-03 | Stripe webhooks sync subscription state (paid, updated, deleted, failed) | INT-01 fix ensures `invoice.payment_failed` actually revokes access tokens via correct Redis key pattern |
| BILL-05 | Plan limits enforced before wxcode engine operations | INT-01 fix is prerequisite: a user with a blacklisted JTI is blocked at `get_current_user` before reaching plan enforcement; without the fix, past-due tokens remain valid |
</phase_requirements>

---

## Summary

Phase 11 is a gap-closure phase with exactly two targeted fixes: a critical Redis key bug in `_handle_payment_failed` and a medium JWT audience wiring error in `billing_admin_router`. Both bugs were identified by the v1.0 audit and have clear root causes, clear correct patterns already present in the codebase, and clear test requirements.

**Fix 1 (INT-01, CRITICAL):** `_handle_payment_failed` in `billing/service.py` lines 872-879 uses `token.token` (the opaque refresh token string) as the Redis blacklist key, writing `auth:blacklist:jti:{refresh_token_string}`. The `is_token_blacklisted` check in `auth/dependencies.py` looks up `auth:blacklist:jti:{jti}` where `jti` is the UUID from the access token's `jti` claim. These keys never match. The correct pattern — query `UserSession.access_token_jti` and call `blacklist_jti(redis, jti)` — is already used identically in `admin/service.py:suspend_tenant` (lines 447-454) and `admin/service.py:force_password_reset` (lines 903-907). This fix requires importing `UserSession` and `blacklist_jti` into the `_handle_payment_failed` lazy-import block and replacing the manual `redis.setex` call with the proper helper.

**Fix 2 (INT-02, MEDIUM):** `billing/router.py` defines a local `require_superuser` dependency (lines 46-60) that accepts regular-audience JWT tokens where `user.is_superuser=True`. Phase 8 introduced `require_admin` from `admin/dependencies.py` which enforces `aud="wxcode-adm-admin"`. All five billing admin endpoints (POST, PATCH, DELETE, GET list, GET single) must replace `Depends(require_superuser)` with `Depends(require_admin)`. The local `require_superuser` function and its `ForbiddenError` import become dead code after the replacement.

**Fix 3 (Success Criterion 3 — E2E test):** An integration test must cover the full E2E flow #8: payment failure webhook → subscription PAST_DUE → access tokens blacklisted → member blocked on platform-level endpoints. The existing `test_webhook_payment_failed` test only verifies PAST_DUE status; it does not verify that the user's JTI is written to Redis, nor that a subsequent request with the old access token is rejected.

**Primary recommendation:** Make the two surgical code changes and extend the existing test. No new files, no new models, no migrations required.

---

## Standard Stack

### Core (no additions needed)

This phase modifies existing code only. All relevant tools are already in use.

| Component | Where Used | What Changes |
|-----------|-----------|--------------|
| `wxcode_adm.auth.models.UserSession` | `admin/service.py` already imports it | Must add to lazy-import block in `billing/service.py:_handle_payment_failed` |
| `wxcode_adm.auth.service.blacklist_jti` | `admin/service.py` top-level import | Must add to lazy-import block in `billing/service.py:_handle_payment_failed` |
| `wxcode_adm.admin.dependencies.require_admin` | `admin/router.py` | Must add import in `billing/router.py` |

### No New Dependencies

No pip packages, no new models, no new migrations, no new files (all changes are in-place edits).

---

## Architecture Patterns

### Pattern 1: Access Token Blacklisting via UserSession JTI

**What:** To immediately invalidate active access tokens for a set of users, query `UserSession.access_token_jti` for those user IDs, then call `blacklist_jti(redis, jti)` for each JTI.

**When to use:** Any time a security event (suspension, payment failure, forced reset) requires immediate session termination before natural token expiry.

**The canonical pattern (from `admin/service.py:suspend_tenant`, lines 445-454):**

```python
# Source: backend/src/wxcode_adm/admin/service.py lines 445-459
if user_ids:
    # Blacklist all active access tokens for these users
    session_result = await db.execute(
        select(UserSession.access_token_jti).where(
            UserSession.user_id.in_(user_ids)
        )
    )
    jtis = [row[0] for row in session_result.fetchall()]
    for jti in jtis:
        await blacklist_jti(redis, jti)

    # Delete all refresh tokens for these users
    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id.in_(user_ids))
    )
```

**Why `blacklist_jti` not `redis.setex` directly:**

```python
# Source: backend/src/wxcode_adm/auth/service.py lines 361-377
async def blacklist_jti(redis: Redis, jti: str) -> None:
    await redis.set(
        f"auth:blacklist:jti:{jti}",
        "1",
        ex=int(settings.ACCESS_TOKEN_TTL_HOURS * 3600),
    )
```

`blacklist_jti` produces exactly the key pattern `auth:blacklist:jti:{jti}` that `is_token_blacklisted` in `auth/dependencies.py` checks.

### Pattern 2: Admin JWT Audience Enforcement

**What:** All routes under `/admin/*` that perform privileged operations must use `require_admin` from `admin/dependencies.py`, NOT a local `is_superuser` check against regular JWT tokens.

**The correct dependency:**

```python
# Source: backend/src/wxcode_adm/admin/dependencies.py lines 52-107
async def require_admin(
    token: str = Depends(admin_oauth2_scheme),
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> User:
    # Decodes token via decode_admin_access_token — enforces aud="wxcode-adm-admin"
    # Checks Redis blacklist
    # Verifies is_superuser=True
    ...
```

**The broken pattern (what billing/router.py currently does):**

```python
# Source: backend/src/wxcode_adm/billing/router.py lines 46-60 — THE BUG
async def require_superuser(
    user: Annotated[User, Depends(require_verified)],  # require_verified uses regular JWT
) -> User:
    if not user.is_superuser:
        raise ForbiddenError(...)
    return user
```

`require_verified` calls `get_current_user` which calls `decode_access_token` — this accepts regular-audience tokens. A superuser who has a regular access token (issued at `/auth/login`) can currently call admin billing endpoints, bypassing the admin audience isolation established in Phase 8.

### Pattern 3: Lazy Imports in Billing Service

**What:** `_handle_payment_failed` uses lazy imports inside the function body to avoid circular imports at module load time.

```python
# Source: backend/src/wxcode_adm/billing/service.py lines 832-838
async def _handle_payment_failed(db: AsyncSession, data_object: dict) -> None:
    from wxcode_adm.auth.models import RefreshToken  # noqa: PLC0415
    from wxcode_adm.tenants.models import TenantMembership, MemberRole  # noqa: PLC0415
    from wxcode_adm.common.redis_client import redis_client  # noqa: PLC0415
    from wxcode_adm.config import settings as _settings  # noqa: PLC0415
    from wxcode_adm.tasks.worker import get_arq_pool  # noqa: PLC0415
    from wxcode_adm.auth.models import User  # noqa: PLC0415
```

New imports for `UserSession` and `blacklist_jti` must also be lazy imports within the function body, using the same `# noqa: PLC0415` comment.

### Pattern 4: Test Infrastructure for Integration Flow #8

**What:** The test for E2E flow #8 must:
1. Create a user with an active session (login gives a JTI stored in `UserSession`)
2. Trigger `invoice.payment_failed` via `process_stripe_event`
3. Verify `UserSession.access_token_jti` JTI is in Redis as `auth:blacklist:jti:{jti}`
4. Make an HTTP request with the original access token and assert 401/403

**How existing tests verify subscription state (from `test_billing.py:test_webhook_payment_failed`):**

```python
# Source: backend/tests/test_billing.py lines 387-429 — current test (incomplete)
async def test_webhook_payment_failed(client):
    token, _ = await _signup_verify_login(c, redis, "webhook_payment_failed@test.com")
    tenant_id = await _create_workspace(c, token, "Payment Failed Test")
    # ... activate subscription ...
    await process_stripe_event(ctx, "evt_payment_failed_1", "invoice.payment_failed", ...)
    # Only checks status == PAST_DUE — does NOT verify JTI blacklisted or token rejected
```

**How `suspend_tenant` test verifies session invalidation (from `test_super_admin.py:test_suspend_tenant_invalidates_sessions`):**

```python
# Source: backend/tests/test_super_admin.py lines 226-248
# After suspension, original user token is used and gets 403/401
r = await c.get(
    "/api/v1/tenants/current",
    headers={"Authorization": f"Bearer {user_token}", "X-Tenant-ID": tenant_id},
)
# asserts non-200 response
```

The E2E integration test for flow #8 must follow the `suspend_tenant` test pattern: use the HTTP client to verify that the original access token is rejected after the webhook fires.

### Anti-Patterns to Avoid

- **Do not use `redis.setex` directly to write blacklist keys.** Always use `blacklist_jti(redis, jti)` — it centralizes the key format and TTL. The current bug is exactly this pattern being used incorrectly.
- **Do not use `delete(RefreshToken)` in bulk instead of the loop pattern.** The existing `_handle_payment_failed` already uses a loop for deletion; the fix only changes what keys are written to Redis before deletion.
- **Do not remove the `RefreshToken` deletion step.** The fix adds JTI blacklisting; it does not replace the existing RefreshToken deletion. Both are required: blacklist prevents the current access token from working, deletion prevents refresh rotation.
- **Do not add `redis` as a parameter to `_handle_payment_failed`.** The function uses `redis_client` singleton from `common/redis_client` (a tech debt noted in the audit, but intentionally not changing that pattern in this phase). `blacklist_jti` accepts a `Redis` instance — pass `redis_client` directly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Redis blacklist key format | Custom `f"auth:blacklist:..."` in billing | `blacklist_jti(redis, jti)` from `auth/service.py` | Canonical helper already exists; direct `setex` is the root cause of INT-01 |
| Admin JWT audience check | Local `is_superuser` check against regular JWT | `require_admin` from `admin/dependencies.py` | `require_admin` calls `decode_admin_access_token` which enforces `aud="wxcode-adm-admin"`; local check is the root cause of INT-02 |
| JTI discovery | Decode JWT string to extract JTI | Query `UserSession.access_token_jti` | `UserSession` is the authoritative store of JTIs for active sessions; `blacklist_jti` does not decode JWTs |

**Key insight:** Both bugs stem from reinventing functionality that already exists in the codebase at a higher quality level. The fix is to use the canonical tools, not to build new ones.

---

## Common Pitfalls

### Pitfall 1: Forgetting that `_handle_payment_failed` uses `redis_client` singleton, not `redis` parameter

**What goes wrong:** If you try to pass `redis` as a parameter to match `admin/service.py:suspend_tenant` style, you'll introduce a signature change that breaks the `process_stripe_event` arq job dispatcher which calls `_handle_payment_failed(db, data_object)`.

**Why it happens:** `admin/service.py` functions receive Redis as a parameter. `_handle_payment_failed` was written with a module-singleton pattern (tech debt noted in audit). The audit explicitly does not require fixing the singleton pattern in this phase.

**How to avoid:** Keep the existing `from wxcode_adm.common.redis_client import redis_client` lazy import. Pass `redis_client` as the argument to `blacklist_jti(redis_client, jti)`.

**Warning signs:** Any change to the function signature of `_handle_payment_failed`.

### Pitfall 2: The existing test `test_webhook_payment_failed` still passes after the fix (no regression signal)

**What goes wrong:** The existing test only checks `sub.status == SubscriptionStatus.PAST_DUE`, which was already correct. After the INT-01 fix, the test still passes. This creates a false sense of completeness.

**Why it happens:** The test was written to verify Phase 4 requirements which did not include verifying JTI blacklisting at the HTTP level.

**How to avoid:** A new, separate test (e.g., `test_payment_failed_blacklists_access_token`) must be written that:
1. Captures the access token JTI from `UserSession` after login
2. Fires the webhook
3. Asserts the JTI exists in Redis under `auth:blacklist:jti:{jti}`
4. Asserts an HTTP request with the original token is rejected

### Pitfall 3: The INT-02 fix changes what HTTP 401/403 a non-admin superuser gets

**What goes wrong:** Before the fix, a superuser with a regular token gets HTTP 403 (SUPERUSER_REQUIRED) because `require_superuser` passes authentication but `is_superuser` is True — wait, actually the superuser would PASS the old check. The point is: after INT-02 fix, a regular-token superuser gets HTTP 401 (InvalidTokenError — wrong audience) because `decode_admin_access_token` rejects the regular token.

**Why it matters:** The test for INT-02 must assert the correct status code. The existing test `test_nonsuperadmin_cannot_create_plan` sends a non-superuser regular token and expects 403. After the fix, this test gets 401 (wrong audience) instead of 403. The test must be updated or a new test added that:
1. Logs in via `/auth/login` (regular audience token) as a superuser
2. Attempts billing admin endpoint
3. Expects 401 (not 403)

**Warning signs:** `test_nonsuperadmin_cannot_create_plan` failing after INT-02 fix with "Expected 403, got 401".

### Pitfall 4: Conftest `mock_get_arq_pool` patches need to be verified for the new E2E test

**What goes wrong:** `_handle_payment_failed` calls `get_arq_pool()` to enqueue payment failure emails. The conftest patches `wxcode_adm.tasks.worker.get_arq_pool`. The new integration test calls `process_stripe_event` directly (same as the existing `test_webhook_payment_failed`), so the existing mock infrastructure handles this correctly.

**How to avoid:** Use the same test structure as `test_webhook_payment_failed` (call `process_stripe_event` via the `ctx = {"session_maker": test_db}` pattern). Do not call the webhook HTTP endpoint directly (that requires Stripe signature verification).

### Pitfall 5: `UserSession` rows only exist when a user has logged in via HTTP

**What goes wrong:** In the E2E test, if you query `UserSession` directly via `test_db` after the fix fires, you need the user to have actually logged in via the HTTP client (not seeded directly into DB) so that `UserSession` rows are created by the normal `_issue_tokens` flow in `auth/service.py`.

**Why it happens:** `UserSession` is created inside `_issue_tokens` alongside `RefreshToken`. If you seed a user directly into `test_db` without going through the HTTP login flow, no `UserSession` rows exist.

**How to avoid:** Use `_signup_verify_login` helper (which calls the HTTP login endpoint) before triggering the webhook. The existing `test_webhook_payment_failed` already does this — the new E2E test must follow the same setup pattern.

---

## Code Examples

### Fix for INT-01: Correct `_handle_payment_failed` token blacklisting

```python
# backend/src/wxcode_adm/billing/service.py — _handle_payment_failed
# Replace lines 865-883 (the token revocation section):

    if user_ids:
        # Blacklist all active access token JTIs in Redis
        from wxcode_adm.auth.models import UserSession  # noqa: PLC0415
        from wxcode_adm.auth.service import blacklist_jti  # noqa: PLC0415

        session_result = await db.execute(
            select(UserSession.access_token_jti).where(
                UserSession.user_id.in_(user_ids)
            )
        )
        jtis = [row[0] for row in session_result.fetchall()]
        for jti in jtis:
            await blacklist_jti(redis_client, jti)

        # Delete all refresh tokens for these users
        tokens_result = await db.execute(
            select(RefreshToken).where(RefreshToken.user_id.in_(user_ids))
        )
        refresh_tokens = list(tokens_result.scalars().all())
        for token in refresh_tokens:
            await db.delete(token)
```

Note: `redis_client` is already lazily imported at line 835 (`from wxcode_adm.common.redis_client import redis_client`). The new `UserSession` and `blacklist_jti` imports must be added inside the `if user_ids:` block, following the same lazy-import style.

### Fix for INT-02: Replace `require_superuser` with `require_admin` in billing router

```python
# backend/src/wxcode_adm/billing/router.py — top of file, add import:
from wxcode_adm.admin.dependencies import require_admin  # noqa: PLC0415

# Then for each of the 5 admin endpoints, replace:
#   user: Annotated[User, Depends(require_superuser)]
# with:
#   user: Annotated[User, Depends(require_admin)]
#
# For the two GET endpoints that use _ (unused user):
#   _: Annotated[User, Depends(require_superuser)]
# with:
#   _: Annotated[User, Depends(require_admin)]
```

After the replacement, the local `require_superuser` function (lines 46-60) and its `ForbiddenError` import become dead code. They can be removed (cleaner) or left in place (safe). Removing is preferred.

### New E2E Integration Test Structure

```python
# backend/tests/test_billing.py — new test for flow #8
async def test_payment_failed_blacklists_access_token(client):
    """
    E2E flow #8: payment failure webhook → subscription PAST_DUE →
    access token JTI blacklisted → member blocked on platform endpoints.
    """
    c, redis, app, test_db = client
    paid_plan_id = await _seed_paid_plan(test_db)

    # 1. User logs in via HTTP (creates UserSession with access_token_jti)
    token, _ = await _signup_verify_login(c, redis, "flow8_test@test.com")
    tenant_id = await _create_workspace(c, token, "Flow 8 Test")

    # 2. Verify user can access platform endpoint before webhook
    r = await c.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 200

    # 3. Activate subscription (so payment_failed finds a stripe_subscription_id)
    from wxcode_adm.billing.service import process_stripe_event
    ctx = {"session_maker": test_db}
    await process_stripe_event(
        ctx, "evt_flow8_checkout", "checkout.session.completed",
        {
            "customer": "cus_flow8",
            "subscription": "sub_flow8_1",
            "metadata": {"tenant_id": tenant_id, "plan_id": str(paid_plan_id)},
        },
    )

    # 4. Capture the JTI from UserSession before the webhook fires
    from sqlalchemy import select
    from wxcode_adm.auth.models import UserSession
    import uuid
    async with test_db() as session:
        result = await session.execute(
            select(UserSession).join(
                # join via user_id — find session for our user
            )
        )
        # Alternative: query UserSession by user_id from TenantMembership
        # The simplest approach: get all UserSession rows for the tenant members

    # 5. Fire payment_failed webhook
    await process_stripe_event(
        ctx, "evt_flow8_failed", "invoice.payment_failed",
        {"subscription": "sub_flow8_1"},
    )

    # 6. Verify subscription status is PAST_DUE
    from wxcode_adm.billing.models import SubscriptionStatus, TenantSubscription
    async with test_db() as session:
        sub = (await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )).scalar_one()
        assert sub.status == SubscriptionStatus.PAST_DUE

    # 7. Verify the access token is now rejected (blacklisted JTI)
    r = await c.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code in (401, 403), (
        f"Expected 401/403 (blacklisted token), got {r.status_code}: {r.text}"
    )
```

**Important note on step 4:** The planner needs to determine the precise query to get `UserSession.access_token_jti` for the test user. The cleanest approach is:
- After login, decode the access token to extract the JTI (JWT is RS256 — use `auth.jwt.decode_access_token` or check the Redis key pattern `auth:blacklist:jti:{jti}` after the webhook fires)
- Or: Query `UserSession` filtered by `user_id` (need to look up user by email)

The test can also verify Redis directly:
```python
# Check that some key matching auth:blacklist:jti:* was written
keys = []
async for k in redis.scan_iter("auth:blacklist:jti:*"):
    keys.append(k)
assert len(keys) > 0, "Expected at least one JTI blacklisted in Redis"
```

---

## State of the Art

| Old Approach | Current Approach | Phase Introduced | Impact on Phase 11 |
|--------------|-----------------|------------------|--------------------|
| Regular JWT `is_superuser` check | Admin-audience JWT `require_admin` | Phase 8 | `billing_admin_router` was never updated to use Phase 8 pattern — INT-02 |
| Manual Redis `setex` for token blacklisting | `blacklist_jti()` helper | Phase 7 (added in 07-03) | `_handle_payment_failed` uses the old pattern — INT-01 |

**Deprecated patterns in this codebase:**
- Direct `redis.setex(f"auth:blacklist:jti:{something}", ...)` calls in service code: replaced by `blacklist_jti(redis, jti)` helper. The `_handle_payment_failed` function is the last remaining instance.
- Local `require_superuser` in billing router: superseded by `require_admin` from `admin/dependencies.py`.

---

## Open Questions

1. **Handling users with no `UserSession` rows (e.g., very old sessions pre-Phase-7)**
   - What we know: `UserSession` was introduced in Phase 7. Any access tokens issued before Phase 7 have no corresponding `UserSession` row; their JTIs cannot be blacklisted this way. In practice this does not matter for this phase since Phase 7 is already shipped and all new logins create `UserSession` rows.
   - What's unclear: Whether to add a defensive comment in the code acknowledging this edge case.
   - Recommendation: Add a brief comment noting that sessions without `UserSession` rows (pre-Phase-7) are not explicitly blacklisted but their refresh tokens are still deleted, preventing re-issuance. No code change needed.

2. **Whether `test_nonsuperadmin_cannot_create_plan` must be updated**
   - What we know: This test sends a regular-audience token for a non-superuser and expects HTTP 403. After INT-02 fix, `require_admin` calls `decode_admin_access_token` which will reject the regular-audience token before checking `is_superuser` — returning HTTP 401 (InvalidTokenError) instead of 403 (ForbiddenError).
   - What's unclear: Whether the test should be updated to expect 401, or whether a separate test for "regular-superuser gets 401" should be added.
   - Recommendation: Update `test_nonsuperadmin_cannot_create_plan` to accept `status_code in (401, 403)` OR change expected status to 401 and rename the test to clarify it tests JWT audience rejection.

---

## Sources

### Primary (HIGH confidence)

All findings are based on direct codebase inspection — no external documentation required.

- `backend/src/wxcode_adm/billing/service.py` — `_handle_payment_failed` bug at lines 872-883
- `backend/src/wxcode_adm/admin/service.py:suspend_tenant` — canonical JTI blacklisting pattern at lines 445-459
- `backend/src/wxcode_adm/admin/service.py:force_password_reset` — second JTI blacklisting instance at lines 903-907
- `backend/src/wxcode_adm/auth/service.py:blacklist_jti` — the correct helper at lines 361-377
- `backend/src/wxcode_adm/auth/service.py:is_token_blacklisted` — Redis key format at lines 380-382
- `backend/src/wxcode_adm/billing/router.py` — `require_superuser` bug at lines 46-60
- `backend/src/wxcode_adm/admin/dependencies.py:require_admin` — correct admin dependency at lines 52-107
- `backend/tests/test_billing.py:test_webhook_payment_failed` — existing (incomplete) test at lines 387-429
- `backend/tests/test_super_admin.py:test_suspend_tenant_invalidates_sessions` — reference test pattern at lines 226-248
- `backend/tests/conftest.py` — FakeRedis + arq mock infrastructure at lines 262-268
- `.planning/v1.0-MILESTONE-AUDIT.md` — INT-01 and INT-02 gap definitions

### Secondary (MEDIUM confidence)

- None needed — all information derived from direct code inspection.

### Tertiary (LOW confidence)

- None.

---

## Metadata

**Confidence breakdown:**
- Bug root cause (INT-01): HIGH — confirmed by reading both the broken code and the correct pattern side-by-side
- Bug root cause (INT-02): HIGH — confirmed by reading `require_superuser` vs `require_admin` source
- Fix correctness: HIGH — fixes mirror existing patterns used in 3+ other locations
- Test strategy: HIGH — existing test infrastructure directly supports the required assertions
- Side effects: MEDIUM — the `test_nonsuperadmin_cannot_create_plan` status code change (403→401) is expected but needs verification during implementation

**Research date:** 2026-03-02
**Valid until:** Stable — this is all internal codebase analysis, not external dependencies
