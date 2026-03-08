"""
Integration tests for Phase 22 — Claude Provisioning API.

Covers all 5 Phase 22 endpoints:
1. PUT  /api/v1/admin/tenants/{id}/claude-token   — set encrypted token
2. DELETE /api/v1/admin/tenants/{id}/claude-token  — revoke token
3. PATCH /api/v1/admin/tenants/{id}/claude-config  — update config (partial)
4. POST  /api/v1/admin/tenants/{id}/activate       — activate tenant
5. GET   /api/v1/tenants/{id}/wxcode-config        — tenant-scoped config (no token)

Plus:
- Audit trail verification (actions recorded, token value never logged)
- Error cases (404, 409, 422, 403)
- Role enforcement (DEVELOPER+ required for wxcode-config, VIEWER denied)
- Tenant mismatch protection (cross-tenant read prevention)

Notes:
- conftest `client` fixture yields (http_client, fake_redis, app, test_db)
- Super-admin is seeded directly via test_db (no HTTP flow)
- WXCODE_ENCRYPTION_KEY is monkeypatched for crypto tests
- arq, Stripe, and Redis dependencies are mocked in the shared conftest.py
"""

import uuid

import pytest
from sqlalchemy import select

from wxcode_adm.audit.models import AuditLog
from wxcode_adm.auth.models import User
from wxcode_adm.auth.password import hash_password
from wxcode_adm.tenants.models import MemberRole, Tenant, TenantMembership


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_crypto_key(monkeypatch, key: str = "test-encryption-key-22") -> None:
    """Monkeypatch WXCODE_ENCRYPTION_KEY on the settings singleton."""
    from pydantic import SecretStr
    from wxcode_adm import config as config_module

    monkeypatch.setattr(
        config_module.settings, "WXCODE_ENCRYPTION_KEY", SecretStr(key)
    )


async def _seed_super_admin(test_db, email: str, password: str) -> None:
    """
    Insert a super-admin user directly into test DB.
    Does NOT go through the HTTP flow (super-admin is pre-seeded in production).
    """
    async with test_db() as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return
        admin = User(
            email=email,
            password_hash=hash_password(password),
            email_verified=True,
            is_active=True,
            is_superuser=True,
        )
        session.add(admin)
        await session.commit()


async def _admin_login(client, email: str, password: str) -> dict:
    """
    Log in as a super-admin and return the token response dict.

    Returns dict with 'access_token' and 'refresh_token' keys.
    """
    r = await client.post(
        "/api/v1/admin/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()


async def _signup_verify_login(
    client, redis, email: str, password: str = "SecurePass1"
) -> tuple[str, str]:
    """
    Sign up, verify email, and log in a regular user.

    Returns (access_token, refresh_token).
    """
    keys_before: set[str] = set()
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys_before.add(k)

    r = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password},
    )
    assert r.status_code == 201, f"Signup failed: {r.text}"

    new_key = None
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k and k not in keys_before:
            new_key = k
            break
    assert new_key is not None, f"No new OTP key after signup for {email}"
    code = await redis.get(new_key)
    assert code is not None

    r = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": code},
    )
    assert r.status_code == 200, f"Verify email failed: {r.text}"

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    data = r.json()
    return data["access_token"], data.get("refresh_token", "")


async def _create_tenant_in_db(
    test_db,
    name: str = "Test Corp",
    slug: str | None = None,
    status: str = "pending_setup",
    database_name: str | None = None,
) -> uuid.UUID:
    """
    Create a Tenant directly in test_db and return its ID.
    """
    if slug is None:
        slug = name.lower().replace(" ", "-").replace("_", "-") + "-" + str(uuid.uuid4())[:8]
    async with test_db() as session:
        tenant = Tenant(
            name=name,
            slug=slug,
            status=status,
            database_name=database_name,
        )
        session.add(tenant)
        await session.commit()
        return tenant.id


# ---------------------------------------------------------------------------
# Admin endpoint tests: PUT /admin/tenants/{id}/claude-token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_claude_token_success(client, test_db, monkeypatch):
    """Super-admin can set the Claude OAuth token. Token is stored encrypted, not returned."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_set_token@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    # Create a tenant directly in DB
    tenant_id = await _create_tenant_in_db(test_db, name="Token Test Corp", slug="token-test-corp")

    # PUT claude-token
    r = await c.put(
        f"/api/v1/admin/tenants/{tenant_id}/claude-token",
        json={"token": "test-oauth-token-abc", "reason": "Initial setup"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "Claude token set" in data.get("message", "")

    # GET tenant detail — verify has_claude_token is True
    r = await c.get(
        f"/api/v1/admin/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["has_claude_token"] is True

    # Raw token must NOT appear in response
    response_text = r.text
    assert "test-oauth-token-abc" not in response_text


@pytest.mark.asyncio
async def test_set_claude_token_not_found(client, test_db, monkeypatch):
    """PUT claude-token with a random UUID returns 404."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_token_404@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    random_id = uuid.uuid4()
    r = await c.put(
        f"/api/v1/admin/tenants/{random_id}/claude-token",
        json={"token": "some-token", "reason": "Test"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Admin endpoint tests: DELETE /admin/tenants/{id}/claude-token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_claude_token_success(client, test_db, monkeypatch):
    """Super-admin can revoke a Claude token. After revocation, has_claude_token is False."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_revoke_token@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    # Create tenant and set a token first
    tenant_id = await _create_tenant_in_db(test_db, name="Revoke Test Corp", slug="revoke-test-corp")

    await c.put(
        f"/api/v1/admin/tenants/{tenant_id}/claude-token",
        json={"token": "some-secret-token", "reason": "Initial setup"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # DELETE with a body: httpx.delete() doesn't support body params;
    # use c.request() with explicit method
    import json as json_lib
    r = await c.request(
        "DELETE",
        f"/api/v1/admin/tenants/{tenant_id}/claude-token",
        content=json_lib.dumps({"reason": "Security rotation"}),
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200, r.text

    # GET tenant detail — has_claude_token should be False now
    r = await c.get(
        f"/api/v1/admin/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["has_claude_token"] is False


@pytest.mark.asyncio
async def test_revoke_claude_token_no_token(client, test_db, monkeypatch):
    """DELETE claude-token when tenant has no token returns 409 with NO_TOKEN error."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_revoke_notoken@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    # Create tenant WITHOUT setting a token
    tenant_id = await _create_tenant_in_db(test_db, name="No Token Corp", slug="no-token-corp")

    import json as json_lib
    r = await c.request(
        "DELETE",
        f"/api/v1/admin/tenants/{tenant_id}/claude-token",
        content=json_lib.dumps({"reason": "Rotation"}),
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error_code") == "NO_TOKEN"


# ---------------------------------------------------------------------------
# Admin endpoint tests: PATCH /admin/tenants/{id}/claude-config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_claude_config_partial(client, test_db, monkeypatch):
    """PATCH claude-config with a single field updates only that field."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_config_partial@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    tenant_id = await _create_tenant_in_db(test_db, name="Config Partial Corp", slug="config-partial-corp")

    # PATCH only the model
    r = await c.patch(
        f"/api/v1/admin/tenants/{tenant_id}/claude-config",
        json={"claude_default_model": "opus"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    # GET tenant detail — verify model updated, others unchanged (defaults)
    r = await c.get(
        f"/api/v1/admin/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["claude_default_model"] == "opus"
    # Default values should remain
    assert detail["claude_max_concurrent_sessions"] == 3
    assert detail["claude_5h_token_budget"] is None
    assert detail["claude_weekly_token_budget"] is None


@pytest.mark.asyncio
async def test_update_claude_config_all_fields(client, test_db, monkeypatch):
    """PATCH claude-config with all 3 fields updates all of them."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_config_all@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    tenant_id = await _create_tenant_in_db(test_db, name="Config All Corp", slug="config-all-corp")

    # PATCH all 4 fields
    r = await c.patch(
        f"/api/v1/admin/tenants/{tenant_id}/claude-config",
        json={
            "claude_default_model": "haiku",
            "claude_max_concurrent_sessions": 5,
            "claude_5h_token_budget": 500000,
            "claude_weekly_token_budget": 2000000,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    # GET detail — verify all 4 updated
    r = await c.get(
        f"/api/v1/admin/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["claude_default_model"] == "haiku"
    assert detail["claude_max_concurrent_sessions"] == 5
    assert detail["claude_5h_token_budget"] == 500000
    assert detail["claude_weekly_token_budget"] == 2000000


@pytest.mark.asyncio
async def test_update_claude_config_empty_rejected(client, test_db, monkeypatch):
    """PATCH claude-config with empty body {} returns 422 (model_validator rejects all-None)."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_config_empty@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    tenant_id = await _create_tenant_in_db(test_db, name="Config Empty Corp", slug="config-empty-corp")

    r = await c.patch(
        f"/api/v1/admin/tenants/{tenant_id}/claude-config",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Admin endpoint tests: POST /admin/tenants/{id}/activate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_tenant_success(client, test_db, monkeypatch):
    """Super-admin can activate a pending_setup tenant that has a database_name."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_activate@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    # Create tenant with pending_setup status and database_name
    tenant_id = await _create_tenant_in_db(
        test_db,
        name="Activate Me Corp",
        slug="activate-me-corp",
        status="pending_setup",
        database_name="wxcode_t_test",
    )

    r = await c.post(
        f"/api/v1/admin/tenants/{tenant_id}/activate",
        json={"reason": "Setup complete"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "activated" in data.get("message", "").lower()

    # GET detail — verify status is active
    r = await c.get(
        f"/api/v1/admin/tenants/{tenant_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["status"] == "active"


@pytest.mark.asyncio
async def test_activate_tenant_wrong_status(client, test_db, monkeypatch):
    """POST activate on an already-active tenant returns 409 with INVALID_STATUS."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_activate_wrong@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    # Create tenant already in active status
    tenant_id = await _create_tenant_in_db(
        test_db,
        name="Already Active Corp",
        slug="already-active-corp",
        status="active",
        database_name="wxcode_t_active",
    )

    r = await c.post(
        f"/api/v1/admin/tenants/{tenant_id}/activate",
        json={"reason": "Trying to activate again"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error_code") == "INVALID_STATUS"


@pytest.mark.asyncio
async def test_activate_tenant_no_database_name(client, test_db, monkeypatch):
    """POST activate on pending_setup tenant without database_name returns 409 with MISSING_DATABASE_NAME."""
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_activate_nodb@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    # Create tenant with pending_setup but NO database_name
    tenant_id = await _create_tenant_in_db(
        test_db,
        name="No DB Corp",
        slug="no-db-corp",
        status="pending_setup",
        database_name=None,
    )

    r = await c.post(
        f"/api/v1/admin/tenants/{tenant_id}/activate",
        json={"reason": "Oops no database"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error_code") == "MISSING_DATABASE_NAME"


# ---------------------------------------------------------------------------
# wxcode-config endpoint tests: GET /tenants/{id}/wxcode-config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wxcode_config_developer_access(client, test_db, monkeypatch):
    """
    Tenant OWNER (level 4 >= DEVELOPER level 2) can access wxcode-config.
    Response includes all expected fields. Token is NOT in response.
    """
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client

    # Sign up and create a workspace (user becomes OWNER)
    access_token, _ = await _signup_verify_login(c, redis, "wxcode_config_owner@test.com")

    r = await c.post(
        "/api/v1/onboarding/workspace",
        json={"name": "Wxcode Config Workspace"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code in (200, 201), r.text
    workspace_data = r.json()
    tenant_id = workspace_data["tenant"]["id"]

    # Set fields and an encrypted token directly in test_db
    from wxcode_adm.common.crypto import encrypt_value
    async with test_db() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
        )
        tenant = result.scalar_one()
        tenant.database_name = "wxcode_t_owner_test"
        tenant.default_target_stack = "fastapi-jinja2"
        tenant.claude_default_model = "sonnet"
        tenant.claude_oauth_token = encrypt_value("super-secret-token-xyz")
        await session.commit()

    # GET wxcode-config with X-Tenant-ID header
    r = await c.get(
        f"/api/v1/tenants/{tenant_id}/wxcode-config",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()

    # All expected fields present
    assert "tenant_id" in data
    assert "database_name" in data
    assert "default_target_stack" in data
    assert "neo4j_enabled" in data
    assert "claude_default_model" in data
    assert "max_concurrent_sessions" in data

    # Values match what we set
    assert data["database_name"] == "wxcode_t_owner_test"
    assert data["default_target_stack"] == "fastapi-jinja2"
    assert data["claude_default_model"] == "sonnet"

    # Token MUST NOT appear in any form
    response_text = r.text
    assert "super-secret-token-xyz" not in response_text
    assert "claude_oauth_token" not in response_text


@pytest.mark.asyncio
async def test_wxcode_config_viewer_denied(client, test_db, monkeypatch):
    """
    A user with VIEWER role (level 1 < DEVELOPER level 2) is denied access to wxcode-config.
    """
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client

    # Create owner user and workspace
    owner_token, _ = await _signup_verify_login(c, redis, "wxcode_config_owner_v@test.com")
    r = await c.post(
        "/api/v1/onboarding/workspace",
        json={"name": "Viewer Test Workspace"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code in (200, 201), r.text
    tenant_id = r.json()["tenant"]["id"]

    # Sign up the VIEWER user
    viewer_token, _ = await _signup_verify_login(c, redis, "wxcode_config_viewer@test.com")

    # Add viewer user to tenant with VIEWER role directly in DB
    async with test_db() as session:
        result = await session.execute(
            select(User).where(User.email == "wxcode_config_viewer@test.com")
        )
        viewer_user = result.scalar_one()
        membership = TenantMembership(
            tenant_id=uuid.UUID(tenant_id),
            user_id=viewer_user.id,
            role=MemberRole.VIEWER,
        )
        session.add(membership)
        await session.commit()

    # Viewer tries to access wxcode-config — should be denied
    r = await c.get(
        f"/api/v1/tenants/{tenant_id}/wxcode-config",
        headers={
            "Authorization": f"Bearer {viewer_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_wxcode_config_tenant_mismatch(client, test_db, monkeypatch):
    """
    DEVELOPER in tenant A gets 404 when trying to read config of tenant B
    using tenant B's ID in path but tenant A's X-Tenant-ID header.
    """
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client

    # Create user A with workspace A
    token_a, _ = await _signup_verify_login(c, redis, "wxcode_mismatch_user_a@test.com")
    r = await c.post(
        "/api/v1/onboarding/workspace",
        json={"name": "Tenant A Workspace"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code in (200, 201), r.text
    tenant_a_id = r.json()["tenant"]["id"]

    # Create a separate tenant B directly in DB (no member for user A)
    tenant_b_id = await _create_tenant_in_db(
        test_db,
        name="Tenant B Corp",
        slug="tenant-b-corp-mismatch",
        database_name="wxcode_t_b",
    )

    # User A (OWNER of tenant A) tries to read tenant B's config
    # by using tenant A's X-Tenant-ID but tenant B's UUID in the path
    r = await c.get(
        f"/api/v1/tenants/{tenant_b_id}/wxcode-config",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Tenant-ID": tenant_a_id,  # tenant A context
        },
    )
    # Should be 404 — mismatch protection
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Audit trail verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provisioning_audit_trail(client, test_db, monkeypatch):
    """
    Provisioning operations create audit log entries.
    Token value must NEVER appear in audit log details.
    """
    _patch_crypto_key(monkeypatch)
    c, redis, app, test_db = client
    email = "admin_audit_trail@test.com"
    pw = "AdminPass1"
    await _seed_super_admin(test_db, email, pw)
    tokens = await _admin_login(c, email, pw)
    admin_token = tokens["access_token"]

    tenant_id = await _create_tenant_in_db(
        test_db,
        name="Audit Trail Corp",
        slug="audit-trail-corp",
        status="pending_setup",
        database_name="wxcode_t_audit",
    )

    # 1. Set token
    r = await c.put(
        f"/api/v1/admin/tenants/{tenant_id}/claude-token",
        json={"token": "audit-test-secret-token", "reason": "Audit test setup"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    # 2. Update config
    r = await c.patch(
        f"/api/v1/admin/tenants/{tenant_id}/claude-config",
        json={"claude_default_model": "haiku"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    # 3. Activate
    r = await c.post(
        f"/api/v1/admin/tenants/{tenant_id}/activate",
        json={"reason": "Audit test activation"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    # Query audit_logs table directly
    async with test_db() as session:
        result = await session.execute(
            select(AuditLog).where(
                AuditLog.resource_id == str(tenant_id)
            )
        )
        audit_entries = result.scalars().all()

    actions = {entry.action for entry in audit_entries}

    # All 3 provisioning operations should be logged
    assert "set_claude_token" in actions, f"set_claude_token not in audit: {actions}"
    assert "update_claude_config" in actions, f"update_claude_config not in audit: {actions}"
    assert "activate_tenant" in actions, f"activate_tenant not in audit: {actions}"

    # Token value must NOT appear in any audit detail
    for entry in audit_entries:
        details_str = str(entry.details)
        assert "audit-test-secret-token" not in details_str, (
            f"Token value found in audit details for action={entry.action}: {entry.details}"
        )
