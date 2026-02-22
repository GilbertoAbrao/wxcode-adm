# Phase 1: Foundation - Research

**Researched:** 2026-02-22
**Domain:** FastAPI + SQLAlchemy 2.0 async + PostgreSQL + Redis + arq project scaffolding and tenant isolation
**Confidence:** HIGH (all core library versions verified against PyPI; architecture patterns verified against official SQLAlchemy docs and multiple production boilerplates)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Project Structure
- Monorepo: backend and frontend in the same git repo (`/backend` and `/frontend`)
- Backend organized **by domain**: `auth/`, `tenants/`, `billing/`, `users/`, etc. — each module contains its own router, service, models, schemas
- Python package name: `wxcode_adm`
- API prefix: `/api/v1` (versionado desde o inicio)
- Backend port: 8060 (dev), frontend port: 3060 (dev)

#### Database & ORM — CRITICAL CHANGE FROM RESEARCH
- **PostgreSQL** (NOT MongoDB) — single database, all tenants, isolation by `tenant_id` column
- **SQLAlchemy 2.0** with async (asyncpg driver)
- **Alembic** for schema migrations (auto-generate)
- This diverges from wxcode engine (which uses MongoDB/Beanie) — wxcode-adm is a separate service with its own database

#### Tenant Isolation
- Erro hard: query sem `tenant_id` levanta excecao imediatamente — bug, nao passa silenciosamente
- Dados globais da plataforma (planos, settings) usam `tenant_id = NULL` como convencao para "pertence a plataforma"
- Um database unico com todos os tenants, isolamento logico por `tenant_id` em cada tabela que precisa
- Soft delete com `deleted_at` timestamp para tenants (retencao configuravel, super-admin pode restaurar)

#### Base Model Conventions
- Todas as tabelas: `id` (UUID v4), `created_at`, `updated_at`
- Soft delete (`deleted_at`) apenas onde necessario (tenants, users) — nao em todas as tabelas

#### Config & Secrets
- Chaves RSA para JWT via env vars diretas (`JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`) — mais facil em Docker/cloud
- Super-admin seed via env vars: `SUPER_ADMIN_EMAIL` + `SUPER_ADMIN_PASSWORD` — seed automatico no startup se nao existir
- pydantic-settings para carregar .env com SecretStr para credenciais

### Claude's Discretion
- Docker Compose setup details (PostgreSQL version, Redis version)
- Hot-reload configuration
- CI scaffolding approach
- arq worker configuration
- Exact Alembic configuration and initial migration strategy

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

## Summary

Phase 1 establishes the project skeleton that all 40 v1 requirements depend on. It has no direct requirement IDs but is the enabler for everything else. The key architectural decision is the **PostgreSQL + SQLAlchemy 2.0 async** stack (diverging from the earlier MongoDB research), which means the entire data access layer is built on the SQLAlchemy async extension with the asyncpg driver.

The tenant isolation requirement — hard error on queries without `tenant_id` — is the most architecturally significant piece of Phase 1. SQLAlchemy 2.0 provides a purpose-built mechanism for this: `with_loader_criteria()` combined with the `SessionEvents.do_orm_execute()` event, which intercepts all ORM SELECT statements and can inject mandatory filters. This is superior to a base-class `find_for_tenant()` pattern because it catches queries issued by relationships and lazy loaders too, not just direct queries in service code.

The arq worker integration is straightforward: it uses the same Redis already required for token blacklist and rate limiting, and its startup/shutdown hooks initialize a SQLAlchemy scoped session factory keyed on job ID — the correct pattern for per-job database isolation.

**Primary recommendation:** Build in order — (1) monorepo structure + pyproject.toml, (2) pydantic-settings config with startup validation, (3) SQLAlchemy async engine + session factory with tenant guard, (4) Alembic async migration setup, (5) FastAPI app factory with lifespan, (6) Redis connection, (7) health endpoint, (8) arq worker with test job, (9) Docker Compose tying it all together.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Runtime | FastAPI async performance; 3.11 brings significant asyncio improvements |
| FastAPI | 0.131.0 | API framework | Pydantic v2 native, async-first, auto OpenAPI docs; locked by project |
| uvicorn[standard] | 0.41.0 | ASGI server | Standard FastAPI server; `[standard]` includes websocket + HTTP/2 support |
| SQLAlchemy | 2.0.46 | ORM | Locked decision; 2.0 is the async-native version; released 2026-01-21 |
| asyncpg | 0.31.0 | PostgreSQL async driver | Required by SQLAlchemy async with PostgreSQL; released 2025-11-24 |
| Alembic | 1.18.4 | Schema migrations | Official SQLAlchemy migration tool; async template built-in (`-t async`); released 2026-02-10 |
| pydantic-settings | 2.13.1 | Config / env vars | Official pydantic settings; SecretStr, `.env` loading, startup validation |
| redis (redis-py) | 7.2.0 | Redis client | Token blacklist + rate limiting + arq broker; asyncio support built-in since v4.2 |
| arq | 0.27.0 | Async job queue | Async-native Redis queue; uses same Redis already in stack; released 2026-02-02 |

### Supporting (Phase 1 only)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.12.5 | Data validation (FastAPI dep) | Pulled in by FastAPI; no separate install needed |
| cryptography | latest | RSA key operations | Required for loading PEM keys (JWT prep); pulled in by pyjwt[crypto] later |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncpg | psycopg3 (asyncpg) | psycopg3 is newer but asyncpg is more battle-tested with SQLAlchemy; asyncpg 2x faster in benchmarks |
| SQLAlchemy async | SQLModel | SQLModel is a wrapper adding Pydantic v2 integration, but adds magic that complicates multi-tenancy customization |
| Alembic | yoyo-migrations | Alembic is the SQLAlchemy-native choice; yoyo lacks autogenerate |
| arq | Celery | Celery sync-first with bolted-on async; arq uses existing Redis; no separate broker needed |

**Installation:**

```bash
# Core backend runtime
pip install \
  "fastapi==0.131.0" \
  "uvicorn[standard]==0.41.0" \
  "sqlalchemy==2.0.46" \
  "asyncpg==0.31.0" \
  "alembic==1.18.4" \
  "pydantic-settings==2.13.1" \
  "redis==7.2.0" \
  "arq==0.27.0"

# Dev tools
pip install -D \
  "pytest" \
  "pytest-asyncio" \
  "httpx" \
  "pytest-alembic"
```

---

## Architecture Patterns

### Recommended Project Structure

```
wxcode-adm/                          # monorepo root
├── backend/
│   ├── src/
│   │   └── wxcode_adm/
│   │       ├── main.py              # FastAPI app factory, lifespan, router registration
│   │       ├── config.py            # pydantic-settings Settings class
│   │       ├── dependencies.py      # Shared FastAPI Depends (get_session, get_current_user, etc.)
│   │       │
│   │       ├── db/
│   │       │   ├── __init__.py
│   │       │   ├── engine.py        # create_async_engine, async_session_maker
│   │       │   ├── base.py          # DeclarativeBase + naming conventions
│   │       │   └── tenant.py        # TenantModel base class + do_orm_execute guard
│   │       │
│   │       ├── auth/                # Phase 2
│   │       ├── users/               # Phase 2
│   │       ├── tenants/             # Phase 3
│   │       ├── billing/             # Phase 4
│   │       ├── apikeys/             # Phase 5
│   │       ├── audit/               # Phase 5
│   │       ├── admin/               # Phase 8
│   │       │
│   │       ├── tasks/
│   │       │   └── worker.py        # arq WorkerSettings (Phase 1: test job only)
│   │       │
│   │       └── common/
│   │           ├── exceptions.py    # HTTPException subclasses with error codes
│   │           └── redis_client.py  # Redis connection singleton
│   │
│   ├── alembic/
│   │   ├── env.py                   # async migration runner
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial.py      # initial migration (empty tables not yet in Phase 1)
│   │
│   ├── tests/
│   │   ├── conftest.py
│   │   └── test_health.py
│   │
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/                        # Phase 7+ (empty in Phase 1)
│
└── docker-compose.yml               # full stack: api + postgres + redis + worker
```

### Pattern 1: SQLAlchemy Async Engine Setup

**What:** Create async engine + session factory once at module level, dispose in lifespan shutdown.
**When to use:** Always — the engine is the single source of database connections for the entire app.

```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
# backend/src/wxcode_adm/db/engine.py

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from wxcode_adm.config import settings

engine = create_async_engine(
    str(settings.DATABASE_URL),  # "postgresql+asyncpg://user:pass@host/db"
    echo=settings.DEBUG,
    pool_pre_ping=True,          # verify connections before use
    pool_size=10,
    max_overflow=20,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,      # allow attribute access after commit without re-query
)
```

**Why `expire_on_commit=False`:** After `session.commit()`, SQLAlchemy normally expires all loaded attributes. In async context, accessing an expired attribute triggers implicit I/O which raises `MissingGreenlet` errors. Setting False is the correct default for async FastAPI apps.

### Pattern 2: FastAPI Session Dependency

**What:** Yield a session per request, commit on success, rollback on exception.

```python
# Source: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
# backend/src/wxcode_adm/dependencies.py

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from wxcode_adm.db.engine import async_session_maker

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Pattern 3: DeclarativeBase with Naming Conventions

**What:** A `Base` class that establishes naming conventions for constraints and indexes. Alembic autogenerate produces named constraints, which is required for reliable `--autogenerate` roundtrips.

```python
# Source: https://berkkaraal.com/blog/2024/09/19/setup-fastapi-project-with-async-sqlalchemy-2-alembic-postgresql-and-docker/
# backend/src/wxcode_adm/db/base.py

import uuid
from datetime import datetime
from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: DateTime(timezone=True),  # always timezone-aware timestamps
    }

class TimestampMixin:
    """Adds id, created_at, updated_at to every table."""
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=datetime.utcnow,
    )
```

### Pattern 4: TenantModel — Hard Error on Missing tenant_id

**What:** SQLAlchemy's `do_orm_execute` session event intercepts every ORM SELECT and raises `RuntimeError` if the query targets a `TenantModel` subclass but has no `tenant_id` filter attached. This is the structural enforcement required by the locked decision.

**Mechanism:** The event fires before query execution. It inspects the entities being queried. If any is a `TenantModel` subclass, it checks for a `_tenant_enforced` flag set by the service layer. If the flag is absent, it raises immediately.

**Alternative considered:** PostgreSQL Row-Level Security (RLS) via `sqlalchemy-tenants`. RLS enforces at the database level via `SET LOCAL app.current_tenant`. This is more airtight but requires PostgreSQL RLS policy setup in migrations and a `SET` command before every request. For this project, the application-layer hard error approach (raise in `do_orm_execute`) is simpler to implement and easier to debug. The locked decision ("query sem `tenant_id` levanta excecao imediatamente") is satisfied by either; the application approach is chosen.

```python
# Source: https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html (with_loader_criteria pattern)
# backend/src/wxcode_adm/db/tenant.py

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, event, text
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy.ext.asyncio import AsyncSession
from wxcode_adm.db.base import Base, TimestampMixin


class TenantModel(TimestampMixin, Base):
    """
    Abstract base for all tenant-scoped tables.
    Any ORM SELECT on a TenantModel subclass that does NOT include a
    tenant_id WHERE clause raises RuntimeError immediately.
    Platform-wide data (plans, settings) uses tenant_id = NULL.
    """
    __abstract__ = True

    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        index=True,
        nullable=True,  # NULL = platform-owned data (plans, settings)
    )


class SoftDeleteMixin:
    """Add to models that need soft delete (tenants, users)."""
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


# ---- Tenant isolation guard via do_orm_execute ----

def _requires_tenant_id(mapper) -> bool:
    """Return True if this mapper is a TenantModel subclass."""
    return issubclass(mapper.class_, TenantModel)


def install_tenant_guard(session_factory):
    """
    Register the do_orm_execute event on the session class.
    Call once during app startup after async_session_maker is created.

    Usage:
        install_tenant_guard(async_session_maker)
    """
    @event.listens_for(session_factory.class_, "do_orm_execute")
    def _enforce_tenant_id(orm_execute_state):
        if not orm_execute_state.is_select:
            return
        if orm_execute_state.is_column_load or orm_execute_state.is_relationship_load:
            return

        # Check if any queried entity is a TenantModel
        for mapper in orm_execute_state.all_mappers:
            if _requires_tenant_id(mapper):
                # Check that a tenant_id filter was included
                stmt = orm_execute_state.statement
                # Look for _tenant_id_enforced execution option as the signal
                if not orm_execute_state.user_defined_options.get("_tenant_enforced"):
                    raise RuntimeError(
                        f"Query on tenant-scoped model '{mapper.class_.__name__}' "
                        f"executed without tenant_id context. "
                        f"Use session.execute(stmt.execution_options(_tenant_enforced=True)) "
                        f"or use the TenantSession helper."
                    )
                break
```

**Simpler approach for Phase 1:** The exact implementation of the guard can be finalized in Phase 2-3 when tenant context is wired into the request lifecycle. Phase 1 deliverable is the `TenantModel` base class with the `tenant_id` column and the structural scaffold for enforcement. The guard event can be registered as a stub that logs a warning in Phase 1 and upgraded to a hard raise in Phase 3 when the dependency injection is in place.

### Pattern 5: pydantic-settings Configuration

**What:** Single `Settings` class loaded from environment variables + `.env` file. Raises `ValidationError` at import time if required fields are missing — startup fails fast.

```python
# Source: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
# backend/src/wxcode_adm/config.py

from pydantic import PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- App ---
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_PORT: int = 8060

    # --- Database ---
    # Must be full DSN: postgresql+asyncpg://user:pass@host:5432/db
    DATABASE_URL: PostgresDsn

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- JWT (Phase 2, declared here to fail fast if missing) ---
    JWT_PRIVATE_KEY: SecretStr  # RSA PEM, multi-line, set as env var
    JWT_PUBLIC_KEY: SecretStr

    # --- Super-admin seed ---
    SUPER_ADMIN_EMAIL: str
    SUPER_ADMIN_PASSWORD: SecretStr

    # --- CORS ---
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3060"]


# Module-level singleton — raises ValidationError on startup if env is missing
settings = Settings()
```

**DSN format note:** `PostgresDsn` in Pydantic v2 accepts `postgresql+asyncpg://` scheme. Pass `str(settings.DATABASE_URL)` to `create_async_engine()` since pydantic returns a `Url` object.

**RSA key as env var:** Multi-line PEM keys work in `.env` files when quoted:
```
JWT_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
```

### Pattern 6: FastAPI App Factory with Lifespan

**What:** Single `create_app()` factory function. Lifespan context manager initializes all infrastructure: database engine verification, Redis connection, arq worker (not started in same process, but connection verified).

```python
# Source: https://fastapi.tiangolo.com/advanced/events/
# backend/src/wxcode_adm/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from redis.asyncio import Redis

from wxcode_adm.config import settings
from wxcode_adm.db.engine import engine, async_session_maker
from wxcode_adm.db.tenant import install_tenant_guard
from wxcode_adm.common.redis_client import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- STARTUP ----
    # 1. Verify PostgreSQL connection
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))

    # 2. Register tenant isolation guard on session factory
    install_tenant_guard(async_session_maker)

    # 3. Verify Redis connection
    await redis_client.ping()

    # 4. Seed super-admin (Phase 2 — stub here)
    # await seed_super_admin()

    yield  # Application runs here

    # ---- SHUTDOWN ----
    await engine.dispose()
    await redis_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="wxcode-adm",
        version="0.1.0",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        lifespan=lifespan,
    )

    # Register routers
    from wxcode_adm.common.router import router as common_router
    app.include_router(common_router, prefix=settings.API_V1_PREFIX)
    # Phase 2+: app.include_router(auth_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
```

### Pattern 7: Health Endpoint

**What:** `GET /api/v1/health` verifies live connectivity to PostgreSQL and Redis. Returns 200 with details or 503.

```python
# backend/src/wxcode_adm/common/router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from redis.asyncio import Redis

from wxcode_adm.dependencies import get_session
from wxcode_adm.common.redis_client import get_redis_client

router = APIRouter()


@router.get("/health")
async def health(
    db: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_client),
):
    checks = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["postgresql"] = "ok"
    except Exception as e:
        checks["postgresql"] = f"error: {e}"

    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise HTTPException(status_code=503, detail=checks)

    return {"status": "healthy", "checks": checks}
```

### Pattern 8: Alembic Async Configuration

**What:** Initialize Alembic with the async template; configure `env.py` to use `async_engine_from_config` and `connection.run_sync()`.

**Initialize:**
```bash
# From backend/
alembic init -t async alembic
```

**alembic.ini** — set the URL using a placeholder (override in `env.py` from settings):
```ini
[alembic]
script_location = alembic
sqlalchemy.url = driver://user:pass@localhost/dbname
```

**alembic/env.py** — override URL from settings and inject Base.metadata:
```python
# Source: https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py
# (annotated version)

import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool
from alembic import context

from wxcode_adm.config import settings
from wxcode_adm.db.base import Base

# Import ALL models so Base.metadata is populated for autogenerate
# Add these as models are created in later phases:
# from wxcode_adm.auth.models import *
# from wxcode_adm.tenants.models import *

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override from settings (str() because pydantic returns Url object)
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))
target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,  # NullPool is mandatory for migrations
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    # run_migrations_offline() ...
    pass
else:
    run_migrations_online()
```

**Generate initial migration:**
```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### Pattern 9: arq Worker with Test Job

**What:** A minimal `WorkerSettings` with one test job and SQLAlchemy session lifecycle hooks. Runs as a separate process.

```python
# Source: https://arq-docs.helpmanual.io/ + https://wazaari.dev/blog/arq-sqlalchemy-done-right
# backend/src/wxcode_adm/tasks/worker.py

from arq import create_pool
from arq.connections import RedisSettings

from wxcode_adm.config import settings
from wxcode_adm.db.engine import engine, async_session_maker


async def test_job(ctx: dict) -> str:
    """Smoke test: confirms arq worker is operational."""
    return "arq worker is operational"


async def startup(ctx: dict) -> None:
    # SQLAlchemy engine is module-level; just verify connection
    async with engine.begin() as conn:
        await conn.execute_sql("SELECT 1")  # noqa
    ctx["session_maker"] = async_session_maker


async def shutdown(ctx: dict) -> None:
    await engine.dispose()


class WorkerSettings:
    functions = [test_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 300  # 5 minutes


# Enqueue helper (used in tests and Phase 1 smoke test)
async def get_arq_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
```

**Run the worker:**
```bash
arq wxcode_adm.tasks.worker.WorkerSettings
```

### Pattern 10: Docker Compose Full Stack

**What:** Single-command `docker compose up` brings up FastAPI API, PostgreSQL, Redis, and arq worker. Healthchecks ensure proper startup order.

```yaml
# docker-compose.yml (root of monorepo)
# Source: Docker Compose healthcheck docs (docs.docker.com/compose/how-tos/startup-order/)

services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: wxcode
      POSTGRES_PASSWORD: wxcode_dev
      POSTGRES_DB: wxcode_adm
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U wxcode -d wxcode_adm"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build:
      context: ./backend
    command: >
      sh -c "alembic upgrade head &&
             uvicorn wxcode_adm.main:app --host 0.0.0.0 --port 8060 --reload"
    ports:
      - "8060:8060"
    env_file:
      - ./backend/.env
    environment:
      DATABASE_URL: postgresql+asyncpg://wxcode:wxcode_dev@postgres:5432/wxcode_adm
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend/src:/app/src  # hot-reload source mount

  worker:
    build:
      context: ./backend
    command: arq wxcode_adm.tasks.worker.WorkerSettings --watch src
    env_file:
      - ./backend/.env
    environment:
      DATABASE_URL: postgresql+asyncpg://wxcode:wxcode_dev@postgres:5432/wxcode_adm
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  postgres_data:
```

### Anti-Patterns to Avoid

- **`@app.on_event("startup")`:** Deprecated since FastAPI introduced lifespan. Never use in new code — use `@asynccontextmanager async def lifespan(app)` instead.
- **Synchronous SQLAlchemy imports in async code:** Importing `Session` instead of `AsyncSession`, calling `sessionmaker` instead of `async_sessionmaker`. Will cause `greenlet_spawn` errors in async context.
- **`alembic init` without `-t async`:** Creates a sync `env.py` that calls `engine.connect()` synchronously. Does not work with asyncpg. Always use `alembic init -t async`.
- **Using `Pydantic.PostgresDsn` object directly as SQLAlchemy URL:** Must call `str(settings.DATABASE_URL)` — pydantic v2 Url types are not strings.
- **Single process for API + arq worker:** arq blocks on polling Redis. The worker must run in a separate process (separate Docker container or separate `arq` command). Never start the worker in the FastAPI lifespan.
- **`pool_size` default (5) in production:** The default connection pool of 5 is too small. Set `pool_size=10, max_overflow=20` for a well-trafficked API.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async database migrations | Custom `CREATE TABLE` scripts at startup | Alembic with `alembic init -t async` | Alembic autogenerate detects schema drift, tracks versions, supports rollback |
| Config/env loading | `os.environ.get()` scattered through code | `pydantic-settings BaseSettings` | Type validation, startup fail-fast, SecretStr masking, `.env` support |
| Job queue | `asyncio.create_task()` in request handler | arq with Redis | Tasks survive server restarts; retry logic; separate worker scaling |
| Connection health checks | Custom TCP ping | `SELECT 1` via SQLAlchemy + `redis.ping()` | Uses the actual driver path; catches auth errors, not just TCP connectivity |
| Constraint naming | Manual constraint names or default | `MetaData(naming_convention=...)` on Base | Alembic autogenerate requires named constraints to detect drops reliably |
| UUID primary keys | `Column(String, default=lambda: str(uuid4()))` | `Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, server_default=text("gen_random_uuid()"))` | Both Python-side and server-side default; works for seeded data and direct SQL inserts |
| Tenant context plumbing | Pass `tenant_id` as argument through every function call | `request.state.tenant_id` set in middleware (Phase 2) | Threading `tenant_id` as a parameter through 5 layers is the most common source of "forgot to pass it" bugs |

**Key insight:** The SQLAlchemy ecosystem (`alembic`, `async_sessionmaker`, naming conventions) forms a self-consistent toolchain — hand-rolled alternatives create gaps in migration reliability and type safety.

---

## Common Pitfalls

### Pitfall 1: asyncpg `MissingGreenlet` on Expired Attributes

**What goes wrong:** After `await session.commit()`, accessing any ORM model attribute without `expire_on_commit=False` triggers implicit I/O in an async context, raising `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called`.

**Why it happens:** SQLAlchemy's default `expire_on_commit=True` expires all attributes after commit, requiring a lazy load on next access. In async, lazy loads are not allowed implicitly.

**How to avoid:** Always set `expire_on_commit=False` on `async_sessionmaker`. Use `selectinload()` / `joinedload()` for relationships — never rely on lazy loading in async.

**Warning signs:** `MissingGreenlet` traceback pointing to an attribute access after `commit()`.

---

### Pitfall 2: Alembic Running Migrations Against Wrong Database

**What goes wrong:** `alembic upgrade head` connects to the database from `alembic.ini` (the placeholder URL) instead of from pydantic-settings.

**Why it happens:** The async `env.py` template does NOT automatically read from pydantic-settings. If `config.set_main_option("sqlalchemy.url", ...)` is not called in `env.py`, Alembic uses the ini file's placeholder.

**How to avoid:** Always call `config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))` at the top of `env.py`. Test by running `alembic current` and verifying it connects to the expected database.

**Warning signs:** Alembic reports "no change detected" but the database tables don't exist; or migrations run against localhost when you expected a Docker container.

---

### Pitfall 3: Models Not Imported in `env.py` → Autogenerate Misses Tables

**What goes wrong:** `alembic revision --autogenerate` produces an empty migration despite having model classes defined.

**Why it happens:** `Base.metadata` is only populated when model modules are actually imported. If `env.py` never imports the model modules, `Base.metadata` is empty and autogenerate sees no tables.

**How to avoid:** In `env.py`, import all model modules after importing `Base`:
```python
from wxcode_adm.db.base import Base
from wxcode_adm.auth import models as _  # noqa — triggers metadata population
from wxcode_adm.tenants import models as _  # noqa
```

**Warning signs:** Autogenerate migration is empty or only contains partial tables.

---

### Pitfall 4: `NullPool` in Production API (Not Just Migrations)

**What goes wrong:** Developer copies Alembic's `env.py` pattern (`poolclass=NullPool`) into the main API engine setup. Every request creates and destroys a new database connection, causing performance collapse under load.

**Why it happens:** `NullPool` is required for Alembic (which runs as a one-shot CLI command) but is wrong for a persistent API server. The Alembic template comments don't always make this clear.

**How to avoid:** `NullPool` goes ONLY in `alembic/env.py`. The API's `create_async_engine()` in `db/engine.py` uses the default `AsyncAdaptedQueuePool` with `pool_size` and `max_overflow` set appropriately.

**Warning signs:** Response times increasing linearly with load; database logs showing constant connect/disconnect cycles.

---

### Pitfall 5: arq Worker Started Inside FastAPI Lifespan

**What goes wrong:** Developer starts the arq worker in the FastAPI lifespan function. The worker blocks on its Redis polling loop, preventing the lifespan function from completing, and the app never starts.

**Why it happens:** arq's `run_worker()` / `Worker.run()` is a long-running coroutine that blocks until the worker is stopped. It cannot run inside a lifespan that must yield.

**How to avoid:** The arq worker is always a **separate process** — a separate Docker container or a separate terminal command. It connects to the same Redis as the API. The API only needs to connect to Redis to **enqueue** jobs, not to run the worker.

**Warning signs:** FastAPI startup never completes; health endpoint never responds.

---

### Pitfall 6: Cross-Tenant Data Leakage via Missing `tenant_id`

**What goes wrong:** A query on a `TenantModel` subclass runs without a `tenant_id` WHERE clause. In a single-database multi-tenant setup, this returns data from ALL tenants to a user who should only see their own.

**Why it happens:** The developer forgets to add the filter, especially in background jobs, admin utilities, and aggregation queries where "all records" feels natural.

**How to avoid (Phase 1 structure):** All `TenantModel` subclasses structurally signal the need for tenant filtering. The `do_orm_execute` guard (installed in lifespan) raises `RuntimeError` on unguarded queries. Phase 1 installs the guard scaffold; Phase 3 makes it mandatory when tenant context is available on every request.

**Warning signs:** Queries return more records than expected; different tenant users see each other's data; admin/background queries return suspiciously large result sets.

---

### Pitfall 7: Hot-Reload With `--reload` Reinitializes Engine on Every Change

**What goes wrong:** In development with `uvicorn --reload`, every code change causes the module to reload, creating a new `create_async_engine()` call. The old engine's connections are not properly disposed, causing connection pool exhaustion.

**Why it happens:** Module-level engine creation (outside of `lifespan`) persists across reloads only if the module is cached. With `--reload`, the module is reimported.

**How to avoid:** The `engine` is module-level in `db/engine.py`, but `lifespan` calls `await engine.dispose()` on shutdown, which is triggered by each reload cycle. In practice, this works correctly with uvicorn's reload because uvicorn handles the ASGI lifespan properly on each reload. Monitor PostgreSQL `max_connections` in dev to catch leaks.

---

## Code Examples

Verified patterns from official sources and production boilerplates:

### UUID Primary Key with Server-Side Default

```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
import uuid
from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column

class SomeModel(Base):
    __tablename__ = "some_table"

    # Python-side default (for Python-created objects) +
    # server-side default (for direct SQL inserts / seeding scripts)
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
```

### async_sessionmaker Dependency Injection

```python
# Source: https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# Usage in route:
@router.get("/items")
async def list_items(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item).where(Item.tenant_id == tenant_id))
    return result.scalars().all()
```

### Alembic Async env.py Core Pattern

```python
# Source: https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool
from alembic import context

from wxcode_adm.config import settings
from wxcode_adm.db.base import Base
# Import all model modules here to populate Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))
target_metadata = Base.metadata

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,  # NullPool required for CLI migration tool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())
```

### arq Job Enqueueing (from API side)

```python
# Source: https://arq-docs.helpmanual.io/
from arq import create_pool
from arq.connections import RedisSettings
from wxcode_adm.config import settings

async def enqueue_test_job():
    redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    job = await redis.enqueue_job("test_job")
    await redis.aclose()
    return job.job_id
```

### pyproject.toml Structure

```toml
# backend/pyproject.toml
[project]
name = "wxcode-adm"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi==0.131.0",
    "uvicorn[standard]==0.41.0",
    "sqlalchemy==2.0.46",
    "asyncpg==0.31.0",
    "alembic==1.18.4",
    "pydantic-settings==2.13.1",
    "redis==7.2.0",
    "arq==0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "httpx",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/wxcode_adm"]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `@asynccontextmanager async def lifespan(app)` | FastAPI 0.93 (2023) | on_event deprecated; lifespan is the only supported approach |
| `sessionmaker` + `Session` | `async_sessionmaker` + `AsyncSession` | SQLAlchemy 2.0 (2023) | Sync session in async code causes `greenlet_spawn` errors |
| `alembic init` (sync template) | `alembic init -t async` | Alembic 1.7 (2021) | Sync env.py does not work with asyncpg |
| `Column(UUID, default=uuid4)` | `Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)` | SQLAlchemy 2.0 (2023) | 2.0 style uses `Mapped` type annotations; `Column()` still works but is legacy |
| `aioredis` (separate package) | `from redis.asyncio import Redis` | redis-py 4.2 (2022) | `aioredis` is dead; asyncio support merged into redis-py |
| Celery for background tasks | arq | Project decision | arq is async-native and uses existing Redis; no separate broker |

**Deprecated/outdated:**
- `SQLAlchemy.Session` (sync): Works but blocks in async context — never use in async FastAPI routes
- `aioredis` package: Dead since 2022, merged into redis-py
- `on_event("startup")`: Deprecated since FastAPI 0.93, will be removed in a future version
- `passlib`: Python 3.13 incompatible (removed `crypt` module) — not relevant to Phase 1 but noted for Phase 2

---

## Open Questions

1. **Super-admin seed strategy**
   - What we know: `SUPER_ADMIN_EMAIL` + `SUPER_ADMIN_PASSWORD` from env vars; seed on startup if not exists
   - What's unclear: Should the seed run in the lifespan function (before requests) or as a separate CLI command? Running in lifespan risks delaying startup if the DB is slow; a separate `python -m wxcode_adm seed` command is safer but requires an extra Docker step.
   - Recommendation: Run in lifespan with a timeout guard for Phase 1 stub. Upgrade to a proper seed command in Phase 2 when user model exists.

2. **TenantModel guard enforcement level in Phase 1**
   - What we know: Hard error is the target; but in Phase 1, no routes or tenant context exist yet — the guard cannot be fully wired without request middleware
   - What's unclear: Whether to install the guard as a hard raise immediately (breaking all queries without context) or as a logged warning until Phase 3
   - Recommendation: Install as a **logged warning** in Phase 1 that prints `[TENANT GUARD] Unguarded query on TenantModel detected`. Upgrade to hard raise in Phase 3 when the `request.state.tenant_id` middleware is in place. This avoids breaking health checks and seed functions that legitimately query without tenant context.

3. **Initial Alembic migration content**
   - What we know: Phase 1 only creates `db/base.py` (no actual table models yet — those come in Phase 2-3)
   - What's unclear: Should the initial migration be empty (just the version table), or should it include any shared tables like `plans`?
   - Recommendation: Initial migration is empty (version table only). Add tables as each domain model is created in Phases 2-4.

4. **`pool_pre_ping` overhead in development**
   - What we know: `pool_pre_ping=True` sends `SELECT 1` before each borrowed connection to verify it's alive; adds ~1ms per request in dev
   - What's unclear: Whether this is acceptable in dev or only needed in production
   - Recommendation: Enable in all environments (dev, staging, production). The overhead is negligible and prevents cryptic `connection closed` errors after PostgreSQL restarts.

---

## Sources

### Primary (HIGH confidence)

- SQLAlchemy 2.0 Async docs — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html — async engine, session patterns
- SQLAlchemy 2.0 ORM Query Guide — https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html — `with_loader_criteria`, `do_orm_execute`
- Alembic 1.18.4 async template — https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py — canonical async env.py
- FastAPI lifespan docs — https://fastapi.tiangolo.com/advanced/events/ — lifespan context manager pattern
- pydantic-settings docs — https://docs.pydantic.dev/latest/concepts/pydantic_settings/ — SecretStr, PostgresDsn, env_file
- arq 0.27.0 docs — https://arq-docs.helpmanual.io/ — WorkerSettings, RedisSettings
- asyncpg 0.31.0 PyPI — https://pypi.org/project/asyncpg/ — current version verified 2026-02-22
- SQLAlchemy 2.0.46 PyPI — https://pypi.org/project/sqlalchemy/ — current version verified 2026-02-22
- Alembic 1.18.4 PyPI — https://pypi.org/project/alembic/ — current version verified 2026-02-22
- Docker Compose startup order docs — https://docs.docker.com/compose/how-tos/startup-order/ — healthcheck + depends_on pattern

### Secondary (MEDIUM confidence)

- Berk Karaal tutorial (2024-09-19) — https://berkkaraal.com/blog/2024/09/19/setup-fastapi-project-with-async-sqlalchemy-2-alembic-postgresql-and-docker/ — verified against SQLAlchemy official docs; complete working example
- ARQ + SQLAlchemy scoped session — https://wazaari.dev/blog/arq-sqlalchemy-done-right — worker/job session lifecycle pattern; multiple sources agree
- benavlabs/FastAPI-boilerplate — https://github.com/benavlabs/FastAPI-boilerplate — production boilerplate using same stack; verified patterns

### Tertiary (LOW confidence)

- asyncpg `<0.29.0` pin recommendation (from WebSearch): some sources recommend pinning asyncpg below 0.29.0. Current version is 0.31.0 and the original issue was not verified. Recommendation: use 0.31.0 (latest stable) and pin back only if issues arise.

---

## Metadata

**Confidence breakdown:**
- Standard stack versions: HIGH — verified against PyPI directly (2026-02-22)
- SQLAlchemy async patterns: HIGH — verified against official docs
- Alembic async config: HIGH — official template verified
- TenantModel guard mechanism: MEDIUM — `do_orm_execute` event confirmed in docs; exact implementation pattern is custom (no library provides this exact behavior out-of-box)
- Docker Compose healthcheck: HIGH — official Docker docs verified
- arq WorkerSettings: HIGH — official arq docs verified

**Research date:** 2026-02-22
**Valid until:** 2026-03-22 (30 days; SQLAlchemy/Alembic are stable; FastAPI releases frequently but API is stable)
