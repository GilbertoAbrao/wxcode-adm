"""
Tests for the tenant isolation guard in wxcode_adm.db.tenant.

Verifies:
- Unguarded ORM queries on TenantModel subclasses raise TenantIsolationError
- Guarded queries (with _tenant_enforced execution option) succeed
- Raw SQL queries are not affected by the guard
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from wxcode_adm.common.exceptions import TenantIsolationError
from wxcode_adm.db.base import Base
from wxcode_adm.db.tenant import TenantModel, install_tenant_guard


class FakeTenantItem(TenantModel):
    """Concrete TenantModel subclass used for testing."""

    __tablename__ = "fake_tenant_item"
    name: Mapped[str] = mapped_column(default="test")


@pytest.fixture
async def guarded_session():
    """
    Fixture that creates an in-memory SQLite async engine with the tenant guard installed.
    Yields the session_maker; tears down tables after the test.
    """
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    install_tenant_guard(session_maker)

    yield session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


async def test_unguarded_query_raises_tenant_isolation_error(guarded_session):
    """An ORM SELECT on FakeTenantItem without _tenant_enforced raises TenantIsolationError."""
    async with guarded_session() as session:
        with pytest.raises(TenantIsolationError):
            await session.execute(select(FakeTenantItem))


async def test_guarded_query_passes(guarded_session):
    """An ORM SELECT with execution_options(_tenant_enforced=True) does NOT raise."""
    async with guarded_session() as session:
        result = await session.execute(
            select(FakeTenantItem).execution_options(_tenant_enforced=True)
        )
        rows = result.scalars().all()
        assert rows == []  # empty table, but no error


async def test_raw_sql_not_affected(guarded_session):
    """Raw SQL via text() bypasses the ORM guard and should not raise."""
    async with guarded_session() as session:
        result = await session.execute(text("SELECT 1"))
        row = result.fetchone()
        assert row[0] == 1
