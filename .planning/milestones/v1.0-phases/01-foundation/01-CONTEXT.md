# Phase 1: Foundation - Context

**Gathered:** 2026-02-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Project scaffolding, infrastructure initialization (PostgreSQL, Redis, arq worker), and tenant isolation base class. Everything phases 2-8 build on top of. No auth, no billing, no business logic — just the skeleton and the rules it enforces.

</domain>

<decisions>
## Implementation Decisions

### Project Structure
- Monorepo: backend and frontend in the same git repo (`/backend` and `/frontend`)
- Backend organized **by domain**: `auth/`, `tenants/`, `billing/`, `users/`, etc. — each module contains its own router, service, models, schemas
- Python package name: `wxcode_adm`
- API prefix: `/api/v1` (versionado desde o inicio)
- Backend port: 8060 (dev), frontend port: 3060 (dev)

### Database & ORM — CRITICAL CHANGE FROM RESEARCH
- **PostgreSQL** (NOT MongoDB) — single database, all tenants, isolation by `tenant_id` column
- **SQLAlchemy 2.0** with async (asyncpg driver)
- **Alembic** for schema migrations (auto-generate)
- This diverges from wxcode engine (which uses MongoDB/Beanie) — wxcode-adm is a separate service with its own database

### Tenant Isolation
- Erro hard: query sem `tenant_id` levanta excecao imediatamente — bug, nao passa silenciosamente
- Dados globais da plataforma (planos, settings) usam `tenant_id = NULL` como convencao para "pertence a plataforma"
- Um database unico com todos os tenants, isolamento logico por `tenant_id` em cada tabela que precisa
- Soft delete com `deleted_at` timestamp para tenants (retencao configuravel, super-admin pode restaurar)

### Base Model Conventions
- Todas as tabelas: `id` (UUID v4), `created_at`, `updated_at`
- Soft delete (`deleted_at`) apenas onde necessario (tenants, users) — nao em todas as tabelas

### Config & Secrets
- Chaves RSA para JWT via env vars diretas (`JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`) — mais facil em Docker/cloud
- Super-admin seed via env vars: `SUPER_ADMIN_EMAIL` + `SUPER_ADMIN_PASSWORD` — seed automatico no startup se nao existir
- pydantic-settings para carregar .env com SecretStr para credenciais

### Claude's Discretion
- Docker Compose setup details (PostgreSQL version, Redis version)
- Hot-reload configuration
- CI scaffolding approach
- arq worker configuration
- Exact Alembic configuration and initial migration strategy

</decisions>

<specifics>
## Specific Ideas

- wxcode usa MongoDB com uma base por tenant; wxcode-adm usa PostgreSQL com uma base unica — sao servicos independentes com databases independentes
- O backend deve seguir patterns similares ao wxcode onde possivel (FastAPI, domain-based modules) mas com ORM diferente (SQLAlchemy vs Beanie)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-02-22*
