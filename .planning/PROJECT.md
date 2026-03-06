# WXCODE ADM

## What This Is

Camada SaaS do WXCODE — o porteiro da plataforma. Backend API (FastAPI) + Frontend UI (Next.js) completos. Gerencia autenticacao, identidade, multi-tenancy, billing e administracao da plataforma. O usuario faz sign-up/sign-in no wxcode-adm, recebe um JWT auto-contido, e e redirecionado para o wxcode (app principal). O wxcode-adm reaparece quando o usuario acessa "My Account" ou "Settings" dentro do wxcode. Inclui portal super-admin com dashboard MRR, audit log, e gestao de tenants/usuarios.

## Core Value

Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.

## Requirements

### Validated

<!-- Shipped in v1.0 — backend API -->

- ✓ Sign-up com email + senha — v1.0
- ✓ Sign-in com email + senha, retornando JWT auto-contido — v1.0
- ✓ OAuth 2.0 (Google, GitHub) — v1.0
- ✓ MFA via TOTP (Google Authenticator, Authy) — v1.0
- ✓ Recuperacao de senha via email — v1.0
- ✓ Verificacao de email para novas contas — v1.0
- ✓ Multi-tenancy com isolamento logico por tenant_id — v1.0
- ✓ Convite de usuarios por tenant — v1.0
- ✓ RBAC por tenant (Owner, Admin, Developer, Viewer) — v1.0
- ✓ CRUD de planos de cobranca mensal (super-admin) — v1.0
- ✓ Integracao Stripe (checkout, billing, customer portal, webhooks) — v1.0
- ✓ Super-admin: gestao de tenants (ver, suspender, deletar) — v1.0
- ✓ Super-admin: gestao de usuarios (ver, bloquear, resetar senha) — v1.0
- ✓ Super-admin: dashboard MRR — v1.0
- ✓ Audit log de acoes sensiveis — v1.0
- ✓ Rate limiting por IP e por usuario — v1.0
- ✓ Redirecionamento para wxcode com access token apos login — v1.0

<!-- Shipped in v2.0 — frontend UI -->

- ✓ Design system Obsidian Studio (tema visual compartilhado com wxcode) — v2.0
- ✓ UI de auth: login, signup, verificacao de email, reset de senha — v2.0
- ✓ UI de MFA: verificacao TOTP, backup codes, trusted device — v2.0
- ✓ UI de onboarding: criacao de workspace apos primeiro login — v2.0
- ✓ UI de perfil: edicao de nome, avatar, troca de senha — v2.0
- ✓ UI de sessoes: lista de sessoes ativas, revogacao — v2.0
- ✓ UI de tenant: convites, gestao de membros, roles, MFA enforcement — v2.0
- ✓ UI de billing: plano atual, checkout Stripe, portal do cliente — v2.0
- ✓ UI super-admin: login isolado, lista de tenants, suspensao/reativacao — v2.0
- ✓ UI super-admin: busca de usuarios, block/unblock — v2.0
- ✓ UI super-admin: dashboard MRR com graficos Recharts — v2.0
- ✓ UI super-admin: audit log viewer, tenant detail, force password reset — v2.0

### Active

<!-- Next milestone — pending definition -->

- [ ] API keys per tenant com escopos granulares (read, write, admin, billing) — PLAT-01 (carry-over v1.0)
- [ ] Revogacao e rotacao de API keys — PLAT-02 (carry-over v1.0)
- [ ] UI de MFA enrollment (QR code + backup codes display) — AUI-08 (deferred v2.1)
- [ ] UI de OAuth login buttons (Google/GitHub) — AUI-09 (deferred v2.1)

### Out of Scope

- Executar operacoes do wxcode engine (import, conversao, parsing) — wxcode-adm nao faz isso
- Terminal interativo — pertence ao wxcode
- Geracao de diagramas, analise de dependencias — pertence ao wxcode
- Planos definidos por tenant (marketplace/whitelabel) — apenas super-admin gerencia planos
- Usuario pertencer a multiplos tenants simultaneamente — isolamento estrito
- Offline mode — plataforma SaaS online-only

## Context

- **WXCODE** e um conversor universal de projetos WinDev/WebDev para stacks modernas
- O wxcode-adm e o gate de acesso: sign-up/sign-in/recovery -> wxcode -> wxcode-adm (account/billing)
- O wxcode valida JWT localmente via chave publica compartilhada (sem introspection)
- Cada servico tera seu proprio dominio (subdomains): auth.wxcode.io (adm), app.wxcode.io (wxcode)
- Frontend do wxcode-adm (Next.js 16, port 3040) e separado do frontend do wxcode (port 3052) e do backend (port 8040)
- Super-admin da plataforma (Gilberto) gerencia planos, tenants, usuarios, metricas e configuracoes
- Tenants podem convidar usuarios, que ficam vinculados exclusivamente ao tenant que convidou
- **Shipped:** Backend API (v1.0, 19,837 LOC Python, 148 tests) + Frontend UI (v2.0, 9,174 LOC TypeScript/React)
- **Tech stack:** FastAPI + SQLAlchemy 2.0 + PostgreSQL + Redis (backend) | Next.js 16 + React 19 + Tailwind v4 + shadcn/ui + TanStack Query (frontend)
- **Migrations:** Alembic chain `None → 001 → ... → 007` (7 migrations)

## Constraints

- **Backend**: Python 3.11+ / FastAPI / SQLAlchemy 2.0 / PostgreSQL
- **Frontend**: Next.js 16 / React 19 / Tailwind CSS v4 / shadcn/ui (new-york) / TypeScript
- **Auth**: JWT auto-contido (RS256 com par de chaves) para que wxcode valide sem chamar wxcode-adm
- **Payments**: Stripe (checkout, billing, customer portal, webhooks)
- **Cache/Sessions**: Redis para rate limiting, blacklist de tokens, sessoes
- **Deploy**: Docker/VPS (container Docker, mesma infra do wxcode)
- **Dominios**: Subdomains separados por servico (auth.wxcode.io, app.wxcode.io, api.wxcode.io)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| JWT auto-contido (RS256) | wxcode valida token localmente sem depender do wxcode-adm | ✓ Good — JWKS endpoint works, wxcode validates locally |
| App separada para UI do adm | Separacao clara de responsabilidades, deploy independente | ✓ Good — frontend/backend monorepo, independent deploy |
| Subdomains por servico | Facilita deploy independente, SSL por servico, separacao clara | — Pending (not yet deployed) |
| Super-admin gerencia planos (CRUD) | Planos nao sao hardcoded, flexibilidade para ajustar ofertas | ✓ Good — plan CRUD + Stripe sync working |
| Usuario isolado a um tenant | Simplicidade, sem complexidade de multi-tenant switching | ✓ Good — cross-tenant isolation test suite confirms zero leakage |
| PostgreSQL + SQLAlchemy (nao MongoDB) | wxcode-adm e SaaS admin com schema relacional; wxcode usa MongoDB por tenant | ✓ Good — relational schema fits SaaS admin perfectly |
| Monorepo backend + frontend | Um repo, deploy independente, backend em /backend, frontend em /frontend | ✓ Good — single repo, clear separation |
| Alembic para migrations | Schema versionado, auto-generate | ✓ Good — 7 linear migrations, no gaps |
| In-memory JWT tokens (frontend) | XSS-safe, tokens lost on reload (user re-logs), SPA redirects to wxcode after login | ✓ Good — acceptable for redirect-based flow |
| Obsidian Studio dark theme | Visual consistency with wxcode frontend | ✓ Good — ported from wxcode, 6 custom components |
| Admin JWT audience isolation | Admin tokens (aud=wxcode-adm-admin) separate from user tokens | ✓ Good — prevents regular users from accessing admin endpoints |
| Custom sidebar (not shadcn Sidebar) | shadcn Sidebar too complex for simple admin nav | ✓ Good — simpler, maintainable |

---
*Last updated: 2026-03-06 after v1.0 + v2.0 milestones completed*
