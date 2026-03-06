# Phase 9: MFA-wxcode Redirect Fix - Research

**Researched:** 2026-02-27
**Domain:** FastAPI / Python async service — cross-phase integration fix
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| USER-04 | User is redirected to wxcode with access token after login | `get_redirect_url` + `create_wxcode_code` already implemented and tested for non-MFA path; fix extends it to MFA path |
| AUTH-11 | User is prompted for TOTP code on login when MFA enabled | MFA two-stage flow fully implemented; fix ensures the completed MFA flow produces the same wxcode redirect output as the non-MFA path |
</phase_requirements>

---

## Summary

The gap is precisely identified and extremely narrow. `mfa_verify` in `backend/src/wxcode_adm/auth/service.py` completes TOTP/backup-code verification and calls `_issue_tokens`, then returns a plain dict with only `access_token`, `refresh_token`, and optionally `device_token`. It never calls `get_redirect_url` or `create_wxcode_code`. The router's `mfa_verify` endpoint checks `if result.get("wxcode_redirect_url")` (line 338) and includes the redirect fields when present — so the wire-up in the router is already correct. Only the service function is incomplete.

The non-MFA login path in `auth/router.py` establishes the exact pattern to replicate: after `_issue_tokens` resolves, load the user object (already loaded in `mfa_verify`), call `get_redirect_url(db, user)`, and if a URL is returned, call `create_wxcode_code(redis, str(user.id), access_token, refresh_token)`. The fix is ~8 lines of Python inside the `mfa_verify` service function.

The integration test must mirror the existing `test_wxcode_code_exchange` in `test_user_account.py`, but use the MFA login path: create a user with MFA enabled, create a workspace, set `tenant.wxcode_url`, complete the two-stage login (`POST /auth/login` → `POST /auth/mfa/verify`), and assert that the `/mfa/verify` response contains `wxcode_redirect_url` and `wxcode_code`; then exchange the code and confirm single-use enforcement.

**Primary recommendation:** Add ~8 lines to `mfa_verify` in `auth/service.py` after `_issue_tokens`, mirroring the login-handler pattern exactly. Add one integration test to `test_oauth_mfa.py` covering the MFA → wxcode redirect → exchange flow.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | project-locked | HTTP routing | Already used project-wide |
| SQLAlchemy async | project-locked | ORM / DB access | All service functions use AsyncSession |
| Redis (via fakeredis in tests) | project-locked | wxcode code storage | `create_wxcode_code` / `exchange_wxcode_code` already use Redis |
| pyotp | project-locked | TOTP generation in tests | Already used in `test_oauth_mfa.py` |
| pytest-asyncio | project-locked | async test runner | All existing tests use this pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlalchemy `select` | project-locked | Query Tenant/TenantMembership | Used inside `get_redirect_url` |
| `secrets` (stdlib) | project-locked | Token generation | Already used in `create_wxcode_code` |
| `json` (stdlib) | project-locked | Serialise wxcode payload | Already used in `create_wxcode_code` |

### Alternatives Considered

None — this is a targeted bug fix with zero new libraries. All tooling is already in place.

**Installation:** No new packages required.

---

## Architecture Patterns

### Existing Service Function Structure

The fix lives entirely inside `mfa_verify` in `auth/service.py`. The function already has the user object loaded (step 2 of the flow), so no extra DB lookup is needed.

```
mfa_verify flow (current):
  1. Redis GET auth:mfa_pending:{mfa_token}  → get user_id
  2. DB SELECT User WHERE id = user_id        → user object (already loaded)
  3. TOTP replay check
  4. Verify TOTP or backup code
  5. Redis DELETE auth:mfa_pending:{mfa_token}
  6. _issue_tokens(db, redis, user)           → TokenResponse
  7. Optionally create_trusted_device
  8. Return result dict

Fix adds between step 6 and 8:
  6a. get_redirect_url(db, user)             → (wxcode_url, tenant_id)
  6b. if wxcode_url: create_wxcode_code(redis, str(user.id), access_token, refresh_token)
  6c. add wxcode_redirect_url + wxcode_code to result dict
  6d. if tenant_id: update user.last_used_tenant_id = tenant_id
```

### Pattern 1: Existing Login Handler (non-MFA path) — Mirror This Exactly

**What:** The non-MFA login in `auth/router.py` (lines 259–275) calls `get_redirect_url` then `create_wxcode_code` after tokens are issued.
**When to use:** Any auth path that issues tokens and should offer wxcode redirect.

```python
# Source: backend/src/wxcode_adm/auth/router.py lines 259-275
# Phase 7: wxcode redirect — resolve tenant wxcode_url for one-time code
wxcode_redirect_url: str | None = None
wxcode_code: str | None = None
if user_obj:
    redirect_url, tenant_id = await service.get_redirect_url(db, user_obj)
    if redirect_url:
        wxcode_code = await service.create_wxcode_code(
            redis,
            str(user_obj.id),
            result["access_token"],
            result["refresh_token"],
        )
        wxcode_redirect_url = redirect_url
        # Update last_used_tenant_id for future redirect targeting (locked decision)
        if tenant_id is not None:
            user_obj.last_used_tenant_id = tenant_id
```

**Key difference for `mfa_verify`:** The service function, not the router, must call these helpers because the router just checks `result.get("wxcode_redirect_url")`. The user object is already in scope within `mfa_verify` — no extra lookup needed.

### Pattern 2: Router Already Wired Correctly

The `mfa_verify` router endpoint at `auth/router.py` lines 333–340 already checks `result.get("wxcode_redirect_url")` and includes both fields in the response if present:

```python
# Source: backend/src/wxcode_adm/auth/router.py lines 333-341
# Phase 7: wxcode redirect — include if user has tenant with wxcode_url
if result.get("wxcode_redirect_url"):
    response_data["wxcode_redirect_url"] = result["wxcode_redirect_url"]
    response_data["wxcode_code"] = result.get("wxcode_code")
```

No router changes needed. Only the service function must be fixed.

### Pattern 3: Integration Test Structure (Mirror `test_wxcode_code_exchange`)

**What:** Existing test in `test_user_account.py` lines 351–411 verifies the non-MFA wxcode redirect flow. The new test mirrors it but uses the MFA login path.
**When to use:** Any new MFA-path wxcode test.

```python
# Source: backend/tests/test_user_account.py lines 351-411 (reference pattern)
# Adapted for MFA path:

@pytest.mark.asyncio
async def test_mfa_verify_includes_wxcode_redirect(client):
    """After MFA verify with tenant wxcode_url set, response includes
    wxcode_redirect_url and wxcode_code; code can be exchanged for tokens;
    code is single-use."""
    c, redis, app, test_db = client

    # 1. Create user with MFA enabled (use existing helper)
    user, secret = await _create_user_with_mfa(test_db, "mfawxcode@test.com")

    # 2. Create workspace for user (need tenant membership for get_redirect_url)
    #    Must use HTTP flow since user has no password-based login record.
    #    Alternative: create tenant + membership directly in DB (faster, no arq)
    async with test_db() as session:
        from wxcode_adm.tenants.models import Tenant, TenantMembership, MemberRole
        tenant = Tenant(name="MFA Wxcode Tenant", wxcode_url="https://app.wxcode.io")
        session.add(tenant)
        await session.flush()
        membership = TenantMembership(
            user_id=user.id, tenant_id=tenant.id, role=MemberRole.owner
        )
        session.add(membership)
        await session.commit()

    # 3. Login → get mfa_token
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "mfawxcode@test.com", "password": "securepass"},
    )
    assert r.status_code == 200
    mfa_token = r.json()["mfa_token"]

    # 4. MFA verify → assert wxcode fields present
    code = pyotp.TOTP(secret).now()
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": code},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("wxcode_redirect_url") == "https://app.wxcode.io"
    assert data.get("wxcode_code") is not None

    # 5. Exchange code → tokens
    exchange_resp = await c.post(
        "/api/v1/auth/wxcode/exchange",
        json={"code": data["wxcode_code"]},
    )
    assert exchange_resp.status_code == 200
    assert "access_token" in exchange_resp.json()

    # 6. Code is single-use
    exchange_resp2 = await c.post(
        "/api/v1/auth/wxcode/exchange",
        json={"code": data["wxcode_code"]},
    )
    assert exchange_resp2.status_code == 401
```

### Anti-Patterns to Avoid

- **Moving logic to router instead of service:** The router already delegates wxcode logic to the service result dict. Adding wxcode calls in the router (duplicate of login handler) creates two divergent code paths. The fix belongs in the service function.
- **Double lookup of user in router:** The router's `mfa_verify` handler has no `user_obj` in scope (it only gets the result dict from the service). Do NOT refactor the router handler to lookup the user — this increases complexity unnecessarily. Keep the fix in the service.
- **Using HTTP onboarding to create workspace in the test:** `_create_user_with_mfa` creates a user without a password hash accessible through HTTP, making the HTTP onboarding flow awkward. Create the Tenant and TenantMembership directly in the DB inside the test.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| One-time code generation | Custom UUID/random system | `create_wxcode_code` in `auth/service.py` | Already implemented with correct TTL, Redis key schema, and atomic GETDEL exchange |
| Tenant URL lookup | Inline DB queries | `get_redirect_url` in `auth/service.py` | Already handles `last_used_tenant_id` preference, fallback to most-recent membership, nil cases |
| TOTP code generation in tests | Custom pyotp wrapper | `pyotp.TOTP(secret).now()` directly | Already used in all existing MFA tests |

**Key insight:** Every piece needed exists. Phase 9 is wiring existing functions together, not building anything new.

---

## Common Pitfalls

### Pitfall 1: Forgetting `last_used_tenant_id` Update

**What goes wrong:** `get_redirect_url` returns `(url, tenant_id)`. If `tenant_id` is not written back to `user.last_used_tenant_id`, the redirect targeting preference is not saved for subsequent logins.
**Why it happens:** The non-MFA path in the router (lines 273–274) does this update. Copying only the `get_redirect_url` + `create_wxcode_code` calls without including the `user_obj.last_used_tenant_id = tenant_id` assignment misses this.
**How to avoid:** Copy the complete block from the login handler, including the `last_used_tenant_id` update.
**Warning signs:** Tests pass but repeat logins don't use the last-used tenant preference.

### Pitfall 2: Not Awaiting `db.flush()` After Tenant Creation in Tests

**What goes wrong:** Creating Tenant + TenantMembership directly in the DB within a test session requires `await session.flush()` before adding TenantMembership (to ensure the Tenant has a PK). Without flush, the FK constraint fails.
**Why it happens:** SQLAlchemy async sessions don't auto-flush before FK-constrained inserts within the same transaction.
**How to avoid:** `await session.flush()` after adding the Tenant, before adding TenantMembership.
**Warning signs:** `IntegrityError: FOREIGN KEY constraint failed` during test setup.

### Pitfall 3: Test User Has No Tenant Membership

**What goes wrong:** `_create_user_with_mfa` creates only a `User` with no `TenantMembership`. `get_redirect_url` checks `last_used_tenant_id` (None) then falls back to most-recent TenantMembership — if none exists, it returns `(None, None)`. The wxcode fields will be absent even after the fix.
**Why it happens:** Test setup omits the membership step.
**How to avoid:** Always create a Tenant with `wxcode_url` set AND a TenantMembership linking the user to that tenant in the test setup.
**Warning signs:** Test asserts `wxcode_redirect_url is not None` but gets `None` — the fix appears to not work.

### Pitfall 4: Confusing Where the Fix Lives

**What goes wrong:** The comment in `auth/router.py` at line 333 says "Note: mfa_verify does not have access to the user object here, but the user_id is embedded in the mfa_token. We resolve it in the response. wxcode_redirect_url and wxcode_code are passed through from service result if present (service resolves them for completeness)." This note was aspirational — the service never implemented it. A developer might misread this as "the service already does this."
**Why it happens:** The comment describes the intended design (service does it) but the implementation was incomplete.
**How to avoid:** Fix is in `mfa_verify` in `auth/service.py` only. Remove or update the misleading comment in the router when fixing.
**Warning signs:** Fixing only the router (adding wxcode calls there) while not touching the service.

### Pitfall 5: Backup-Code Path Skipped in Tests

**What goes wrong:** Only testing TOTP verification for the wxcode redirect, missing the backup code verification path.
**Why it happens:** Backup code test is more complex to set up.
**How to avoid:** The success criteria require "the one-time wxcode_code from MFA verify can be exchanged" — the TOTP path is sufficient for SC2. One test covering TOTP is enough. A second test for backup codes is optional (nice-to-have, not required by success criteria).

---

## Code Examples

### Service Fix — mfa_verify (after `_issue_tokens` call)

```python
# Source: auth/service.py — mfa_verify function
# After step 6 (_issue_tokens), add:

result: dict = {
    "access_token": token_response.access_token,
    "refresh_token": token_response.refresh_token,
}

# Phase 9: wxcode redirect — same pattern as non-MFA login handler
redirect_url, tenant_id = await get_redirect_url(db, user)
if redirect_url:
    wxcode_code = await create_wxcode_code(
        redis,
        str(user.id),
        token_response.access_token,
        token_response.refresh_token,
    )
    result["wxcode_redirect_url"] = redirect_url
    result["wxcode_code"] = wxcode_code
    if tenant_id is not None:
        user.last_used_tenant_id = tenant_id
```

### Test Helper — Direct DB Tenant Setup

```python
# Source: test_user_account.py (reference pattern adapted for MFA test)
# Creates tenant with wxcode_url and membership directly in test DB

async with test_db() as session:
    from wxcode_adm.tenants.models import Tenant, TenantMembership, MemberRole
    tenant = Tenant(name="MFA Wxcode Tenant", wxcode_url="https://app.wxcode.io")
    session.add(tenant)
    await session.flush()  # Required: assign tenant.id before FK reference
    membership = TenantMembership(
        user_id=user.id,
        tenant_id=tenant.id,
        role=MemberRole.owner,
    )
    session.add(membership)
    await session.commit()
```

### Updating `last_used_tenant_id`

```python
# Source: auth/router.py lines 272-274 (reference pattern)
# Update last_used_tenant_id to persist tenant preference:
if tenant_id is not None:
    user.last_used_tenant_id = tenant_id
# Note: user is already loaded in mfa_verify service function (step 2)
# The session will commit this update when the request completes.
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| wxcode redirect only for non-MFA | wxcode redirect for ALL auth paths | Phase 9 | MFA users get same seamless redirect as non-MFA users |

**Deprecated/outdated:**
- The misleading comment in `auth/router.py` lines 333–336 ("Note: mfa_verify does not have access to the user object here...") should be removed or replaced with accurate documentation after the fix is applied.

---

## Open Questions

1. **Should the router comment be updated or removed?**
   - What we know: The comment at `router.py:333–336` was written when the design intended the service to handle it, but the implementation was never completed.
   - What's unclear: Whether to simply remove the comment or replace with a brief accurate note.
   - Recommendation: Remove the four-line "Note:" comment block entirely — the code becomes self-documenting once the service is fixed.

2. **Should a second test cover backup-code MFA → wxcode redirect?**
   - What we know: Success criteria SC1 and SC2 specify only that MFA verify includes wxcode fields and that the code can be exchanged.
   - What's unclear: Whether the TOTP path alone satisfies "MFA verify" or if backup code path must be separately tested.
   - Recommendation: One TOTP-path test satisfies both success criteria. A backup-code variant is optional; the code path after `_issue_tokens` is identical regardless of TOTP vs backup, so TOTP coverage is sufficient.

3. **Does `user.last_used_tenant_id` update require `await db.flush()`?**
   - What we know: The non-MFA login handler in the router does NOT call explicit flush — the session commit at request end persists it. The `mfa_verify` service function also relies on the request-level session commit.
   - What's unclear: Whether `user.last_used_tenant_id = tenant_id` inside the service function is picked up by the session before commit.
   - Recommendation: No explicit flush needed. SQLAlchemy tracks dirty objects in the session; the commit at request teardown (via `override_get_session` in conftest) will persist the update. This is the existing pattern used in the non-MFA login handler.

---

## Sources

### Primary (HIGH confidence)

- `backend/src/wxcode_adm/auth/service.py` — `mfa_verify` (lines 1599–1723), `_issue_tokens` (874–939), `get_redirect_url` (1007–1052), `create_wxcode_code` (947–982) — direct code inspection
- `backend/src/wxcode_adm/auth/router.py` — `mfa_verify` endpoint (lines 284–355), login handler wxcode block (lines 259–281) — direct code inspection
- `backend/src/wxcode_adm/auth/schemas.py` — `LoginResponse`, `MfaVerifyRequest` — direct code inspection
- `.planning/v1.0-MILESTONE-AUDIT.md` — "Integration Gap: MFA → wxcode Redirect (CRITICAL)" section — audit document
- `backend/tests/test_oauth_mfa.py` — MFA test helpers and existing SC4 tests (lines 628–785) — direct code inspection
- `backend/tests/test_user_account.py` — `test_wxcode_code_exchange` (lines 350–411) — reference test pattern
- `backend/tests/conftest.py` — fixture structure, session management pattern — direct code inspection

### Secondary (MEDIUM confidence)

None needed — all findings come from direct codebase inspection.

### Tertiary (LOW confidence)

None.

---

## Metadata

**Confidence breakdown:**
- Bug location: HIGH — confirmed by audit document + direct code reading; `mfa_verify` in `service.py` never calls `get_redirect_url` or `create_wxcode_code`
- Fix implementation: HIGH — exact pattern exists in `auth/router.py` login handler; direct copy with minor adaptation
- Test pattern: HIGH — `test_wxcode_code_exchange` in `test_user_account.py` is the direct reference; existing MFA helpers (`_create_user_with_mfa`, `pyotp.TOTP`) are in place
- No new infrastructure: HIGH — zero new libraries, zero new endpoints, zero schema changes required

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (stable — no external dependencies, pure internal code fix)
