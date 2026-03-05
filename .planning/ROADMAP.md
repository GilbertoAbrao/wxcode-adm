# Roadmap: WXCODE ADM

## Milestones

- ✅ **v1.0 Backend API** - Phases 1-11 (shipped 2026-03-04)
- 🚧 **v2.0 Frontend UI** - Phases 12-17 (in progress)

## Phases

<details>
<summary>✅ v1.0 Backend API (Phases 1-11) - SHIPPED 2026-03-04</summary>

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
- [x] 01-04-PLAN.md — Gap closure: upgrade tenant guard from WARNING to TenantIsolationError raise

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
- [x] 02-01-PLAN.md — RSA key infrastructure, JWT RS256 signing/verification, JWKS endpoint, User model, auth exceptions, password hashing
- [x] 02-02-PLAN.md — Sign-up endpoint, email verification (6-digit OTP via Redis + arq), super-admin seed
- [x] 02-03-PLAN.md — Sign-in endpoint, refresh token rotation (DB storage), access token Redis blacklist, logout
- [x] 02-04-PLAN.md — Password reset flow (itsdangerous signed link, single-use via pw_hash salt, session revocation)
- [x] 02-05-PLAN.md — FastAPI auth dependencies (get_current_user, require_verified), Alembic migration, integration tests

### Phase 3: Multi-Tenancy and RBAC
**Goal**: Every authenticated user can create or join tenants, every tenant-scoped action requires explicit tenant context via header, and per-tenant roles determine what each user can do within each tenant
**Depends on**: Phase 2
**Requirements**: TNNT-01, TNNT-02, TNNT-03, TNNT-04, TNNT-05, RBAC-01, RBAC-02, RBAC-03
**Success Criteria** (what must be TRUE):
  1. After a verified user completes the onboarding step, a tenant is created with an auto-generated permanent slug and the user is assigned the Owner role
  2. Tenant Owner or Admin can invite a user by email; the invited user receives an email with a 7-day expiry token
  3. The 4 RBAC roles (Owner, Admin, Developer, Viewer) plus billing_access toggle are enforced on every API endpoint
  4. Owner or Admin can change any member's role or remove them from the tenant
  5. Tenant Owner can transfer ownership to another member; the previous owner's role is downgraded to Admin
  6. Every database query in the system includes tenant_id; a cross-tenant isolation test suite confirms zero data leakage between tenants
**Plans**: 5 plans

Plans:
- [x] 03-01-PLAN.md — Tenant, TenantMembership, Invitation, OwnershipTransfer models, MemberRole enum, domain exceptions, Pydantic schemas
- [x] 03-02-PLAN.md — Tenant context dependency (X-Tenant-ID header), require_role RBAC factory, onboarding workspace endpoint, tenant info endpoints
- [x] 03-03-PLAN.md — Invitation flow (itsdangerous token, invite by email, accept endpoint, arq email job)
- [x] 03-04-PLAN.md — Member management (change role, remove, leave tenant), ownership transfer (request + accept)
- [x] 03-05-PLAN.md — Alembic migration 002, integration tests for all 6 success criteria, cross-tenant isolation test suite

### Phase 4: Billing Core
**Goal**: Tenants can subscribe to a paid plan, manage their billing, and the system enforces plan limits before any wxcode engine operation is allowed
**Depends on**: Phase 3
**Requirements**: BILL-01, BILL-02, BILL-03, BILL-04, BILL-05
**Success Criteria** (what must be TRUE):
  1. Super-admin can create, update, and delete billing plans with limits; each plan is synced to a Stripe Price and the catalog is the single source of truth for plan definitions
  2. User can subscribe to a plan by clicking through Stripe Checkout and arriving back at the app with an active subscription reflected immediately
  3. When Stripe delivers a webhook event (subscription.updated, invoice.paid, invoice.payment_failed, subscription.deleted), the subscription state in the database is updated correctly within one webhook delivery
  4. User can open the Stripe Customer Portal from within the app and manage their subscription, payment method, and invoices without contacting support
  5. When a tenant exceeds their plan's limits, the API returns HTTP 402 with a clear message before passing the request to the wxcode engine
**Plans**: 5 plans

Plans:
- [x] 04-01-PLAN.md — Stripe SDK + config, billing models, exceptions, stripe_client singleton, plan CRUD API (super-admin), Stripe Price/Meter sync
- [x] 04-02-PLAN.md — Stripe Customer creation at workspace onboarding, free plan bootstrap, Stripe Checkout session endpoint
- [x] 04-03-PLAN.md — Webhook ingestion (raw body, signature verify, arq enqueue with _job_id dedup), webhook processors
- [x] 04-04-PLAN.md — Customer Portal session endpoint, subscription status API, plan enforcement dependencies
- [x] 04-05-PLAN.md — Alembic migration 003, conftest billing imports + Stripe mocks, integration tests for all 5 success criteria

### Phase 5: Platform Security
**Goal**: Every sensitive API surface has rate limiting, every significant action is recorded in an immutable audit log, and all transactional emails are delivered via templated, tracked messages
**Depends on**: Phase 3
**Requirements**: PLAT-03, PLAT-04, PLAT-05
**Success Criteria** (what must be TRUE):
  1. Login, sign-up, and password reset endpoints reject requests over their rate limits with a 429 response
  2. Every sensitive action is written to an append-only audit log that cannot be modified or deleted by tenant users
  3. Users receive well-formatted HTML email for each transactional event: email verification, password reset, member invitation, and payment failure notification
**Plans**: 4 plans

Plans:
- [x] 05-01-PLAN.md — Rate limiting middleware (slowapi, Redis sliding window) on auth + all authenticated endpoints
- [x] 05-02-PLAN.md — Audit log model (append-only), write_audit helper, super-admin query API, arq cron retention purge
- [x] 05-03-PLAN.md — Transactional email templates (Jinja2 HTML + plain-text): verify, reset, invite, payment_failed; shared FastMail singleton
- [x] 05-04-PLAN.md — Alembic migration 004, integration tests for PLAT-03, PLAT-04, PLAT-05

### Phase 6: OAuth and MFA
**Goal**: Users can authenticate with Google or GitHub without creating a password, and tenants can require two-factor authentication for all members
**Depends on**: Phase 3
**Requirements**: AUTH-08, AUTH-09, AUTH-10, AUTH-11, AUTH-12, AUTH-13
**Success Criteria** (what must be TRUE):
  1. User can sign in with Google (OAuth 2.0 PKCE) and land in the app with a valid JWT
  2. User can sign in with GitHub (OAuth 2.0 PKCE) under the same conditions and protections as Google
  3. User can enable MFA by scanning a QR code in an authenticator app and saving backup codes
  4. When MFA is enabled on the account, the login flow prompts for a TOTP code after password validation
  5. Tenant Owner can enforce MFA for all tenant members
  6. User can mark a device as trusted for 30 days; trusted devices skip the TOTP prompt until the trust period expires
**Plans**: 5 plans

Plans:
- [x] 06-01-PLAN.md — Foundation (deps, models, oauth registry, SessionMiddleware) + Google/GitHub OAuth sign-in
- [x] 06-02-PLAN.md — TOTP MFA enrollment (pyotp, QR code, backup codes, enable/disable)
- [x] 06-03-PLAN.md — Two-stage MFA login, TOTP verification, backup code redemption, trusted device cookie
- [x] 06-04-PLAN.md — Tenant MFA enforcement toggle, session revocation, OAuth-only user flows
- [x] 06-05-PLAN.md — Alembic migration 005, integration tests for all 6 success criteria

### Phase 7: User Account
**Goal**: Users can manage their own profile and sessions, and are seamlessly redirected to the wxcode application after login with their access token embedded in the redirect
**Depends on**: Phase 2
**Requirements**: USER-01, USER-02, USER-03, USER-04
**Success Criteria** (what must be TRUE):
  1. User can view and update their profile (display name, email, avatar) and changes are reflected immediately in subsequent API responses
  2. User can change their password by providing their current password; the old password is rejected after the change
  3. User can view a list of their active sessions (device, IP, last active) and revoke any individual session or all sessions except the current one
  4. After a successful login, the user is redirected to the wxcode application URL with the access token embedded; wxcode receives a valid JWT and grants access without a second login
**Plans**: 4 plans

Plans:
- [x] 07-01-PLAN.md — UserSession model, new User/Tenant columns, _issue_tokens session metadata persistence, per-request last_active tracking
- [x] 07-02-PLAN.md — User profile endpoints (GET/PATCH /users/me), avatar upload, password change with session invalidation
- [x] 07-03-PLAN.md — Session listing and revocation endpoints, wxcode one-time code exchange redirect flow
- [x] 07-04-PLAN.md — Alembic migration 006, integration tests for all 4 success criteria

### Phase 8: Super-Admin
**Goal**: The platform super-admin can view, suspend, and manage all tenants and users across the platform, and has a live MRR dashboard to track revenue health
**Depends on**: Phase 4, Phase 5
**Requirements**: SADM-01, SADM-02, SADM-03, SADM-04, SADM-05
**Success Criteria** (what must be TRUE):
  1. Super-admin can list all tenants with pagination, filtering by plan and status, and see member count and current plan for each tenant
  2. Super-admin can suspend a tenant (all member logins rejected) or soft-delete it; both actions are recorded in the audit log
  3. Super-admin can search users by email, view their tenant membership and account status, block a user, or force a password reset
  4. Super-admin MRR dashboard shows active subscription count, monthly recurring revenue, and plan distribution
  5. Super-admin endpoints are protected by a separate JWT audience claim and reject any token issued for tenant users
**Plans**: 4 plans

Plans:
- [x] 08-01-PLAN.md — Admin module foundation: JWT audience isolation (aud claim), require_admin dependency, IP allowlist guard, admin login/refresh/logout
- [x] 08-02-PLAN.md — Tenant management: list tenants (paginated, filtered by plan/status), tenant detail, suspend, reactivate, soft-delete
- [x] 08-03-PLAN.md — User management: search users, user detail with memberships and sessions, per-tenant block/unblock, force password reset
- [x] 08-04-PLAN.md — MRR dashboard, Alembic migration 007, integration tests for all 5 success criteria

### Phase 9: MFA-wxcode Redirect Fix
**Goal**: MFA-authenticated users receive the same wxcode redirect URL and one-time code as non-MFA users, ensuring all login paths lead to seamless wxcode handoff
**Depends on**: Phase 6, Phase 7
**Requirements**: USER-04 (strengthened), AUTH-11 (strengthened)
**Success Criteria** (what must be TRUE):
  1. After TOTP verification via POST /auth/mfa/verify, the response includes wxcode_redirect_url and wxcode_code when the user's tenant has a wxcode_url configured
  2. The one-time wxcode_code from MFA verify can be exchanged at the wxcode exchange endpoint and returns a valid access token
**Plans**: 1 plan

Plans:
- [x] 09-01-PLAN.md — Fix mfa_verify to call get_redirect_url + create_wxcode_code after _issue_tokens, integration test for MFA → wxcode redirect flow

### Phase 10: API Key Management
**Goal**: Tenants have programmable API access via scoped keys that can be created, listed, revoked, and rotated by Owner or Admin
**Depends on**: Phase 3, Phase 5
**Requirements**: PLAT-01, PLAT-02
**Success Criteria** (what must be TRUE):
  1. Tenant Owner or Admin can generate an API key with a chosen scope (read, write, admin, billing); the key is shown once in full and stored as an HMAC hash
  2. Tenant Owner or Admin can list active API keys (masked, showing scope and creation date) and revoke any key; all requests using the revoked key are rejected immediately
  3. Tenant Owner or Admin can rotate a key (atomic revoke + generate replacement)
  4. API key authentication is accepted as an alternative to JWT Bearer tokens on tenant-scoped endpoints
**Plans**: 1 plan

Plans:
- [ ] 10-01-PLAN.md — APIKey model, HMAC hashing, CRUD endpoints, key auth middleware, Alembic migration 008, integration tests for PLAT-01 and PLAT-02

### Phase 11: Billing Integration Fixes
**Goal**: Payment failure webhook correctly revokes all active access tokens, and billing admin routes enforce admin JWT audience isolation
**Depends on**: Phase 4, Phase 8
**Requirements**: BILL-01 (strengthened), BILL-03 (strengthened), BILL-05 (strengthened)
**Success Criteria** (what must be TRUE):
  1. When _handle_payment_failed runs, it queries UserSession.access_token_jti for each affected user and calls blacklist_jti(redis, jti) — existing access tokens are immediately invalidated
  2. All billing admin routes use require_admin from admin/dependencies.py — a regular user JWT receives 401/403 on admin billing endpoints
  3. Integration test verifies E2E flow: payment failure webhook → subscription PAST_DUE → access tokens blacklisted → member blocked on platform-level endpoints
**Plans**: 1 plan

Plans:
- [x] 11-01-PLAN.md — Fix _handle_payment_failed blacklist, replace require_superuser with require_admin on billing admin routes, integration tests for INT-01 and INT-02

</details>

---

### v2.0 Frontend UI (In Progress)

**Milestone Goal:** Criar toda a interface web do wxcode-adm — auth flows, gestao de tenant, billing, user account e super-admin panel — usando a mesma identidade visual (Obsidian Studio) do wxcode frontend. Stack: Next.js 16, React 19, Tailwind CSS v4, shadcn/ui (new-york), TypeScript, TanStack React Query.

## Phase Details

### Phase 12: Design System Foundation
**Goal**: A working Next.js frontend project exists with the Obsidian Studio visual identity fully applied — design tokens, custom components, and app shell — so every subsequent phase builds on a consistent, production-ready UI base
**Depends on**: Nothing (first v2 phase; backend API at localhost:8040 already exists)
**Requirements**: DS-01, DS-02, DS-03
**Success Criteria** (what must be TRUE):
  1. Running `pnpm dev` starts the Next.js app without errors and the root page renders in a browser with the Obsidian Studio dark theme applied (deep dark background, correct color tokens)
  2. GlowButton, GlowInput, LoadingSkeleton, EmptyState, ErrorState, and AnimatedList components are importable from the component library and render correctly with their Obsidian Studio styles in a browser
  3. The app shell layout displays a sidebar navigation on desktop, collapses to a hamburger on mobile, and enforces dark mode globally (no light mode flash or fallback)
  4. Tailwind CSS v4, shadcn/ui (new-york), and TypeScript path aliases (@/) resolve correctly with no build errors
**Plans**: 3 plans

Plans:
- [x] 12-01-PLAN.md — Next.js 16 project init with pnpm, Tailwind CSS v4, shadcn/ui new-york config, TypeScript path aliases, dev server boot
- [x] 12-02-PLAN.md — Port Obsidian Studio theme (globals.css, design tokens) and 6 custom components (GlowButton, GlowInput, LoadingSkeleton, EmptyState, ErrorState, AnimatedList) from wxcode frontend
- [x] 12-03-PLAN.md — App shell layout (responsive sidebar navigation, dark mode enforced), TanStack React Query provider, visual verification

### Phase 13: Auth Flows UI
**Goal**: A user arriving at the wxcode-adm URL can complete the full authentication journey — sign up, verify email, log in, reset password, handle MFA, create their workspace, and land in the wxcode app — entirely through the UI with no manual API calls
**Depends on**: Phase 12
**Requirements**: AUI-01, AUI-02, AUI-03, AUI-04, AUI-05, AUI-06, AUI-07
**Success Criteria** (what must be TRUE):
  1. User can fill in the signup form with email and password, submit, and arrive at an email verification page — form validation rejects invalid emails and weak passwords inline
  2. User can enter the 6-digit OTP code received by email on the verification page and proceed to the workspace onboarding page
  3. User can fill in a workspace name on the onboarding page and submit to create their tenant, then be redirected into the authenticated area
  4. User can log in with their email and password via the login form and be redirected to the wxcode app URL with the access token embedded
  5. When MFA is enabled on the account, the login flow shows a TOTP input step after password validation; user can enter a backup code as fallback
  6. User can request a password reset by entering their email, receive a reset link, click it, and set a new password — the form enforces password confirmation match
**Plans**: 4 plans

Plans:
- [ ] 13-01-PLAN.md — API client (typed fetch wrapper), auth token management (in-memory), AuthProvider context, TanStack Query auth hooks, (auth) route group layout, react-hook-form + zod install
- [ ] 13-02-PLAN.md — Signup page and login page with react-hook-form + zod validation, shared validation schemas, MFA branching, wxcode redirect handling
- [ ] 13-03-PLAN.md — Email verification page (6-digit OTP input, resend with cooldown), forgot password page, reset password page (new password + confirmation)
- [ ] 13-04-PLAN.md — MFA verify page (TOTP input, backup code fallback, trust device), workspace onboarding page (create workspace name)

### Phase 14: User Account UI
**Goal**: An authenticated user can view and manage their profile, change their password, and see and revoke active sessions entirely through the UI
**Depends on**: Phase 13
**Requirements**: UAI-01, UAI-02, UAI-03
**Success Criteria** (what must be TRUE):
  1. User can navigate to account settings, see their current display name and avatar, edit the display name inline, and upload a new avatar — changes persist after page refresh
  2. User can change their password by entering the current password and a new password with confirmation; an incorrect current password shows an inline error
  3. User can see a list of all active sessions showing device, IP, and last active time; clicking "Revoke" on any session removes it from the list immediately
**Plans**: 2 plans

Plans:
- [ ] 14-01-PLAN.md — useUserAccount hooks (profile, avatar, password, sessions) + account page profile section
- [ ] 14-02-PLAN.md — Password change form + sessions list with revocation UI

### Phase 15: Tenant Management UI
**Goal**: A Tenant Owner or Admin can manage workspace membership — inviting new members, adjusting roles, removing members, and toggling MFA enforcement — entirely through the UI
**Depends on**: Phase 13
**Requirements**: TMI-01, TMI-02, TMI-03
**Success Criteria** (what must be TRUE):
  1. Owner or Admin can view the full member list with each member's display name, email, role, and invitation status; the list updates after inviting a new member by email
  2. Owner or Admin can change a member's role via a dropdown and remove a member from the workspace; removed members disappear from the list immediately
  3. Tenant Owner can toggle MFA enforcement on or off for the workspace; the toggle reflects the current enforcement state on page load
**Plans**: 3 plans

Plans:
- [x] 15-01-PLAN.md — TanStack Query hooks for tenant endpoints (X-Tenant-ID header injection), /team page with member list (AnimatedList), invite member form
- [x] 15-02-PLAN.md — Role change dropdown, remove member action with confirmation, MFA enforcement toggle for Owner
- [ ] 15-03-PLAN.md — Gap closure: expose mfa_enforced in GET /tenants/me, seed MFA toggle from API data on page load

### Phase 16: Billing UI
**Goal**: A user with billing access can view their current plan, subscribe or upgrade via Stripe Checkout, and access the Stripe Customer Portal for invoice and payment management — all through the UI
**Depends on**: Phase 13
**Requirements**: BUI-01, BUI-02, BUI-03
**Success Criteria** (what must be TRUE):
  1. User with billing access can navigate to the billing page and see their current plan name, status (active, past_due, canceled), and renewal date
  2. User can view available plans, click "Subscribe" or "Upgrade", and be redirected to Stripe Checkout; after completing payment, they return to the billing page with the updated plan reflected
  3. User can click "Manage Billing" and be redirected to the Stripe Customer Portal where they can update payment methods and download invoices
**Plans**: 2 plans

Plans:
- [ ] 16-01: Billing page layout, current subscription display, plan catalog with plan cards (GlowButton CTAs)
- [ ] 16-02: Stripe Checkout redirect flow, Customer Portal redirect, subscription status polling after checkout return

### Phase 17: Super-Admin UI
**Goal**: The platform super-admin can log in via a dedicated admin portal, manage tenants and users across the platform, and take moderation actions — all through a UI isolated from the tenant-facing application
**Depends on**: Phase 12
**Requirements**: SAI-01, SAI-02, SAI-03
**Success Criteria** (what must be TRUE):
  1. Admin can navigate to /admin/login, enter credentials, and be authenticated with an admin-audience JWT; regular user credentials are rejected on the admin login page
  2. Admin can view a paginated tenant list, filter by plan and status, and suspend or reactivate a tenant — the tenant's status updates in the list immediately after the action
  3. Admin can search users by email, view user details (membership, account status), and block or unblock a user — the user's blocked status updates immediately after the action
**Plans**: 2 plans

Plans:
- [ ] 17-01: Admin section routing (/admin/*), admin login page with admin-audience JWT auth, admin route protection, admin API client hooks
- [ ] 17-02: Tenant list page (paginated, plan/status filters, suspend/reactivate actions)
- [ ] 17-03: User search page (email search, user detail drawer, block/unblock actions)

## Progress

**Execution Order:**
v2.0 phases execute in numeric order: 12 → 13 → 14 → 15 → 16 → 17
(Phase 17 depends only on Phase 12 for the design system; can be done in any order relative to 14-16)

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
| 13. Auth Flows UI | 4/4 | Complete    | 2026-03-04 | - |
| 14. User Account UI | 2/2 | Complete    | 2026-03-05 | - |
| 15. Tenant Management UI | v2.0 | 2/2 | Complete | 2026-03-05 |
| 16. Billing UI | v2.0 | 0/2 | Not started | - |
| 17. Super-Admin UI | v2.0 | 0/3 | Not started | - |
