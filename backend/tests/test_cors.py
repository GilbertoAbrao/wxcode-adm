"""
CORS behavior tests for wxcode-adm.

Tests that:
1. Allowed origins (ALLOWED_ORIGINS) receive correct Access-Control headers
2. Disallowed origins are rejected (no permissive headers returned)
3. Preflight (OPTIONS) requests work for allowed origins
4. Preflight requests are rejected for disallowed origins
5. Tenant wxcode_url origins are honored via DynamicCORSMiddleware

Uses httpx.AsyncClient with ASGITransport. The local `cors_client` fixture
patches ALLOWED_ORIGINS to an explicit list (overriding .env wildcard) so that
CORS behavior can be deterministically tested.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

from wxcode_adm.db.base import Base
import wxcode_adm.auth.models  # noqa: F401
import wxcode_adm.tenants.models  # noqa: F401
import wxcode_adm.billing.models  # noqa: F401
from wxcode_adm import main as main_module


# ---------------------------------------------------------------------------
# Local CORS fixture
# ---------------------------------------------------------------------------


def _generate_rsa_keys() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


async def _make_sqlite_session_maker():
    """Create an in-memory SQLite session maker for test DB."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    _jsonb_originals = {}
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if isinstance(col.type, JSONB):
                _jsonb_originals[(table.name, col.name)] = (col.type, col.server_default)
                col.type = JSON()
                col.server_default = None
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            key = (table.name, col.name)
            if key in _jsonb_originals:
                col.type, col.server_default = _jsonb_originals[key]
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False), engine


@pytest.fixture
async def cors_client(monkeypatch):
    """
    Async HTTP client configured for CORS testing.

    Patches ALLOWED_ORIGINS to ["http://localhost:3060"] (overrides any .env wildcard)
    so CORS origin-checking behavior can be tested deterministically.

    Yields (client, app, tenant_cache) where tenant_cache is the
    _tenant_origin_cache set that can be modified to add dynamic origins.
    """
    import fakeredis.aioredis
    from wxcode_adm import config as config_module
    from wxcode_adm.dependencies import get_session, get_redis

    private_pem, public_pem = _generate_rsa_keys()

    monkeypatch.setattr(config_module.settings, "JWT_PRIVATE_KEY", SecretStr(private_pem))
    monkeypatch.setattr(config_module.settings, "JWT_PUBLIC_KEY", SecretStr(public_pem))
    monkeypatch.setattr(config_module.settings, "STRIPE_SECRET_KEY", SecretStr("sk_test_fake"))
    monkeypatch.setattr(config_module.settings, "STRIPE_WEBHOOK_SECRET", SecretStr("whsec_fake"))
    monkeypatch.setattr(config_module.settings, "STRIPE_PUBLISHABLE_KEY", "pk_test_fake")
    monkeypatch.setattr(config_module.settings, "FRONTEND_URL", "http://localhost:3060")
    # Explicitly override ALLOWED_ORIGINS to a specific list (not wildcard)
    monkeypatch.setattr(config_module.settings, "ALLOWED_ORIGINS", ["http://localhost:3060"])

    # Isolate tenant cache — start empty for each test
    test_tenant_cache: set[str] = set()
    monkeypatch.setattr(main_module, "_tenant_origin_cache", test_tenant_cache)

    from wxcode_adm.main import create_app

    app = create_app()
    app.state.limiter.enabled = False

    session_maker, db_engine = await _make_sqlite_session_maker()
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_session():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, app, test_tenant_cache

    await fake_redis.aclose()
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await db_engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_allowed_origin_returns_headers(cors_client):
    """
    Requests from an ALLOWED_ORIGINS origin receive the correct
    Access-Control-Allow-Origin echo header.

    With allow_credentials=True, Starlette echoes the specific allowed origin
    rather than returning '*'.
    """
    c, app, _ = cors_client
    response = await c.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3060"},
    )
    acao = response.headers.get("access-control-allow-origin")
    assert acao == "http://localhost:3060", (
        f"Expected origin echo for allowed origin, got: {acao}"
    )


@pytest.mark.asyncio
async def test_cors_disallowed_origin_no_headers(cors_client):
    """
    Requests from a non-allowed origin should not receive permissive
    Access-Control-Allow-Origin headers.
    """
    c, app, _ = cors_client
    response = await c.get(
        "/api/v1/health",
        headers={"Origin": "http://evil.example.com"},
    )
    acao = response.headers.get("access-control-allow-origin")
    # Header must not be present or must not echo the evil origin
    assert acao is None or acao != "http://evil.example.com", (
        f"Evil origin should not be echoed, got: {acao}"
    )


@pytest.mark.asyncio
async def test_cors_preflight_allowed_origin(cors_client):
    """
    OPTIONS preflight from an allowed origin returns 200 with correct CORS headers.
    """
    c, app, _ = cors_client
    response = await c.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3060",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3060"
    assert "access-control-allow-methods" in response.headers


@pytest.mark.asyncio
async def test_cors_preflight_disallowed_origin(cors_client):
    """
    OPTIONS preflight from a disallowed origin returns a non-permissive response.
    Starlette returns 400 for disallowed CORS preflight and must NOT echo the
    evil origin in Access-Control-Allow-Origin.
    """
    c, app, _ = cors_client
    response = await c.options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    acao = response.headers.get("access-control-allow-origin")
    assert acao is None or acao != "http://evil.example.com", (
        f"Evil origin should not be echoed in preflight, got: {acao}"
    )


@pytest.mark.asyncio
async def test_cors_tenant_wxcode_url_origin(cors_client):
    """
    Requests from a tenant wxcode_url origin are allowed when the origin
    is in the _tenant_origin_cache.

    Uses direct cache manipulation (simpler than full DB + lifespan) since
    the unit being tested is DynamicCORSMiddleware's origin checking logic,
    not the DB loading path.
    """
    c, app, tenant_cache = cors_client

    # Inject tenant wxcode_url directly into the cache
    tenant_custom_origin = "https://custom.example.com"
    tenant_cache.add(tenant_custom_origin)

    response = await c.get(
        "/api/v1/health",
        headers={"Origin": tenant_custom_origin},
    )
    acao = response.headers.get("access-control-allow-origin")
    assert acao == tenant_custom_origin, (
        f"Tenant origin should be echoed back. Got: {acao}"
    )
