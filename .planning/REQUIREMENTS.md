# Requirements: WXCODE ADM

**Defined:** 2026-02-22
**Core Value:** Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Authentication

- [x] **AUTH-01**: User can sign up with email and password
- [x] **AUTH-02**: User receives 6-digit verification code by email after signup
- [x] **AUTH-03**: User can verify email entering the 6-digit code
- [x] **AUTH-04**: User can reset password via email link
- [x] **AUTH-05**: User receives JWT RS256 access token + refresh token on login
- [x] **AUTH-06**: Refresh token rotation with revocation on logout
- [x] **AUTH-07**: JWKS endpoint exposes public key for wxcode to validate tokens locally
- [x] **AUTH-08**: User can sign in with Google via OAuth 2.0 (PKCE)
- [x] **AUTH-09**: User can sign in with GitHub via OAuth 2.0 (PKCE)
- [x] **AUTH-10**: User can enable MFA via TOTP (QR code setup + backup codes)
- [x] **AUTH-11**: User is prompted for TOTP code on login when MFA enabled
- [x] **AUTH-12**: Tenant owner can enforce MFA for all tenant members
- [x] **AUTH-13**: User can skip MFA on remembered devices (30-day)

### Multi-Tenancy

- [x] **TNNT-01**: Tenant auto-created on user sign-up
- [x] **TNNT-02**: Tenant has human-readable slug identifier
- [x] **TNNT-03**: User invitation by email with 7-day expiry token
- [x] **TNNT-04**: Invited user belongs exclusively to the inviting tenant
- [x] **TNNT-05**: Owner can transfer ownership to another member

### RBAC

- [x] **RBAC-01**: 5 roles enforced: Owner, Admin, Developer, Viewer, Billing
- [x] **RBAC-02**: Owner/Admin can change member roles
- [x] **RBAC-03**: Owner/Admin can remove members from tenant

### Billing

- [x] **BILL-01**: Super-admin can CRUD billing plans (synced with Stripe)
- [x] **BILL-02**: User can subscribe to a plan via Stripe Checkout
- [x] **BILL-03**: Stripe webhooks sync subscription state (paid, updated, deleted, failed)
- [x] **BILL-04**: User can manage billing via Stripe Customer Portal
- [x] **BILL-05**: Plan limits enforced before wxcode engine operations

### Platform & Security

- [ ] **PLAT-01**: API keys per tenant with granular scopes (read, write, admin, billing)
- [ ] **PLAT-02**: API key revocation and rotation
- [x] **PLAT-03**: Rate limiting per IP and per user (login, signup, reset, API)
- [x] **PLAT-04**: Immutable audit log of sensitive actions
- [x] **PLAT-05**: Transactional email templates (verify, reset, invite, payment failed)

### Super-Admin

- [x] **SADM-01**: View all tenants (paginated, with plan/status/members)
- [x] **SADM-02**: Suspend or soft-delete tenant
- [x] **SADM-03**: View all users (search by email, view membership/status)
- [x] **SADM-04**: Block user or force password reset
- [x] **SADM-05**: MRR dashboard (active subscriptions, revenue, plan distribution)

### User Account

- [x] **USER-01**: User can view and edit profile (name, email, avatar)
- [x] **USER-02**: User can change password (requires current password)
- [x] **USER-03**: User can list and revoke active sessions
- [x] **USER-04**: User is redirected to wxcode with access token after login

## v2 Requirements (Frontend UI)

Requirements for v2.0 milestone. Each maps to roadmap phases.

### Design System

- [x] **DS-01**: Frontend Next.js project initialized with Tailwind CSS v4, shadcn/ui (new-york), TypeScript, and path aliases matching wxcode frontend
- [x] **DS-02**: Obsidian Studio theme (globals.css, tokens.css) and custom components (GlowButton, GlowInput, LoadingSkeleton, EmptyState, ErrorState, AnimatedList) ported from wxcode
- [ ] **DS-03**: App shell layout with sidebar navigation, responsive design, and dark mode enforced

### Auth UI

- [ ] **AUI-01**: User can sign up with email and password via a signup form with validation
- [ ] **AUI-02**: User can log in with email and password via a login form
- [ ] **AUI-03**: User sees email verification page and can enter 6-digit OTP code after signup
- [ ] **AUI-04**: User can request password reset via email and set new password via reset link
- [ ] **AUI-05**: User is prompted for TOTP code on login when MFA is enabled, with backup code fallback
- [ ] **AUI-06**: User sees workspace onboarding page after first login (create workspace name)
- [ ] **AUI-07**: After successful auth, user is redirected to wxcode with access token

### User Account UI

- [ ] **UAI-01**: User can view and edit profile (display name, avatar upload)
- [ ] **UAI-02**: User can change password from account settings
- [ ] **UAI-03**: User can view list of active sessions (device, IP, last active) and revoke any session

### Tenant Management UI

- [ ] **TMI-01**: Owner/Admin can view member list with roles and invite new members by email
- [ ] **TMI-02**: Owner/Admin can change member roles or remove members
- [ ] **TMI-03**: Owner can enable/disable MFA enforcement for the tenant

### Billing UI

- [ ] **BUI-01**: User with billing access can view current subscription plan and status
- [ ] **BUI-02**: User can select a plan and complete subscription via Stripe Checkout redirect
- [ ] **BUI-03**: User can access Stripe Customer Portal for payment method and invoice management

### Super-Admin UI

- [ ] **SAI-01**: Admin can log in via separate admin login page with admin-audience JWT
- [ ] **SAI-02**: Admin can view paginated tenant list with filters (plan, status) and suspend/reactivate tenants
- [ ] **SAI-03**: Admin can search users by email, view details, and block/unblock users

## v2.1 Deferred

- **AUI-08**: MFA enrollment UI (QR code + backup codes display)
- **AUI-09**: OAuth login buttons (Google/GitHub)
- **SAI-04**: MRR dashboard with Recharts charts
- **SAI-05**: Force password reset from admin panel

## v3 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Authentication

- **AUTH-14**: User can sign in with Microsoft via OAuth 2.0 (PKCE)
- **AUTH-15**: Passwordless login (magic link / passkeys)

### Billing

- **BILL-06**: Usage-based metered billing (conversions, tokens LLM, API calls) via Stripe Meters
- **BILL-07**: Usage dashboard per tenant (current period consumption)
- **BILL-08**: Dunning management (automatic retries + email on payment failure)
- **BILL-09**: Proration on plan upgrade/downgrade
- **BILL-10**: Trial period support per plan
- **BILL-11**: Coupon / discount code support

### Platform & Security

- **PLAT-06**: IP allowlist per tenant (Enterprise)
- **PLAT-07**: Feature flags / global platform settings (kill switch, maintenance mode)

### Super-Admin

- **SADM-06**: Churn/expansion MRR breakdown
- **SADM-07**: Usage heatmap by tenant (power users / at-risk identification)

### Enterprise

- **ENTR-01**: SAML SSO (Okta, Azure AD)
- **ENTR-02**: SCIM provisioning (user sync from IdP)
- **ENTR-03**: Audit log SIEM webhook forwarding

## Out of Scope

| Feature | Reason |
|---------|--------|
| Execute wxcode engine operations (import, conversion, parsing) | wxcode-adm is identity/billing gate only |
| Multi-tenant switching (user in multiple orgs) | Strict single-tenant isolation per PROJECT.md |
| Custom per-tenant plans | Only super-admin manages plan catalog |
| Real-time billing dashboard (WebSockets) | Polling every 60s sufficient |
| Social login beyond Google/GitHub/Microsoft | 3 providers cover 95%+ of developer audience |
| Built-in analytics/BI charts | Use Stripe Dashboard + external tools |
| Multi-currency billing | Let Stripe handle currency conversion |
| Custom OAuth provider per tenant | API keys cover programmatic access |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 2 | Complete |
| AUTH-02 | Phase 2 | Complete |
| AUTH-03 | Phase 2 | Complete |
| AUTH-04 | Phase 2 | Complete |
| AUTH-05 | Phase 2 | Complete |
| AUTH-06 | Phase 2 | Complete |
| AUTH-07 | Phase 2 | Complete |
| AUTH-08 | Phase 6 | Complete |
| AUTH-09 | Phase 6 | Complete |
| AUTH-10 | Phase 6 | Complete |
| AUTH-11 | Phase 6 | Complete |
| AUTH-12 | Phase 6 | Complete |
| AUTH-13 | Phase 6 | Complete |
| TNNT-01 | Phase 3 | Complete |
| TNNT-02 | Phase 3 | Complete |
| TNNT-03 | Phase 3 | Complete |
| TNNT-04 | Phase 3 | Complete |
| TNNT-05 | Phase 3 | Complete |
| RBAC-01 | Phase 3 | Complete |
| RBAC-02 | Phase 3 | Complete |
| RBAC-03 | Phase 3 | Complete |
| BILL-01 | Phase 4+11 | Complete (Phase 11 strengthens: admin JWT isolation) |
| BILL-02 | Phase 4 | Complete |
| BILL-03 | Phase 4+11 | Complete (Phase 11 strengthens: payment failure blacklist fix) |
| BILL-04 | Phase 4 | Complete |
| BILL-05 | Phase 4+11 | Complete (Phase 11 strengthens: payment failure blacklist fix) |
| PLAT-01 | Phase 10 | Pending |
| PLAT-02 | Phase 10 | Pending |
| PLAT-03 | Phase 5 | Complete |
| PLAT-04 | Phase 5 | Complete |
| PLAT-05 | Phase 5 | Complete |
| SADM-01 | Phase 8 | Complete |
| SADM-02 | Phase 8 | Complete |
| SADM-03 | Phase 8 | Complete |
| SADM-04 | Phase 8 | Complete |
| SADM-05 | Phase 8 | Complete |
| USER-01 | Phase 7 | Complete |
| USER-02 | Phase 7 | Complete |
| USER-03 | Phase 7 | Complete |
| USER-04 | Phase 7 | Complete |
| DS-01 | Phase 12 | Complete |
| DS-02 | Phase 12 | Complete |
| DS-03 | Phase 12 | Pending |
| AUI-01 | Phase 13 | Pending |
| AUI-02 | Phase 13 | Pending |
| AUI-03 | Phase 13 | Pending |
| AUI-04 | Phase 13 | Pending |
| AUI-05 | Phase 13 | Pending |
| AUI-06 | Phase 13 | Pending |
| AUI-07 | Phase 13 | Pending |
| UAI-01 | Phase 14 | Pending |
| UAI-02 | Phase 14 | Pending |
| UAI-03 | Phase 14 | Pending |
| TMI-01 | Phase 15 | Pending |
| TMI-02 | Phase 15 | Pending |
| TMI-03 | Phase 15 | Pending |
| BUI-01 | Phase 16 | Pending |
| BUI-02 | Phase 16 | Pending |
| BUI-03 | Phase 16 | Pending |
| SAI-01 | Phase 17 | Pending |
| SAI-02 | Phase 17 | Pending |
| SAI-03 | Phase 17 | Pending |

**Coverage (v1):**
- v1 requirements: 40 total
- Mapped to phases: 40
- Unmapped: 0

**Coverage (v2):**
- v2 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-02-22*
*Last updated: 2026-03-04 after milestone v2.0 roadmap creation (Phases 12-17)*
