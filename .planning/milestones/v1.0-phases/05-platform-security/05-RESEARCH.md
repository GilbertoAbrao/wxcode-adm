# Phase 5: Platform Security - Research

**Researched:** 2026-02-23
**Domain:** Rate limiting (slowapi + Redis), audit log (SQLAlchemy append-only), HTML transactional email templates (Jinja2 + fastapi-mail)
**Confidence:** HIGH (stack already installed, codebase patterns well-understood, official docs verified)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### API Keys — DEFERRED
- API key creation, revocation, and scope enforcement are NOT part of this phase
- PLAT-01 and PLAT-02 deferred to a future phase
- Phase 5 focuses on rate limiting (PLAT-03), audit log (PLAT-04), and email templates (PLAT-05)

#### Rate Limiting
- Strict auth endpoint limits: 5 requests/minute per IP for login, sign-up, password reset
- Global rate limit for all authenticated endpoints: fixed limit for all tenants regardless of plan
- 429 response includes Retry-After header (standard HTTP)
- Rate limits stored in Redis sliding window — persist across restarts

#### Audit Log
- Log ALL write operations (POST/PATCH/DELETE), not just sensitive ones
- Detail level: action + target only (who did what to whom) — no before/after diffs
- Query access: super-admin only for now — tenant-scoped query API comes later
- Retention: rolling window — auto-purge entries older than a configurable period (e.g., 12 months)
- Append-only: tenant users cannot modify or delete audit entries

#### Email Templates
- Branded and polished HTML emails with full header/footer, colors, styled layout
- Brand colors: extracted from WXCODE project design tokens (see Color Palette section)
- Every email includes both HTML and plain-text versions for deliverability
- 4 templates: email verification, password reset, member invitation, payment failure notification
- Jinja2 HTML templates with a shared base layout

### Claude's Discretion
- Global rate limit threshold for authenticated endpoints (e.g., 60/min, 100/min)
- Audit log retention period (12 months suggested, Claude can adjust)
- Email template exact layout and spacing
- Jinja2 template inheritance structure
- Audit log table schema details (JSON column for details vs separate columns)

### Deferred Ideas (OUT OF SCOPE)
- API key management (PLAT-01, PLAT-02) — create, revoke, rotate scoped API keys
- Tenant-scoped audit log query API — tenant owners querying their own logs
- Per-plan rate limits — different limits based on billing plan
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PLAT-03 | Rate limiting per IP and per user (login, signup, reset, API) | slowapi 0.1.9 already installed; Redis backend via `storage_uri`; `@limiter.limit()` decorator pattern verified |
| PLAT-04 | Immutable audit log of sensitive actions | Hand-rolled SQLAlchemy model; append-only via application-level (no DELETE endpoint); JSONB `details` column; arq cron for retention purge |
| PLAT-05 | Transactional email templates (verify, reset, invite, payment failed) | fastapi-mail 1.6.2 already installed with Jinja2 support; `html_template`+`plain_template` pattern; refactor existing plain-text senders |
</phase_requirements>

---

## Summary

Phase 5 adds three security/polish layers to the platform: rate limiting on auth endpoints and all authenticated routes, an immutable audit log for all write operations, and branded HTML email templates replacing the current plain-text stubs. All required libraries (`slowapi`, `fastapi-mail`) are already installed in `pyproject.toml` — no new dependencies are needed.

The biggest design decision for **rate limiting** is the async Redis compatibility of slowapi. Research confirms slowapi 0.1.9 uses the `limits` library for storage, and `storage_uri="redis://..."` provides a synchronous Redis connection under the hood. For a production async FastAPI app, this means the rate-limit check will briefly block the async event loop (microseconds for a local Redis call). For the scale of this platform this is acceptable — the alternative (custom middleware with `redis.asyncio`) is significantly more code. The `SlowAPIASGIMiddleware` variant (vs `SlowAPIMiddleware`) is recommended for async apps.

The **audit log** is best implemented as a pure application-level append-only table — no DB triggers needed. A `write_audit` helper function called explicitly from service code after successful write operations provides clean control over what gets logged. The `details` column should be `JSONB` to allow flexible per-action metadata without schema changes. Retention is handled by an arq cron job that purges rows older than a configurable `AUDIT_LOG_RETENTION_DAYS` setting.

The **email templates** require a refactor of all four existing plain-text senders (`send_verification_email`, `send_reset_email`, `send_invitation_email`, `send_payment_failed_email`) to use fastapi-mail's `html_template` + `plain_template` parameters. The WXCODE brand uses "Obsidian Studio" dark-mode tokens in the UI, but emails render on white backgrounds in most clients — the brand palette is best adapted for a light-background email style using the accent blue (#3b82f6) as the CTA button color and obsidian-800/900 for text.

**Primary recommendation:** Implement in order: (1) rate limiting — one plan file, zero new deps; (2) audit log — new model + migration + write helper + cron; (3) email templates — refactor four existing senders, add 8 template files (4 HTML + 4 plain).

---

## Standard Stack

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| slowapi | 0.1.9 | Rate limiting decorator for FastAPI/Starlette | Only actively maintained limiter for Starlette/FastAPI; adapted from flask-limiter; already in pyproject.toml |
| redis (asyncio) | 5.3.1 | Redis client (existing) | Already in use for JWT blacklist, OTP storage, arq queue |
| fastapi-mail | 1.6.2 | Email sending with Jinja2 template support | Already installed; provides `html_template` + `plain_template` in single send call |
| Jinja2 | (transitive via fastapi-mail) | HTML template rendering | Standard Python templating; already a transitive dependency |
| sqlalchemy | 2.0.46 | Audit log ORM model | Already in use for all models |
| arq | 0.27.0 | Cron job for audit log retention purge | Already in use for async tasks |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sqlalchemy.dialects.postgresql.JSONB` | (part of sqlalchemy) | JSONB column for audit log `details` | Use for audit_logs.details field — flexible schema-less metadata per action |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| slowapi storage_uri (sync Redis) | Custom async middleware with redis.asyncio | Custom = 3x more code, no decorator API, must handle Redis errors manually — not worth it at this scale |
| JSONB `details` column | Separate columns per action type | More columns = schema migrations for each new action type; JSONB allows future flexibility without migrations |
| arq cron for retention purge | PostgreSQL pg_cron extension | pg_cron requires DB-level install; arq cron is already available and consistent with existing task patterns |
| fastapi-mail + Jinja2 | Pure Jinja2 + smtplib | fastapi-mail already handles async SMTP, attachments, multipart — no reason to replace |

**Installation:** No new packages needed. All dependencies already in `pyproject.toml`.

---

## Architecture Patterns

### Recommended Project Structure for New Code

```
backend/src/wxcode_adm/
├── audit/                    # NEW module
│   ├── __init__.py
│   ├── models.py             # AuditLog SQLAlchemy model
│   ├── service.py            # write_audit() helper function
│   └── router.py             # GET /admin/audit-logs (super-admin only)
├── common/
│   ├── rate_limit.py         # NEW: limiter singleton + limiter.exempt helper
│   └── ...                   # existing files unchanged
├── tasks/
│   └── worker.py             # MODIFIED: add purge_old_audit_logs cron job
├── auth/
│   └── email.py              # MODIFIED: replace plain-text with html_template
├── tenants/
│   └── email.py              # MODIFIED: replace plain-text with html_template
├── billing/
│   └── email.py              # MODIFIED: replace plain-text with html_template
└── templates/                # NEW directory
    └── email/
        ├── base.html         # Jinja2 base layout (extends pattern)
        ├── verify_email.html
        ├── verify_email.txt
        ├── reset_password.html
        ├── reset_password.txt
        ├── invitation.html
        ├── invitation.txt
        ├── payment_failed.html
        └── payment_failed.txt

alembic/versions/
└── 004_add_audit_logs_table.py  # NEW migration
```

### Pattern 1: slowapi Rate Limiting Setup

**What:** Attach `Limiter` singleton to `app.state`, register exception handler, add ASGI middleware, apply `@limiter.limit()` decorator to endpoints.

**When to use:** Apply strict limits to auth endpoints; apply a global default to all other endpoints via `default_limits`.

**Critical rules:**
1. Route decorator (`@router.post(...)`) MUST be ABOVE `@limiter.limit(...)`.
2. Endpoint function MUST accept `request: Request` parameter.
3. Use `SlowAPIASGIMiddleware` (not `SlowAPIMiddleware`) for async FastAPI apps.

```python
# Source: slowapi docs https://slowapi.readthedocs.io/en/latest/
# common/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware

from wxcode_adm.config import settings

# Module-level singleton — attached to app.state in create_app()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],  # global default for all endpoints
    storage_uri=settings.REDIS_URL,  # e.g., "redis://localhost:6379/0"
)
```

```python
# main.py — in create_app()
from wxcode_adm.common.rate_limit import limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIASGIMiddleware)
```

```python
# auth/router.py — applying strict per-endpoint limit
from fastapi import Request
from wxcode_adm.common.rate_limit import limiter

@auth_api_router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")   # BELOW the route decorator
async def login(
    request: Request,        # REQUIRED by slowapi
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    ...
```

**429 Response:** `_rate_limit_exceeded_handler` returns HTTP 429 with `Retry-After` header automatically. The response body is: `{"error": "Rate limit exceeded: 5 per 1 minute"}`.

**Exempting endpoints:** Apply `@limiter.exempt` to public endpoints that should not count (e.g., health check, JWKS).

```python
@router.get("/.well-known/jwks.json")
@limiter.exempt
async def jwks_endpoint() -> dict:
    ...
```

### Pattern 2: Audit Log Write Helper

**What:** A standalone `write_audit()` async function called explicitly from service code after a successful write operation. NOT a middleware — middleware cannot know whether the operation succeeded.

**When to use:** Call at the end of any service function that performs a write (create/update/delete). Pass the DB session so the audit row is written in the same transaction.

```python
# audit/service.py
from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.audit.models import AuditLog


async def write_audit(
    db: AsyncSession,
    actor_id: uuid.UUID | None,      # user who performed the action (None = system)
    action: str,                      # e.g., "login", "invite_user", "update_plan"
    resource_type: str,               # e.g., "user", "tenant", "invitation", "plan"
    resource_id: str | None,          # stringified UUID of affected resource
    tenant_id: uuid.UUID | None,      # None for platform-level actions
    ip_address: str | None = None,    # client IP from request
    details: dict[str, Any] | None = None,  # flexible per-action metadata
) -> None:
    """
    Append a single audit log entry. Called within the service transaction.
    No exceptions are swallowed — let the caller's transaction handle failure.
    """
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=tenant_id,
        ip_address=ip_address,
        details=details or {},
    )
    db.add(entry)
    # Caller's session commit (via get_session dependency) will flush this row.
```

**Usage in service code:**

```python
# auth/service.py
async def login(db, redis, body):
    user = await _authenticate(db, body)
    tokens = await _issue_tokens(db, redis, user)
    await write_audit(
        db,
        actor_id=user.id,
        action="login",
        resource_type="user",
        resource_id=str(user.id),
        tenant_id=None,
        ip_address=None,  # inject from Request if available
    )
    return tokens
```

### Pattern 3: Audit Log Retention via arq Cron

**What:** An arq cron job that runs once per day and deletes rows older than `AUDIT_LOG_RETENTION_DAYS` from `audit_logs`.

```python
# tasks/worker.py — add to WorkerSettings.cron_jobs
from arq import cron
from wxcode_adm.audit.service import purge_old_audit_logs

class WorkerSettings:
    cron_jobs = [
        cron(purge_old_audit_logs, hour=2, minute=0)  # 2 AM daily
    ]
```

```python
# audit/service.py
from datetime import datetime, timezone, timedelta
from sqlalchemy import delete

async def purge_old_audit_logs(ctx: dict) -> int:
    """arq cron job: delete audit_logs older than AUDIT_LOG_RETENTION_DAYS."""
    session_maker = ctx["session_maker"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
    async with session_maker() as session:
        result = await session.execute(
            delete(AuditLog).where(AuditLog.created_at < cutoff)
        )
        await session.commit()
    return result.rowcount
```

### Pattern 4: fastapi-mail HTML Templates with Jinja2

**What:** Configure `ConnectionConfig` with `TEMPLATE_FOLDER`, then call `fm.send_message(message, html_template="...", plain_template="...")` for multipart emails.

**Critical:** In fastapi-mail >= 0.5.0 (including 1.6.2), `template_body` variables are accessed directly in templates (e.g., `{{ code }}`), NOT as `{{ body.code }}` (that was the pre-0.4.0 API).

```python
# common/mail.py — shared FastMail singleton
from pathlib import Path
from fastapi_mail import ConnectionConfig, FastMail

from wxcode_adm.config import settings

_mail_conf = ConnectionConfig(
    MAIL_USERNAME=settings.SMTP_USER,
    MAIL_PASSWORD=settings.SMTP_PASSWORD,
    MAIL_FROM=settings.SMTP_FROM_EMAIL,
    MAIL_FROM_NAME=settings.SMTP_FROM_NAME,
    MAIL_PORT=settings.SMTP_PORT,
    MAIL_SERVER=settings.SMTP_HOST,
    MAIL_STARTTLS=settings.SMTP_TLS,
    MAIL_SSL_TLS=settings.SMTP_SSL,
    USE_CREDENTIALS=bool(settings.SMTP_USER),
    TEMPLATE_FOLDER=Path(__file__).parent.parent / "templates" / "email",
)

# Shared singleton — ConnectionConfig is expensive to construct per-call
fast_mail = FastMail(_mail_conf)
```

```python
# auth/email.py — refactored send_verification_email
from fastapi_mail import MessageSchema, MessageType

async def send_verification_email(ctx, user_id, email, code):
    message = MessageSchema(
        subject="WXCODE — Verify your email",
        recipients=[email],
        template_body={"code": code, "email": email},
        subtype=MessageType.html,
    )
    await fast_mail.send_message(
        message,
        html_template="verify_email.html",
        plain_template="verify_email.txt",
    )
```

### Pattern 5: Jinja2 Template Inheritance

**What:** A `base.html` template with `{% block content %}` that all 4 email templates extend. Keeps header/footer consistent.

```html
<!-- templates/email/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}WXCODE{% endblock %}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f5;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#f4f4f5;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="background-color:#ffffff;border-radius:8px;overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="background-color:#18181b;padding:32px 40px;text-align:center;">
              <span style="color:#f4f4f5;font-size:22px;font-weight:bold;letter-spacing:2px;">
                WXCODE
              </span>
            </td>
          </tr>
          <!-- Content -->
          <tr>
            <td style="padding:40px;color:#27272a;font-size:15px;line-height:1.6;">
              {% block content %}{% endblock %}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color:#f4f4f5;padding:24px 40px;text-align:center;
                       color:#71717a;font-size:12px;border-top:1px solid #e5e7eb;">
              &copy; 2026 WXCODE. All rights reserved.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

```html
<!-- templates/email/verify_email.html -->
{% extends "base.html" %}
{% block title %}Verify your email — WXCODE{% endblock %}
{% block content %}
<h2 style="color:#18181b;font-size:20px;margin-top:0;">Verify your email address</h2>
<p>Use the code below to verify your email. It expires in <strong>10 minutes</strong>.</p>
<div style="background-color:#f4f4f5;border-radius:6px;padding:24px;text-align:center;
            font-size:32px;font-weight:bold;letter-spacing:8px;color:#18181b;margin:24px 0;">
  {{ code }}
</div>
<p style="color:#71717a;font-size:13px;">If you did not create a WXCODE account, ignore this email.</p>
{% endblock %}
```

### Anti-Patterns to Avoid

- **Decorator order reversal:** In FastAPI, putting `@limiter.limit()` ABOVE `@router.post()` breaks rate limiting silently.
- **Missing `request: Request` parameter:** slowapi cannot hook into the request without it — no error, just no rate limiting.
- **Using `SlowAPIMiddleware` (not ASGI variant):** The non-ASGI middleware is WSGI-based and does not work correctly in pure async FastAPI. Use `SlowAPIASGIMiddleware`.
- **Writing audit log in middleware:** Middleware fires before the route handler AND before commit — you cannot know if the operation succeeded. Write audit after the successful operation in service code.
- **Audit log in a separate transaction:** If the audit write is in a separate session from the service operation, a crash between the two creates inconsistency. Use the same session — both operations commit together.
- **Using `{{ body.variable }}` in Jinja2 templates:** This is the pre-0.4.0 API. In fastapi-mail 1.6.2, variables from `template_body` are accessed directly as `{{ variable }}`.
- **CSS that doesn't inline:** Email clients (Gmail, Outlook) strip `<style>` blocks. All CSS must be inline in the HTML attributes. No flexbox, grid, or CSS variables — use table layout and inline `style=""`.
- **Configuring `ConnectionConfig` per-send:** `ConnectionConfig` and `FastMail` construction is expensive; build once as a module-level singleton in `common/mail.py`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rate limit counting in Redis | Custom Lua scripts + Redis ZADD sliding window | slowapi with `storage_uri` | slowapi already uses the `limits` library which implements sliding window natively in Redis; Lua script atomicity already handled |
| 429 response with Retry-After | Custom exception handler | `_rate_limit_exceeded_handler` from slowapi | Handles header formatting and response body correctly |
| Multipart (HTML+plain) email | Manually build MIME multipart messages | `fm.send_message(..., html_template=..., plain_template=...)` | fastapi-mail handles MIME construction, content-type headers, and Jinja2 rendering |
| Audit log timestamp | `datetime.now()` in Python | `server_default=text("now()")` in column definition | Server-side timestamp is immune to application clock skew and is assigned atomically with the INSERT |
| Retention purge scheduling | Separate cron process, system crontab | arq `cron()` in `WorkerSettings.cron_jobs` | arq worker is already running; adding a cron job is 5 lines |

**Key insight:** All three feature areas (rate limiting, email, scheduling) have established library support already installed. The value is in configuration and integration, not custom implementation.

---

## Common Pitfalls

### Pitfall 1: slowapi sync Redis in async context
**What goes wrong:** `storage_uri="redis://..."` uses a synchronous Redis driver under the hood via the `limits` library. Rate limit checks will briefly block the async event loop.
**Why it happens:** slowapi's underlying `limits` library supports async Redis via `"async+redis://"` URI, but slowapi's own decorator layer was still primarily sync as of 2023 (confirmed by maintainer in GitHub issue #130). The `limits` library has since added async storage, but the integration in slowapi may vary by version.
**How to avoid:** For the scale of this platform, the sync blocking is negligible (sub-millisecond for local Redis). If future load testing shows it's a bottleneck, evaluate upgrading to a version of slowapi with full async support or switching to a custom middleware. Do not over-engineer prematurely.
**Warning signs:** p99 latency spikes under load on rate-limited endpoints — investigate with profiling before optimizing.

### Pitfall 2: Rate limit not applying to authenticated endpoints
**What goes wrong:** Global `default_limits` in the `Limiter` constructor only apply when `SlowAPIASGIMiddleware` (or `SlowAPIMiddleware`) is added. Without the middleware, only explicitly decorated endpoints are limited.
**Why it happens:** The global limit is enforced by middleware, not the decorator. The decorator is per-endpoint override.
**How to avoid:** Always add `app.add_middleware(SlowAPIASGIMiddleware)` after setting `app.state.limiter`. Verify in tests that a bare authenticated endpoint gets 429 after N requests.

### Pitfall 3: Audit log actor_id is None for logged-in actions
**What goes wrong:** Service functions that need actor_id don't receive the `User` object — they only receive `db` and request body.
**Why it happens:** Service functions in this codebase receive `db: AsyncSession` and body schemas — the `user` comes from the router dependency. The service doesn't automatically have access to it.
**How to avoid:** Thread the `actor_id: uuid.UUID` (or the full `User`) through every service function that performs auditable writes. Update service function signatures to accept it. This is a refactor touchpoint in every audited service.

### Pitfall 4: Jinja2 `TemplateNotFound` in tests
**What goes wrong:** Tests that exercise email sending fail with `TemplateNotFound` because the `TEMPLATE_FOLDER` path is relative and doesn't resolve correctly from the test runner's cwd.
**Why it happens:** `Path(__file__).parent.parent / "templates" / "email"` resolves at import time relative to the module file, which is correct. But if ConnectionConfig is constructed before the templates directory exists, it will raise at startup.
**How to avoid:** Use `Path(__file__).parent.parent / "templates" / "email"` (absolute derivation from module location). Mock `fast_mail.send_message` in tests using `conf.SUPPRESS_SEND = 1` or by patching the FastMail instance.

### Pitfall 5: `updated_at` on AuditLog model
**What goes wrong:** Including `updated_at` on the `AuditLog` model via `TimestampMixin` implies the row can be updated — conceptually wrong for an append-only log.
**Why it happens:** The project uses `TimestampMixin` for all models. Blindly applying it to `AuditLog` inherits `updated_at`.
**How to avoid:** Do NOT use `TimestampMixin` for `AuditLog`. Define only `id` and `created_at` manually. There is no `updated_at` on an append-only table. Inherit `Base` only.

### Pitfall 6: Alembic import of audit models
**What goes wrong:** Autogenerate doesn't detect the new `audit_logs` table because `audit.models` is not imported in `alembic/env.py`.
**Why it happens:** The env.py imports each module explicitly to populate `Base.metadata`. A new module must be added.
**How to avoid:** Add `from wxcode_adm.audit import models as _audit_models  # noqa: F401` to `alembic/env.py` when creating the audit module.

### Pitfall 7: IP address extraction in service code
**What goes wrong:** Services don't have access to `Request` — only routers do. Audit log entries end up with `ip_address=None` for all actions.
**Why it happens:** The clean architecture separation means service code receives domain objects, not HTTP request objects.
**How to avoid:** Extract the client IP at the router level using `request.client.host` (with `X-Forwarded-For` consideration if behind a proxy) and pass it as a plain `str` argument to the service function alongside the `actor_id`. Keep `Request` out of service code — only pass the extracted value.

---

## Code Examples

Verified patterns from official sources and codebase analysis:

### AuditLog SQLAlchemy Model (no TimestampMixin)

```python
# audit/models.py
# Source: SQLAlchemy 2.0 docs + project Base pattern
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wxcode_adm.db.base import Base


class AuditLog(Base):
    """
    Immutable append-only audit log entry.

    Intentionally does NOT use TimestampMixin — there is no updated_at on
    an append-only table. id and created_at are declared manually.

    actor_id is nullable to support system-initiated actions (e.g., cron jobs,
    Stripe webhooks) where no human actor is present.
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        nullable=False,
    )
    # Who performed the action (None for system/webhook actions)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Tenant context (None for platform-level actions like super-admin ops)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Action identifier: "login", "invite_user", "revoke_invitation",
    # "update_plan", "subscription_created", "payment_failed", etc.
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Resource type: "user", "tenant", "invitation", "plan", "subscription"
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Stringified UUID or other identifier of the affected resource
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Client IP address (extracted at router level, passed to service)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # Flexible per-action metadata without schema migrations
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
```

### Alembic Migration for audit_logs

```python
# alembic/versions/004_add_audit_logs_table.py
def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL",
                                name=op.f("fk_audit_logs_actor_id_users")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL",
                                name=op.f("fk_audit_logs_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"])
    op.create_index(op.f("ix_audit_logs_tenant_id"), "audit_logs", ["tenant_id"])
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])
```

### slowapi Complete FastAPI Integration

```python
# common/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from wxcode_adm.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],      # global limit (Claude's discretion)
    storage_uri=settings.REDIS_URL,    # "redis://localhost:6379/0"
)

# Re-export for convenient import in main.py
__all__ = ["limiter", "_rate_limit_exceeded_handler"]
```

```python
# main.py additions in create_app()
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from wxcode_adm.common.rate_limit import limiter, _rate_limit_exceeded_handler

# After app = FastAPI(...):
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIASGIMiddleware)
```

### Audit Log Super-Admin Query Endpoint

```python
# audit/router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth.models import User
from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.audit.models import AuditLog
from wxcode_adm.dependencies import get_session

audit_router = APIRouter(prefix="/admin/audit-logs", tags=["audit"])


@audit_router.get("/")
async def list_audit_logs(
    user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    action: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
) -> list[dict]:
    if not user.is_superuser:
        raise ForbiddenError(error_code="FORBIDDEN", message="Super-admin only")
    # ... build query with optional filters
```

---

## WXCODE Brand Colors (Email-Adapted)

The WXCODE UI uses an "Obsidian Studio" dark-mode palette. For emails (which render on white backgrounds in most clients), the following adaptations are recommended:

**Source:** `/Users/gilberto/projetos/wxk/wxcode/frontend/src/app/tokens.css` (verified)

| Token | Hex Value | Email Role |
|-------|-----------|-----------|
| `--obsidian-900` | `#0c0c0f` | Email header background |
| `--obsidian-800` | `#18181b` | Header text, logo wordmark |
| `--obsidian-700` | `#27272a` | Body heading text |
| `--obsidian-200` | `#d4d4d8` | Subtle dividers |
| `--obsidian-100` | `#f4f4f5` | Email outer background, code block bg |
| `--accent-blue` | `#3b82f6` | CTA button background (primary action) |
| `--accent-blue-dark` | `#2563eb` | CTA button hover equivalent |
| `--accent-green` | `#10b981` | Success indicators |
| `--accent-amber` | `#f59e0b` | Warning context (payment failed header) |
| `--accent-rose` | `#f43f5e` | Error/danger context |

**Email palette summary:**
- Header: dark background (`#0c0c0f`) with white text (`#f4f4f5`)
- Body: white (`#ffffff`) with dark text (`#27272a`)
- CTA buttons: blue (`#3b82f6`) with white text
- Code/OTP display blocks: light gray background (`#f4f4f5`) with dark text
- Footer: light gray (`#f4f4f5`) with muted text (`#71717a`)

---

## Claude's Discretion Recommendations

### Global Rate Limit Threshold
**Recommendation: 60 requests/minute** per IP for authenticated endpoints.

Rationale: This allows ~1 request/second sustained, which covers normal human usage and client-side polling at reasonable intervals. It blocks automated abuse without impacting legitimate power users. Auth endpoints get the stricter 5/minute.

### Audit Log Retention Period
**Recommendation: 365 days (12 months)**, configured as `AUDIT_LOG_RETENTION_DAYS: int = 365` in Settings.

Rationale: 12 months matches typical compliance windows (SOC 2, ISO 27001 suggest 12 months of logs). Longer retention increases DB storage cost; shorter loses investigative value. Keep it configurable so operators can adjust.

### Audit Log details Column
**Recommendation: JSONB with flat key-value metadata.**

Do not use separate columns per action type. JSONB allows capturing action-specific metadata (e.g., `{"invited_role": "admin"}` for invite, `{"plan_name": "pro"}` for plan change) without schema migrations. Keep details minimal — action + target is the primary record; details is supplementary context.

### Jinja2 Template Structure
**Recommendation: Single `base.html` with `{% block content %}` and `{% block title %}`.**

Four HTML templates extend base.html. Four plain-text templates are standalone (no inheritance needed for text). Total: 9 files (1 base + 4 HTML children + 4 plain text).

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| fastapi-limiter (aioredis-based) | slowapi (limits-based, Redis backend) | 2023 — fastapi-limiter went unmaintained | Already decided; slowapi is the choice |
| `{{ body.variable }}` in fastapi-mail templates | `{{ variable }}` direct access | fastapi-mail 0.4.0+ | Templates must NOT use `body.` prefix |
| Plain-text only email bodies | Multipart HTML + plain-text | Current best practice | Both HTML and .txt must be provided |
| SlowAPIMiddleware (WSGI) | SlowAPIASGIMiddleware | slowapi 0.1.x | Always use ASGI variant for FastAPI |
| TimestampMixin on all models | Manual id+created_at for audit log | N/A (design choice) | AuditLog must NOT have updated_at |

**Deprecated/outdated:**
- `fastapi-limiter`: Unmaintained since 2023. Do not use.
- `{{ body.variable }}` Jinja2 syntax: Pre-0.4.0 fastapi-mail API. Use `{{ variable }}` directly.
- `@app.on_event("startup"/"shutdown")`: Already deprecated in this project. Lifespan context manager is the pattern.

---

## Open Questions

1. **IP extraction behind a reverse proxy**
   - What we know: `request.client.host` returns the direct connection IP. Behind nginx/caddy, this is the proxy IP, not the client IP. `X-Forwarded-For` header contains the real IP but can be spoofed.
   - What's unclear: Is the current deployment behind a proxy? Does slowapi's `get_remote_address` handle `X-Forwarded-For` automatically?
   - Recommendation: Check slowapi's `get_remote_address` implementation — it reads `X-Forwarded-For` if present. For audit log IP capture, extract from `request.client.host` for now and document that proxy configuration may require updating this.

2. **Test strategy for rate limiting with fakeredis**
   - What we know: Tests use `fakeredis` for Redis mocking. The `limiter` is a module-level singleton initialized with `storage_uri=settings.REDIS_URL`.
   - What's unclear: Can fakeredis be plugged into slowapi's storage layer, or must rate limit tests use `limiter.enabled=False`?
   - Recommendation: In test fixtures, override `app.state.limiter` with a new `Limiter(enabled=False)` or use `limiter.enabled = False` in rate-limit-specific tests. For tests that verify the 429 behavior itself, use the real limiter with an in-memory backend (`Limiter(key_func=..., default_limits=["1/minute"])` without `storage_uri`).

3. **fastapi-mail SUPPRESS_SEND in tests**
   - What we know: fastapi-mail has a `SUPPRESS_SEND` flag in `ConnectionConfig` that disables actual SMTP sends. The current codebase wraps SMTP in try/except.
   - What's unclear: Whether the existing arq job try/except pattern should be replaced or supplemented with `SUPPRESS_SEND=True` in test/dev environments.
   - Recommendation: Add `SUPPRESS_SEND: bool = False` to Settings (maps to env var `SUPPRESS_SEND`). Set to `True` in tests. This is cleaner than try/except for test isolation.

---

## Sources

### Primary (HIGH confidence)
- `slowapi` PyPI/readthedocs — storage_uri format, decorator pattern, `_rate_limit_exceeded_handler`, `SlowAPIASGIMiddleware`, `default_limits`, `@limiter.exempt`
- slowapi GitHub examples.md — `default_limits`, `storage_uri="redis://host:port/n"`, `SlowAPIASGIMiddleware`
- fastapi-mail docs (sabuhish.github.io) — `TEMPLATE_FOLDER`, `html_template`, `plain_template`, `template_body` direct variable access, `ConnectionConfig` parameters
- arq docs (arq-docs.helpmanual.io) — `cron()` function, `cron_jobs` in WorkerSettings, scheduling parameters
- SQLAlchemy 2.0 docs — `JSONB` from `sqlalchemy.dialects.postgresql`, `mapped_column(JSONB)`, `Mapped[dict]`
- Project codebase (`/Users/gilberto/projetos/wxk/wxcode-adm/`) — existing patterns for models, dependencies, services, worker, migrations

### Secondary (MEDIUM confidence)
- `/Users/gilberto/projetos/wxk/wxcode/frontend/src/app/tokens.css` — WXCODE brand color palette (verified file contents)
- slowapi GitHub issue #130 — confirmation that sync Redis limitation exists in current slowapi; maintainer statement
- WebSearch results cross-verified: `storage_uri="redis://..."` syntax, `SlowAPIASGIMiddleware` recommendation, `template_body` direct access in fastapi-mail

### Tertiary (LOW confidence)
- `from slowapi.storage import RedisStorage` pattern — mentioned in WebSearch but not verified against official slowapi docs; prefer `storage_uri` constructor parameter instead (HIGH confidence)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed, versions pinned, existing usage in codebase
- Architecture: HIGH — patterns derived from existing codebase + official docs
- Rate limiting configuration: HIGH — slowapi docs verified, known async limitation documented
- Audit log design: HIGH — standard SQLAlchemy patterns, JSONB usage verified
- Email templates: HIGH — fastapi-mail docs verified for html_template/plain_template API
- Brand colors: HIGH — read directly from project source files
- Pitfalls: MEDIUM — some based on analysis and community sources, not all individually tested

**Research date:** 2026-02-23
**Valid until:** 2026-05-23 (90 days — stable libraries, unlikely to change)
