# Stack Research

**Domain:** SaaS Auth/Billing/Multi-tenancy platform (Python/FastAPI/MongoDB)
**Researched:** 2026-02-22
**Confidence:** HIGH (all core versions verified against PyPI/official sources)

---

## Constraints (Non-Negotiable)

These are fixed by the parent project (wxcode) and cannot be changed:

| Technology | Reason Fixed |
|------------|-------------|
| Python 3.11+ | Stack consistency with wxcode engine |
| FastAPI | Stack consistency with wxcode engine |
| Beanie ODM | Stack consistency with wxcode engine |
| MongoDB | Stack consistency with wxcode engine |
| Redis | Rate limiting, token blacklist, sessions |
| Docker/VPS | Same infra as wxcode |

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Runtime | Fixed constraint; 3.11 brings significant async performance improvements over 3.10 |
| FastAPI | 0.131.0 | API framework | Fixed constraint; Pydantic v2 integration, native async, auto OpenAPI docs |
| Uvicorn | 0.41.0 | ASGI server | Standard production server for FastAPI; supports `--workers` for multi-process |
| Pydantic | 2.12.5 | Data validation / schemas | FastAPI 0.131+ requires Pydantic v2; v2 is 5-50x faster than v1, uses Rust core |
| pydantic-settings | 2.13.1 | Configuration / env vars | Official Pydantic settings management; type-safe `.env` loading, SecretStr support |
| Beanie ODM | 2.0.1 | MongoDB async ODM | Fixed constraint; v2.0 moves from Motor to PyMongo Async API, Pydantic v2 native |
| Motor | 3.7.1 | Async MongoDB driver | Beanie v2.0 dependency; still required as a transitive dep even after Beanie's internal shift |
| Redis (redis-py) | 7.2.0 | Cache / rate limiting / token blacklist | Fixed constraint; redis-py 4.2+ merged aioredis, use `from redis.asyncio import Redis` |

### Authentication & Security

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| PyJWT | 2.11.0 | JWT creation and verification (RS256) | FastAPI team officially migrated docs from `python-jose` to PyJWT; `python-jose` last released 2021 and has known security issues. Install with `pyjwt[crypto]` for RS256 support |
| pwdlib | 0.3.0 | Password hashing | Modern replacement for `passlib` (unmaintained, incompatible with Python 3.13+ crypt removal); use `pwdlib[argon2]` — Argon2id is the OWASP and PHC winner, memory-hard, GPU-resistant |
| pyotp | 2.9.0 | TOTP/MFA — generates and verifies one-time passwords | Standard library for RFC 6238 TOTP; generates `otpauth://` URIs for authenticator apps |
| qrcode | 8.2 | QR code image generation for TOTP setup | Paired with pyotp to generate QR codes for Google Authenticator/Authy enrollment |
| authlib | 1.6.8 | OAuth 2.0 social login (Google, GitHub, Microsoft) | The most complete OAuth 2.0 / OIDC client library for Python; Starlette/FastAPI integration built-in via `authlib.integrations.starlette_client` |
| cryptography | latest | RSA key pair operations | Required by `pyjwt[crypto]`; generates/loads RS256 PEM keys used for self-contained JWTs |
| itsdangerous | latest | Signed tokens for email verification / password reset | URLSafeTimedSerializer produces time-limited tokens safe for use in email links; no database lookups needed |

### Billing

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| stripe | 14.3.0 | Stripe billing integration | Official Stripe Python SDK; covers Checkout, Subscriptions, Billing Meters (usage-based), Customer Portal, and Webhook signature verification. No alternative — use Stripe's own SDK |

### Email

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| fastapi-mail | 1.6.2 | Transactional email (SMTP/STARTTLS or API-based) | Async-native mail library designed for FastAPI; supports Jinja2 HTML templates for email verification and password reset flows |

### Background Tasks

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| arq | 0.27.0 | Async job queue backed by Redis | Fully asyncio-native (no sync/async bridging like Celery requires); handles email delivery, Stripe webhook retries, audit log writes. Uses the already-required Redis. v0.27.0 adds Python 3.13 support; maintenance mode confirmed but stable |

### Rate Limiting

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| slowapi | 0.1.9 | Per-IP and per-user rate limiting | Battle-tested FastAPI/Starlette wrapper around `limits`; supports Redis backend for distributed rate limiting across multiple app instances; decorator-based API mirrors Flask-Limiter which team likely knows |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| pytest | latest | Test runner | Standard |
| pytest-asyncio | 1.3.0 | Async test support | Required for testing FastAPI + Beanie async routes; use `asyncio_mode = "auto"` in `pytest.ini` |
| httpx | 0.28.1 | HTTP client for tests + OAuth calls | TestClient and AsyncClient for integration tests; also used in OAuth flows with authlib |
| mongomock-motor | latest | In-memory MongoDB for tests | Avoid hitting real MongoDB in unit tests; `AsyncMongoMockClient` replaces Motor client |
| python-dotenv | latest | `.env` loading in dev | pydantic-settings handles this natively; python-dotenv is only needed if using bare env var loading outside settings class |

---

## Supporting Libraries (Optional, Phase-Specific)

| Library | Purpose | When to Add |
|---------|---------|-------------|
| Pillow | Image processing backend for `qrcode` | Required when generating QR images via `qrcode[pil]`; add at TOTP phase |
| APScheduler / arq scheduled jobs | Scheduled billing metric aggregation | When building usage-based billing aggregation; arq supports `cron=...` in worker |
| prometheus-fastapi-instrumentator | Metrics endpoint for Prometheus/Grafana | When adding observability; not needed for MVP |
| sentry-sdk | Error tracking | Add when going to production; one-line FastAPI integration |

---

## Installation

```bash
# Core runtime
pip install \
  "fastapi==0.131.0" \
  "uvicorn[standard]==0.41.0" \
  "pydantic==2.12.5" \
  "pydantic-settings==2.13.1" \
  "beanie==2.0.1" \
  "motor==3.7.1" \
  "redis==7.2.0"

# Auth & security
pip install \
  "pyjwt[crypto]==2.11.0" \
  "pwdlib[argon2]==0.3.0" \
  "pyotp==2.9.0" \
  "qrcode[pil]==8.2" \
  "authlib==1.6.8" \
  "itsdangerous"

# Billing
pip install "stripe==14.3.0"

# Email
pip install "fastapi-mail==1.6.2"

# Background tasks & rate limiting
pip install "arq==0.27.0" "slowapi==0.1.9"

# Dev / test
pip install -D \
  "pytest" \
  "pytest-asyncio==1.3.0" \
  "httpx==0.28.1" \
  "mongomock-motor"
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| JWT library | PyJWT 2.11.0 | python-jose | python-jose: last released 2021, has CVEs, FastAPI team explicitly deprecated its use in docs (Discussion #11345). PyJWT is actively maintained by the JWT community |
| JWT library | PyJWT 2.11.0 | fastapi-jwt | Wrapper around python-jose — same abandoned dependency problem |
| Password hashing | pwdlib[argon2] | passlib[bcrypt] | passlib: unmaintained since 2023, uses Python `crypt` module removed in Python 3.13; Argon2 is strictly superior to bcrypt for brute-force resistance |
| OAuth social login | authlib | httpx-oauth (fastapi-users dep) | authlib has broader OAuth/OIDC provider coverage and is actively maintained by a full-time author; httpx-oauth is narrower and tied to fastapi-users |
| OAuth social login | authlib | fastapi-users | fastapi-users bundles too much opinionated scaffolding; we need control over user model, multi-tenancy fields, and RBAC that conflicts with fastapi-users' User model |
| Background tasks | arq | Celery | Celery requires a separate worker process framework, is synchronous by default (async support is bolted on), and adds Redis + broker configuration complexity. arq is lighter, async-native, and uses the Redis we already have |
| Background tasks | arq | FastAPI BackgroundTasks | Built-in BackgroundTasks runs inside the request/response cycle — if the server restarts, jobs are lost. Not acceptable for email delivery or Stripe event processing |
| Rate limiting | slowapi | fastapi-limiter | fastapi-limiter has not been updated since 2023; slowapi is more actively maintained and has Redis backend support |
| Rate limiting | slowapi | fastapi-advanced-rate-limiter | Very new project (2024), insufficient production track record |
| Email | fastapi-mail | SendGrid SDK / Mailgun SDK | Vendor-specific SDKs lock to a provider; fastapi-mail is provider-agnostic (SMTP, or configure with any SMTP provider) and supports templates |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `python-jose` | Not maintained since 2021, known CVEs, FastAPI team abandoned it — see GitHub Discussion #11345 | `pyjwt[crypto]` |
| `passlib` | Uses Python `crypt` module deprecated in 3.12, removed in 3.13; not maintained since 2023 | `pwdlib[argon2]` |
| `aioredis` (standalone) | Merged into `redis-py` in v4.2 (2022); standalone `aioredis` last released December 2021, effectively dead | `redis==7.2.0` with `from redis.asyncio import Redis` |
| `fastapi-users` | Highly opinionated user model fights multi-tenancy and custom RBAC; takes over auth routing in ways that conflict with tenant-scoped JWT claims design | Build auth routes directly with PyJWT + Beanie |
| `Celery` for async tasks | Sync-first library with bolted-on async; requires more infrastructure; overkill when arq + Redis already in the stack | `arq` |
| `databases` (encode/databases) | Designed for SQL databases; MongoDB/Beanie already handles async DB access natively | Beanie ODM |
| Pydantic v1 | FastAPI 0.131+ requires Pydantic v2 minimum 2.7.0; v1 support is deprecated | Pydantic v2 |

---

## Stack Patterns by Variant

**JWT RS256 self-contained tokens (required for wxcode validation without callback):**
- Generate RSA key pair at startup (or load from secrets): `openssl genrsa -out private.pem 2048`
- Sign tokens with private key in wxcode-adm
- Share public key with wxcode (file mount or env var)
- wxcode validates locally: `jwt.decode(token, public_key, algorithms=["RS256"])`
- Token payload includes: `sub` (user_id), `tenant_id`, `roles`, `plan`, `exp`, `iat`

**Multi-tenancy logical isolation:**
- Every Beanie document model includes `tenant_id: PydanticObjectId` as an indexed field
- FastAPI dependency `get_current_tenant()` extracts `tenant_id` from JWT
- All queries filter by `tenant_id` — enforced via base query helper, not ad-hoc per route
- Never trust `tenant_id` from request body — always from verified JWT

**TOTP/MFA enrollment flow:**
- Generate `pyotp.random_base32()` secret, store encrypted in user document (not plaintext)
- Return `pyotp.TOTP(secret).provisioning_uri()` URI
- Render URI as QR code via `qrcode[pil]` → return as base64 PNG
- Verify with `pyotp.TOTP(secret).verify(code)` before enabling MFA

**Stripe webhook processing:**
- Verify signature: `stripe.Webhook.construct_event(payload, sig_header, secret)`
- Enqueue verified events to arq job queue — never process inline
- Idempotency: store `stripe_event_id` in MongoDB and skip duplicates

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| beanie 2.0.1 | pydantic >=2.0, motor >=3.0 | Beanie v2.0 requires Pydantic v2; v1.x was compatible with Pydantic v1 |
| fastapi 0.131.0 | pydantic >=2.7.0 | FastAPI dropped Pydantic v1 support; requires v2.7+ minimum |
| pyjwt 2.11.0 | cryptography >=3.4 | `pyjwt[crypto]` installs cryptography automatically |
| authlib 1.6.8 | httpx >=0.23.0 | Starlette integration uses httpx as the HTTP client for OAuth flows |
| slowapi 0.1.9 | starlette >=0.14 (fastapi >=0.63) | slowapi depends on Starlette internals; works with current FastAPI |
| arq 0.27.0 | Python 3.9+, redis >=4.2.0 | arq 0.27.0 adds Python 3.13 support; uses redis-py asyncio internally |
| pytest-asyncio 1.3.0 | Python >=3.10, pytest >=8.0 | Use `asyncio_mode = "auto"` in pytest.ini to avoid per-test decorators |

---

## Sources

- FastAPI official docs — https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ — JWT patterns
- FastAPI GitHub Discussion #11345 — https://github.com/fastapi/fastapi/discussions/11345 — python-jose deprecation
- FastAPI GitHub PR #13917 — https://github.com/fastapi/fastapi/pull/13917 — passlib → pwdlib migration
- Beanie ODM PyPI — https://pypi.org/project/beanie/ — version 2.0.1 (Nov 20, 2025) [HIGH confidence]
- FastAPI PyPI — https://pypi.org/project/fastapi/ — version 0.131.0 (Feb 22, 2026) [HIGH confidence]
- PyJWT PyPI — https://pypi.org/project/PyJWT/ — version 2.11.0 (Jan 30, 2026) [HIGH confidence]
- stripe PyPI — https://pypi.org/project/stripe/ — version 14.3.0 (Jan 28, 2026) [HIGH confidence]
- redis-py PyPI — https://pypi.org/project/redis/ — version 7.2.0 (Feb 16, 2026) [HIGH confidence]
- pydantic-settings PyPI — https://pypi.org/project/pydantic-settings/ — version 2.13.1 (Feb 19, 2026) [HIGH confidence]
- pwdlib PyPI — https://pypi.org/project/pwdlib/ — version 0.3.0 (Oct 25, 2025) [HIGH confidence]
- authlib GitHub releases — https://github.com/lepture/authlib/releases — version 1.6.8 (Feb 17, 2025) [HIGH confidence]
- arq GitHub releases — https://github.com/python-arq/arq/releases — version 0.27.0 (Feb 2, 2025) [HIGH confidence]
- fastapi-mail PyPI — https://pypi.org/project/fastapi-mail/ — version 1.6.2 (Feb 17, 2026) [HIGH confidence]
- slowapi PyPI/GitHub — version 0.1.9 (Feb 5, 2024) [HIGH confidence — latest available]
- pyotp GitHub releases — https://github.com/pyauth/pyotp/releases — version 2.9.0 (Jul 27, 2023) [HIGH confidence — library is stable, TOTP spec doesn't change]
- qrcode PyPI — version 8.2 (May 1, 2025) [MEDIUM confidence — from search result, not direct PyPI fetch]
- motor PyPI — https://pypi.org/project/motor/ — version 3.7.1 (May 14, 2025) [HIGH confidence]
- pydantic PyPI — version 2.12.5 (Nov 26, 2025) [HIGH confidence]
- uvicorn PyPI — https://pypi.org/project/uvicorn/ — version 0.41.0 (Feb 16, 2026) [HIGH confidence]
- pytest-asyncio PyPI — version 1.3.0 (Nov 10, 2025) [HIGH confidence]
- httpx PyPI — version 0.28.1 (Dec 6, 2024) [HIGH confidence]
- Stripe docs — https://docs.stripe.com/billing/subscriptions/usage-based/implementation-guide — usage-based billing patterns
- MongoDB multi-tenancy docs — https://www.mongodb.com/docs/atlas/build-multi-tenant-arch/ — logical isolation patterns

---
*Stack research for: WXCODE ADM — SaaS Auth/Billing/Multi-tenancy*
*Researched: 2026-02-22*
