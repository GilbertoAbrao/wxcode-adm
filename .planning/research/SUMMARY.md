# Project Research Summary

**Project:** WXCODE ADM — SaaS Authentication, Billing, and Multi-Tenancy Platform
**Domain:** SaaS auth/billing backend (Python/FastAPI/MongoDB)
**Researched:** 2026-02-22
**Confidence:** HIGH

## Executive Summary

WXCODE ADM is a purpose-built SaaS infrastructure layer — handling authentication, multi-tenancy, billing, and access control — for the WXCODE conversion engine. Unlike off-the-shelf solutions (Auth0, Clerk, WorkOS), it is tightly integrated with the WXCODE stack (Python/FastAPI/Beanie/MongoDB/Redis) and must issue RS256 JWTs that the wxcode engine validates locally without a network call per request. This architecture requires wxcode-adm to own the RSA private key exclusively, expose a JWKS endpoint for public key distribution, and embed tenant context (tenant_id, role, plan, scopes) directly in token claims so the engine can enforce quotas without touching the database on every conversion.

The recommended build approach is domain-modular with strict tenant isolation enforced at the data layer: every MongoDB document carries a `tenant_id` field and every query must include it. The stack is non-negotiable (fixed by the parent project), so choices center on library selection within that stack. Key choices are PyJWT over python-jose (security, maintenance), pwdlib[argon2] over passlib (Python 3.13 compatibility), arq over Celery (async-native, uses existing Redis), and authlib for OAuth2 social login. Stripe is the billing source of truth — all subscription state must be driven by webhook events, never by API response assumptions.

The three highest-risk areas are: (1) multi-tenant data isolation — a single missing `tenant_id` filter silently breaches all tenants with no error visible at the application layer; (2) Stripe webhook idempotency and raw-body signature verification — Stripe delivers events at-least-once and signature verification is broken by any JSON parsing before the raw bytes are consumed; (3) JWT algorithm confusion — an RS256 implementation that trusts the `alg` field from the incoming token allows attackers to sign arbitrary claims using the public key. All three must be addressed structurally in foundation phases, not retrofitted.

---

## Key Findings

### Recommended Stack

The stack is fixed by the parent project for all core infrastructure. Library selection within that stack is the only variable. All versions are verified against PyPI as of 2026-02-22.

**Core technologies:**
- **FastAPI 0.131.0 + Pydantic 2.12.5:** Framework + validation; Pydantic v2 is required (v1 dropped in FastAPI 0.131+); provides 5-50x faster validation via Rust core
- **Beanie 2.0.1 + Motor 3.7.1:** Async MongoDB ODM; v2.0 requires Pydantic v2 and transitions to PyMongo Async API internally
- **Redis 7.2.0 (redis-py):** Token blacklist, refresh token metadata, rate limit counters, usage counters — use `from redis.asyncio import Redis` (standalone `aioredis` is dead)
- **PyJWT 2.11.0 [crypto]:** RS256 JWT creation and verification; explicitly recommended by FastAPI team over python-jose (CVEs, unmaintained since 2021)
- **pwdlib 0.3.0 [argon2]:** Password hashing; replaces passlib (removed `crypt` module in Python 3.13); Argon2id is OWASP winner
- **authlib 1.6.8:** OAuth2 social login (Google/GitHub/Microsoft) via Authorization Code Flow + PKCE; native Starlette integration
- **stripe 14.3.0:** Official Stripe SDK; covers Checkout, Subscriptions, Billing Meters (use Meters API — legacy usage records deprecated 2025-03-31), Customer Portal, webhook signature verification
- **arq 0.27.0:** Async job queue on Redis; replaces Celery for email delivery, Stripe webhook processing, usage aggregation
- **fastapi-mail 1.6.2:** Async transactional email with Jinja2 HTML templates
- **slowapi 0.1.9:** Redis-backed distributed rate limiting (fastapi-limiter unmaintained since 2023)
- **pydantic-settings 2.13.1:** Type-safe `.env` loading with SecretStr for credentials
- **itsdangerous:** Signed, time-limited tokens for email verification and password reset links (no DB lookup needed)
- **pyotp 2.9.0 + qrcode 8.2:** TOTP/MFA — generates RFC 6238 codes and QR codes for authenticator app enrollment

**Do not use:** python-jose (CVEs), passlib (Python 3.13 incompatible), aioredis standalone (dead), fastapi-users (fights multi-tenancy), Celery (sync-first), Pydantic v1.

See `.planning/research/STACK.md` for full version compatibility matrix and installation commands.

### Expected Features

The MVP must ship all P1 features to function as a paid SaaS product. P2 features are triggered by specific business events (first enterprise prospect, first involuntary churn, etc.) — do not build them speculatively.

**Must have (table stakes / P1 — v1):**
- Email + password sign-up/sign-in with email verification
- Password reset via email (short-lived, single-use token)
- JWT RS256 issuance + refresh token rotation with Redis blacklist
- JWKS endpoint (`/.well-known/jwks.json`) — required for wxcode local validation
- OAuth social login: Google + GitHub (Microsoft deferred to v1.x)
- Auto-tenant creation on sign-up; RBAC with 5 roles (Owner/Admin/Developer/Viewer/Billing)
- User invitation to tenant (email, 7-day expiry)
- Plan CRUD by super-admin (Free/Starter/Pro/Enterprise)
- Stripe Checkout + Webhooks (invoice.paid, subscription.updated/deleted, payment_failed)
- Stripe Customer Portal (self-service billing)
- Plan enforcement (quota check before wxcode engine operations; HTTP 402 on limit exceeded)
- API keys per tenant (prefixed `wxk_live_`/`wxk_test_`, scoped, HMAC-hashed, revocable)
- Rate limiting (Redis sliding window: 5/min login, 3/min sign-up, 3/hr reset, 100/min API)
- Audit log (immutable append-only)
- Super-admin: tenant list, user list, suspend/block, MRR dashboard
- Transactional email templates: verify, reset, invite, payment_failed

**Should have (differentiators / P2 — v1.x, trigger-driven):**
- MFA via TOTP with per-tenant enforcement and remember-device (30-day skip)
- Usage-based metered billing (Stripe Meters API) + usage dashboard per tenant
- Dunning management (Stripe Smart Retries + 7-day grace period on payment_failed)
- Trial period support (Stripe `trial_period_days`)
- Super-admin: churn/expansion MRR breakdown, usage heatmap by tenant
- Feature flags/global limits (MongoDB `platform_settings`, Redis-cached)
- IP allowlist per tenant (Enterprise plan only)
- OAuth: Microsoft

**Defer (v2+):**
- SAML SSO + SCIM provisioning (requires enterprise contracts justifying 4-8 weeks)
- Passkeys/WebAuthn (frontend investment, low demand from developer audience)
- Multi-tenant switching (explicitly out of scope per PROJECT.md)
- Custom per-tenant plans (explicitly out of scope per PROJECT.md)
- Audit log SIEM webhook forwarding

**Anti-features to reject:** Multi-currency billing (let Stripe handle it), real-time WebSocket billing dashboard (polling every 60s is sufficient), custom OAuth provider registration per tenant.

See `.planning/research/FEATURES.md` for full dependency graph and prioritization matrix.

### Architecture Approach

The system follows a domain-modular FastAPI structure where each domain (auth, tenants, billing, users, admin, apikeys, audit) owns its router, service, models, and schemas with no cross-domain model imports. Five key architectural patterns govern the system: (1) tenant context as immutable request state injected by middleware from JWT claims, never threaded as function parameters; (2) Stripe webhooks processed with "receive fast, process async" — verify signature + idempotency check + enqueue to arq, return 200 in under 100ms; (3) RS256 asymmetric JWT with JWKS public key distribution so wxcode validates locally with zero network calls; (4) Redis-backed usage counters for real-time quota enforcement with periodic hourly flush to MongoDB and Stripe Meters; (5) direct Beanie queries with mandatory `tenant_id` guard enforced by a `TenantDocument` base class and cross-tenant isolation tests.

**Major components:**
1. **auth/ module** — signup, login, OAuth flows, MFA, password reset, JWT RS256 signing; the prerequisite for all other modules
2. **tenants/ module + middleware** — tenant CRUD, RBAC, member management, invitations; injects `TenantContext` into every authenticated request
3. **billing/ module** — Stripe Checkout/Portal, webhook ingestion, subscription state, plan enforcement; `billing/webhooks.py`, `billing/usage.py`, `billing/stripe_client.py` are explicitly split
4. **tasks/ module (arq)** — async email delivery, Stripe event processing, usage aggregation, token cleanup; orchestrates across domains without coupling them
5. **admin/ module** — super-admin with cross-tenant read access; separate `aud` JWT claim; IP allowlisted
6. **middleware stack** — security headers, rate limiting, tenant context injection — applied in that order

**MongoDB index rule:** Every tenant-scoped collection has `tenant_id` as the leftmost field in all compound indexes. Queries without `tenant_id` are bugs.

**Build order is dictated by dependency:** Foundation → Auth Core → Multi-Tenancy → Billing Core → Usage Metering → Supporting Features (OAuth, MFA, API keys, audit, email, rate limiting) → Admin + Observability.

See `.planning/research/ARCHITECTURE.md` for project directory structure, code examples, data flow diagrams, and scaling considerations.

### Critical Pitfalls

1. **JWT algorithm confusion (RS256 → HS256 downgrade):** Always pass `algorithms=["RS256"]` explicitly to `jwt.decode()`. Never trust the `alg` field from the incoming token. A missing explicit algorithm parameter is an auth bypass. Address in Phase 2 (Auth Core) before any endpoints go live.

2. **Cross-tenant data leakage via missing `tenant_id` filter:** MongoDB has no row-level security. A single query without `tenant_id` silently exposes all tenants' data. Use a `TenantDocument` base class that injects `tenant_id` into all find/update/delete operations structurally. Add automated isolation tests that verify every endpoint returns 0 cross-tenant records. Address in Phase 1 (Foundation/Data Layer) — cannot be retrofitted.

3. **Stripe webhook idempotency + raw body parsing:** Stripe delivers events at-least-once. Without idempotency, duplicate subscription state changes cause billing inconsistencies. FastAPI's JSON body parsing alters byte representation and breaks Stripe's signature verification — always use `await request.body()` raw bytes before calling `stripe.Webhook.construct_event()`. Address in Phase 4 (Billing Core) from day one of webhook implementation.

4. **Billing entitlement drift:** Subscription cancellations and payment failures must revoke access via webhook — not via scheduled jobs or polling. Store full subscription status (not a boolean `is_subscribed`), handle all Stripe states (`active`, `trialing`, `past_due`, `canceled`, `incomplete`), and define explicit entitlement computation per state. Address in Phase 4 (Billing Core) before plan enforcement is built.

5. **OAuth2 account takeover via email collision:** Never auto-link an OAuth account to an existing password account by email match alone. Require explicit "link accounts" flow; verify `email_verified: true` in OAuth ID token; validate `state` parameter as one-time CSRF token. Address in Phase 6 (Supporting Features / OAuth).

6. **MongoDB CVE-2025-14847 (MongoBleed):** Actively exploited heap memory leak. Pin MongoDB to patched versions: 8.0.17+, 7.0.28+, or 6.0.27+. Address in project setup before any data is stored.

See `.planning/research/PITFALLS.md` for full pitfall list, recovery strategies, and "Looks Done But Isn't" verification checklist.

---

## Implications for Roadmap

Based on the combined research, the dependency graph is clear and largely non-negotiable. Auth Core blocks everything. Multi-tenancy must precede billing (Stripe Customer is per-tenant). Billing Core must precede Usage Metering. Supporting features (OAuth, MFA, API keys, audit, rate limiting) are parallel after multi-tenancy. Admin is last because it reads across all modules.

The feature set for v1 is large but well-defined — 19 P1 features in the MVP definition. Grouping by dependency (as the architecture research prescribes) produces 7 natural phases.

### Phase 1: Foundation and Data Layer
**Rationale:** All application code depends on infrastructure. The `tenant_id` isolation pattern must be established here — before any domain models exist — because retrofitting it is a migration under live traffic. MongoDB CVE-2025-14847 patch must be verified here.
**Delivers:** Working FastAPI app with MongoDB + Beanie init, Redis connection pool, pydantic-settings config, shared exceptions, and the `TenantDocument` base class that enforces tenant isolation structurally.
**Addresses:** Foundation for all 19 P1 features; cross-tenant data leakage prevention (Pitfall 2); MongoDB security patch (Pitfall 6).
**Avoids:** Building any domain model before the isolation pattern is locked in; storing `tenant_id` only as a convention rather than a structural constraint.
**Research flag:** Standard patterns — no additional research needed. FastAPI app factory, Beanie initialization, pydantic-settings are all well-documented.

### Phase 2: Authentication Core
**Rationale:** Auth is the prerequisite for all other phases. No endpoint can be tested or built without authentication. RS256 JWT issuance and the JWKS endpoint must be live before wxcode integration is possible — this is the single hardest architectural dependency.
**Delivers:** Sign-up, sign-in, logout, email verification, password reset, RS256 JWT issuance + refresh token rotation, token blacklist in Redis, JWKS endpoint.
**Addresses:** FEATURES.md table-stakes auth features; JWT RS256 + JWKS endpoint (integration-blocking P1); refresh token rotation.
**Avoids:** JWT algorithm confusion attack (Pitfall 1) — hardcode `algorithms=["RS256"]` from the first line of jwt.py; Redis blacklist TTL misconfiguration; RBAC global vs. tenant-scoped roles.
**Research flag:** Standard patterns well-documented. PyJWT + FastAPI dependency injection for auth is the current recommended pattern per FastAPI docs.

### Phase 3: Multi-Tenancy and RBAC
**Rationale:** Tenant model is the billing unit. Stripe Customer is created per-tenant on sign-up. RBAC is meaningless without a tenant context. All subsequent features (billing, API keys, audit log) require `tenant_id` to exist.
**Delivers:** Auto-tenant creation on sign-up, Tenant/TenantMembership/Invitation models, RBAC with 5 roles enforced via FastAPI dependencies, user invitation flow, ownership transfer, member management.
**Addresses:** Tenant creation (P1), RBAC (P1), User invitation (P1).
**Avoids:** Trusting URL `tenant_id` over JWT `tenant_id` (Architecture Anti-Pattern 2); missing `tenant_id` filter in queries.
**Research flag:** Standard patterns. MongoDB multi-tenancy with logical isolation is well-documented and the architecture research provides explicit implementation patterns.

### Phase 4: Billing Core
**Rationale:** Revenue generation. Stripe Checkout, webhooks, and Customer Portal are P1 blockers for launch. Plan enforcement must exist before the wxcode engine can enforce quotas against subscription limits. The Stripe webhook architecture (verify + idempotency + async queue) must be implemented correctly from day one.
**Delivers:** Plan definitions and limits, Stripe Customer creation on tenant sign-up, Stripe Checkout for Starter/Pro plans, webhook processing (subscription.created/updated/deleted, invoice.paid, invoice.payment_failed), Customer Portal, plan enforcement (HTTP 402 on quota exceeded), subscription state management.
**Addresses:** Stripe Checkout + Webhooks (P1), Customer Portal (P1), Plan enforcement (P1), MRR foundation for super-admin dashboard.
**Avoids:** Stripe raw body parsing destroying signature verification (Pitfall 6); webhook idempotency failure (Pitfall 3); billing entitlement drift (Pitfall 4); storing `is_subscribed: bool` instead of full subscription status.
**Research flag:** This phase likely benefits from `/gsd:research-phase` during planning. Stripe Billing Meters API (replacing deprecated legacy usage records as of 2025-03-31) has specific integration requirements. Idempotency key patterns and webhook retry handling have nuances not fully captured in the architecture overview.

### Phase 5: Supporting Features
**Rationale:** OAuth, MFA, API keys, audit log, rate limiting, and email templates are all independent of each other but depend on Phases 2-3. This phase makes the product complete for v1 launch. Grouping them together is correct because they share no dependencies on each other and can be parallelized within the phase.
**Delivers:** OAuth 2.0 social login (Google + GitHub), MFA via TOTP (pyotp + QR enrollment + backup codes), API key generation/revocation with scopes, immutable audit log, transactional email templates (verify/reset/invite/payment_failed), Redis sliding-window rate limiting on sensitive endpoints.
**Addresses:** OAuth Google + GitHub (P1), API keys (P1), Rate limiting (P1), Audit log (P1), Transactional emails (P1). MFA is P2 but has a natural home here alongside auth features.
**Avoids:** OAuth2 account takeover via email collision (Pitfall 5) — explicit account-linking flow, `email_verified` check, `state` CSRF validation; TOTP replay vulnerability and clock drift (Pitfall 7 from PITFALLS.md).
**Research flag:** OAuth PKCE flow and account-linking edge cases warrant a brief research pass during planning. The `state` parameter pattern and `email_verified` handling differ per provider (Google, GitHub behave differently).

### Phase 6: Usage Metering
**Rationale:** Usage-based billing is a P2 differentiator but has a natural sequencing dependency — it requires an active subscription (Phase 4) and a stable internal API contract with the wxcode engine. The internal `/billing/usage/report` endpoint must be stable before wxcode integration. Redis counter + periodic Stripe Meters flush is the only viable pattern for high-frequency per-tenant quota enforcement without hitting MongoDB per conversion.
**Delivers:** Redis-backed usage counters (INCRBY per tenant/metric/period), quota enforcement (Redis read, no DB hit per conversion), internal `/billing/usage/report` endpoint authenticated by internal API key, hourly arq scheduled task flushing counters to MongoDB and Stripe Meters API, usage dashboard per tenant (current period, conversions used/remaining).
**Addresses:** Usage-based metered billing (P2), Usage dashboard (P2); establishes the wxcode engine ↔ wxcode-adm usage reporting contract.
**Avoids:** Metered billing idempotency failure (usage event counted twice on retry); using deprecated legacy usage records API (must use Stripe Billing Meters introduced 2025-03-31); synchronous Stripe usage submission blocking request path.
**Research flag:** The Stripe Billing Meters API (post-basil) warrants verification during planning. The event submission format, idempotency key requirements, and billing period cutoff behavior changed with the 2025-03-31 deprecation.

### Phase 7: Super-Admin and Observability
**Rationale:** Admin panel is last because it reads from all other modules — it can only be built after all domain data exists. Super-admin isolation (separate `aud` claim, IP allowlist) must be an architecture decision made before the first admin endpoint, not retrofitted.
**Delivers:** Super-admin panel with tenant list/suspend/delete, user list/block/force-reset, plan CRUD (Stripe Price IDs), MRR dashboard (new/expansion/churned MRR from Stripe data), feature flags (`platform_settings` in MongoDB, Redis-cached), scheduled token cleanup task, session listing/revocation for users.
**Addresses:** Super-admin management (P1), MRR dashboard (P1), Feature flags (P2), Super-admin churn/MRR breakdown (P2).
**Avoids:** Super-admin API exposed on same auth domain as tenant API (Pitfall 8 from PITFALLS.md) — separate `aud` claim + IP allowlist from day one of this phase; RBAC inline role logic scattered across handlers.
**Research flag:** Standard patterns. Super-admin RBAC with separate audience claim is a well-understood pattern.

### Phase Ordering Rationale

- **Foundation before auth:** Redis connection pool and Beanie initialization must exist before any service can run. The `TenantDocument` base class must exist before any domain model is created.
- **Auth before everything:** JWT issuance and the FastAPI dependency (`get_current_user`, `require_role`) are consumed by every subsequent module. Nothing can be tested without auth.
- **Multi-tenancy before billing:** Stripe Customer is created per-tenant at sign-up. Billing requires a valid `tenant_id` to create subscriptions. Plan enforcement requires RBAC to be defined.
- **Billing before metering:** Usage metering requires an active subscription to meter against. The `current_plan_limits` that quota enforcement checks come from the subscription state maintained in Phase 4.
- **Supporting features after multi-tenancy:** OAuth, MFA, and API keys are all scoped to a tenant. They share no dependency on billing, so they can be built in parallel with Phase 4 if the team has capacity.
- **Admin last:** It queries across all domains. Building it last means complete data exists to query. Super-admin isolation is a day-one architecture decision within Phase 7, not a retrofit.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Billing Core):** Stripe Billing Meters API specifics (event format, idempotency requirements, billing period cutoff behavior post-2025-03-31 deprecation). Stripe webhook retry behavior edge cases.
- **Phase 5 (Supporting Features):** OAuth PKCE flow per-provider differences (Google `email_verified` behavior vs. GitHub's approach). Account-linking flow UX edge cases.
- **Phase 6 (Usage Metering):** Stripe Billing Meters API (same concern as Phase 4 but deeper — event submission at scale, period rollover, reconciliation with MongoDB counters).

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** FastAPI app factory, Beanie init, pydantic-settings — exhaustively documented.
- **Phase 2 (Auth Core):** PyJWT + FastAPI is the current recommended pattern per FastAPI official docs.
- **Phase 3 (Multi-Tenancy):** Logical isolation with `tenant_id` on every document is MongoDB's recommended pattern for SaaS.
- **Phase 7 (Admin):** RBAC with FastAPI dependencies is standard; super-admin audience claim separation is well-understood.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI as of 2026-02-22. Library choices grounded in official FastAPI migration guides (python-jose → PyJWT, passlib → pwdlib). No version conflicts identified. |
| Features | HIGH | Scope defined in PROJECT.md; validated against Auth0/Clerk/WorkOS feature sets and Stripe billing docs. P1/P2/P3 prioritization is opinionated but well-grounded in SaaS industry benchmarks. |
| Architecture | HIGH | Patterns verified against official FastAPI docs, Stripe docs, MongoDB multi-tenancy guide, and microservices.io JWT patterns. Code examples are concrete and consistent with stated library versions. |
| Pitfalls | HIGH | Sourced from PortSwigger (JWT confusion), OWASP (MFA), Stripe docs (webhook), MongoDB security advisories (CVE-2025-14847), and Auth0 security blog. CVE-2025-14847 is actively exploited — treat as urgent. |

**Overall confidence:** HIGH

### Gaps to Address

- **qrcode version:** Version 8.2 was sourced from search results (MEDIUM confidence), not direct PyPI fetch. Verify at project setup: `pip install "qrcode[pil]"` and check installed version.
- **Stripe Billing Meters API:** The 2025-03-31 deprecation of legacy usage records and the exact Meters API event format needs a validation pass during Phase 4 planning. The PITFALLS research confirmed this but didn't enumerate the new API request shape in detail.
- **MongoDB version constraint:** CVE-2025-14847 requires MongoDB 8.0.17+, 7.0.28+, or 6.0.27+. The project infrastructure (Docker/VPS shared with wxcode) must be verified to be running a patched version before any data is stored.
- **arq maintenance status:** arq 0.27.0 is in maintenance mode (confirmed by research). This is acceptable for the current use case, but if the project grows significantly, migration to a more actively developed queue (e.g., Celery with proper async, or a dedicated queue service) should be evaluated at 18+ months.
- **Dunning grace period:** The 7-day grace period on `invoice.payment_failed` is an industry recommendation; the exact period should be validated against the WXCODE business model during requirements (some SaaS use 3 days, others 14).

---

## Sources

### Primary (HIGH confidence)
- FastAPI official docs (fastapi.tiangolo.com) — JWT patterns, dependency injection, security
- FastAPI GitHub Discussion #11345 — python-jose deprecation rationale
- FastAPI GitHub PR #13917 — passlib → pwdlib migration
- PyPI (pypi.org) — all package versions verified February 2026
- Stripe official docs (docs.stripe.com) — webhook signature, subscriptions, Billing Meters API, Customer Portal, idempotency
- Stripe Changelog 2025-03-31 — legacy usage records deprecation
- MongoDB official docs — multi-tenancy patterns, compound index strategy
- MongoDB CVE-2025-14847 security advisory — MongoBleed, actively exploited
- OWASP Multifactor Authentication Cheat Sheet — TOTP replay protection
- PortSwigger Web Security Academy — JWT algorithm confusion, OAuth vulnerabilities
- microservices.io (2025) — JWT authorization patterns for microservices
- IETF RFC 9700 — OAuth 2.0 Security Best Current Practices
- Curity JWT Best Practices — token claims verification checklist

### Secondary (MEDIUM confidence)
- WorkOS developer guide to SaaS multi-tenant architecture — component patterns
- Stigg Blog — Stripe webhook best practices (practitioner post-mortem)
- Frontegg SaaS multitenancy blog — component decomposition
- SuperTokens RS256 vs HS256 — JWT algorithm selection
- Auth0 blog — RS256/HS256 comparison, refresh token patterns
- Authgear — common TOTP implementation mistakes
- Vitally SaaS churn benchmarks 2025 — 0.8% involuntary churn rate

### Tertiary (LOW confidence)
- qrcode 8.2 version — from search result, not direct PyPI fetch; verify at setup

---
*Research completed: 2026-02-22*
*Ready for roadmap: yes*
