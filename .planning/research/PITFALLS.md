# Pitfalls Research

**Domain:** SaaS Authentication / Billing / Multi-Tenancy Platform (WXCODE ADM)
**Researched:** 2026-02-22
**Confidence:** HIGH (multiple authoritative sources: OWASP, PortSwigger, Stripe docs, MongoDB docs, Auth0, CVE databases)

---

## Critical Pitfalls

### Pitfall 1: JWT Algorithm Confusion (RS256 → HS256 Downgrade)

**What goes wrong:**
An attacker changes the JWT header `alg` field from `RS256` to `HS256` and signs a forged token using the RSA public key as the HMAC secret. If the server blindly trusts the `alg` claim from the token, the verification passes — granting the attacker the ability to impersonate any user, including super-admins. This is one of the most exploited JWT vulnerabilities.

**Why it happens:**
Developers use generic JWT libraries that accept the `alg` value from the incoming token header rather than enforcing a fixed algorithm at the server configuration level. The public key is "public" so developers underestimate how it can be weaponized when an algorithm switch is allowed.

**How to avoid:**
Never trust the `alg` field from the incoming JWT. Enforce the algorithm at library configuration time, not at decode time. In Python with `python-jose` or `PyJWT`, always pass `algorithms=["RS256"]` explicitly. Never pass a list containing both asymmetric and symmetric algorithms. Store the public key as a proper RSAPublicKey object, not as a raw string that could be coerced into an HMAC secret.

```python
# WRONG - never do this
payload = jwt.decode(token, public_key)  # trusts token's alg field

# CORRECT
payload = jwt.decode(token, public_key, algorithms=["RS256"])  # enforces RS256 only
```

**Warning signs:**
- JWT library is initialized without explicit `algorithms` parameter
- Library accepts a list like `algorithms=["RS256", "HS256"]`
- `alg` is read from token headers in application code before verification
- Public key is stored/handled as a raw PEM string rather than a parsed key object

**Phase to address:** Authentication foundation phase (Phase 1 / Core Auth). Must be locked down before any endpoints go live.

---

### Pitfall 2: Cross-Tenant Data Leakage via Missing `tenant_id` Filter

**What goes wrong:**
In MongoDB logical multi-tenancy, every query MUST include a `tenant_id` filter. A single endpoint handler that forgets to scope by `tenant_id` — even during a quick hotfix, a new developer contribution, or a background job — leaks data across all tenants. This is the most common and most catastrophic multi-tenancy bug: it is invisible until exploited.

**Why it happens:**
The responsibility for applying `tenant_id` is distributed across every query in the application. There is no database-level enforcement (unlike row-level security in Postgres). Any query helper, aggregation pipeline, or background job that omits `tenant_id` is a silent data breach waiting to happen. Beanie ODM provides no automatic tenant scoping middleware out of the box.

**How to avoid:**
Implement a mandatory query wrapper or Beanie document base class that automatically injects `tenant_id` into all find/update/delete operations. Make it architecturally impossible to query without tenant context. For example, create a `TenantDocument` base class that overrides `find()` to require a `tenant_id` parameter and inject it automatically. Enforce via code review rules and automated tests that query every endpoint without a tenant token and verify it returns 403 or empty results — never another tenant's data.

```python
# Pattern: Base class that enforces tenant scoping
class TenantDocument(Document):
    tenant_id: str

    @classmethod
    def find_for_tenant(cls, tenant_id: str, *args, **kwargs):
        return cls.find(cls.tenant_id == tenant_id, *args, **kwargs)
    # Override find() to require tenant context — never expose bare find()
```

**Warning signs:**
- Queries using `Model.find()` directly without `tenant_id` condition
- Background jobs or scheduled tasks that process "all records" without tenant scoping
- Admin utilities that read without `tenant_id` — even for debugging
- Aggregation pipelines where `$match` stage does not include `tenant_id` as first stage
- Tests that pass a `tenant_id` of `None` and still return records

**Phase to address:** Multi-tenancy data layer phase (Phase 1, before any domain models are built). The pattern must be established as a foundation, not retrofitted later.

---

### Pitfall 3: Stripe Webhook Processing Without Idempotency

**What goes wrong:**
Stripe guarantees at-least-once webhook delivery. The same `customer.subscription.updated`, `invoice.payment_succeeded`, or `checkout.session.completed` event will arrive 2-3 times under normal conditions. Without idempotency checks, subscription state is applied multiple times: users get access revoked and re-granted erratically, invoices are marked paid twice, usage credits are doubled, or — worst — users maintain access after cancellation because a `customer.subscription.deleted` event was processed but a duplicate `customer.subscription.updated` re-activated them seconds later.

**Why it happens:**
Developers treat webhooks like reliable, ordered events. They are neither. Stripe retries for up to 3 days on failure. Network conditions, deployments, and queue backlogs all cause duplicates. Developers also forget that Stripe does not guarantee event delivery order.

**How to avoid:**
Persist each processed `event.id` in a deduplicate store (Redis with TTL, or MongoDB `processed_webhook_events` collection). Before processing any webhook, check if `event.id` was already processed. Return HTTP 200 immediately for duplicates without reprocessing. Additionally, verify the webhook signature using `stripe.Webhook.construct_event()` with the raw request body — not the parsed JSON body. In FastAPI, use `await request.body()` for this, since FastAPI's JSON parsing will change the byte representation.

```python
# FastAPI webhook handler pattern
@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    raw_body = await request.body()  # raw bytes required for signature check
    sig_header = request.headers.get("stripe-signature")
    event = stripe.Webhook.construct_event(raw_body, sig_header, WEBHOOK_SECRET)

    # Idempotency check
    if await redis.get(f"processed_webhook:{event.id}"):
        return {"status": "already_processed"}
    await redis.setex(f"processed_webhook:{event.id}", 86400, "1")
    # ... process event
```

**Warning signs:**
- No `processed_webhook_events` table or Redis key pattern for deduplication
- Webhook handler parses `request.json()` before passing to `stripe.Webhook.construct_event()`
- Subscription status updates applied without checking current state first (not idempotent)
- No dead-letter queue or alerting on webhook processing failures

**Phase to address:** Billing integration phase. Must be implemented from the first webhook handler — never add idempotency "later."

---

### Pitfall 4: Billing State Not Enforced at Runtime (Access/Entitlement Drift)

**What goes wrong:**
The most common revenue-leakage bug in SaaS: a user's subscription expires, trial ends, or payment fails — but they retain full access because access control checks the local DB subscription status, which is never updated. Alternatively, a user upgrades but the feature flags don't unlock until the next request. The billing system (Stripe) and the entitlement system (local DB) become out of sync and stay that way.

**Why it happens:**
Teams build "grant access on signup" then forget to build "revoke access on cancellation/failure." Stripe's state is the source of truth, but teams store a copy locally and don't treat webhook-driven updates as critical path. It's also common to check `subscription_status == "active"` but forget `trialing`, `past_due`, `unpaid`, and `incomplete` states.

**How to avoid:**
Define an explicit entitlement computation function that maps Stripe subscription status → allowed feature set. Use Stripe webhooks to keep local `tenant.subscription_status` in sync, and treat webhook failures as P0 incidents. Test every Stripe subscription lifecycle event: `trial_will_end`, `customer.subscription.paused`, `customer.subscription.deleted`, `invoice.payment_failed`, `invoice.payment_action_required`. Gate every protected API endpoint against the computed entitlement, not just a boolean `is_active` flag.

```python
# Explicit entitlement mapping — never use a boolean flag
def compute_entitlements(subscription_status: str, plan_id: str) -> Entitlements:
    if subscription_status in ("active", "trialing"):
        return plan_entitlements[plan_id]
    elif subscription_status == "past_due":
        return GRACE_PERIOD_ENTITLEMENTS  # read-only, no new resources
    else:  # canceled, unpaid, incomplete_expired
        return NO_ACCESS_ENTITLEMENTS
```

**Warning signs:**
- Access checks use `user.is_subscribed` (boolean) rather than current subscription status
- No webhook handler for `invoice.payment_failed`
- No webhook handler for `customer.subscription.deleted`
- Tests only cover "happy path" subscription creation, not cancellation or failed payment
- Trial end date stored locally but not re-verified against Stripe

**Phase to address:** Billing integration phase. The entitlement model must be designed before implementing any feature gating — retrofitting is high risk.

---

### Pitfall 5: OAuth2 Account Linking via Email Collision (Account Takeover)

**What goes wrong:**
A user registers with `user@example.com` + password. Later, an attacker creates a Google account for `user@example.com` (or uses an existing one with a malicious name claim). When the attacker authenticates via Google OAuth, the system finds an existing user with that email and silently links/merges the accounts, granting the attacker full access to the victim's tenant, data, and billing.

**Why it happens:**
Developers assume email address is a reliable unique identifier across providers. It is not. Email addresses can be registered with multiple OAuth providers, and the claim is not verified by the SaaS platform against the original password-based account. The `state` parameter is also often omitted or improperly validated, enabling CSRF attacks on the OAuth flow.

**How to avoid:**
Never auto-link OAuth accounts to existing password-based accounts by email alone. Instead: (1) If an account with that email already exists via a different authentication method, show a "link accounts" flow that requires the user to first authenticate with their existing method. (2) Only trust email-verified claims from OAuth providers (`email_verified: true` in the ID token). (3) Always validate the OAuth `state` parameter as a one-time CSRF token stored in the user's session. (4) Track `auth_provider` per user and reject cross-provider logins without explicit linking consent.

**Warning signs:**
- OAuth callback handler performs `User.find_by_email(email)` and logs in on match
- `state` parameter is not validated or is a static value
- `email_verified` claim from ID token is not checked
- Users can log in via Google with an email that's registered via password without seeing any linking prompt

**Phase to address:** OAuth2 social login phase. Must be designed with the account model from the start — cannot be patched after users are live.

---

### Pitfall 6: Stripe Raw Body Parsing Destroys Webhook Signature Verification

**What goes wrong:**
FastAPI (and most frameworks) automatically parse the request body as JSON when `Content-Type: application/json` is detected. Stripe's webhook signature is computed over the exact raw bytes of the payload. If the application reads `request.json()` or uses Pydantic body parsing before calling `stripe.Webhook.construct_event()`, the byte-level representation may differ (whitespace, key ordering, encoding), causing every legitimate Stripe webhook to fail signature verification — or silently disabling signature verification entirely when developers "fix" it by catching the exception.

**Why it happens:**
Framework magic. FastAPI's dependency injection encourages using Pydantic models as request body parameters. Developers follow the FastAPI pattern for all endpoints, not realizing the webhook endpoint is special. Some Cloudflare/proxy configurations also alter request bodies, breaking signatures.

**How to avoid:**
The Stripe webhook endpoint MUST use `await request.body()` explicitly and pass these raw bytes to `stripe.Webhook.construct_event()`. It must NOT be a Pydantic body parameter. Add this endpoint to any middleware that modifies request bodies (ensure it's excluded). Validate the signature using the Stripe CLI locally during development.

**Warning signs:**
- Stripe webhook handler has a Pydantic model as its body parameter
- `stripe.Webhook.construct_event()` is called with `json.dumps(await request.json())` instead of raw bytes
- Signature verification is wrapped in a bare `except` that swallows the error
- Integration tests mock Stripe events as JSON strings without proper signature headers

**Phase to address:** Billing integration phase, Day 1 of webhook implementation.

---

### Pitfall 7: TOTP Clock Drift and Replay Vulnerability

**What goes wrong:**
Two failure modes: (1) Clock drift between the user's authenticator app and the server causes valid TOTP codes to be rejected intermittently — killing user experience and generating support tickets. (2) A valid TOTP code is accepted multiple times within its 30-second window (replay attack), allowing an attacker who intercepts the code to use it again immediately.

**Why it happens:**
Clock drift: Server clock is not NTP-synchronized, or the verification window is set to exactly 0 (accept only current time step). Replay: No "used codes" store is implemented — just stateless HMAC validation.

**How to avoid:**
(1) Clock drift: Use a ±1 step window (accepts codes valid in the 30 seconds before and after the current step). Ensure server NTP sync. (2) Replay: Store each used `(user_id, totp_code, time_step)` tuple in Redis with TTL of 90 seconds. Reject any code that's been seen before for that user in that time window. (3) Validate the provisioning URI format carefully — generate `otpauth://` URIs with correct Base32-encoded secrets, test with multiple authenticator apps (Google Authenticator, Authy, 1Password) before shipping.

**Warning signs:**
- TOTP verification has no tolerance window (exact current step only)
- No Redis/DB store for "recently used TOTP codes"
- Server NTP configuration not verified in deployment runbook
- Provisioning URI only tested with one authenticator app
- TOTP secret stored as hex/ASCII instead of Base32

**Phase to address:** MFA implementation phase. Replay protection must be implemented together with TOTP verification, not added later.

---

### Pitfall 8: Super-Admin API Exposed to the Same Auth Stack

**What goes wrong:**
The super-admin panel (tenant CRUD, billing plan management, system-wide configuration) uses the same JWT auth middleware as tenant-facing endpoints. This means: (1) A compromised tenant JWT with a forged role claim can elevate to super-admin if role validation is imperfect. (2) Rate limiting, session management, and brute-force protection apply equally to super-admin — which may be less robust for high-value targets. (3) Super-admin API endpoints are discoverable by tenants exploring the API.

**Why it happens:**
It's faster to reuse the existing auth stack. Developers assume RBAC role checks are sufficient. The super-admin endpoints are "protected by roles" so they feel safe.

**How to avoid:**
Isolate the super-admin API on a separate FastAPI router (ideally separate application mount or internal-only network binding). Require a separate super-admin JWT issued from a distinct `aud` (audience) claim — never accept tenant JWTs on super-admin endpoints. Implement IP allowlisting for super-admin routes. Add MFA requirement as a gateway even for valid super-admin tokens (step-up authentication). Log all super-admin actions to an immutable audit log.

**Warning signs:**
- Super-admin endpoints share the same `@require_role("super_admin")` decorator pattern as tenant roles
- No separate super-admin credential store or session management
- Super-admin routes are accessible from the same public domain/IP as tenant routes
- No audit logging on super-admin mutations

**Phase to address:** Super-admin panel phase. Architecture decision must be made before building the first admin endpoint.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Store `is_subscribed: bool` instead of full subscription state | Simple access checks | Cannot handle `past_due`, grace periods, or partial access — requires schema migration under live traffic | Never |
| Apply `tenant_id` filter manually in each query | Simple to start | Any new query that forgets it leaks data — no guardrails | Never (use base class pattern) |
| Single Redis instance for rate limiting + token blacklist + session | Fewer services to manage | Single point of failure takes down auth + rate limiting simultaneously | Only in dev/staging |
| Verify webhook signatures only in non-production | Faster local dev | Signature verification bugs only discovered after deploy | Dev only, never staging/prod |
| Store Stripe `customer_id` without a uniqueness constraint | Easier initial coding | Duplicate customers in Stripe cause double-billing; hard to reconcile | Never |
| Hardcode plan limits in feature flag checks | Fast to ship | Plan changes require code deploys; cannot manage plans via admin UI | Never if super-admin panel exists |
| JWT expiry set to 24h+ for "better UX" | Fewer re-auth prompts | Token compromise gives 24h attacker window; blacklist must hold tokens for full lifetime | Never for access tokens; use refresh tokens instead |
| Use `alg: "none"` in test environments | Simplifies test setup | Test environment bleeds into prod config; auth bypass in production | Never |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Stripe Webhooks | Parse `request.json()` before signature verification | Use `await request.body()` (raw bytes) exclusively; do not let FastAPI parse the body |
| Stripe Webhooks | Process events synchronously in the webhook handler | Return HTTP 200 immediately, push to a queue (Redis/Celery), process async to avoid timeout |
| Stripe Subscriptions | Trust only `checkout.session.completed` for provisioning | Also handle `customer.subscription.created`, `invoice.payment_succeeded` for retry scenarios |
| Stripe Metered Billing | Submit usage records at end of billing period | Submit in real-time or via hourly batch — submitting at period end risks missing the cutoff window |
| Stripe Metered Billing | Use legacy `usage_records` API | Stripe deprecated legacy usage records in v2025-03-31.basil — use Billing Meters API |
| OAuth2 (Google/GitHub/Microsoft) | Trust `email` claim as unique identifier | Check `email_verified: true`, use provider `sub` (subject ID) as primary key, handle email-provider combination |
| OAuth2 State Parameter | Use a static state value or omit it | Generate a cryptographically random state per request, store in session, validate on callback |
| Redis Blacklist | Store entire valid token set (whitelist) | Store only revoked tokens with TTL equal to token remaining lifetime — whitelist approach kills statelessness and scale |
| MongoDB | Index only `tenant_id` as single field | Use compound indexes with `tenant_id` as leftmost field: `{tenant_id: 1, <query_field>: 1}` |
| RS256 Key Management | Embed private key in application config/env var directly | Load from secrets manager (HashiCorp Vault, AWS Secrets Manager) at startup; rotate without code deploys |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| No compound index with `tenant_id` as prefix | Queries slow as tenant grows; MongoDB COLLSCAN on large collections | Add `{tenant_id: 1, <field>: 1}` compound index for every filtered query | 10K+ documents per tenant |
| Redis blacklist without TTL scoping | Redis memory grows unbounded with revoked tokens | Set TTL on each blacklist key equal to the token's remaining expiry duration | 100K+ revocations over token lifetime |
| Synchronous Stripe usage record submission | API timeouts block user requests during billing | Queue usage events, batch-submit to Stripe Meters API asynchronously | Any significant API latency spike |
| Loading full tenant subscription object for every request | Database hit on every authenticated request | Cache subscription state in Redis with TTL = 60s; invalidate on webhook update | 1K+ req/s per tenant |
| Beanie `find()` without `.project()` | Fetches entire documents when only a few fields needed | Always use `.project()` for list endpoints; define response projection models | 50+ fields per document |
| Single MongoDB collection for all tenants, no shard key | Collection grows to billions of documents with no shard key | Define shard key as `{tenant_id: "hashed"}` from the start | 10M+ documents total |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Accept JWT `alg` field from token header | Full auth bypass via RS256→HS256 confusion attack; attacker signs arbitrary claims | Hardcode `algorithms=["RS256"]` in JWT decode call; never read `alg` from token |
| Missing TOTP replay protection | Valid code intercepted and reused within 30-second window | Store used `(user_id, code, time_step)` in Redis with 90s TTL |
| Auto-link OAuth accounts by email without verification | Account takeover: attacker's Google account merges into victim's password account | Require explicit user consent for cross-provider account linking; verify `email_verified` claim |
| Omit `state` parameter validation in OAuth2 callback | CSRF attack hijacks OAuth flow to link attacker's OAuth account to victim's session | Generate random per-request state, store in session, validate on callback |
| Super-admin endpoints on same auth domain as tenant API | Tenant JWT with forged role escalates to super-admin | Separate `aud` claim + IP allowlist for super-admin; never accept tenant tokens on admin routes |
| Webhook endpoint accepts unsigned payloads | Fake subscription events; attacker grants free access or revokes legitimate users | Always verify Stripe-Signature header; never skip in any environment |
| JWT `RS256` public key in JWKS endpoint without `kid` (Key ID) | Key rotation is operationally difficult; verification services cache wrong key | Include `kid` in JWT header and JWKS; implement key ID lookup in wxcode verification |
| MongoDB CVE-2025-14847 (MongoBleed) unpatched | Unauthenticated heap memory leak exposes inter-tenant query data from server memory | Pin MongoDB to patched versions: 8.0.17+, 7.0.28+, 6.0.27+ — this is actively exploited in the wild |
| Store Stripe webhook secret in application database | Key compromised = all webhook verification bypassed | Store webhook secret in environment variable or secrets manager only |
| RBAC role checks scattered across endpoint implementations | Permission bypass via forgotten check; inconsistency as codebase grows | Centralize all RBAC in FastAPI dependencies; never inline role logic in handler functions |

---

## UX Pitfalls

Common user experience mistakes in auth/billing SaaS.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No grace period on payment failure | Users locked out immediately on first failed charge; causes panic and churn | Implement 7-day grace period on `invoice.payment_failed`; send reminder emails before hard revocation |
| MFA enrollment UX not tested with actual mobile devices | Authenticator QR codes fail on specific apps; users unable to enroll | Test provisioning URIs with Google Authenticator, Authy, and 1Password before launch |
| Generic "access denied" error on subscription expiry | Users don't know why they're blocked; contact support instead of upgrading | Distinguish between auth failure (401) and entitlement failure (402/403) with clear upgrade prompt |
| OAuth login creates duplicate account instead of merging | User has two accounts; data split; billing charged twice | Show "Account already exists — link accounts?" flow before creating a second account |
| No "billing history" accessible to non-Owner roles | Billing-role users can't view invoices; Owners become bottleneck | Stripe Customer Portal link accessible to `Billing` role without exposing plan management |
| Password reset doesn't invalidate existing sessions | Attacker who stole a session token retains access after victim resets password | On password reset, revoke all active refresh tokens and add access tokens to blacklist |
| TOTP recovery codes not generated at enrollment | Users locked out when phone lost; no recovery path | Generate 8-10 one-time recovery codes at TOTP setup; prompt to save them; track used codes |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **JWT Auth:** Token is decoded and user is loaded — but `algorithms=["RS256"]` is hardcoded (not read from token), `exp` is verified, `aud` is verified, and `iss` is verified. Verify all four claims, not just signature.
- [ ] **Multi-tenancy:** CRUD endpoints all filter by `tenant_id` — but background jobs, analytics queries, admin utilities, and aggregation pipelines do too. Run a query without `tenant_id` and verify 0 cross-tenant records return.
- [ ] **Stripe Webhooks:** Signature verification is implemented — but the handler also has idempotency check, dead-letter queue, and alerting on >3 consecutive failures. Signature without idempotency is incomplete.
- [ ] **TOTP MFA:** Code verification is implemented — but replay protection (used codes in Redis), clock drift tolerance (±1 window), and recovery codes are also present. Missing any one breaks real-world usage.
- [ ] **OAuth2 Login:** Google login creates/updates user — but `email_verified: true` is checked, `state` is validated, `sub` is stored as primary link key, and duplicate-account flow is handled. Email alone is insufficient.
- [ ] **Subscription Gating:** Active subscriptions pass — but `trialing`, `past_due` (grace period), `paused`, `incomplete`, and `canceled` states are all handled with explicit behavior. Missing states = silent access drift.
- [ ] **RBAC:** Roles are stored and checked — but roles are scoped to the tenant (an Owner in tenant A is not an Owner in tenant B), and there is a separate, strictly isolated super-admin role. Global roles = privilege escalation path.
- [ ] **Token Blacklist:** Logout invalidates tokens via Redis — but the blacklist TTL matches the token's remaining expiry, Redis key naming is collision-safe (includes `jti` claim), and Redis failure does NOT cause logout to silently succeed (fail closed).
- [ ] **Metered Billing:** Usage events are recorded — but they use idempotency keys, are submitted via async queue (not synchronously), and handle the billing period cutoff edge case (usage in the last minute of a period).
- [ ] **Super-Admin Panel:** CRUD for plans and tenants works — but every mutation is logged to an immutable audit trail, super-admin tokens have a separate `aud` claim, and IP allowlisting is enforced.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cross-tenant data leak discovered | HIGH | Immediately rotate all tenant JWTs (force re-auth); audit all queries in last 30 days via MongoDB oplog; notify affected tenants per breach disclosure requirements; patch query layer before bringing service back up |
| Webhook idempotency not implemented and duplicate billing occurs | HIGH | Pull all Stripe events for affected customers; reconcile against local state; issue refunds for duplicate charges via Stripe API; implement idempotency before re-enabling webhooks |
| Algorithm confusion vulnerability discovered before exploit | MEDIUM | Deploy `algorithms=["RS256"]` fix immediately; invalidate all existing tokens (force re-login); audit logs for any tokens with non-RS256 `alg` headers; rotate RS256 key pair as precaution |
| Stripe entitlement drift (users with canceled subscriptions have access) | MEDIUM | Run reconciliation script: for each tenant, fetch current subscription status from Stripe API, compare to local DB, apply correct entitlement state; log all corrections for audit |
| TOTP codes accepted without replay protection, then exploited | HIGH | Force MFA re-enrollment for all affected users; rotate user secrets; add replay protection before re-enabling MFA; check audit logs for anomalous auth patterns |
| MongoDB MongoBleed (CVE-2025-14847) on unpatched version | CRITICAL | Take MongoDB offline immediately; patch to fixed version; audit connection logs for unauthenticated zlib requests; assume all in-memory query data was potentially leaked; notify affected tenants |
| OAuth email collision account takeover | HIGH | Identify affected accounts (accounts linked via OAuth without explicit user consent); revoke OAuth links; force password reset for affected accounts; add explicit account-linking consent flow before re-enabling OAuth |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| JWT algorithm confusion (RS256→HS256) | Phase 1: Core Authentication | Penetration test: submit token with `alg: HS256` signed with public key — must return 401 |
| Cross-tenant data leakage | Phase 1: Multi-tenancy Data Layer | Automated test: authenticated tenant A user queries all endpoints, verify no tenant B data returns |
| Missing TOTP replay protection | Phase 2: MFA Implementation | Test: reuse same TOTP code twice in 30s window — second use must return 401 |
| OAuth2 email collision account takeover | Phase 2: OAuth2 Social Login | Test: create account via password, then OAuth login with same email — must show linking flow, not silent merge |
| Stripe webhook idempotency | Phase 3: Billing Integration | Test: deliver same Stripe event ID twice — subscription state changes only once |
| Billing entitlement drift | Phase 3: Billing Integration | Test: simulate Stripe `customer.subscription.deleted` webhook — tenant loses access within seconds |
| Stripe raw body signature failure | Phase 3: Billing Integration | Test: send Stripe webhook from Stripe CLI — must verify signature successfully |
| Super-admin isolation | Phase 4: Super-Admin Panel | Test: present tenant JWT to super-admin endpoint — must return 403; super-admin JWT presented to tenant endpoint — must return 403 |
| Metered billing idempotency / cutoff | Phase 3: Billing Integration | Test: submit same usage event ID twice — counted once; submit usage 1 minute before period end — appears on correct invoice |
| Compound index missing `tenant_id` prefix | Phase 1: Multi-tenancy Data Layer | Load test: 100K documents per tenant, query without compound index — verify explain() shows IXSCAN not COLLSCAN |
| Redis blacklist TTL misconfiguration | Phase 1: Core Authentication | Test: revoke token, wait TTL+1 second — token must be rejected (not re-accepted due to expired blacklist key) |
| RBAC global vs. tenant-scoped roles | Phase 1: Core Authentication | Test: Owner in tenant A attempts to access tenant B resources — must return 403 |

---

## Sources

- PortSwigger Web Security Academy — JWT Algorithm Confusion Attacks: https://portswigger.net/web-security/jwt/algorithm-confusion
- PortSwigger Web Security Academy — OAuth 2.0 Authentication Vulnerabilities: https://portswigger.net/web-security/oauth
- Auth0 — Critical Vulnerabilities in JSON Web Token Libraries: https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/
- Authgear — 5 Common TOTP Mistakes Developers Make: https://www.authgear.com/post/5-common-totp-mistakes
- Stigg Blog — Best Practices for Stripe Webhook Integration: https://www.stigg.io/blog-posts/best-practices-i-wish-we-knew-when-integrating-stripe-webhooks
- Stripe Documentation — Using Webhooks with Subscriptions: https://docs.stripe.com/billing/subscriptions/webhooks
- Stripe Documentation — Resolve Webhook Signature Verification Errors: https://docs.stripe.com/webhooks/signature
- Stripe Documentation — Usage-Based Billing (Meters API): https://docs.stripe.com/billing/subscriptions/usage-based
- Stripe Changelog — Deprecating Legacy Usage Records (2025-03-31): https://docs.stripe.com/changelog/basil/2025-03-31/deprecate-legacy-usage-based-billing
- MongoDB Documentation — Build a Multi-Tenant Architecture: https://www.mongodb.com/docs/atlas/build-multi-tenant-arch/
- Jit.io — Enhance MongoDB Security for Atlas With Scalable Tenant Isolation: https://www.jit.io/blog/enhance-mongodb-security-for-atlas-with-scalable-tenant-isolation
- MongoDB Security Update (MongoBleed CVE-2025-14847): https://www.mongodb.com/company/blog/news/mongodb-server-security-update-december-2025
- Wiz Blog — MongoBleed CVE-2025-14847: https://www.wiz.io/blog/mongobleed-cve-2025-14847-exploited-in-the-wild-mongodb
- OWASP — Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- APIsec — JWT Security Vulnerabilities Prevention Guide: https://www.apisec.ai/blog/jwt-security-vulnerabilities-prevention
- Curity — JWT Security Best Practices Checklist: https://curity.io/resources/learn/jwt-best-practices/
- Auth0 — Refresh Tokens: What Are They and When to Use Them: https://auth0.com/blog/refresh-tokens-what-are-they-and-when-to-use-them/
- Security Boulevard — SaaS Privilege Escalation Detection: https://securityboulevard.com/2025/08/how-can-you-stop-saas-privilege-escalation-fast-with-real-time-detection-automatic-containment/
- IETF RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://datatracker.ietf.org/doc/rfc9700/

---
*Pitfalls research for: SaaS Authentication / Billing / Multi-Tenancy (WXCODE ADM)*
*Researched: 2026-02-22*
