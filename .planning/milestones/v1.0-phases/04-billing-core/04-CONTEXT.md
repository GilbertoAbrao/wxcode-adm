# Phase 4: Billing Core - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Stripe-backed subscription billing for tenants: plan catalog (super-admin managed), Stripe Checkout flow, webhook processing, Customer Portal, and plan enforcement. Hybrid billing model — monthly subscription tiers with included token quota plus per-token overage billing. No trial periods; a permanent free tier handles exploration.

</domain>

<decisions>
## Implementation Decisions

### Plan catalog design
- Hybrid billing: monthly subscription fee + usage-based token metering
- Plans define two limit types: **token quota** (included monthly allowance + overage rate) and **member cap** (hard limit)
- Plans are fully manageable by super-admin via CRUD API — tiers, limits, and pricing are not hardcoded
- Each plan syncs to a Stripe Price (subscription component) + Stripe Billing Meter (usage component)
- No trial periods — a permanent free tier with low limits serves as the entry point

### Checkout & subscription flow
- No coupon/promo code support at launch
- Upgrades apply immediately with Stripe proration
- Downgrades take effect at end of current billing period (not immediate)
- Post-checkout redirect behavior: Claude's Discretion

### Payment failure handling
- No grace period — tenant is immediately restricted on payment failure
- Restricted tenant: can access wxcode-adm (to fix payment) but cannot access wxcode engine
- JWT tokens are revoked on payment failure, forcing re-authentication with restricted state
- Notification: email sent to tenant owner + admins with billing_access
- Automatic restoration: when Stripe confirms payment resolved (invoice.paid webhook), tenant is automatically restored to their paid plan — no manual intervention

### Enforcement behavior
- Warning headers at 80% and 100% of token quota in API responses
- Token usage: **overage billing** for paid plans — requests continue beyond quota, extra tokens billed at overage rate (never block a paying customer)
- Token usage on free tier: **hard block** at quota — HTTP 402 with upgrade prompt, no overage possible (no payment method)
- Member limit: **hard cap** on all plans — HTTP 402 when trying to invite beyond plan limit, must upgrade
- On payment failure: wxcode-adm accessible, wxcode engine blocked, JWT tokens revoked

### Claude's Discretion
- Post-checkout redirect destination (dashboard vs billing page)
- Stripe webhook retry/idempotency implementation details
- Token usage tracking granularity and storage approach
- Overage rate display and communication in warning headers

</decisions>

<specifics>
## Specific Ideas

- Token metering is the primary usage metric — wxcode engine operations consume tokens
- "Permite acessar apenas o wxcode-adm mas nao permite acessar o wxcode, revoga jwt tokens" — on payment lapse, admin access stays but engine access is cut and tokens are revoked
- Free tier is the permanent on-ramp, not a time-limited trial

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-billing-core*
*Context gathered: 2026-02-23*
