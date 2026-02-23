# Roadmap: WXCODE ADM

## Overview

WXCODE ADM is built in strict dependency order: the infrastructure foundation must exist before any domain models; auth core must be live before anything else can be authenticated; multi-tenancy and RBAC must exist before billing (Stripe Customer is per-tenant); billing must be functional before plan enforcement is meaningful; platform security hardening and OAuth/MFA are layered on top of the stable auth+tenant base; user account self-service closes out the tenant-facing product; and super-admin is built last because it reads across every domain. Eight phases, zero enterprise theater — each phase delivers a coherent, verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Project scaffolding, infrastructure init, and tenant isolation base class
- [ ] **Phase 2: Auth Core** - Email/password auth, JWT RS256 issuance, JWKS endpoint, token lifecycle
- [ ] **Phase 3: Multi-Tenancy and RBAC** - Tenant creation, role enforcement, invitations, ownership transfer
- [ ] **Phase 4: Billing Core** - Stripe plans, Checkout, webhooks, Customer Portal, plan enforcement
- [ ] **Phase 5: Platform Security** - API keys, rate limiting, audit log, transactional email templates
- [ ] **Phase 6: OAuth and MFA** - Google/GitHub OAuth, TOTP MFA, remember-device, tenant MFA enforcement
- [ ] **Phase 7: User Account** - Profile editing, password change, session management, wxcode redirect
- [ ] **Phase 8: Super-Admin** - Tenant and user management, MRR dashboard, super-admin isolation

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
  6. User can reset a forgotten password via a single-use email link that expires in 1 hour
  7. The JWKS endpoint (/.well-known/jwks.json) exposes the RSA public key and wxcode can validate a token locally using that key without calling wxcode-adm
**Plans**: 5 plans

Plans:
- [ ] 02-01-PLAN.md — RSA key infrastructure, JWT RS256 signing/verification, JWKS endpoint, User model, auth exceptions, password hashing
- [ ] 02-02-PLAN.md — Sign-up endpoint, email verification (6-digit OTP via Redis + arq), super-admin seed
- [ ] 02-03-PLAN.md — Sign-in endpoint, refresh token rotation (DB storage), access token Redis blacklist, logout
- [ ] 02-04-PLAN.md — Password reset flow (itsdangerous signed link, single-use via pw_hash salt, session revocation)
- [ ] 02-05-PLAN.md — FastAPI auth dependencies (get_current_user, require_verified), Alembic migration, integration tests

### Phase 3: Multi-Tenancy and RBAC
**Goal**: Every authenticated user belongs to exactly one tenant, every action is scoped to that tenant, and roles determine what each user can do within their tenant
**Depends on**: Phase 2
**Requirements**: TNNT-01, TNNT-02, TNNT-03, TNNT-04, TNNT-05, RBAC-01, RBAC-02, RBAC-03
**Success Criteria** (what must be TRUE):
  1. When a user completes sign-up, a tenant is auto-created with a human-readable slug and the user is assigned the Owner role
  2. Tenant Owner or Admin can invite a user by email; the invited user receives an email with a 7-day expiry token and, upon accepting, is exclusively bound to that tenant
  3. The 5 RBAC roles (Owner, Admin, Developer, Viewer, Billing) are enforced on every API endpoint — a Viewer cannot perform an Admin action and receives a 403 response
  4. Owner or Admin can change any member's role or remove them from the tenant
  5. Tenant Owner can transfer ownership to another member; the previous owner's role is downgraded to Admin
  6. Every database query in the system includes tenant_id; a cross-tenant isolation test suite confirms zero data leakage between tenants
**Plans**: TBD

Plans:
- [ ] 03-01: Tenant model, TenantMembership model, slug generation, auto-create on sign-up
- [ ] 03-02: RBAC dependency (require_role), role enforcement on all existing endpoints
- [ ] 03-03: Invitation flow (email token, accept endpoint, exclusive binding)
- [ ] 03-04: Member management (change role, remove member, ownership transfer)
- [ ] 03-05: Tenant context middleware, cross-tenant isolation test suite

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
**Plans**: TBD

Plans:
- [ ] 04-01: Plan model, plan CRUD API (super-admin only), Stripe Price sync
- [ ] 04-02: Stripe Customer creation on tenant sign-up, Stripe Checkout session endpoint
- [ ] 04-03: Webhook ingestion (raw body, signature verify, idempotency, arq enqueue)
- [ ] 04-04: Webhook processors (subscription state machine, invoice events, payment_failed)
- [ ] 04-05: Stripe Customer Portal endpoint, subscription state display API
- [ ] 04-06: Plan enforcement dependency (check quota before wxcode operations, HTTP 402)

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
**Plans**: TBD

Plans:
- [ ] 05-01: API key model, key generation (wxk_live_/wxk_test_ prefix, HMAC hash), scope enforcement
- [ ] 05-02: API key revocation, rotation, listing endpoints
- [ ] 05-03: Rate limiting middleware (slowapi, Redis sliding window) on all sensitive endpoints
- [ ] 05-04: Audit log model (append-only), audit log writer, audit log query API (tenant-scoped)
- [ ] 05-05: Transactional email templates (Jinja2 HTML): verify, reset, invite, payment_failed

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
**Plans**: TBD

Plans:
- [ ] 06-01: authlib OAuth2 integration, Google sign-in (PKCE, state CSRF, email_verified check)
- [ ] 06-02: GitHub sign-in (PKCE, state CSRF, account-linking guard)
- [ ] 06-03: TOTP enrollment (pyotp, QR code, backup codes), MFA model
- [ ] 06-04: TOTP verification in login flow, backup code redemption, replay protection
- [ ] 06-05: Tenant MFA enforcement (require_mfa dependency), remember-device (30-day cookie)

### Phase 7: User Account
**Goal**: Users can manage their own profile and sessions, and are seamlessly redirected to the wxcode application after login with their access token embedded in the redirect
**Depends on**: Phase 2
**Requirements**: USER-01, USER-02, USER-03, USER-04
**Success Criteria** (what must be TRUE):
  1. User can view and update their profile (display name, email, avatar) and changes are reflected immediately in subsequent API responses
  2. User can change their password by providing their current password; the old password is rejected after the change
  3. User can view a list of their active sessions (device, IP, last active) and revoke any individual session or all sessions except the current one
  4. After a successful login, the user is redirected to the wxcode application URL with the access token embedded as a query parameter or fragment; wxcode receives a valid JWT and grants access without a second login
**Plans**: TBD

Plans:
- [ ] 07-01: User profile endpoints (GET/PATCH), avatar handling
- [ ] 07-02: Password change endpoint (current password verification, token invalidation)
- [ ] 07-03: Session listing and revocation (Redis session metadata, revoke by session ID)
- [ ] 07-04: Post-login redirect flow to wxcode with access token handoff

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
**Plans**: TBD

Plans:
- [ ] 08-01: Super-admin JWT audience (aud claim), super-admin auth dependency, IP guard
- [ ] 08-02: Tenant list, tenant suspend, tenant soft-delete endpoints
- [ ] 08-03: User list (search by email), user block, force password reset endpoints
- [ ] 08-04: MRR dashboard (Stripe subscription query, plan distribution aggregation)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 4/4 | Complete | 2026-02-22 |
| 2. Auth Core | 0/5 | Planned | - |
| 3. Multi-Tenancy and RBAC | 0/5 | Not started | - |
| 4. Billing Core | 0/6 | Not started | - |
| 5. Platform Security | 0/5 | Not started | - |
| 6. OAuth and MFA | 0/5 | Not started | - |
| 7. User Account | 0/4 | Not started | - |
| 8. Super-Admin | 0/4 | Not started | - |
