"""
Shared test fixtures for wxcode-adm integration tests.

Provides:
- rsa_keys: session-scoped RSA 2048-bit key pair (PEM strings)
- test_db: function-scoped in-memory SQLite async engine with all tables
- test_redis: function-scoped FakeRedis instance
- client: function-scoped async HTTP client with dependency overrides

The settings singleton is patched per-test via monkeypatch so JWT key
operations use test keys instead of requiring real RSA keys in environment.

Note: The arq pool (get_arq_pool) is mocked in tests to avoid real Redis
connections during email enqueueing.

SQLite compatibility: The production models use PostgreSQL-specific server
defaults (gen_random_uuid(), now()). For SQLite tests we create tables using
a metadata copy with those server defaults removed, relying on the Python-level
defaults defined in the model columns (default=uuid.uuid4, default=datetime.now,
etc.). The model instances still receive correct values because SQLAlchemy
evaluates Python-side defaults before INSERT.
"""

import uuid
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import MetaData, Table, Column, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from wxcode_adm.db.base import Base


# ---------------------------------------------------------------------------
# RSA key fixture (session-scoped — expensive to generate)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keys() -> tuple[str, str]:
    """
    Generate a 2048-bit RSA key pair for JWT signing in tests.

    Returns:
        (private_pem, public_pem) as PEM-encoded strings.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


# ---------------------------------------------------------------------------
# Test database fixture (function-scoped — fresh DB per test)
# ---------------------------------------------------------------------------


def _build_sqlite_metadata() -> MetaData:
    """
    Build a SQLite-compatible metadata object from Base.metadata.

    Strips PostgreSQL-specific server_defaults (gen_random_uuid(), now())
    from all columns so SQLite can create the tables. Python-level defaults
    on the models (default=uuid.uuid4, etc.) still apply at INSERT time.
    """
    # We need to import the models to ensure they are registered in Base.metadata
    import wxcode_adm.auth.models  # noqa: F401
    import wxcode_adm.tenants.models  # noqa: F401

    sqlite_meta = MetaData()
    for table in Base.metadata.sorted_tables:
        new_cols = []
        for col in table.columns:
            # Copy column but remove server_default (PostgreSQL-specific functions)
            new_col = col._copy()
            new_col.server_default = None
            new_cols.append(new_col)
        Table(table.name, sqlite_meta, *new_cols, *[c._copy() for c in table.constraints])
    return sqlite_meta


@pytest.fixture
async def test_db():
    """
    Create an in-memory SQLite async engine with all auth tables.

    Yields the async_sessionmaker. Tables are dropped on teardown.
    Uses aiosqlite driver (no Docker/PostgreSQL needed).

    Server defaults that require PostgreSQL functions (gen_random_uuid, now())
    are stripped; Python-level model defaults (uuid.uuid4, etc.) are used instead.
    """
    # Ensure models are registered
    import wxcode_adm.auth.models  # noqa: F401
    import wxcode_adm.tenants.models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    yield session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test Redis fixture (function-scoped — fresh fake Redis per test)
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_redis():
    """
    Create a FakeRedis instance for testing.

    Yields the FakeRedis instance. Closed on teardown.
    Uses decode_responses=True to match the production redis_client behavior.
    """
    import fakeredis.aioredis

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield fake_redis
    await fake_redis.aclose()


# ---------------------------------------------------------------------------
# HTTP client fixture (function-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(test_db, test_redis, rsa_keys, monkeypatch):
    """
    Create an async HTTP test client with all dependencies overridden.

    Overrides:
    - get_session: uses test SQLite DB
    - get_redis: uses FakeRedis
    - settings.JWT_PRIVATE_KEY: test RSA private key
    - settings.JWT_PUBLIC_KEY: test RSA public key
    - get_arq_pool: returns a mock that silently accepts enqueue_job calls
    """
    private_pem, public_pem = rsa_keys

    # Patch settings with test RSA keys
    from wxcode_adm import config as config_module
    monkeypatch.setattr(config_module.settings, "JWT_PRIVATE_KEY", SecretStr(private_pem))
    monkeypatch.setattr(config_module.settings, "JWT_PUBLIC_KEY", SecretStr(public_pem))

    # Patch reset_serializer in service module (it captures settings at import time)
    from itsdangerous import URLSafeTimedSerializer
    import wxcode_adm.auth.service as auth_service_module
    monkeypatch.setattr(
        auth_service_module,
        "reset_serializer",
        URLSafeTimedSerializer(private_pem, salt="password-reset"),
    )

    # Patch invitation_serializer in tenant service module (same pattern as above)
    import wxcode_adm.tenants.service as tenant_service_module
    monkeypatch.setattr(
        tenant_service_module,
        "invitation_serializer",
        URLSafeTimedSerializer(private_pem, salt="tenant-invitation"),
    )

    # Mock arq pool to avoid real Redis connections during email enqueueing
    class _FakeArqJob:
        job_id = "fake-job-id"

    class _FakeArqPool:
        async def enqueue_job(self, *args, **kwargs):
            return _FakeArqJob()

        async def aclose(self):
            pass

    async def mock_get_arq_pool():
        return _FakeArqPool()

    monkeypatch.setattr(auth_service_module, "get_arq_pool", mock_get_arq_pool)
    monkeypatch.setattr(tenant_service_module, "get_arq_pool", mock_get_arq_pool)

    # Build the FastAPI app and override dependencies
    from wxcode_adm.main import create_app
    from wxcode_adm.dependencies import get_session, get_redis

    app = create_app()

    async def override_get_session():
        async with test_db() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_get_redis():
        return test_redis

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, test_redis, app, test_db
