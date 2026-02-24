"""
Integration tests for Phase 5 platform security features.

Covers 3 Phase 5 success criteria:
- PLAT-03: Rate limiting — 429 + Retry-After on auth endpoints, health/JWKS exempt
- PLAT-04: Audit log — write_audit creates entries, purge_old_audit_logs deletes
           old rows, super-admin can query, non-superusers get 403
- PLAT-05: Email templates — all 4 sender functions use HTML + plain-text
           templates, templates extend base.html, direct variable access

Note: The `client` fixture yields a 4-tuple: (http_client, fake_redis, app, test_db).
Rate limit tests re-enable the limiter within the test body (it is disabled by
default in the client fixture for test isolation).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from wxcode_adm.audit.models import AuditLog
from wxcode_adm.audit.service import purge_old_audit_logs, write_audit
from wxcode_adm.auth.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMPLATES_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "wxcode_adm"
    / "templates"
    / "email"
)


async def _signup_verify_login(client, redis, email="user@test.com", password="securepass"):
    """Sign up, verify email, and log in. Returns TokenResponse dict."""
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text

    keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys.append(k)

    # Find OTP key belonging to this user (latest registered)
    user_otp_key = keys[-1]
    user_id = user_otp_key.replace("auth:otp:", "")
    code = await redis.get(f"auth:otp:{user_id}")
    assert code is not None

    r = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": code},
    )
    assert r.status_code == 200, r.text

    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


async def _create_superadmin(test_db):
    """Create a super-admin user directly in the DB and return it."""
    from wxcode_adm.auth.password import hash_password

    async with test_db() as session:
        admin = User(
            email="superadmin@wxcode.io",
            password_hash=hash_password("adminpassword"),
            is_active=True,
            email_verified=True,
            is_superuser=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin


async def _get_auth_headers(client, redis, email, password):
    """Get Authorization headers for a user (sign up + verify + login)."""
    tokens = await _signup_verify_login(client, redis, email, password)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ===========================================================================
# SECTION 1: Rate Limiting Tests (PLAT-03 — Success Criteria 3)
# ===========================================================================


def _enable_original_limiter_with_memory_storage(app):
    """
    Helper: enable the original limiter (from app.state.limiter) and replace its
    Redis storage with an in-memory backend so rate limits work without Redis.

    Returns (original_storage, original_limiter_strategy) for restoration.

    The original limiter MUST be used (not a new Limiter instance) because
    @limiter.exempt registers routes in _exempt_routes on the original limiter.
    Swapping to a new limiter loses all exempt registrations.
    """
    from limits.storage import MemoryStorage
    from limits.strategies import FixedWindowRateLimiter

    original_limiter = app.state.limiter
    original_storage = original_limiter._storage
    original_limiter_strategy = original_limiter._limiter

    # Replace storage with fresh in-memory backend
    mem_storage = MemoryStorage()
    original_limiter._storage = mem_storage
    original_limiter._limiter = FixedWindowRateLimiter(mem_storage)
    original_limiter.enabled = True

    return original_storage, original_limiter_strategy


def _restore_original_limiter(app, original_storage, original_limiter_strategy):
    """Restore the limiter to its original state and disable it."""
    limiter = app.state.limiter
    limiter._storage = original_storage
    limiter._limiter = original_limiter_strategy
    limiter.enabled = False


async def test_auth_endpoint_rate_limited(client):
    """
    PLAT-03: Auth endpoints return 429 after exceeding the 5/minute rate limit.

    Strategy: Enable the original limiter (preserving @limiter.exempt on health/JWKS)
    with an in-memory storage backend so no Redis is needed. Then call the login
    endpoint 6 times — the 6th must return 429 (5/minute limit).
    """
    c, redis, app, test_db = client

    orig_storage, orig_strategy = _enable_original_limiter_with_memory_storage(app)

    try:
        # First 5 requests: within the 5/minute auth limit.
        # Login with invalid creds returns 401 (not 429).
        for i in range(5):
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": "notexist@test.com", "password": "wrongpass"},
            )
            assert r.status_code != 429, (
                f"Request {i + 1} of 5 was rate-limited prematurely: {r.status_code}"
            )

        # 6th request: must be rate-limited (429)
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "notexist@test.com", "password": "wrongpass"},
        )
        assert r.status_code == 429, (
            f"Expected 429 on 6th request (5/minute limit), got {r.status_code}: {r.text}"
        )
    finally:
        _restore_original_limiter(app, orig_storage, orig_strategy)


async def test_health_endpoint_exempt(client):
    """
    PLAT-03: Health endpoint is exempt from rate limiting.

    Health checks must never be blocked by rate limits — infrastructure
    monitoring requires reliable access regardless of request volume.

    The @limiter.exempt decorator on health_check sets it in the original
    limiter's _exempt_routes, so it is respected even with memory storage.
    """
    c, redis, app, test_db = client

    orig_storage, orig_strategy = _enable_original_limiter_with_memory_storage(app)

    try:
        # Hit health endpoint 10 times — should never get 429
        # (global default is 60/minute, but health is @limiter.exempt)
        for i in range(10):
            r = await c.get("/api/v1/health")
            assert r.status_code in (200, 503), (
                f"Request {i + 1}: expected 200/503 (health status), got {r.status_code}: {r.text}"
            )
    finally:
        _restore_original_limiter(app, orig_storage, orig_strategy)


async def test_jwks_endpoint_exempt(client):
    """
    PLAT-03: JWKS endpoint is exempt from rate limiting.

    External services (e.g., the wxcode engine) fetch the public key to
    verify JWTs — this endpoint must never count against rate limits.

    The @limiter.exempt decorator on jwks_endpoint preserves exemption
    even when in-memory storage is swapped in.
    """
    c, redis, app, test_db = client

    orig_storage, orig_strategy = _enable_original_limiter_with_memory_storage(app)

    try:
        # Hit JWKS endpoint 10 times — should always return 200, never 429
        for i in range(10):
            r = await c.get("/.well-known/jwks.json")
            assert r.status_code == 200, (
                f"Request {i + 1}: expected 200, got {r.status_code}: {r.text}"
            )
    finally:
        _restore_original_limiter(app, orig_storage, orig_strategy)


async def test_rate_limit_response_includes_retry_after(client):
    """
    PLAT-03: Rate-limited responses include the Retry-After header.

    The Retry-After header tells clients how many seconds to wait before
    retrying, enabling proper backoff strategies.

    Makes 6 calls to trigger the 5/minute auth limit, then verifies the
    429 response includes Retry-After.
    """
    c, redis, app, test_db = client

    orig_storage, orig_strategy = _enable_original_limiter_with_memory_storage(app)

    try:
        # Exhaust the 5/minute auth rate limit
        for _ in range(5):
            await c.post(
                "/api/v1/auth/login",
                json={"email": "x@test.com", "password": "p"},
            )
        # 6th request — must be rate-limited with Retry-After header
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "x@test.com", "password": "p"},
        )
        assert r.status_code == 429, f"Expected 429, got {r.status_code}"
        assert "retry-after" in {k.lower() for k in r.headers}, (
            f"Expected Retry-After header in 429 response; headers: {dict(r.headers)}"
        )
    finally:
        _restore_original_limiter(app, orig_storage, orig_strategy)


# ===========================================================================
# SECTION 2: Audit Log Tests (PLAT-04 — Success Criteria 4)
# ===========================================================================


async def test_write_audit_creates_entry(client):
    """PLAT-04: write_audit creates an entry in the audit_logs table."""
    c, redis, app, test_db = client

    async with test_db() as session:
        user_id = uuid.uuid4()
        await write_audit(
            session,
            action="login",
            resource_type="user",
            actor_id=user_id,
            resource_id=str(user_id),
            tenant_id=None,
            ip_address="127.0.0.1",
            details={"method": "password"},
        )
        await session.commit()

        result = await session.execute(select(AuditLog).where(AuditLog.action == "login"))
        entries = result.scalars().all()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.action == "login"
    assert entry.resource_type == "user"
    assert entry.actor_id == user_id
    assert entry.resource_id == str(user_id)
    assert entry.ip_address == "127.0.0.1"
    assert entry.details == {"method": "password"}


async def test_write_audit_system_action_no_actor(client):
    """PLAT-04: write_audit with actor_id=None creates entry with NULL actor (system action)."""
    c, redis, app, test_db = client

    async with test_db() as session:
        await write_audit(
            session,
            action="system_cleanup",
            resource_type="system",
            actor_id=None,
        )
        await session.commit()

        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "system_cleanup")
        )
        entry = result.scalar_one()

    assert entry.actor_id is None
    assert entry.action == "system_cleanup"


async def test_write_audit_details_stored_as_json(client):
    """PLAT-04: write_audit stores details dict correctly."""
    c, redis, app, test_db = client

    details = {"role": "admin", "invited_by": "owner@test.com"}

    async with test_db() as session:
        await write_audit(
            session,
            action="invite_user",
            resource_type="invitation",
            details=details,
        )
        await session.commit()

        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "invite_user")
        )
        entry = result.scalar_one()

    assert entry.details == details
    assert entry.details["role"] == "admin"
    assert entry.details["invited_by"] == "owner@test.com"


async def test_purge_old_audit_logs(client):
    """PLAT-04: purge_old_audit_logs deletes entries older than retention period."""
    c, redis, app, test_db = client

    from wxcode_adm.config import settings

    async with test_db() as session:
        # Create 3 audit entries
        now = datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)

        # 2 old entries — should be purged
        old_entry_1 = AuditLog(
            action="old_action_1",
            resource_type="user",
            details={},
        )
        old_entry_2 = AuditLog(
            action="old_action_2",
            resource_type="tenant",
            details={},
        )
        # 1 recent entry — should survive
        recent_entry = AuditLog(
            action="recent_action",
            resource_type="user",
            details={},
        )
        session.add_all([old_entry_1, old_entry_2, recent_entry])
        await session.commit()

        # Backdate the old entries past the retention cutoff
        await session.refresh(old_entry_1)
        await session.refresh(old_entry_2)
        old_entry_1.created_at = cutoff - timedelta(days=1)
        old_entry_2.created_at = cutoff - timedelta(days=10)
        await session.commit()

    # Build mock ctx with session_maker and run purge
    mock_ctx = {"session_maker": test_db}
    deleted = await purge_old_audit_logs(mock_ctx)
    assert deleted == 2

    # Verify only the recent entry remains
    async with test_db() as session:
        result = await session.execute(select(AuditLog))
        remaining = result.scalars().all()

    assert len(remaining) == 1
    assert remaining[0].action == "recent_action"


async def test_audit_log_query_superadmin(client):
    """PLAT-04: Super-admin can query the audit log endpoint (200)."""
    c, redis, app, test_db = client

    # Create a super-admin and get their auth token
    admin = await _create_superadmin(test_db)

    # Create an audit entry to query
    async with test_db() as session:
        await write_audit(
            session,
            action="test_action",
            resource_type="test",
            details={"test": True},
        )
        await session.commit()

    # Log in as superadmin using the auth endpoint
    # The superadmin was created directly in DB (already verified), so we use
    # the login endpoint directly
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "superadmin@wxcode.io", "password": "adminpassword"},
    )
    assert r.status_code == 200, f"Superadmin login failed: {r.text}"
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = await c.get("/api/v1/admin/audit-logs/", headers=headers)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


async def test_audit_log_query_non_superadmin_forbidden(client):
    """PLAT-04: Non-superadmin users get 403 on audit log endpoint."""
    c, redis, app, test_db = client

    # Create a regular user and log in
    tokens = await _signup_verify_login(
        c, redis, email="regular@test.com", password="password123"
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = await c.get("/api/v1/admin/audit-logs/", headers=headers)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    assert r.json()["error_code"] == "FORBIDDEN"


async def test_audit_log_query_filtering(client):
    """PLAT-04: Audit log endpoint supports filtering by action."""
    c, redis, app, test_db = client

    # Use unique action names that won't collide with auth endpoint audit entries
    # (auth endpoints produce "login", "signup", "verify_email" audit entries)
    async with test_db() as session:
        await write_audit(session, action="test_filter_event_a", resource_type="user", details={})
        await write_audit(session, action="test_filter_event_a", resource_type="user", details={})
        await write_audit(session, action="test_filter_event_b", resource_type="user", details={})
        await session.commit()

    # Create superadmin and get tokens
    await _create_superadmin(test_db)
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "superadmin@wxcode.io", "password": "adminpassword"},
    )
    assert r.status_code == 200, r.text
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Filter by action=test_filter_event_a — should return exactly 2 entries
    r = await c.get("/api/v1/admin/audit-logs/?action=test_filter_event_a", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2, f"Expected 2 entries for test_filter_event_a, got {data['total']}"
    assert all(item["action"] == "test_filter_event_a" for item in data["items"])

    # Filter by action=test_filter_event_b — should return exactly 1 entry
    r = await c.get("/api/v1/admin/audit-logs/?action=test_filter_event_b", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1, f"Expected 1 entry for test_filter_event_b, got {data['total']}"
    assert data["items"][0]["action"] == "test_filter_event_b"


# ===========================================================================
# SECTION 3: Email Template Tests (PLAT-05 — Success Criteria 5)
# ===========================================================================


async def test_verification_email_uses_html_template():
    """
    PLAT-05: send_verification_email sends with html_template and plain_template.

    Patches wxcode_adm.common.mail.fast_mail (the singleton) to capture the call.
    The email functions import fast_mail lazily inside try/except, so they always
    use the module-level singleton from common.mail — patching there captures all calls.
    """
    from wxcode_adm.auth.email import send_verification_email
    import wxcode_adm.common.mail as mail_module

    mock_send = AsyncMock()
    original_fast_mail = mail_module.fast_mail
    mock_fast_mail = MagicMock()
    mock_fast_mail.send_message = mock_send
    mail_module.fast_mail = mock_fast_mail

    try:
        await send_verification_email(
            ctx={},
            user_id="test-user-id",
            email="user@test.com",
            code="123456",
        )
    finally:
        mail_module.fast_mail = original_fast_mail

    assert mock_send.called, "fast_mail.send_message was not called"
    call_kwargs = mock_send.call_args

    # The message is the first positional arg
    message = call_kwargs.args[0]
    assert message.template_body.get("code") == "123456"
    assert message.template_body.get("email") == "user@test.com"

    # html_template and plain_template are kwargs to send_message
    assert call_kwargs.kwargs.get("html_template") == "verify_email.html"
    assert call_kwargs.kwargs.get("plain_template") == "verify_email.txt"


async def test_reset_email_uses_html_template():
    """PLAT-05: send_reset_email sends with html_template and correct template_body."""
    from wxcode_adm.auth.email import send_reset_email
    import wxcode_adm.common.mail as mail_module

    mock_send = AsyncMock()
    reset_link = "https://app.wxcode.io/reset?token=abc123"
    original_fast_mail = mail_module.fast_mail
    mock_fast_mail = MagicMock()
    mock_fast_mail.send_message = mock_send
    mail_module.fast_mail = mock_fast_mail

    try:
        await send_reset_email(
            ctx={},
            user_id="test-user-id",
            email="user@test.com",
            reset_link=reset_link,
        )
    finally:
        mail_module.fast_mail = original_fast_mail

    assert mock_send.called, "fast_mail.send_message was not called"
    call_kwargs = mock_send.call_args

    message = call_kwargs.args[0]
    assert message.template_body.get("reset_link") == reset_link
    assert call_kwargs.kwargs.get("html_template") == "reset_password.html"
    assert call_kwargs.kwargs.get("plain_template") == "reset_password.txt"


async def test_invitation_email_uses_html_template():
    """PLAT-05: send_invitation_email sends with invitation templates and correct template_body."""
    from wxcode_adm.tenants.email import send_invitation_email
    import wxcode_adm.common.mail as mail_module

    mock_send = AsyncMock()
    original_fast_mail = mail_module.fast_mail
    mock_fast_mail = MagicMock()
    mock_fast_mail.send_message = mock_send
    mail_module.fast_mail = mock_fast_mail

    try:
        await send_invitation_email(
            ctx={},
            email="invitee@test.com",
            tenant_name="Acme Corp",
            invite_link="https://app.wxcode.io/invite/token123",
            role="member",
        )
    finally:
        mail_module.fast_mail = original_fast_mail

    assert mock_send.called, "fast_mail.send_message was not called"
    call_kwargs = mock_send.call_args

    message = call_kwargs.args[0]
    assert message.template_body.get("tenant_name") == "Acme Corp"
    assert message.template_body.get("role") == "member"
    assert message.template_body.get("invite_link") == "https://app.wxcode.io/invite/token123"
    assert call_kwargs.kwargs.get("html_template") == "invitation.html"
    assert call_kwargs.kwargs.get("plain_template") == "invitation.txt"


async def test_payment_failed_email_uses_html_template():
    """PLAT-05: send_payment_failed_email sends with payment_failed templates and correct template_body."""
    from wxcode_adm.billing.email import send_payment_failed_email
    import wxcode_adm.common.mail as mail_module

    mock_send = AsyncMock()
    original_fast_mail = mail_module.fast_mail
    mock_fast_mail = MagicMock()
    mock_fast_mail.send_message = mock_send
    mail_module.fast_mail = mock_fast_mail

    try:
        await send_payment_failed_email(
            ctx={},
            email="owner@acme.com",
            tenant_name="Acme Corp",
        )
    finally:
        mail_module.fast_mail = original_fast_mail

    assert mock_send.called, "fast_mail.send_message was not called"
    call_kwargs = mock_send.call_args

    message = call_kwargs.args[0]
    assert message.template_body.get("tenant_name") == "Acme Corp"
    assert call_kwargs.kwargs.get("html_template") == "payment_failed.html"
    assert call_kwargs.kwargs.get("plain_template") == "payment_failed.txt"


def test_all_html_templates_extend_base():
    """
    PLAT-05: All 4 HTML email templates extend base.html via Jinja2 inheritance.

    This verifies the template hierarchy is correct and all transactional
    emails share the same branded WXCODE layout.
    """
    html_templates = [
        "verify_email.html",
        "reset_password.html",
        "invitation.html",
        "payment_failed.html",
    ]

    for template_name in html_templates:
        template_path = TEMPLATES_DIR / template_name
        assert template_path.exists(), f"Template file not found: {template_path}"
        content = template_path.read_text()
        assert '{% extends "base.html" %}' in content, (
            f"{template_name} does not contain '{{%% extends \"base.html\" %%}}'"
        )


def test_templates_use_direct_variables_not_body_prefix():
    """
    PLAT-05: HTML templates use {{ variable }} directly, not {{ body.variable }}.

    fastapi-mail 1.6.2 passes template_body dict at top level via
    render(**template_data) — using {{ body.variable }} would cause
    all template variables to be undefined.
    """
    html_templates = [
        "verify_email.html",
        "reset_password.html",
        "invitation.html",
        "payment_failed.html",
    ]

    for template_name in html_templates:
        template_path = TEMPLATES_DIR / template_name
        assert template_path.exists(), f"Template file not found: {template_path}"
        content = template_path.read_text()
        assert "{{ body." not in content, (
            f"{template_name} contains '{{{{ body.' prefix — fastapi-mail 1.6.2 "
            f"uses direct variables; {{ body.variable }} would be undefined"
        )
