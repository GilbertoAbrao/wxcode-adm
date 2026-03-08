"""
Integration tests for Phase 20 Plan 02 — Tenant model extension.

Tests cover the new fields added to the Tenant model:
- claude_oauth_token (nullable, stores Fernet-encrypted value)
- claude_default_model (default "sonnet")
- claude_max_concurrent_sessions (default 3)
- claude_5h_token_budget (nullable, null = unlimited, 5-hour window)
- claude_weekly_token_budget (nullable, null = unlimited, weekly window)
- database_name (nullable)
- default_target_stack (default "fastapi-jinja2")
- neo4j_enabled (default True)
- status (default "pending_setup", plain String)

All tests use the test_db fixture (in-memory SQLite) and pytest.mark.asyncio.
The crypto round-trip test monkeypatches WXCODE_ENCRYPTION_KEY so it is
isolated from the actual environment value.
"""

import pytest

from wxcode_adm.tenants.models import Tenant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_crypto_key(monkeypatch, key: str = "test-encryption-key") -> None:
    """Monkeypatch WXCODE_ENCRYPTION_KEY on the settings singleton."""
    from pydantic import SecretStr
    from wxcode_adm import config as config_module

    monkeypatch.setattr(
        config_module.settings, "WXCODE_ENCRYPTION_KEY", SecretStr(key)
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_claude_fields_defaults(test_db):
    """New Claude fields have correct defaults on a minimal Tenant instance."""
    async with test_db() as session:
        tenant = Tenant(name="Defaults Test", slug="defaults-test")
        session.add(tenant)
        await session.flush()

        assert tenant.claude_oauth_token is None
        assert tenant.claude_default_model == "sonnet"
        assert tenant.claude_max_concurrent_sessions == 3
        assert tenant.claude_5h_token_budget is None
        assert tenant.claude_weekly_token_budget is None


@pytest.mark.asyncio
async def test_tenant_wxcode_fields_defaults(test_db):
    """New wxcode fields have correct defaults on a minimal Tenant instance."""
    async with test_db() as session:
        tenant = Tenant(name="Wxcode Defaults", slug="wxcode-defaults")
        session.add(tenant)
        await session.flush()

        assert tenant.database_name is None
        assert tenant.default_target_stack == "fastapi-jinja2"
        assert tenant.neo4j_enabled is True
        assert tenant.status == "pending_setup"


@pytest.mark.asyncio
async def test_tenant_claude_oauth_token_encrypted_roundtrip(test_db, monkeypatch):
    """claude_oauth_token stores Fernet-encrypted value that round-trips correctly."""
    _patch_crypto_key(monkeypatch, "test-crypto-key-for-tenant-tests")

    from wxcode_adm.common.crypto import decrypt_value, encrypt_value

    original_token = "claude-oauth-access-token-abc123"
    encrypted = encrypt_value(original_token)

    async with test_db() as session:
        tenant = Tenant(
            name="Crypto Tenant",
            slug="crypto-tenant",
            claude_oauth_token=encrypted,
        )
        session.add(tenant)
        await session.commit()

    # Reload from DB and decrypt
    from sqlalchemy import select

    async with test_db() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.slug == "crypto-tenant")
        )
        loaded = result.scalar_one()

        assert loaded.claude_oauth_token is not None
        assert loaded.claude_oauth_token != original_token  # stored encrypted
        decrypted = decrypt_value(loaded.claude_oauth_token)
        assert decrypted == original_token


@pytest.mark.asyncio
async def test_tenant_status_values(test_db):
    """All valid status values persist and reload correctly."""
    valid_statuses = ["pending_setup", "active", "suspended", "cancelled"]

    for i, status in enumerate(valid_statuses):
        async with test_db() as session:
            tenant = Tenant(
                name=f"Status Test {i}",
                slug=f"status-test-{i}",
                status=status,
            )
            session.add(tenant)
            await session.commit()

        from sqlalchemy import select

        async with test_db() as session:
            result = await session.execute(
                select(Tenant).where(Tenant.slug == f"status-test-{i}")
            )
            loaded = result.scalar_one()
            assert loaded.status == status, (
                f"Expected status={status!r}, got {loaded.status!r}"
            )


@pytest.mark.asyncio
async def test_tenant_custom_claude_config(test_db):
    """Custom Claude config values persist and reload correctly."""
    async with test_db() as session:
        tenant = Tenant(
            name="Custom Claude",
            slug="custom-claude",
            claude_default_model="opus",
            claude_max_concurrent_sessions=10,
            claude_5h_token_budget=1_000_000,
            claude_weekly_token_budget=5_000_000,
        )
        session.add(tenant)
        await session.commit()

    from sqlalchemy import select

    async with test_db() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.slug == "custom-claude")
        )
        loaded = result.scalar_one()

        assert loaded.claude_default_model == "opus"
        assert loaded.claude_max_concurrent_sessions == 10
        assert loaded.claude_5h_token_budget == 1_000_000
        assert loaded.claude_weekly_token_budget == 5_000_000


@pytest.mark.asyncio
async def test_tenant_database_name_pattern(test_db):
    """database_name field persists and reloads with the wxcode naming pattern."""
    async with test_db() as session:
        tenant = Tenant(
            name="Acme Corp",
            slug="acme",
            database_name="wxcode_t_acme",
        )
        session.add(tenant)
        await session.commit()

    from sqlalchemy import select

    async with test_db() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )
        loaded = result.scalar_one()
        assert loaded.database_name == "wxcode_t_acme"
