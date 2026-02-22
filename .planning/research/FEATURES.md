# Feature Research

**Domain:** SaaS Authentication / Billing / Multi-Tenancy Platform (internal SaaS layer for WXCODE)
**Researched:** 2026-02-22
**Confidence:** HIGH (project scope defined in PROJECT.md; industry patterns verified against Auth0, Clerk, WorkOS, Stripe docs, and SaaS benchmarks)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that users of any SaaS platform assume exist. Missing these makes the product feel broken or incomplete — users abandon without giving feedback.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Email + password sign-up / sign-in | The baseline of any SaaS product; absence = no product | LOW | Password stored bcrypt cost-12; validation on sign-up (length, complexity) |
| Email verification on sign-up | Prevents spam accounts; users distrust unverified products | LOW | Token-based, configurable expiry; re-send flow required |
| Forgot-password / reset-password via email | Any SaaS without this gets immediate churn on first lockout | LOW | Short-lived token (15–60 min); single-use; IP rate-limited |
| JWT-based session management (access + refresh tokens) | Standard expectation for stateless APIs; enables multi-service auth | MEDIUM | RS256 asymmetric signing so wxcode validates locally without calling wxcode-adm |
| Refresh token rotation with revocation | Users expect sessions to persist across browser restarts; revocation prevents token theft | MEDIUM | Store refresh token hash in Redis; blacklist on logout or suspicious activity |
| OAuth 2.0 social login (Google, GitHub, Microsoft) | Developers and tech users expect "Login with Google/GitHub" — reduces sign-up friction by ~40% | MEDIUM | Authorization Code Flow + PKCE; link OAuth account to existing user on email match |
| MFA via TOTP (Google Authenticator, Authy) | Required for any product targeting professional/enterprise buyers | MEDIUM | `pyotp` library; QR code for initial setup; backup codes (10 single-use) |
| Tenant (organization) creation on sign-up | Multi-tenant SaaS: user belongs to an organization from day one | LOW | Auto-create personal tenant; slug-based identifier; soft-delete with configurable retention |
| User invitation to tenant by email | Core multi-tenancy primitive — collaborative products require invite flows | MEDIUM | Signed invitation token; expiry 7 days; auto-accept on sign-up with same email |
| RBAC per tenant (Owner / Admin / Developer / Viewer / Billing) | Without role enforcement, every user is effectively an admin — security failure | MEDIUM | Roles stored in `tenant_memberships`; enforced via FastAPI dependency injection |
| Change user role within tenant | Tenant admins need to promote/demote members without super-admin help | LOW | Owner-only can change other Owners; Admin can manage non-Owner roles |
| Remove member from tenant | Personnel change management is standard in any team tool | LOW | Revoke access immediately; soft-remove from membership |
| Transfer ownership | Prevents tenant orphans when founders leave | LOW | Two-step confirmation; old Owner becomes Admin |
| Stripe Checkout for plan subscription | Users expect to subscribe to a plan without leaving the app | MEDIUM | Server-side session creation; redirect to Stripe hosted page; success/cancel URL handling |
| Stripe Billing recurring subscriptions | Automated monthly invoicing is the SaaS model | MEDIUM | Webhook-driven state sync (`invoice.paid`, `subscription.updated`, `subscription.deleted`) |
| Stripe Customer Portal (self-service) | Users expect to update payment methods, download invoices, cancel — without contacting support | MEDIUM | Server-generated portal session URL; redirects back to wxcode-adm |
| Stripe Webhook processing | Billing state must stay in sync with Stripe (payments fail, cards expire) | MEDIUM | Signature verification; idempotent handlers; dead-letter queue for failed events |
| Plan enforcement (feature gates / usage limits) | Users must not exceed their plan limits silently — must be informed and blocked gracefully | MEDIUM | Check limits before operation in wxcode engine; HTTP 402 with clear error message |
| API key generation per tenant (with scopes) | Developer users expect programmatic access for CI/CD and integrations | MEDIUM | Prefixed keys (`wxk_live_`, `wxk_test_`); scoped to `read`, `write`, `admin`, `billing`; stored as HMAC hash |
| API key revocation and rotation | Security hygiene — leaked keys must be neutralizable | LOW | Immediate revocation; rotation creates new key before deleting old |
| Rate limiting (IP + user level) | Prevents credential stuffing, DoS, and billing abuse | MEDIUM | Redis sliding window; separate limits for login (5/min), sign-up (3/min), reset (3/hr), API (100/min) |
| Audit log of sensitive actions | Compliance and incident response — enterprise buyers require this | MEDIUM | Immutable append-only log; captures actor, action, resource, IP, timestamp |
| User profile management (view/edit) | Basic account hygiene — name, email, avatar | LOW | `GET /users/me`, `PUT /users/me`; email change requires re-verification |
| Password change for authenticated users | Standard account settings feature | LOW | Requires current password confirmation |
| Active session listing and revocation | Users want to see and kill sessions on other devices | MEDIUM | Sessions stored in Redis with device fingerprint; revoke by session ID |
| Super-admin: view all tenants | Platform operator must manage their customer base | LOW | Paginated list with plan, status, created date, member count |
| Super-admin: suspend / delete tenant | Fraud prevention and churn management | LOW | Suspend = block login for all tenant members; delete = soft-delete with data retention |
| Super-admin: view all users | Support and incident response | LOW | Search by email; view tenant membership, last login, status |
| Super-admin: block user / force password reset | Security incident response | LOW | Block = blacklist all tokens; force reset = invalidate password hash |
| MRR / revenue dashboard (super-admin) | Platform operator needs business metrics to operate | MEDIUM | Derived from Stripe data: MRR, new MRR, churned MRR, active subscriptions, plan distribution |

---

### Differentiators (Competitive Advantage)

Features that go beyond what users assume. These create competitive advantage for WXCODE as a SaaS product — not every SaaS platform offers these out of the box.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Usage-based metered billing (Stripe Meters) | Converts variable usage (LLM tokens, conversions, storage) into revenue — aligns cost with value delivered | HIGH | Stripe Meters API; event ingestion from wxcode engine; usage reported to Stripe at billing cycle; shown to tenant in real-time dashboard |
| Usage dashboard per tenant (current period) | Transparency reduces churn — users who see usage understand their bill | MEDIUM | Aggregate from `usage_records`; show conversions used/remaining, token spend, API calls; billing period progress |
| Dunning management (Stripe automatic retries + email) | Involuntary churn (failed payments) averages 0.8% in B2B SaaS — recoverable with proper dunning | MEDIUM | Configure Stripe Smart Retries; `invoice.payment_failed` webhook triggers email to Billing role; grace period before downgrade |
| Proration on plan upgrade/downgrade | Fair billing on plan changes = trust; users penalize SaaS that overcharges on upgrades | MEDIUM | Stripe handles proration math; wxcode-adm calls `subscription.update()` with `proration_behavior='create_prorations'` |
| Trial period support (per plan) | Reduces conversion friction — users can evaluate before committing | LOW | Stripe `trial_period_days` on subscription creation; `trial_will_end` webhook triggers conversion email |
| Coupon / discount code support | Sales team and growth hacks require discount codes for demos and partnerships | LOW | Stripe coupons applied at checkout; super-admin creates codes in Stripe dashboard |
| MFA enforcement per tenant (optional vs mandatory) | Enterprise tenants require MFA for all members — security compliance | LOW | Tenant-level setting; if `mfa_required=true`, post-login redirect to MFA setup if not enrolled |
| Remember device for MFA (30-day skip) | Reduces MFA friction for trusted devices without lowering security | LOW | Device fingerprint stored in Redis with 30-day TTL; skip MFA prompt on recognized device |
| Tenant-level MFA trust configuration | Owner can require MFA for all members or leave optional — enterprise control | LOW | Setting in `tenants` collection; enforced at login time |
| IP allowlist per tenant (Enterprise plan only) | Enterprise security requirement — restrict access to corporate IP ranges | MEDIUM | Stored in tenant config; middleware checks `X-Forwarded-For` against allowlist; reject with 403 |
| RS256 JWT with key rotation support | Asymmetric JWT means wxcode validates tokens locally — no network call per request; key rotation without downtime | HIGH | RSA key pair; JWKS endpoint (`/.well-known/jwks.json`); wxcode caches public key with TTL; wxcode-adm signs with active private key |
| JWKS endpoint for public key distribution | Standard OIDC pattern — allows future integrations (CLI tools, other services) without sharing secrets | LOW | Expose public key at standard URL; consumed by wxcode engine at startup or periodically refreshed |
| Super-admin: churn and MRR breakdown | Distinguish churned MRR, expansion MRR, new MRR — actionable metrics for business decisions | MEDIUM | Derived from Stripe events + local subscription history; new/expansion/churned MRR by period |
| Super-admin: usage heatmap by tenant | Identify power users and at-risk tenants for proactive customer success | MEDIUM | Aggregate `usage_records` by tenant; flag tenants with high usage (upsell) or low usage (churn risk) |
| Super-admin: feature flags and global limits | Adjust platform behavior without deployment (kill switch, maintenance mode, emergency limits) | MEDIUM | Feature flags stored in MongoDB `platform_settings`; read by API on startup or cached in Redis; togglable at runtime |
| Invitation link expiry and re-send | Invitations expire (7 days) — without re-send, failed invites require manual intervention | LOW | Re-send generates new token; old token invalidated |
| Tenant slug / human-readable identifier | Allows display names in URLs (app.wxcode.io/t/acme-corp) and support tickets | LOW | Auto-generated from tenant name; unique index; editable by Owner |
| Stripe metered billing event validation | Ensure usage events are not duplicated before reporting to Stripe (idempotent event ingestion) | MEDIUM | Track event IDs in `usage_records`; Stripe idempotency keys on meter event calls |
| Email transactional templates (HTML) | Professional emails reduce spam flags and build brand trust | LOW | Templates for: verify email, reset password, invite member, payment failed, trial ending, plan upgraded |

---

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem reasonable but create disproportionate cost, complexity, or security risk for this stage of the product.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multi-tenant switching (user belongs to multiple orgs) | Enterprise users often work across organizations | Doubles complexity of authorization model; JWT claims become ambiguous; RBAC enforcement requires context switching; PROJECT.md explicitly out-of-scope | Strict single-tenant isolation with clean offboarding; if needed later, implement as separate account per tenant |
| SAML SSO (enterprise IdP integration) | Enterprise buyers often require Okta/Azure AD/LDAP login | Enormous implementation complexity (XML signatures, metadata exchange, IdP configuration per tenant); adds 4-8 weeks; not needed until enterprise tier has paying customers | Offer TOTP MFA + OAuth as bridge; SAML can be added in v2 when first enterprise contract requires it |
| SCIM provisioning (user sync from IdP) | Enterprises want automated user lifecycle management | Requires SAML SSO first; adds another 2-4 weeks; zero value without enterprise SSO | Manual invite flow covers 95% of use cases at current scale |
| Real-time billing dashboard (WebSockets/SSE) | Users want live usage counters | Usage data is aggregated server-side; real-time updates require persistent connections and caching complexity; refresh every 60s is indistinguishable to users | Polling every 60 seconds on the billing page; server-sent events only if proven valuable |
| Custom plan creation per tenant | Some power users want bespoke pricing | Defeats the purpose of a plan-based model; creates billing edge cases; super-admin burden scales O(n) with tenants | Super-admin manages a fixed plan catalog; Enterprise plan covers unlimited use cases |
| Multi-currency billing | International SaaS | Stripe already handles currency localization for the payer; adding multi-currency on the backend requires accounting for FX, VAT, and reporting complexity | Let Stripe handle currency; invoice in USD; Stripe automatically converts for local payment methods |
| Custom OAuth provider registration per tenant (OAuth server) | Advanced API integrations | Building a full OAuth authorization server (beyond client registration) requires RFC 6749 compliance, consent flows, PKCE, OIDC discovery — 6-10 weeks; zero user demand at this stage | API keys cover programmatic access; OAuth social login covers the user-facing case |
| Social login beyond Google/GitHub/Microsoft | More options = more conversion | Each additional provider requires maintenance of SDK, redirect URIs, error handling, and token normalization; Slack, Twitter/X, Apple Sign In each add 1-2 days + ongoing maintenance | Start with G/GH/MS (covers 95%+ of developer audience); add Apple Sign In only if iOS app ships |
| Audit log export (SIEM integration) | Security teams want logs in Splunk/Datadog | Complex integration surface; each SIEM has different log formats; webhook forwarding is simpler and more flexible | Expose paginated audit log API; let enterprise customers pull and forward; add syslog/webhook forwarding in v2 |
| Passwordless login (magic link / passkeys) | Lower friction sign-in | Adds complexity to auth flow; passkeys (WebAuthn) require frontend work and device management; magic links require email delivery SLA; current user base (developers) comfortable with password + TOTP | Deliver this as v2 differentiator after core auth is stable |
| "Built-in" analytics / BI charts | Admins want dashboards | Building BI from scratch is never finished; charts always need more dimensions; creates maintenance burden | Use Stripe Dashboard for revenue metrics; use MongoDB Atlas Charts or Metabase for internal analytics; focus on the 3-4 KPIs that matter |

---

## Feature Dependencies

```
[Email Verification]
    └──required-by──> [Trusted Account Status]
                           └──required-by──> [Tenant Invitation Acceptance]

[Sign-up + Sign-in]
    └──required-by──> [OAuth Social Login]  (account linking requires existing user model)
    └──required-by──> [MFA Setup]           (must be authenticated to enroll TOTP)
    └──required-by──> [Tenant Creation]     (sign-up triggers auto-tenant)

[Tenant Creation]
    └──required-by──> [RBAC]               (roles live within a tenant)
    └──required-by──> [User Invitation]    (invites require a target tenant)
    └──required-by──> [API Keys]           (API keys scoped to tenant)
    └──required-by──> [Audit Log]          (log entries reference tenant_id)
    └──required-by──> [Stripe Checkout]    (subscription belongs to tenant)

[Stripe Checkout]
    └──required-by──> [Stripe Webhooks]    (subscription state managed via webhooks)
    └──required-by──> [Plan Enforcement]   (must have subscription to enforce plan limits)
    └──required-by──> [Customer Portal]    (portal manages existing subscription)

[Stripe Webhooks]
    └──required-by──> [Usage-Based Billing] (meter event sync requires active subscription)
    └──required-by──> [Dunning Management]  (payment failure handling requires webhook)
    └──required-by──> [Trial Support]       (trial_will_end event requires webhook)

[Usage Tracking (wxcode engine → wxcode-adm)]
    └──required-by──> [Usage-Based Billing]
    └──required-by──> [Usage Dashboard (tenant)]
    └──required-by──> [Usage Heatmap (super-admin)]

[JWT RS256 with JWKS]
    └──required-by──> [wxcode local token validation] (no network call per request)

[MFA Enrollment]
    └──optional──> [MFA Enforcement per Tenant]    (enforcement requires enrollment flow to exist)
    └──optional──> [Remember Device]               (skip only when MFA is active)

[Super-admin Auth (super-admin role)]
    └──required-by──> [Tenant Management]
    └──required-by──> [User Management]
    └──required-by──> [MRR Dashboard]
    └──required-by──> [Feature Flags]
    └──required-by──> [Plan CRUD]

[Plan CRUD (super-admin)]
    └──required-by──> [Stripe Checkout]     (plans must exist before checkout)
    └──required-by──> [Plan Enforcement]    (limits sourced from plan definition)
```

### Dependency Notes

- **Sign-up must precede OAuth**: OAuth social login links to an existing user account by email — the user model must exist first.
- **Tenant must precede RBAC**: Roles only make sense within the context of a tenant. RBAC enforcement requires `tenant_id` in every request.
- **Stripe Checkout must precede Webhooks**: You must create subscriptions before you can receive lifecycle events from Stripe.
- **Usage Tracking is a cross-service contract**: wxcode engine must call `POST /usage/events` on wxcode-adm for every billable operation — this API must be stable before wxcode integration.
- **RS256 key pair must be provisioned before JWT issuance**: wxcode must have the public key at startup; JWKS endpoint must be reachable from wxcode.
- **Plan CRUD must precede Stripe Checkout**: Plans define Stripe Price IDs; Checkout sessions reference those price IDs.
- **Super-admin role is a separate RBAC axis**: Super-admin is a platform-level role (stored on User document), distinct from tenant-level RBAC. Must be seeded on first deploy.

---

## MVP Definition

### Launch With (v1)

The minimum that makes WXCODE usable as a paid SaaS product.

- [ ] **Sign-up + sign-in (email/password)** — no product without this
- [ ] **Email verification** — prevents spam; required before billing
- [ ] **Password reset via email** — without this, first lockout = permanent churn
- [ ] **JWT RS256 issuance + refresh token rotation** — wxcode integration requires self-contained token
- [ ] **JWKS endpoint** — wxcode validates tokens locally; must be live before wxcode integration
- [ ] **OAuth: Google + GitHub** (Microsoft can wait) — covers developer audience; GitHub is highest value for dev tool
- [ ] **Auto-tenant creation on sign-up** — every user needs a tenant; single-tenant model is simpler
- [ ] **RBAC: Owner + Admin + Developer + Viewer + Billing** — all 5 roles defined and enforced at API level
- [ ] **User invitation (email-based, 7-day expiry)** — team access required for any paid team plan
- [ ] **Plan CRUD by super-admin (Free, Starter, Pro, Enterprise)** — plans must exist before billing
- [ ] **Stripe Checkout for Starter and Pro** — revenue-generating subscriptions
- [ ] **Stripe Webhooks** (invoice.paid, subscription.updated, subscription.deleted, payment_failed) — billing state sync
- [ ] **Stripe Customer Portal** — self-service billing reduces support load immediately
- [ ] **Plan enforcement (limits check before wxcode engine operations)** — prevents free users exceeding quota
- [ ] **API keys per tenant (with scopes, revocation)** — CLI and CI/CD access needed from day one
- [ ] **Rate limiting (login, sign-up, reset, API)** — security requirement before public launch
- [ ] **Audit log** — basic compliance; required if any enterprise trial users in v1
- [ ] **Super-admin: tenant list, user list, suspend/block** — operator needs basic control panel
- [ ] **MRR dashboard (super-admin)** — operator needs to know revenue from day 1
- [ ] **Transactional emails** (verify, reset, invite, payment_failed) — essential communication

### Add After Validation (v1.x)

Add when core is working and first paying customers are onboarded.

- [ ] **MFA via TOTP** — trigger: first enterprise prospect asks; or any security incident
- [ ] **MFA enforcement per tenant** — trigger: MFA enrollment shipped and working
- [ ] **Remember device for MFA** — trigger: MFA user feedback about friction
- [ ] **Usage-based metered billing** (conversions, tokens, API calls) — trigger: first customer hits plan limits and requests overage billing
- [ ] **Usage dashboard per tenant** — trigger: first billing complaint about unexpected charges
- [ ] **Dunning management** — trigger: first involuntary churn due to payment failure
- [ ] **Trial period support** — trigger: first sales motion requiring trial offering
- [ ] **OAuth: Microsoft** — trigger: first enterprise prospect uses Azure AD
- [ ] **Super-admin: churn/expansion MRR breakdown** — trigger: first month of consistent revenue
- [ ] **Super-admin: usage heatmap** — trigger: 5+ tenants with meaningful usage data
- [ ] **Feature flags (platform settings)** — trigger: first time a deployment fix requires a kill switch
- [ ] **IP allowlist (Enterprise tier)** — trigger: first enterprise contract signed

### Future Consideration (v2+)

Defer until product-market fit confirmed or explicit enterprise demand.

- [ ] **SAML SSO** — defer: requires enterprise contracts justifying 4-8 week effort
- [ ] **SCIM provisioning** — defer: requires SAML SSO first
- [ ] **Passkeys / WebAuthn** — defer: requires frontend investment; low demand from developer audience initially
- [ ] **Magic link login** — defer: not clearly better than password+TOTP for developer audience
- [ ] **Audit log SIEM webhook forwarding** — defer: implement API export first; webhook when first enterprise requires it
- [ ] **Multi-tenant switching** — explicitly out of scope per PROJECT.md
- [ ] **Custom per-tenant plans** — explicitly out of scope per PROJECT.md

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Sign-up / sign-in (email+password) | HIGH | LOW | P1 |
| Email verification | HIGH | LOW | P1 |
| Password reset | HIGH | LOW | P1 |
| JWT RS256 + JWKS endpoint | HIGH | MEDIUM | P1 |
| Refresh token rotation | HIGH | MEDIUM | P1 |
| Tenant creation on sign-up | HIGH | LOW | P1 |
| RBAC (5 roles) | HIGH | MEDIUM | P1 |
| User invitation | HIGH | MEDIUM | P1 |
| Stripe Checkout + Webhooks | HIGH | MEDIUM | P1 |
| Stripe Customer Portal | HIGH | LOW | P1 |
| Plan enforcement | HIGH | MEDIUM | P1 |
| API keys (scopes + revocation) | HIGH | MEDIUM | P1 |
| Rate limiting | HIGH | MEDIUM | P1 |
| Audit log | MEDIUM | MEDIUM | P1 |
| Transactional emails (4 templates) | HIGH | LOW | P1 |
| Super-admin tenant/user management | MEDIUM | LOW | P1 |
| MRR dashboard (super-admin) | HIGH | MEDIUM | P1 |
| OAuth (Google + GitHub) | HIGH | MEDIUM | P1 |
| MFA via TOTP | HIGH | MEDIUM | P2 |
| Usage-based metered billing | HIGH | HIGH | P2 |
| Usage dashboard (tenant) | MEDIUM | MEDIUM | P2 |
| Dunning management | HIGH | MEDIUM | P2 |
| Trial period support | MEDIUM | LOW | P2 |
| MFA enforcement per tenant | MEDIUM | LOW | P2 |
| Remember device (MFA) | LOW | LOW | P2 |
| OAuth: Microsoft | LOW | MEDIUM | P2 |
| Super-admin: churn/MRR breakdown | MEDIUM | MEDIUM | P2 |
| Feature flags (platform) | MEDIUM | MEDIUM | P2 |
| IP allowlist (Enterprise) | MEDIUM | MEDIUM | P2 |
| Super-admin: usage heatmap | LOW | MEDIUM | P3 |
| Coupon / discount support | LOW | LOW | P3 |
| SAML SSO | MEDIUM | HIGH | P3 |
| Passkeys / WebAuthn | MEDIUM | HIGH | P3 |
| Audit log SIEM webhook | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch (revenue-generating, security-critical, or integration-blocking)
- P2: Should have — add in v1.x when first user demand or business trigger occurs
- P3: Nice to have — defer to v2 or explicit enterprise demand

---

## Competitor Feature Analysis

Compared against Auth0, Clerk, WorkOS (auth-focused SaaS platforms), and Stripe Billing documentation.

| Feature | Auth0 | Clerk | WorkOS | Our Approach |
|---------|-------|-------|--------|--------------|
| Email + password auth | Yes | Yes | Yes | Yes — bespoke; no vendor lock-in |
| OAuth social login | Yes (many providers) | Yes (many providers) | Yes | Google + GitHub + Microsoft (covers developer audience) |
| MFA / TOTP | Yes | Yes | Yes | Yes — pyotp; per-tenant enforcement |
| Multi-tenant organizations | Yes (via Organizations) | Yes (basic) | Yes (core product) | Yes — single-tenant-per-user model; simpler than multi-org switching |
| RBAC | Yes (roles/permissions) | Yes (basic roles) | Yes | Yes — 5 roles defined by domain (Owner/Admin/Developer/Viewer/Billing) |
| SAML SSO | Yes (Enterprise) | Yes (Enterprise) | Yes (core) | No (v2+) — not needed until enterprise contracts justify cost |
| SCIM provisioning | Yes | No | Yes | No (v2+) — follows SAML |
| JWT issuance | Yes | Yes | Yes | Yes — RS256; JWKS endpoint; self-contained claims |
| User invitation | Yes | Yes | Yes | Yes — email-based; 7-day expiry |
| API keys | Not built-in | Not built-in | Not built-in | Yes — differentiator; `wxk_live_` prefix; scoped; hashable |
| Stripe billing built-in | No (separate) | No (separate) | No (separate) | Yes — deeply integrated; metered + subscription; single source of truth |
| Usage-based billing | No | No | No | Yes — differentiator; meter events from wxcode engine to Stripe |
| Super-admin panel | Yes (management API) | Yes (dashboard) | Yes (dashboard) | Yes — purpose-built for WXCODE operator; MRR, churn, per-tenant usage |
| Audit log | Yes (enterprise) | Yes (basic) | Yes | Yes — immutable; accessible to Owner/Admin and super-admin |
| Rate limiting | Yes (built-in) | Yes (built-in) | Yes | Yes — Redis-backed; configured per endpoint |

---

## Sources

- [WorkOS vs Auth0 vs Clerk comparison](https://workos.com/blog/workos-vs-auth0-vs-clerk) — table stakes auth features for B2B SaaS
- [Auth0 Alternatives for B2B SaaS 2026](https://www.scalekit.com/blog/auth0-alternatives) — ecosystem survey
- [Auth0 vs WorkOS CIAM 2026](https://securityboulevard.com/2025/12/auth0-vs-workos-which-ciam-platform-fits-your-saas-better-in-2026/) — enterprise auth requirements
- [Clerk Essential User Management Features 2025](https://clerk.com/articles/essential-user-management-features-startups) — startup-stage auth expectations
- [Stripe Billing Documentation](https://docs.stripe.com/billing) — subscription and usage-based billing capabilities
- [Stripe Usage-Based Billing](https://docs.stripe.com/billing/subscriptions/usage-based) — metered billing patterns
- [Stripe SaaS Integration Guide](https://docs.stripe.com/saas) — recommended integration patterns
- [Stripe Customer Portal](https://docs.stripe.com/customer-management) — self-service billing UI capabilities and limitations
- [Kinde Multi-Tenant Billing Architecture](https://kinde.com/learn/billing/billing-infrastructure/multi-tenant-billing-architecture-scaling-b2b-saas-across-enterprise-hierarchies/) — tenant billing patterns
- [Frontegg SaaS Multitenancy](https://frontegg.com/blog/saas-multitenancy) — multi-tenancy component breakdown
- [RS256 vs HS256 — Auth0](https://auth0.com/blog/rs256-vs-hs256-whats-the-difference/) — JWT algorithm selection rationale
- [JWT Best Practices — Curity](https://curity.io/resources/learn/jwt-best-practices/) — token security patterns
- [SaaS Churn Benchmarks 2025](https://www.vitally.io/post/saas-churn-benchmarks) — 3.5% average B2B churn; 0.8% involuntary
- [Top SaaS Revenue Metrics 2025](https://www.peaka.com/blog/top-saas-revenue-metrics/) — MRR breakdown (new, expansion, churned)
- [SaaS Application Architecture: Multi-Tenancy 2026](https://www.promaticsindia.com/blog/saas-application-architecture-multi-tenancy-scale) — isolation patterns
- WXCODE ADM README.md and .planning/PROJECT.md — authoritative scope and constraints

---
*Feature research for: WXCODE ADM — SaaS authentication, billing, and multi-tenancy platform*
*Researched: 2026-02-22*
