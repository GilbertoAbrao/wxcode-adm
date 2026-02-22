# Architecture Research

**Domain:** SaaS Authentication / Billing / Multi-Tenancy platform (Python/FastAPI/MongoDB)
**Researched:** 2026-02-22
**Confidence:** HIGH — stack is fixed, patterns verified against official docs and authoritative sources

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        WXCODE Platform                            │
│                                                                    │
│  ┌─────────────────┐           ┌──────────────────────────────┐   │
│  │  auth.wxcode.io │           │  wxcode (Engine/CLI)         │   │
│  │  (Next.js SPA)  │           │  validates JWT via pub key    │   │
│  └────────┬────────┘           │  calls /usage/report         │   │
│           │ HTTPS              └──────────┬───────────────────┘   │
│           │                              │ HTTP                   │
│           ▼                              ▼                        │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                      wxcode-adm API                         │   │
│  │               FastAPI  |  Port 8060                         │   │
│  │                                                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │   │
│  │  │   auth/  │  │ tenants/ │  │ billing/ │  │  admin/  │   │   │
│  │  │ Router   │  │ Router   │  │ Router   │  │ Router   │   │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │   │
│  │       └─────────────┴─────────────┴──────────────┘         │   │
│  │                          │                                  │   │
│  │              ┌───────────┴───────────┐                      │   │
│  │              │    Service Layer      │                      │   │
│  │              │ (business logic)      │                      │   │
│  │              └───────────┬───────────┘                      │   │
│  │                          │                                  │   │
│  │   ┌──────────────────────┼───────────────────────┐         │   │
│  │   ▼                      ▼                       ▼         │   │
│  │ ┌──────┐           ┌──────────┐           ┌──────────┐     │   │
│  │ │Redis │           │ MongoDB  │           │  Stripe  │     │   │
│  │ │Cache │           │ (Beanie) │           │   API    │     │   │
│  │ └──────┘           └──────────┘           └──────────┘     │   │
│  │                                                             │   │
│  │  ┌──────────────────────────────────────────────┐          │   │
│  │  │       Celery Worker (async tasks)            │          │   │
│  │  │  email_tasks | billing_tasks | cleanup_tasks │          │   │
│  │  └──────────────────────────────────────────────┘          │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌──────────────────┐                                             │
│  │  Stripe Webhooks │ ──────────────► /billing/webhooks/stripe    │
│  └──────────────────┘                                             │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow: Authentication (Primary Path)

```
Browser / CLI
     │
     ▼
POST /auth/login
     │
     ├─► [Redis] check token blacklist
     ├─► [MongoDB] fetch User by email
     ├─► [bcrypt] verify password
     ├─► [MFA?] check TOTP if enabled on tenant
     ├─► [JWT RS256] sign access_token + refresh_token
     │       claims: sub, tenant_id, role, plan, scopes, jti
     ├─► [Redis] store refresh token metadata (jti → user_id, ttl=30d)
     └─► [MongoDB] create Session record (device fingerprint)
             │
             ▼
         access_token (15min) + refresh_token (30d)
             │
             ▼
         wxcode engine receives access_token
         validates locally via RS256 public key
         NO network call to wxcode-adm required
```

### Data Flow: Stripe Webhook (Critical Path)

```
Stripe Event
     │
     ▼
POST /billing/webhooks/stripe
     │
     ├─► [IMMEDIATELY] verify Stripe-Signature header
     │       (5-min window enforced by Stripe)
     ├─► [MongoDB] idempotency check: stripe_event_id already processed?
     │       YES → return 200 immediately (do nothing)
     │       NO  → persist event as "processing"
     │
     ├─► [Celery] enqueue billing_task(event_type, event_data)
     │       return 200 to Stripe immediately (< 5s requirement)
     │
     └─► [Celery Worker] processes event:
             ├── customer.subscription.created
             │   └─► create/update Subscription in MongoDB
             ├── customer.subscription.updated
             │   └─► update plan limits on Tenant + Subscription
             ├── customer.subscription.deleted
             │   └─► downgrade to Free, set grace_period
             ├── invoice.paid
             │   └─► clear dunning flags, log Invoice
             ├── invoice.payment_failed
             │   └─► set dunning_level++, send payment_failed email
             └── mark event as "processed" in MongoDB
```

### Data Flow: Usage Reporting (wxcode → wxcode-adm)

```
wxcode Engine (after each conversion)
     │
     ▼
POST /billing/usage/report  [internal endpoint]
     Headers: X-API-Key: wxk_internal_...
     Body: { tenant_id, metric, quantity, timestamp }
     │
     ├─► [FastAPI] validate internal API key
     ├─► [MongoDB] write UsageRecord (tenant_id, metric, qty, period)
     ├─► [Redis] increment usage counter (INCRBY, keyed by tenant+metric+period)
     │   └─► fast read for limit enforcement (no DB hit per conversion)
     │
     └─► [Celery - scheduled] hourly aggregation task
             ├─► reads Redis counters
             ├─► calls stripe.UsageRecord.create() for metered billing
             └─► persists aggregated totals in MongoDB
```

---

## Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| **auth/ Router** | Signup, login, logout, OAuth flows, MFA, password reset, email verify | Service Layer, Redis, MongoDB, OAuth Providers |
| **auth/ Service** | JWT creation (RS256), token validation, bcrypt verify, refresh rotation | MongoDB, Redis, JWT library |
| **tenants/ Router** | CRUD tenants, member management, invitations, ownership transfer | Service Layer, MongoDB |
| **tenants/ Middleware** | Extract tenant_id from JWT claims on every request, attach to request state | Redis (token blacklist), MongoDB (tenant lookup) |
| **billing/ Router** | Stripe Checkout, Customer Portal URL, usage queries, invoice listing | Stripe API, MongoDB |
| **billing/ Webhooks** | Receive + verify Stripe events, enqueue to Celery | Redis (idempotency), MongoDB, Celery |
| **billing/ Usage** | Record per-tenant metrics, aggregate for Stripe metered billing | MongoDB, Redis counters, Stripe API |
| **apikeys/ Router** | Generate/revoke API keys with scopes, rate limits per key | MongoDB, Redis |
| **users/ Router** | Profile, password change, session listing, session revocation | MongoDB, Redis |
| **admin/ Router** | Super-admin: platform metrics, tenant list, plan management, feature flags | MongoDB, Redis, Stripe |
| **audit/ Service** | Append-only log of sensitive actions (no updates, ever) | MongoDB (audit_logs collection) |
| **email/ Service** | Dispatch transactional emails (verify, reset, invite, payment_failed) | Celery queue (async), SMTP |
| **middleware/ rate_limit** | Per-IP and per-user rate limits on sensitive endpoints | Redis (sliding window counters) |
| **middleware/ security** | Security headers (HSTS, CSP, X-Frame-Options), CORS, CSRF | — |
| **tasks/ Celery** | Async: email send, usage aggregation, Stripe sync, token cleanup | MongoDB, Redis, Stripe, SMTP |
| **Redis** | Token blacklist, refresh token metadata, rate limit counters, usage counters, session cache | All services |
| **MongoDB (Beanie)** | Primary data store: all entities with tenant_id isolation | All services |
| **Stripe** | Subscription lifecycle, invoices, metered usage, customer portal | billing/ service only |

---

## Recommended Project Structure

```
wxcode-adm/
├── src/
│   └── wxcode_adm/
│       ├── main.py                    # FastAPI app factory, lifespan, router registration
│       ├── config.py                  # pydantic-settings Settings class
│       ├── dependencies.py            # Shared FastAPI Depends: get_current_user, require_role,
│       │                              #   get_tenant_context, check_plan_limit
│       │
│       ├── auth/                      # Identity & credential management
│       │   ├── router.py              # /auth/* endpoints
│       │   ├── service.py             # AuthService: login, signup, token logic
│       │   ├── jwt.py                 # RS256 sign/verify, claim extraction
│       │   ├── oauth.py               # PKCE flow, provider callbacks
│       │   ├── mfa.py                 # TOTP setup/verify, backup codes
│       │   ├── password.py            # bcrypt hash/verify, policy
│       │   └── schemas.py             # Pydantic request/response models
│       │
│       ├── users/                     # User profile, sessions, API keys
│       │   ├── router.py              # /users/me endpoints
│       │   ├── service.py
│       │   ├── models.py              # User (Beanie Document)
│       │   └── schemas.py
│       │
│       ├── tenants/                   # Multi-tenancy: org, members, invitations
│       │   ├── router.py              # /tenants/* endpoints
│       │   ├── service.py             # TenantService: CRUD, membership, invites
│       │   ├── models.py              # Tenant, TenantMembership, Invitation
│       │   ├── schemas.py
│       │   └── middleware.py          # TenantContextMiddleware
│       │
│       ├── billing/                   # Stripe integration, usage metering
│       │   ├── router.py              # /billing/* endpoints
│       │   ├── service.py             # SubscriptionService: checkout, portal, plan changes
│       │   ├── stripe_client.py       # Thin Stripe SDK wrapper (test/live mode)
│       │   ├── webhooks.py            # Event handler dispatch (signature verify + queue)
│       │   ├── usage.py              # UsageTracker: record, aggregate, report to Stripe
│       │   ├── plans.py               # Plan definitions, limit enforcement
│       │   ├── models.py              # Subscription, UsageRecord, Invoice, StripeEvent
│       │   └── schemas.py
│       │
│       ├── apikeys/                   # API key lifecycle
│       │   ├── router.py              # /api-keys/* endpoints
│       │   ├── service.py
│       │   ├── models.py              # APIKey (hashed, prefixed)
│       │   └── schemas.py
│       │
│       ├── audit/                     # Immutable audit trail
│       │   ├── service.py             # AuditService.log() — append-only
│       │   ├── models.py              # AuditLog (no delete, no update)
│       │   └── schemas.py
│       │
│       ├── admin/                     # Super-admin: platform-wide management
│       │   ├── router.py              # /admin/* (super_admin role required)
│       │   ├── service.py             # Platform metrics, tenant ops, config
│       │   └── schemas.py
│       │
│       ├── email/                     # Transactional email
│       │   ├── service.py             # EmailService.send_*() methods
│       │   └── templates/             # Jinja2 HTML templates
│       │       ├── verify_email.html
│       │       ├── reset_password.html
│       │       ├── invite_member.html
│       │       └── payment_failed.html
│       │
│       ├── middleware/                # Global FastAPI middleware
│       │   ├── rate_limit.py          # Redis sliding-window rate limiter
│       │   ├── security.py            # Security headers, CORS, CSRF tokens
│       │   └── tenant_context.py      # Set request.state.tenant_id from JWT
│       │
│       ├── tasks/                     # Celery async workers
│       │   ├── worker.py              # Celery app definition, beat schedule
│       │   ├── email_tasks.py         # send_verification_email, etc.
│       │   ├── billing_tasks.py       # process_webhook_event, aggregate_usage
│       │   └── cleanup_tasks.py       # expire tokens, purge old sessions
│       │
│       └── common/                    # Shared utilities
│           ├── exceptions.py          # HTTPException subclasses with error codes
│           ├── pagination.py          # Cursor-based pagination helper
│           ├── security.py            # Constant-time compare, token generators
│           └── redis_client.py        # Redis connection pool singleton
│
├── tests/
│   ├── conftest.py                    # mongomock + Redis fake fixtures, auth helpers
│   ├── test_auth/
│   ├── test_tenants/
│   ├── test_billing/                  # Stripe mock fixtures critical here
│   └── test_users/
│
├── .env.example
├── requirements.txt
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

### Structure Rationale

- **Domain modules (auth, tenants, billing, users, admin, apikeys, audit):** Each owns its router, service, models, and schemas. No cross-domain model imports — services communicate through their public interfaces only. This prevents circular dependencies and makes each domain independently testable.
- **billing/ is the most complex module:** Split `webhooks.py`, `usage.py`, and `stripe_client.py` explicitly to separate concerns — webhook ingestion, usage tracking, and Stripe SDK wrapping are distinct responsibilities.
- **tasks/ at top level, not inside billing/:** Celery tasks orchestrate across domains (billing + email + cleanup) — keeping them at the same level as domain modules prevents inappropriate coupling.
- **common/redis_client.py:** Redis connection pool created once at app startup, shared via dependency injection — not scattered across modules.
- **admin/ as its own module:** Super-admin is a separate concern from tenant-admin. Different auth requirements (`super_admin` role), different data access patterns (cross-tenant queries), and different risk profile warrant isolation.

---

## Architectural Patterns

### Pattern 1: Tenant Context as Immutable Request State

**What:** Every authenticated request carries `request.state.tenant` (a `TenantContext` dataclass with `tenant_id`, `plan`, `limits`, `role`). Populated once by middleware from JWT claims. Never passed as function arguments through the call stack.

**When to use:** All domain services that need tenant scoping — which is all of them.

**Trade-offs:** Slightly implicit (context in request state vs. explicit argument), but eliminates the repeated `tenant_id` parameter threading that causes bugs when forgotten.

**Example:**
```python
# middleware/tenant_context.py
@app.middleware("http")
async def inject_tenant_context(request: Request, call_next):
    token = extract_bearer(request)
    if token:
        claims = jwt_service.decode(token)  # verifies RS256 signature
        tenant = await tenant_cache.get(claims["tenant_id"])
        request.state.tenant = TenantContext(
            tenant_id=claims["tenant_id"],
            role=claims["role"],
            plan=tenant.plan,
            limits=PLAN_LIMITS[tenant.plan],
        )
    return await call_next(request)

# In any service — NO tenant_id parameter threading
class ConversionService:
    async def check_quota(self, request: Request) -> None:
        ctx = request.state.tenant
        usage = await redis.get(f"usage:{ctx.tenant_id}:conversions:{current_period()}")
        if int(usage or 0) >= ctx.limits.conversions_per_month:
            raise QuotaExceededError(ctx.limits.conversions_per_month)
```

### Pattern 2: Stripe Webhook — Receive Fast, Process Async

**What:** The webhook endpoint does exactly three things synchronously: verify signature, check idempotency, enqueue to Celery. All business logic runs in the worker. The endpoint returns 200 in under 5 seconds — always.

**When to use:** Every Stripe webhook handler. Non-negotiable — Stripe's 5-minute signature window combined with retry behavior means synchronous processing causes duplicate events.

**Trade-offs:** Adds Celery dependency, but eliminates webhook timeouts, duplicate processing bugs, and Stripe disabling your endpoint.

**Example:**
```python
# billing/webhooks.py
@router.post("/billing/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    # Step 1: Verify signature (raises if invalid or > 5 min old)
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    # Step 2: Idempotency check
    existing = await StripeEvent.find_one(StripeEvent.stripe_id == event["id"])
    if existing:
        return {"status": "already_processed"}

    # Step 3: Persist + enqueue (fail-safe: persist before enqueue)
    record = StripeEvent(stripe_id=event["id"], type=event["type"], status="queued")
    await record.insert()
    process_stripe_event.delay(event["id"], event["type"], dict(event["data"]["object"]))

    return {"status": "queued"}
```

### Pattern 3: RS256 JWT with Public Key Distribution

**What:** wxcode-adm signs tokens with its RSA private key. The wxcode engine validates tokens locally using the distributed RSA public key. Zero network calls to wxcode-adm per engine request.

**When to use:** All inter-service token validation in the wxcode platform.

**Trade-offs:** Token revocation requires a blacklist (Redis `jti` check in wxcode-adm middleware only — the engine doesn't check the blacklist). This is the known RS256 tradeoff: stateless validation vs. instant revocation. Mitigate with short-lived access tokens (15 minutes).

**Example:**
```python
# auth/jwt.py
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt

class JWTService:
    def __init__(self, private_key_pem: str, public_key_pem: str):
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
        self._public_key = public_key_pem  # distributed to wxcode engine

    def create_access_token(self, user: User, tenant: Tenant) -> str:
        payload = {
            "sub": str(user.id),
            "tenant_id": str(tenant.id),
            "role": tenant.membership.role,
            "plan": tenant.subscription.plan,
            "scopes": user.api_scopes,
            "jti": str(uuid4()),          # for blacklist on logout
            "iat": now(),
            "exp": now() + timedelta(minutes=15),
        }
        return pyjwt.encode(payload, self._private_key, algorithm="RS256")

    def decode(self, token: str) -> dict:
        return pyjwt.decode(token, self._public_key, algorithms=["RS256"])
```

### Pattern 4: Redis-Backed Usage Counters with Periodic Flush

**What:** Every usage event (conversion, API call, token consumption) increments a Redis counter atomically. Counters are keyed as `usage:{tenant_id}:{metric}:{YYYY-MM}`. Quota enforcement reads Redis — not MongoDB. A scheduled Celery task (hourly) flushes Redis totals to MongoDB and reports to Stripe Metered Billing.

**When to use:** Any high-frequency per-tenant metric that needs real-time quota enforcement.

**Trade-offs:** Redis counters are eventually consistent with MongoDB (up to 1-hour drift). Acceptable for billing; not acceptable for financial ledgers. Counters can be lost on Redis restart — initialize from MongoDB on startup.

**Example:**
```python
# billing/usage.py
async def record_usage(tenant_id: str, metric: str, quantity: int = 1):
    key = f"usage:{tenant_id}:{metric}:{current_billing_period()}"
    await redis.incrby(key, quantity)
    await redis.expire(key, 90 * 24 * 3600)  # 90-day TTL, cleaned by period rollover

async def check_quota(tenant_id: str, metric: str, limit: int) -> bool:
    key = f"usage:{tenant_id}:{metric}:{current_billing_period()}"
    current = int(await redis.get(key) or 0)
    return current < limit  # True = under quota
```

### Pattern 5: Repository-Free Direct Beanie Queries with tenant_id Guard

**What:** Beanie Documents are queried directly in service methods. No repository layer. Every query that touches tenant-scoped data MUST include `.find(Model.tenant_id == ctx.tenant_id, ...)` — enforced by code review and tested with isolation tests.

**When to use:** This project's scale (one tenant per user model, small team) doesn't warrant a full repository pattern. Direct Beanie queries with mandatory tenant_id filtering is simpler and equally safe.

**Trade-offs:** Relies on discipline and tests rather than structural enforcement. Counter this with integration tests that verify cross-tenant data isolation explicitly (`test_tenants/test_isolation.py`).

**Example:**
```python
# tenants/service.py
async def get_tenant_members(tenant_id: str, ctx: TenantContext) -> list[User]:
    # tenant_id from ctx (JWT-derived), not from URL param directly
    return await TenantMembership.find(
        TenantMembership.tenant_id == ctx.tenant_id  # isolation enforced here
    ).to_list()
```

---

## Data Flow Summary

### Request Flow (Authenticated API Call)

```
Client Request
    │
    ├─► [Middleware: security.py]      — security headers, CORS
    ├─► [Middleware: rate_limit.py]    — check Redis sliding window
    ├─► [Middleware: tenant_context.py] — decode JWT, set request.state.tenant
    │
    ▼
Router (FastAPI)
    │
    ├─► [Dependency: get_current_user]  — resolve User from JWT sub
    ├─► [Dependency: require_role("admin")] — check role in tenant context
    │
    ▼
Service Layer
    ├─► [Redis] — quota checks, cache reads
    ├─► [MongoDB / Beanie] — data queries (all scoped by tenant_id)
    └─► [Stripe / Email] — external calls when needed

    ▼
Response (Pydantic schema serialization)
```

### Key Data Flows

1. **Signup flow:** Browser → POST /auth/signup → create User → create Tenant (personal) → create TenantMembership (Owner) → create Stripe Customer → queue verify_email task → return access_token + refresh_token

2. **Plan upgrade flow:** Browser → POST /billing/checkout → create Stripe Checkout Session → redirect to Stripe → Stripe redirects back → Stripe fires `customer.subscription.created` webhook → Celery updates Subscription + Tenant.plan in MongoDB → user's next JWT reflects new plan limits

3. **Conversion quota enforcement flow:** wxcode engine → check_quota(tenant_id, "conversions") → Redis read (no DB) → proceed if under limit → execute conversion → POST /billing/usage/report → Redis INCRBY → hourly Celery flush to Stripe

4. **Token refresh flow:** Client → POST /auth/refresh → Redis check (refresh jti exists and not blacklisted) → issue new access_token (same tenant context) → optional: rotate refresh token (delete old jti, store new jti)

5. **Logout flow:** Client → POST /auth/logout → Redis: add access jti to blacklist (ttl = token remaining expiry) → Redis: delete refresh jti → MongoDB: update Session.revoked_at

---

## Anti-Patterns

### Anti-Pattern 1: Synchronous Stripe Webhook Processing

**What people do:** Process all Stripe business logic synchronously inside the webhook handler function.
**Why it's wrong:** Stripe expects a response within 5 seconds. A slow database write or email send causes a timeout. Stripe retries. You get duplicate events. Subscription state becomes inconsistent.
**Do this instead:** Verify signature + check idempotency + enqueue to Celery, then return 200. Total handler time: under 100ms.

### Anti-Pattern 2: Trusting URL tenant_id Over JWT tenant_id

**What people do:** `GET /tenants/{tenant_id}/members` — fetch members for the tenant_id in the URL path.
**Why it's wrong:** A user in Tenant A can request `/tenants/{tenant_b_id}/members` and see another tenant's data.
**Do this instead:** Always use `request.state.tenant.tenant_id` (from JWT) as the authoritative tenant scope. Validate that the URL's tenant_id matches the JWT tenant_id where needed, never use URL param as the isolation boundary.

### Anti-Pattern 3: Storing Stripe Customer State Without Webhook Sync

**What people do:** Update subscription state directly after Stripe API calls (checkout session creation, subscription update).
**Why it's wrong:** Stripe is the source of truth for billing state. API responses can be stale, out-of-order, or followed by corrections. Subscription state must be driven by webhook events.
**Do this instead:** After any Stripe API call, wait for the corresponding webhook event to update local state. Store a "pending" status and resolve it when the webhook arrives.

### Anti-Pattern 4: Sharing JWT Secret Across Services

**What people do:** All services share an HS256 secret, so any service can sign tokens.
**Why it's wrong:** Any compromised service can forge tokens for any user in any tenant. The blast radius of a breach is the entire platform.
**Do this instead:** RS256 asymmetric keys — only wxcode-adm has the private key and can sign. wxcode engine only has the public key and can only verify. A compromised wxcode engine cannot forge tokens.

### Anti-Pattern 5: Missing Idempotency on Usage Reporting

**What people do:** wxcode engine posts usage, the handler increments the counter. On retry (network failure), usage is double-counted.
**Why it's wrong:** The user gets billed twice for the same conversion. Quota is exhausted prematurely.
**Do this instead:** Each usage report carries a unique `idempotency_key` (e.g., `conversion_id`). wxcode-adm checks Redis or MongoDB before recording — if key seen, return 200 without incrementing.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Stripe** | REST API via stripe-python SDK; webhooks for state sync | Idempotency keys on all write calls. Never trust API response state — wait for webhook. Test mode and live mode share same code path via STRIPE_SECRET_KEY prefix. |
| **OAuth Providers (Google, GitHub, Microsoft)** | Authorization Code Flow with PKCE; callback to /auth/oauth/{provider}/callback | State param (CSRF) stored in Redis with 10-min TTL. Provider token exchanged for user info; never stored. |
| **SMTP (Email)** | Async via fastapi-mail / aiosmtplib | All email sending via Celery tasks — never block request path. Retry on SMTP failure. |
| **wxcode Engine** | HTTP REST (engine calls wxcode-adm for quota checks; wxcode-adm has no inbound dependency on engine) | Engine authenticates with internal API key (`wxk_internal_` prefix). Separate from user-facing JWT. |

### Internal Module Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| auth/ ↔ tenants/ | Direct service call during signup only (create tenant + membership) | Post-signup: no cross-domain coupling. |
| billing/ ↔ tenants/ | billing/ reads Tenant.subscription_id; updates Tenant.plan on webhook | Tenant is the billing unit. Subscription is owned by billing/, referenced by tenants/. |
| billing/ ↔ tasks/ | Celery task dispatch (fire-and-forget) | billing/webhooks.py enqueues; tasks/billing_tasks.py executes. |
| auth/ ↔ email/ | Via tasks/ only (never direct) | auth/ enqueues email tasks; email/ service is invoked by Celery workers. |
| admin/ ↔ all | Read-only cross-tenant queries + config writes | admin/ is the only module permitted to query across tenant_id boundaries. |
| middleware/ ↔ auth/ | middleware reads JWT via auth/jwt.py | One-directional: middleware imports jwt service; auth router does not import middleware. |

---

## Suggested Build Order

Build order is dictated by dependency: lower layers must exist before higher layers can be built.

```
Phase 1: Foundation
├── config.py + Settings (pydantic-settings)
├── MongoDB connection + Beanie init
├── Redis connection pool
├── common/exceptions.py
└── main.py (app factory, lifespan events)

Phase 2: Auth Core  [blocks everything else]
├── users/models.py (User document)
├── auth/jwt.py (RS256 sign/verify)
├── auth/password.py (bcrypt)
├── auth/schemas.py
├── auth/service.py
├── auth/router.py (signup, login, refresh, logout)
└── middleware/tenant_context.py

Phase 3: Multi-Tenancy
├── tenants/models.py (Tenant, TenantMembership)
├── tenants/service.py
├── tenants/router.py (CRUD, members)
├── dependencies.py (get_current_user, require_role, get_tenant_context)
└── Update auth/service.py: create personal tenant on signup

Phase 4: Billing Core
├── billing/plans.py (plan limits definitions)
├── billing/models.py (Subscription, Invoice, StripeEvent)
├── billing/stripe_client.py (SDK wrapper)
├── billing/service.py (checkout, portal)
├── billing/webhooks.py (receive + queue)
├── tasks/worker.py (Celery app)
├── tasks/billing_tasks.py (process_stripe_event)
└── billing/router.py

Phase 5: Usage Metering
├── billing/usage.py (record, check, aggregate)
├── tasks/billing_tasks.py: add aggregate_usage periodic task
└── /billing/usage/report internal endpoint

Phase 6: Supporting Features
├── auth/oauth.py + OAuth router endpoints
├── auth/mfa.py + MFA router endpoints
├── apikeys/models.py + service + router
├── audit/service.py + models (append-only)
├── email/service.py + templates
├── tasks/email_tasks.py
└── middleware/rate_limit.py

Phase 7: Admin & Observability
├── admin/router.py + service.py (super-admin)
├── tasks/cleanup_tasks.py
└── users/router.py (sessions, profile)
```

**Rationale for this ordering:**
- Auth Core (Phase 2) is the prerequisite for everything — no other module can be tested without authentication.
- Multi-Tenancy (Phase 3) must precede Billing because Stripe Customer is created per-tenant, not per-user.
- Billing Core (Phase 4) before Usage Metering (Phase 5) because metering depends on Subscription state to know what to meter against.
- Supporting features (Phase 6) are independent of each other but depend on Phase 3 (tenant context) for scoping.
- Admin (Phase 7) last because it reads from all other modules; building it last lets it query complete data.

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0–500 tenants | Single wxcode-adm instance, single MongoDB, Redis Standalone. Current architecture handles this with no changes. |
| 500–10K tenants | Add MongoDB read replicas for audit log queries. Redis Sentinel for HA. Add Celery worker replicas (stateless). Rate limit tuning. |
| 10K+ tenants | MongoDB sharding by tenant_id. Redis Cluster. Dedicated Celery queues per task type (email vs billing vs cleanup). Consider extracting usage metering to a separate service. |

### Scaling Priorities

1. **First bottleneck:** Celery worker queue depth during Stripe webhook bursts (end-of-month billing). Fix: add more Celery worker replicas — they're stateless.
2. **Second bottleneck:** MongoDB query performance on tenant_id-filtered collections as usage_records grows. Fix: composite index `(tenant_id, period, metric)` — add during Phase 5 before data grows.
3. **Third bottleneck (future):** Usage aggregation job contention at billing period close. Fix: partition aggregation by tenant_id range across multiple Celery workers.

---

## MongoDB Collections and Index Strategy

| Collection | Key Indexes | Notes |
|------------|-------------|-------|
| `users` | `email` (unique), `tenant_id` | Always query by email or tenant_id |
| `tenants` | `stripe_customer_id` (unique), `slug` (unique) | Webhook lookup by customer_id |
| `tenant_memberships` | `(tenant_id, user_id)` (unique composite) | Membership check is the hot path |
| `subscriptions` | `tenant_id` (unique), `stripe_subscription_id` (unique) | One subscription per tenant |
| `usage_records` | `(tenant_id, metric, period)` (composite) | All usage queries use this composite |
| `stripe_events` | `stripe_id` (unique) | Idempotency check on every webhook |
| `api_keys` | `key_hash` (unique), `tenant_id` | Auth lookup by hash, list by tenant |
| `audit_logs` | `tenant_id + created_at` (compound), `actor_id` | Append-only, no updates ever |
| `sessions` | `jti` (unique), `(user_id, active)` | Refresh token validation hot path |
| `invitations` | `token` (unique), `(tenant_id, email)` | Invite lookup and duplicate check |

**Rule:** Every collection that contains tenant-scoped data has `tenant_id` as the first field in all composite indexes. Queries without `tenant_id` in the filter are treated as bugs.

---

## Sources

- WorkOS Developer Guide to SaaS Multi-Tenant Architecture: https://workos.com/blog/developers-guide-saas-multi-tenant-architecture (HIGH confidence — authoritative SaaS infrastructure vendor)
- Stigg: Stripe Webhook Best Practices: https://www.stigg.io/blog-posts/best-practices-i-wish-we-knew-when-integrating-stripe-webhooks (MEDIUM confidence — practitioner post-mortem)
- Stripe Official API — Idempotent Requests: https://docs.stripe.com/api/idempotent_requests (HIGH confidence — official Stripe documentation)
- Stripe Official API — Webhook Signature Verification: https://docs.stripe.com/webhooks (HIGH confidence — official Stripe documentation)
- SuperTokens: RS256 vs HS256: https://supertokens.com/blog/rs256-vs-hs256 (MEDIUM confidence — auth infrastructure vendor)
- microservices.io: Authentication and authorization with JWT (2025): https://microservices.io/post/architecture/2025/07/22/microservices-authn-authz-part-3-jwt-authorization.html (HIGH confidence — authoritative microservices architecture resource)
- FastAPI + Beanie ODM integration patterns: https://testdriven.io/blog/fastapi-beanie/ (MEDIUM confidence — practitioner tutorial, verified against Beanie docs)
- Frontegg: SaaS Multitenancy Components: https://frontegg.com/blog/saas-multitenancy (MEDIUM confidence — auth infrastructure vendor)

---
*Architecture research for: WXCODE ADM — SaaS Auth/Billing/Multi-Tenancy platform*
*Researched: 2026-02-22*
