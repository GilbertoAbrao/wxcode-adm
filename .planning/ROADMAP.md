# Roadmap: WXCODE ADM

## Overview

WXCODE ADM is built in strict dependency order: the infrastructure foundation must exist before any domain models; auth core must be live before anything else can be authenticated; multi-tenancy and RBAC must exist before billing (Stripe Customer is per-tenant); billing must be functional before plan enforcement is meaningful; platform security hardening and OAuth/MFA are layered on top of the stable auth+tenant base; user account self-service closes out the tenant-facing product; and super-admin is built last because it reads across every domain. Eight phases, zero enterprise theater — each phase delivers a coherent, verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Project scaffolding, infrastructure init, and tenant isolation base class
- [x] **Phase 2: Auth Core** - Email/password auth, JWT RS256 issuance, JWKS endpoint, token lifecycle (completed 2026-02-23)
- [x] **Phase 3: Multi-Tenancy and RBAC** - Tenant creation, role enforcement, invitations, ownership transfer (completed 2026-02-23)
- [ ] **Phase 4: Billing Core** - Stripe plans, Checkout, webhooks, Customer Portal, plan enforcement
- [x] **Phase 5: Platform Security** - API keys, rate limiting, audit log, transactional email templates (completed 2026-02-24)
- [x] **Phase 6: OAuth and MFA** - Google/GitHub OAuth, TOTP MFA, remember-device, tenant MFA enforcement (completed 2026-02-24)
- [x] **Phase 7: User Account** - Profile editing, password change, session management, wxcode redirect (completed 2026-02-25)
- [x] **Phase 8: Super-Admin** - Tenant and user management, MRR dashboard, super-admin isolation (completed 2026-02-26)
- [x] **Phase 9: MFA-wxcode Redirect Fix** - Fix mfa_verify to generate wxcode redirect after TOTP verification (gap closure) (completed 2026-02-28)
- [ ] **Phase 10: API Key Management** - Tenant API keys with granular scopes, revocation, and rotation (gap closure)
- [ ] **Phase 11: Billing Integration Fixes** - Fix payment failure blacklist bug and billing admin JWT audience isolation (gap closure)

## Phase Details

### Phase 1: Foundation
**Goal**: A working FastAPI application with all infrastructure initialized, tenant isolation enforced at the data layer, and every domain ready to build on a secure, consistent base
**Depends on**: Nothing (first phase)
**Requirements**: (No direct v1 requirements — enabler for all 40)
**Success Criteria** (what must be TRUE):
  1. FastAPI application starts, health endpoint returns 200, and all infrastructure connections (PostgreSQL, Redis) are verified live
  2. SQLAlchemy 2.0 async is initialized with a TenantModel base class that structurally injects tenant_id into queries — a query without tenant_id is a runtime error, not a silent bug
  3. pydantic-settings loads all environment variables with SecretStr for credentials and raises a clear error on missing required config at startup
  4. Docker Compose brings up the full stack (FastAPI, PostgreSQL, Redis) with a single command
  5. arq worker starts and processes a test job, confirming the async task queue is operational before any email or webhook work begins
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md — Project skeleton, pyproject.toml, pydantic-settings config, SQLAlchemy engine, TenantModel, Alembic async init
- [x] 01-02-PLAN.md — FastAPI app factory with lifespan, Redis client, health endpoint, arq worker with test job
- [x] 01-03-PLAN.md — Dockerfile, docker-compose.yml, full stack verification
- [ ] 01-04-PLAN.md — Gap closure: upgrade tenant guard from WARNING to TenantIsolationError raise

### Phase 2: Auth Core
**Goal**: Users can securely create accounts, verify their identity, recover access, and receive a JWT RS256 token that wxcode can validate locally without calling wxcode-adm
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07
**Success Criteria** (what must be TRUE):
  1. User can sign up with email and password and immediately receives a 6-digit verification code by email
  2. User can verify their email by entering the 6-digit code, enabling full account access
  3. User can log in with verified email and password and receive an RS256 access token plus a refresh token
  4. User can use the refresh token to obtain a new access token; the old refresh token is revoked (rotation enforced)
  5. User can log out, invalidating their refresh token; blacklisted tokens are rejected on subsequent requests
  6. User can reset a forgotten password via a single-use email link that expires in 24 hours
  7. The JWKS endpoint (/.well-known/jwks.json) exposes the RSA public key and wxcode can validate a token locally using that key without calling wxcode-adm
**Plans**: 5 plans

Plans:
- [ ] 02-01-PLAN.md — RSA key infrastructure, JWT RS256 signing/verification, JWKS endpoint, User model, auth exceptions, password hashing
- [ ] 02-02-PLAN.md — Sign-up endpoint, email verification (6-digit OTP via Redis + arq), super-admin seed
- [ ] 02-03-PLAN.md — Sign-in endpoint, refresh token rotation (DB storage), access token Redis blacklist, logout
- [ ] 02-04-PLAN.md — Password reset flow (itsdangerous signed link, single-use via pw_hash salt, session revocation)
- [ ] 02-05-PLAN.md — FastAPI auth dependencies (get_current_user, require_verified), Alembic migration, integration tests

### Phase 3: Multi-Tenancy and RBAC
**Goal**: Every authenticated user can create or join tenants, every tenant-scoped action requires explicit tenant context via header, and per-tenant roles determine what each user can do within each tenant
**Depends on**: Phase 2
**Requirements**: TNNT-01, TNNT-02, TNNT-03, TNNT-04, TNNT-05, RBAC-01, RBAC-02, RBAC-03
**Success Criteria** (what must be TRUE):
  1. After a verified user completes the onboarding step (POST /api/v1/onboarding/workspace with a workspace name), a tenant is created with an auto-generated permanent slug and the user is assigned the Owner role
  2. Tenant Owner or Admin can invite a user by email; the invited user receives an email with a 7-day expiry token; existing users accept via POST /invitations/accept, new users auto-join after completing sign-up and email verification (no separate accept step); the user gains membership in the inviting tenant (multiple concurrent memberships supported)
  3. The 4 RBAC roles (Owner, Admin, Developer, Viewer) plus billing_access toggle are enforced on every API endpoint — a Viewer cannot perform an Admin action and receives a 403 response
  4. Owner or Admin can change any member's role or remove them from the tenant
  5. Tenant Owner can transfer ownership to another member; the previous owner's role is downgraded to Admin
  6. Every database query in the system includes tenant_id; a cross-tenant isolation test suite confirms zero data leakage between tenants
**Plans**: 5 plans

Plans:
- [ ] 03-01-PLAN.md — Tenant, TenantMembership, Invitation, OwnershipTransfer models, MemberRole enum, domain exceptions, Pydantic schemas
- [ ] 03-02-PLAN.md — Tenant context dependency (X-Tenant-ID header), require_role RBAC factory, onboarding workspace endpoint, tenant info endpoints
- [ ] 03-03-PLAN.md — Invitation flow (itsdangerous token, invite by email, accept endpoint, arq email job)
- [ ] 03-04-PLAN.md — Member management (change role, remove, leave tenant), ownership transfer (request + accept)
- [ ] 03-05-PLAN.md — Alembic migration 002, integration tests for all 6 success criteria, cross-tenant isolation test suite

**Phase requirement IDs (every ID MUST appear in a plan's `requirements` field):** TNNT-01, TNNT-02, TNNT-03, TNNT-04, TNNT-05, RBAC-01, RBAC-02, RBAC-03

### Phase 4: Billing Core
**Goal**: Tenants can subscribe to a paid plan, manage their billing, and the system enforces plan limits before any wxcode engine operation is allowed
**Depends on**: Phase 3
**Requirements**: BILL-01, BILL-02, BILL-03, BILL-04, BILL-05
**Success Criteria** (what must be TRUE):
  1. Super-admin can create, update, and delete billing plans with limits; each plan is synced to a Stripe Price and the catalog is the single source of truth for plan definitions
  2. User can subscribe to a plan by clicking through Stripe Checkout and arriving back at the app with an active subscription reflected immediately
  3. When Stripe delivers a webhook event (subscription.updated, invoice.paid, invoice.payment_failed, subscription.deleted), the subscription state in the database is updated correctly within one webhook delivery — no polling required
  4. User can open the Stripe Customer Portal from within the app and manage their subscription, payment method, and invoices without contacting support
  5. When a tenant exceeds their plan's limits, the API returns HTTP 402 with a clear message before passing the request to the wxcode engine — no wxcode engine operation runs over-limit
**Plans**: 5 plans

Plans:
- [ ] 04-01-PLAN.md — Stripe SDK + config, billing models (Plan, TenantSubscription, WebhookEvent), exceptions, stripe_client singleton, plan CRUD API (super-admin), Stripe Price/Meter sync
- [ ] 04-02-PLAN.md — Stripe Customer creation at workspace onboarding, free plan bootstrap, Stripe Checkout session endpoint
- [ ] 04-03-PLAN.md — Webhook ingestion (raw body, signature verify, arq enqueue with _job_id dedup), webhook processors (subscription state machine, payment failure + JWT revocation + email)
- [ ] 04-04-PLAN.md — Customer Portal session endpoint, subscription status API, plan enforcement dependencies (active subscription, token quota, member cap)
- [ ] 04-05-PLAN.md — Alembic migration 003, conftest billing imports + Stripe mocks, integration tests for all 5 success criteria

**Phase requirement IDs (every ID MUST appear in a plan's `requirements` field):** BILL-01, BILL-02, BILL-03, BILL-04, BILL-05

### Phase 5: Platform Security
**Goal**: Every sensitive API surface has rate limiting, every significant action is recorded in an immutable audit log, tenants have programmable API access with scoped keys, and all transactional emails are delivered via templated, tracked messages
**Depends on**: Phase 3
**Requirements**: PLAT-01, PLAT-02, PLAT-03, PLAT-04, PLAT-05
**Success Criteria** (what must be TRUE):
  1. Tenant Owner or Admin can generate an API key with a chosen scope (read, write, admin, billing); the key is shown once in full and stored as an HMAC hash; subsequent requests use the hashed value for lookup
  2. Tenant Owner or Admin can revoke any API key or rotate it (revoke + generate replacement) and all requests using the revoked key are rejected immediately
  3. Login, sign-up, and password reset endpoints reject requests over their rate limits (Redis sliding window) with a 429 response; limits persist across restarts because they live in Redis
  4. Every sensitive action (login, role change, invitation, API key creation/revocation, billing change, admin action) is written to an append-only audit log that cannot be modified or deleted by tenant users
  5. Users receive well-formatted HTML email for each transactional event: email verification, password reset, member invitation, and payment failure notification
**Plans**: 4 plans

NOTE: PLAT-01 and PLAT-02 (API key management) are DEFERRED to a future phase per user decision.

Plans:
- [ ] 05-01-PLAN.md — Rate limiting middleware (slowapi, Redis sliding window) on auth + all authenticated endpoints
- [ ] 05-02-PLAN.md — Audit log model (append-only), write_audit helper, super-admin query API, arq cron retention purge
- [ ] 05-03-PLAN.md — Transactional email templates (Jinja2 HTML + plain-text): verify, reset, invite, payment_failed; shared FastMail singleton
- [ ] 05-04-PLAN.md — Alembic migration 004, integration tests for PLAT-03, PLAT-04, PLAT-05

### Phase 6: OAuth and MFA
**Goal**: Users can authenticate with Google or GitHub without creating a password, and tenants can require two-factor authentication for all members
**Depends on**: Phase 3
**Requirements**: AUTH-08, AUTH-09, AUTH-10, AUTH-11, AUTH-12, AUTH-13
**Success Criteria** (what must be TRUE):
  1. User can sign in with Google (OAuth 2.0 PKCE) and land in the app with a valid JWT; a new account is created on first sign-in, an existing matching account is not auto-linked by email alone
  2. User can sign in with GitHub (OAuth 2.0 PKCE) under the same conditions and protections as Google
  3. User can enable MFA by scanning a QR code in an authenticator app and saving backup codes; enrollment is confirmed by entering a valid TOTP code
  4. When MFA is enabled on the account, the login flow prompts for a TOTP code after password validation and rejects login without a valid code or backup code
  5. Tenant Owner can enforce MFA for all tenant members; members without MFA set up are prompted to enroll before completing login
  6. User can mark a device as trusted for 30 days; trusted devices skip the TOTP prompt until the trust period expires
**Plans**: 5 plans

**Phase requirement IDs (every ID MUST appear in a plan's `requirements` field):** AUTH-08, AUTH-09, AUTH-10, AUTH-11, AUTH-12, AUTH-13

Plans:
- [x] 06-01-PLAN.md — Foundation (deps, models, oauth registry, SessionMiddleware) + Google/GitHub OAuth sign-in
- [ ] 06-02-PLAN.md — TOTP MFA enrollment (pyotp, QR code, backup codes, enable/disable)
- [ ] 06-03-PLAN.md — Two-stage MFA login, TOTP verification, backup code redemption, trusted device cookie
- [ ] 06-04-PLAN.md — Tenant MFA enforcement toggle, session revocation, OAuth-only user flows
- [ ] 06-05-PLAN.md — Alembic migration 005, integration tests for all 6 success criteria

### Phase 7: User Account
**Goal**: Users can manage their own profile and sessions, and are seamlessly redirected to the wxcode application after login with their access token embedded in the redirect
**Depends on**: Phase 2
**Requirements**: USER-01, USER-02, USER-03, USER-04
**Success Criteria** (what must be TRUE):
  1. User can view and update their profile (display name, email, avatar) and changes are reflected immediately in subsequent API responses
  2. User can change their password by providing their current password; the old password is rejected after the change
  3. User can view a list of their active sessions (device, IP, last active) and revoke any individual session or all sessions except the current one
  4. After a successful login, the user is redirected to the wxcode application URL with the access token embedded as a query parameter or fragment; wxcode receives a valid JWT and grants access without a second login
**Plans**: 4 plans

**Phase requirement IDs (every ID MUST appear in a plan's `requirements` field):** USER-01, USER-02, USER-03, USER-04

Plans:
- [ ] 07-01-PLAN.md — UserSession model, new User/Tenant columns, _issue_tokens session metadata persistence, per-request last_active tracking
- [ ] 07-02-PLAN.md — User profile endpoints (GET/PATCH /users/me), avatar upload, password change with session invalidation
- [ ] 07-03-PLAN.md — Session listing and revocation endpoints, wxcode one-time code exchange redirect flow
- [ ] 07-04-PLAN.md — Alembic migration 006, integration tests for all 4 success criteria

### Phase 8: Super-Admin
**Goal**: The platform super-admin (Gilberto) can view, suspend, and manage all tenants and users across the platform, and has a live MRR dashboard to track revenue health — all through endpoints isolated from the tenant-facing API
**Depends on**: Phase 4, Phase 5
**Requirements**: SADM-01, SADM-02, SADM-03, SADM-04, SADM-05
**Success Criteria** (what must be TRUE):
  1. Super-admin can list all tenants with pagination, filtering by plan and status, and see member count and current plan for each tenant
  2. Super-admin can suspend a tenant (all member logins rejected with a clear "account suspended" message) or soft-delete it; both actions are recorded in the audit log
  3. Super-admin can search users by email, view their tenant membership and account status, block a user (immediate session invalidation), or force a password reset
  4. Super-admin MRR dashboard shows active subscription count, monthly recurring revenue, and plan distribution, all derived from live Stripe subscription data
  5. Super-admin endpoints are protected by a separate JWT audience claim (aud: "wxcode-adm-admin") and reject any token issued for tenant users — tenant JWTs cannot access admin endpoints even with correct credentials
**Plans**: 4 plans

**Phase requirement IDs (every ID MUST appear in a plan's `requirements` field):** SADM-01, SADM-02, SADM-03, SADM-04, SADM-05

Plans:
- [ ] 08-01-PLAN.md — Admin module foundation: JWT audience isolation (aud claim), require_admin dependency, IP allowlist guard, admin login/refresh/logout, enforcement hooks in get_tenant_context and get_current_user
- [ ] 08-02-PLAN.md — Tenant management: list tenants (paginated, filtered by plan/status), tenant detail, suspend with session invalidation, reactivate, soft-delete
- [ ] 08-03-PLAN.md — User management: search users (email/name/tenant filter), user detail with memberships and sessions, per-tenant block/unblock, force password reset
- [ ] 08-04-PLAN.md — MRR dashboard (on-demand aggregation from local DB), Alembic migration 007, integration tests for all 5 success criteria

### Phase 9: MFA-wxcode Redirect Fix
**Goal**: MFA-authenticated users receive the same wxcode redirect URL and one-time code as non-MFA users, ensuring all login paths lead to seamless wxcode handoff
**Depends on**: Phase 6, Phase 7
**Requirements**: USER-04 (strengthened), AUTH-11 (strengthened)
**Gap Closure**: Closes integration gap (Phase 6 → Phase 7) and flow gap ("MFA login → wxcode redirect") from v1.0 audit
**Success Criteria** (what must be TRUE):
  1. After TOTP verification via POST /auth/mfa/verify, the response includes wxcode_redirect_url and wxcode_code when the user's tenant has a wxcode_url configured — identical to the non-MFA login path
  2. The one-time wxcode_code from MFA verify can be exchanged at the wxcode exchange endpoint and returns a valid access token
**Plans**: 1 plan

Plans:
- [ ] 09-01-PLAN.md — Fix mfa_verify to call get_redirect_url + create_wxcode_code after _issue_tokens, integration test for MFA → wxcode redirect flow

### Phase 10: API Key Management
**Goal**: Tenants have programmable API access via scoped keys that can be created, listed, revoked, and rotated by Owner or Admin
**Depends on**: Phase 3, Phase 5
**Requirements**: PLAT-01, PLAT-02
**Gap Closure**: Closes deferred requirements PLAT-01 and PLAT-02 from v1.0 audit
**Success Criteria** (what must be TRUE):
  1. Tenant Owner or Admin can generate an API key with a chosen scope (read, write, admin, billing); the key is shown once in full and stored as an HMAC hash; subsequent requests use the hashed value for lookup
  2. Tenant Owner or Admin can list active API keys (masked, showing scope and creation date) and revoke any key; all requests using the revoked key are rejected immediately
  3. Tenant Owner or Admin can rotate a key (atomic revoke + generate replacement) and the new key is returned in the response
  4. API key authentication is accepted as an alternative to JWT Bearer tokens on tenant-scoped endpoints; the key's scope restricts which endpoints are accessible
**Plans**: 1 plan

Plans:
- [ ] 10-01-PLAN.md — APIKey model, HMAC hashing, CRUD endpoints, key auth middleware, Alembic migration 008, integration tests for PLAT-01 and PLAT-02

**Phase requirement IDs (every ID MUST appear in a plan's `requirements` field):** PLAT-01, PLAT-02

### Phase 11: Billing Integration Fixes
**Goal**: Payment failure webhook correctly revokes all active access tokens, and billing admin routes enforce admin JWT audience isolation — closing the two integration gaps found in the v1.0 audit
**Depends on**: Phase 4, Phase 8
**Requirements**: BILL-01 (strengthened), BILL-03 (strengthened), BILL-05 (strengthened)
**Gap Closure**: Closes INT-01 (critical: payment failure blacklist bug), INT-02 (medium: billing admin JWT bypass), and flow gap #8 from v1.0 audit
**Success Criteria** (what must be TRUE):
  1. When `_handle_payment_failed` runs, it queries `UserSession.access_token_jti` for each affected user and calls `blacklist_jti(redis, jti)` — the same pattern used in `admin/service.py:suspend_tenant`; existing access tokens are immediately invalidated
  2. All billing admin routes (plan CRUD) use `require_admin` from `admin/dependencies.py` instead of local `require_superuser` — a regular user JWT (even with `is_superuser=True`) receives 401/403 on admin billing endpoints
  3. Integration test verifies E2E flow #8: payment failure webhook → subscription PAST_DUE → access tokens blacklisted → member blocked on platform-level endpoints
**Plans**: 1 plan

Plans:
- [ ] 11-01-PLAN.md — Fix _handle_payment_failed blacklist (use UserSession.access_token_jti), replace require_superuser with require_admin on billing admin routes, integration tests for INT-01 and INT-02

**Phase requirement IDs (every ID MUST appear in a plan's `requirements` field):** BILL-01, BILL-03, BILL-05

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 4/4 | Complete | 2026-02-22 |
| 2. Auth Core | 5/5 | Complete   | 2026-02-23 |
| 3. Multi-Tenancy and RBAC | 5/5 | Complete    | 2026-02-23 |
| 4. Billing Core | 4/5 | In Progress|  |
| 5. Platform Security | 4/4 | Complete    | 2026-02-24 |
| 6. OAuth and MFA | 4/5 | Complete    | 2026-02-24 |
| 7. User Account | 4/4 | Complete    | 2026-02-25 |
| 8. Super-Admin | 4/4 | Complete   | 2026-02-26 |
| 9. MFA-wxcode Redirect Fix | 1/1 | Complete   | 2026-02-28 |
| 10. API Key Management | 0/1 | Pending | |
| 11. Billing Integration Fixes | 0/1 | Pending | |
