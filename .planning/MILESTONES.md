# Milestones

## v1.0 Backend API (Shipped: 2026-03-04)

**Phases:** 1-11 (10 complete, 1 pending)
**Plans:** 38 executed
**Backend:** 19,837 LOC Python, 148 tests passing
**Timeline:** 11 days (2026-02-22 → 2026-03-04)
**Git range:** 72cad9c → 91d940b

**Key accomplishments:**
1. JWT RS256 auth with signup, login, email verification, password reset, and JWKS for wxcode token validation
2. OAuth 2.0 (Google + GitHub) and TOTP MFA with trusted device support
3. Multi-tenancy with workspace onboarding, invitations, RBAC (Owner/Admin/Developer/Viewer), cross-tenant isolation
4. Stripe billing integration with plan CRUD, Checkout, webhooks, Customer Portal, and plan limit enforcement
5. Platform security with rate limiting, immutable audit log, and transactional email templates
6. Super-admin panel with tenant/user management, MRR dashboard, and admin JWT audience isolation

### Known Gaps
- **PLAT-01**: API keys per tenant with granular scopes — Phase 10 not executed
- **PLAT-02**: API key revocation and rotation — Phase 10 not executed

---


## v2.0 Frontend UI (Shipped: 2026-03-06)

**Phases:** 12-19 (8 complete)
**Plans:** 20 executed
**Frontend:** 9,174 LOC TypeScript/React (51 source files)
**Timeline:** 3 days (2026-03-04 → 2026-03-06)
**Git range:** e075b3e → eaf54db

**Key accomplishments:**
1. Obsidian Studio design system with 6 custom components ported from wxcode, app shell with responsive sidebar
2. Full auth flow UI: signup, login, email verification, password reset, MFA verify, workspace onboarding
3. User account management: profile editing, avatar upload, password change, session list with revocation
4. Tenant management: member list, invitations, role management, MFA enforcement toggle
5. Billing UI: subscription display, plan catalog, Stripe Checkout + Customer Portal integration
6. Super-admin portal: admin login, tenant list with moderation, user search with block/unblock, MRR dashboard, audit log viewer, tenant detail, force password reset

**Deferred to v2.1:**
- **AUI-08**: MFA enrollment UI (QR code + backup codes display)
- **AUI-09**: OAuth login buttons (Google/GitHub)

---


## v3.0 WXCODE Engine Integration (Shipped: 2026-03-09)

**Phases:** 20-26 (7 complete)
**Plans:** 15 executed
**Backend:** 13,710 LOC Python + 7,624 LOC tests (192 tests)
**Frontend:** 11,004 LOC TypeScript/React
**Timeline:** 3 days (2026-03-07 → 2026-03-09)

**Key accomplishments:**
1. Fernet AES encryption service for Claude OAuth tokens at rest with SHA-256 passphrase derivation
2. Tenant model extension with status lifecycle (pending_setup/active/suspended/cancelled), database_name, and Claude config fields
3. Plan operational limits: max_projects, max_output_projects, max_storage_gb, dual token quotas (5h + weekly rolling windows)
4. Admin provisioning API: Claude token set/revoke, config PATCH, wxcode-config PATCH, tenant activation with full audit logging
5. Admin UI: WXCODE integration section in tenant detail, plans page with limits, session persistence, wxcode provisioning config
6. Production CORS: DynamicCORSMiddleware with static origins + per-tenant wxcode_url cache
7. Integration contract documented (INTEGRATION-CONTRACT.md v0.2.0) + wxcode-config endpoint with plan_limits for engine bootstrap

**Tech debt:**
- 4 human verification items pending browser testing (activation flow, session persistence, plan toggle/delete, dual budget/quota)
- Production deployment requires ALLOWED_ORIGINS set to explicit domain list
- `decrypt_value` exported but not called in production (by design — token exchange is documented mechanism)

---

