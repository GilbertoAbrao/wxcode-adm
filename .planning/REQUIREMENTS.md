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
- [ ] **AUTH-12**: Tenant owner can enforce MFA for all tenant members
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

- [ ] **SADM-01**: View all tenants (paginated, with plan/status/members)
- [ ] **SADM-02**: Suspend or soft-delete tenant
- [ ] **SADM-03**: View all users (search by email, view membership/status)
- [ ] **SADM-04**: Block user or force password reset
- [ ] **SADM-05**: MRR dashboard (active subscriptions, revenue, plan distribution)

### User Account

- [ ] **USER-01**: User can view and edit profile (name, email, avatar)
- [ ] **USER-02**: User can change password (requires current password)
- [ ] **USER-03**: User can list and revoke active sessions
- [ ] **USER-04**: User is redirected to wxcode with access token after login

## v2 Requirements

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
| AUTH-12 | Phase 6 | Pending |
| AUTH-13 | Phase 6 | Complete |
| TNNT-01 | Phase 3 | Complete |
| TNNT-02 | Phase 3 | Complete |
| TNNT-03 | Phase 3 | Complete |
| TNNT-04 | Phase 3 | Complete |
| TNNT-05 | Phase 3 | Complete |
| RBAC-01 | Phase 3 | Complete |
| RBAC-02 | Phase 3 | Complete |
| RBAC-03 | Phase 3 | Complete |
| BILL-01 | Phase 4 | Complete |
| BILL-02 | Phase 4 | Complete |
| BILL-03 | Phase 4 | Complete |
| BILL-04 | Phase 4 | Complete |
| BILL-05 | Phase 4 | Complete |
| PLAT-01 | Phase 5 | Pending |
| PLAT-02 | Phase 5 | Pending |
| PLAT-03 | Phase 5 | Complete |
| PLAT-04 | Phase 5 | Complete |
| PLAT-05 | Phase 5 | Complete |
| SADM-01 | Phase 8 | Pending |
| SADM-02 | Phase 8 | Pending |
| SADM-03 | Phase 8 | Pending |
| SADM-04 | Phase 8 | Pending |
| SADM-05 | Phase 8 | Pending |
| USER-01 | Phase 7 | Pending |
| USER-02 | Phase 7 | Pending |
| USER-03 | Phase 7 | Pending |
| USER-04 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 40 total
- Mapped to phases: 40
- Unmapped: 0

---
*Requirements defined: 2026-02-22*
*Last updated: 2026-02-22 after roadmap creation — all 40 requirements mapped*
