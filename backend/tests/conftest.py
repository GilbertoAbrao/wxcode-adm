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
from sqlalchemy import JSON, MetaData, Table, Column, event
from sqlalchemy.dialects.postgresql import JSONB
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
    import wxcode_adm.billing.models  # noqa: F401
    from wxcode_adm.audit import models as _audit_models  # noqa: F401
    # Phase 6: ensure OAuth/MFA models are registered (they are in auth.models
    # but explicit import is future-proof and documents intent)
    from wxcode_adm.auth.models import OAuthAccount, MfaBackupCode, TrustedDevice  # noqa: F401

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
    # Ensure models are registered (including audit models for audit_logs table)
    import wxcode_adm.auth.models  # noqa: F401
    import wxcode_adm.tenants.models  # noqa: F401
    import wxcode_adm.billing.models  # noqa: F401
    from wxcode_adm.audit import models as _audit_models  # noqa: F401
    # Phase 6: ensure OAuth/MFA models are registered
    from wxcode_adm.auth.models import OAuthAccount, MfaBackupCode, TrustedDevice  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    # SQLite does not support JSONB or PostgreSQL server defaults like '{}'::jsonb.
    # Patch all JSONB columns in Base.metadata to use JSON (SQLite-compatible) and
    # remove the PostgreSQL-specific server_default before create_all.
    # Originals are restored after table creation so production code is unaffected.
    _jsonb_originals = {}
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if isinstance(col.type, JSONB):
                _jsonb_originals[(table.name, col.name)] = (col.type, col.server_default)
                col.type = JSON()
                col.server_default = None  # strip '{}'::jsonb — SQLite can't parse it

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Restore original JSONB types and server_defaults so production code is unaffected
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            key = (table.name, col.name)
            if key in _jsonb_originals:
                col.type, col.server_default = _jsonb_originals[key]

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Seed the free plan required by bootstrap_free_subscription (called at workspace creation).
    # All tests that create a workspace need at least one active free plan in the DB.
    from wxcode_adm.billing.models import Plan
    async with session_maker() as session:
        free_plan = Plan(
            name="Free",
            slug="free",
            monthly_fee_cents=0,
            token_quota_5h=10000,
            token_quota_weekly=50000,
            overage_rate_cents_per_token=0,
            member_cap=3,
            is_active=True,
        )
        session.add(free_plan)
        await session.commit()

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

    # Mock arq pool in billing modules too
    # webhook_router imports get_arq_pool at module level — patch as attribute
    import wxcode_adm.billing.webhook_router as webhook_router_module
    monkeypatch.setattr(webhook_router_module, "get_arq_pool", mock_get_arq_pool)

    # billing service uses lazy import (from wxcode_adm.tasks.worker import get_arq_pool)
    # inside _handle_payment_failed — patch at source module so re-imports get the mock
    import wxcode_adm.tasks.worker as tasks_worker_module
    monkeypatch.setattr(tasks_worker_module, "get_arq_pool", mock_get_arq_pool)

    # Mock redis_client used in _handle_payment_failed for token blacklisting.
    # The service lazily imports it from wxcode_adm.common.redis_client, so we
    # patch the source module — Python's module cache ensures the lazy import
    # picks up the test_redis instance instead of the real Redis connection.
    import wxcode_adm.common.redis_client as redis_client_module
    monkeypatch.setattr(redis_client_module, "redis_client", test_redis)

    # Mock Stripe client to avoid real API calls in tests
    import wxcode_adm.billing.stripe_client as stripe_client_module

    class _FakeStripeCustomer:
        id = "cus_test_123"

    class _FakeStripeProduct:
        id = "prod_test_123"

    class _FakeStripePrice:
        id = "price_test_123"

    class _FakeStripeMeter:
        id = "mtr_test_123"

    class _FakeStripeCheckoutSession:
        url = "https://checkout.stripe.com/test"
        id = "cs_test_123"

    class _FakeStripePortalSession:
        url = "https://billing.stripe.com/test"

    class _FakeStripeCustomers:
        async def create_async(self, **kwargs):
            return _FakeStripeCustomer()

    class _FakeStripeProducts:
        async def create_async(self, **kwargs):
            return _FakeStripeProduct()

        async def update_async(self, product_id, **kwargs):
            return _FakeStripeProduct()

    class _FakeStripePrices:
        async def create_async(self, **kwargs):
            return _FakeStripePrice()

        async def update_async(self, price_id, **kwargs):
            return _FakeStripePrice()

    class _FakeStripeBillingMeters:
        async def create_async(self, **kwargs):
            return _FakeStripeMeter()

    class _FakeStripeBilling:
        meters = _FakeStripeBillingMeters()

    class _FakeStripeCheckoutSessions:
        async def create_async(self, **kwargs):
            return _FakeStripeCheckoutSession()

    class _FakeStripeCheckout:
        sessions = _FakeStripeCheckoutSessions()

    class _FakeStripeBillingPortalSessions:
        async def create_async(self, **kwargs):
            return _FakeStripePortalSession()

    class _FakeStripeBillingPortal:
        sessions = _FakeStripeBillingPortalSessions()

    class _FakeStripeClient:
        customers = _FakeStripeCustomers()
        products = _FakeStripeProducts()
        prices = _FakeStripePrices()
        billing = _FakeStripeBilling()
        checkout = _FakeStripeCheckout()
        billing_portal = _FakeStripeBillingPortal()

    fake_stripe = _FakeStripeClient()
    monkeypatch.setattr(stripe_client_module, "stripe_client", fake_stripe)

    # Also patch in service module (from wxcode_adm.billing.stripe_client import stripe_client
    # creates a module-level binding in service.py that must be patched separately)
    import wxcode_adm.billing.service as billing_service_module
    monkeypatch.setattr(billing_service_module, "stripe_client", fake_stripe)

    # Patch Stripe config settings so config.py doesn't fail validation
    monkeypatch.setattr(config_module.settings, "STRIPE_SECRET_KEY", SecretStr("sk_test_fake"))
    monkeypatch.setattr(config_module.settings, "STRIPE_WEBHOOK_SECRET", SecretStr("whsec_fake"))
    monkeypatch.setattr(config_module.settings, "STRIPE_PUBLISHABLE_KEY", "pk_test_fake")
    monkeypatch.setattr(config_module.settings, "FRONTEND_URL", "http://localhost:3060")

    # Build the FastAPI app and override dependencies
    from wxcode_adm.main import create_app
    from wxcode_adm.dependencies import get_session, get_redis

    app = create_app()

    # Disable rate limiter by default for test isolation.
    # Individual rate limit tests re-enable it within the test body.
    # This is the standard slowapi approach: setting limiter.enabled = False
    # causes all @limiter.limit() decorators to be no-ops.
    app.state.limiter.enabled = False

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
