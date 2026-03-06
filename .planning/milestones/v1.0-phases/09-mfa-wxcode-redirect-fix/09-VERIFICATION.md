---
phase: 09-mfa-wxcode-redirect-fix
verified: 2026-02-27T20:30:00Z
status: passed
score: 3/3 must-haves verified
re_verification: false
---

# Phase 9: MFA-wxcode Redirect Fix Verification Report

**Phase Goal:** MFA-authenticated users receive the same wxcode redirect URL and one-time code as non-MFA users, ensuring all login paths lead to seamless wxcode handoff
**Verified:** 2026-02-27T20:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After TOTP verification via POST /auth/mfa/verify, the response includes `wxcode_redirect_url` and `wxcode_code` when the user's tenant has a `wxcode_url` configured | VERIFIED | `service.py` lines 1718-1730: `get_redirect_url` and `create_wxcode_code` called inside `mfa_verify` after `_issue_tokens`; result dict populated with both fields; router passthrough at `router.py:338-340` confirmed |
| 2 | The one-time `wxcode_code` from MFA verify can be exchanged at the wxcode exchange endpoint and returns a valid access token | VERIFIED | Integration test `test_mfa_verify_includes_wxcode_redirect` (line 829-835) performs the exchange and asserts 200 + `access_token` in response; exchange endpoint at `router.py:500` calls `service.exchange_wxcode_code(redis, body.code)` |
| 3 | The `wxcode_code` is single-use — a second exchange attempt returns 401 | VERIFIED | Integration test lines 837-842 assert `exchange_resp2.status_code == 401`; enforced by existing `exchange_wxcode_code` Redis GETDEL logic (no new code needed) |

**Score:** 3/3 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/src/wxcode_adm/auth/service.py` | `mfa_verify` function with wxcode redirect support; contains `get_redirect_url` and `create_wxcode_code` calls | VERIFIED | Lines 1718-1730 contain the Phase 9 block. Both helper calls are present: `await get_redirect_url(db, user)` at line 1719, `await create_wxcode_code(...)` at lines 1721-1726. `result["wxcode_redirect_url"]` and `result["wxcode_code"]` assigned at lines 1727-1728. `user.last_used_tenant_id` updated at line 1730. |
| `backend/tests/test_oauth_mfa.py` | Integration test `test_mfa_verify_includes_wxcode_redirect` proving full MFA -> wxcode redirect -> exchange flow | VERIFIED | Test at line 788 is substantive (58 lines added per commit `c58d8a0`). Covers: tenant setup with `wxcode_url`, MFA login two-stage flow, assertion of both wxcode fields in response, successful exchange, single-use 401 enforcement. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `service.py:mfa_verify` | `service.py:get_redirect_url` | `await get_redirect_url(db, user)` after `_issue_tokens` | WIRED | Line 1719: `redirect_url, tenant_id = await get_redirect_url(db, user)` — both functions in same file, direct call confirmed |
| `service.py:mfa_verify` | `service.py:create_wxcode_code` | `await create_wxcode_code(...)` when `redirect_url` exists | WIRED | Lines 1721-1726: called inside `if redirect_url:` guard — correct conditional pattern matching non-MFA login path |
| `router.py:mfa_verify endpoint` | `result dict wxcode fields` | `result.get("wxcode_redirect_url")` passthrough | WIRED | Line 338: `if result.get("wxcode_redirect_url"):` — lines 339-340 copy both fields into `response_data`; confirmed existing pre-Phase-9 |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| USER-04 | 09-01-PLAN.md | User is redirected to wxcode with access token after login | SATISFIED (strengthened) | Previously satisfied by Phase 7 for non-MFA path. Phase 9 extends the same redirect pattern to the MFA login path via `mfa_verify`. REQUIREMENTS.md marks USER-04 as Complete (Phase 7); Phase 9 closes the MFA-path gap. |
| AUTH-11 | 09-01-PLAN.md | User is prompted for TOTP code on login when MFA enabled | SATISFIED (strengthened) | Previously satisfied by Phase 6 for the MFA challenge/verify flow. Phase 9 ensures the completed MFA verify response includes the wxcode handoff fields, making the MFA login path fully equivalent to the non-MFA path end-to-end. REQUIREMENTS.md marks AUTH-11 as Complete (Phase 6). |

**Orphaned requirements:** None. No additional Phase 9 requirement IDs appear in REQUIREMENTS.md that are not declared in the plan's `requirements` field.

**Note on requirement ownership:** REQUIREMENTS.md maps USER-04 to Phase 7 and AUTH-11 to Phase 6 — both already marked Complete. Phase 9 "strengthens" both (per ROADMAP.md language) by extending the wxcode redirect to the MFA login path. This is a gap-closure contribution, not primary ownership; the requirements are already satisfied and Phase 9 makes the implementation more complete.

---

### Anti-Patterns Found

None detected in the modified lines of `service.py` (lines 1718-1730) or `test_oauth_mfa.py` (lines 788-843). No TODO/FIXME comments, no stub returns, no empty handlers, no placeholder text.

---

### Human Verification Required

None. All three observable truths are verified programmatically via:

1. Direct code inspection of `service.py` (the fix block exists, is substantive, and calls both helper functions)
2. Direct code inspection of the router passthrough (already wired pre-Phase-9)
3. Existence and content of the integration test covering the full flow including exchange and single-use enforcement
4. Verified commit hashes `81ad93d` (service.py patch) and `c58d8a0` (integration test) confirm both changes are committed to the repository

The integration test itself asserts all three truths end-to-end. The test is not a stub: it performs real HTTP calls through the full FastAPI + async SQLAlchemy + fakeredis test stack, per the existing test infrastructure pattern confirmed by the 148-test suite count.

---

### Gaps Summary

No gaps. All three must-have truths are verified. Both artifacts exist, are substantive (not stubs), and are wired into the execution path. Both key links are confirmed. Both requirement IDs declared in the plan's frontmatter are accounted for in REQUIREMENTS.md and the implementation satisfies what Phase 9 claims to contribute to each. No blocker anti-patterns found.

The implementation precisely matches the plan's design:

- `mfa_verify` in `service.py` now calls `get_redirect_url` and `create_wxcode_code` after `_issue_tokens` — between step 6 (tokens) and step 7 (trusted device), as the plan specified
- The router required zero changes (confirmed): `result.get("wxcode_redirect_url")` passthrough at `router.py:338` was already in place
- The integration test covers the complete MFA -> tenant wxcode_url -> one-time code -> exchange -> single-use enforcement chain
- `MemberRole.OWNER` (uppercase) used in the test, matching the enum definition — the plan's pitfall warning was heeded
- `await session.flush()` called before TenantMembership creation in the test — the FK constraint pitfall avoided
- `user.last_used_tenant_id` update included in the service fix — the redirect targeting preference pitfall avoided

---

_Verified: 2026-02-27T20:30:00Z_
_Verifier: Claude (gsd-verifier)_
