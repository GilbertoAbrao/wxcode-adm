# WXCODE ADM

## What This Is

Camada SaaS do WXCODE — o porteiro da plataforma. Gerencia autenticacao, identidade, multi-tenancy, billing e administracao da plataforma. O usuario faz sign-up/sign-in no wxcode-adm, recebe um JWT auto-contido, e e redirecionado para o wxcode (app principal). O wxcode-adm reaparece quando o usuario acessa "My Account" ou "Settings" dentro do wxcode.

## Core Value

Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.

## Current Milestone: v2.0 Frontend UI

**Goal:** Criar toda a interface web do wxcode-adm — auth flows, gestao de tenant, billing, user account e super-admin panel — usando a mesma identidade visual (Obsidian Studio) do wxcode frontend.

**Target features:**
- Auth flows: login, signup, email verification, password reset, OAuth, MFA setup/verify
- User account: profile editing, password change, session management
- Tenant management: workspace onboarding, member invites, role management, tenant settings
- Billing & plans: subscription view, plan selection, Stripe Checkout, Customer Portal
- Super-admin panel: tenant list, user management, MRR dashboard

## Requirements

### Validated

<!-- Shipped in v1.0 — backend API complete -->

- ✓ Sign-up com email + senha — v1.0 Phase 2
- ✓ Sign-in com email + senha, retornando JWT auto-contido — v1.0 Phase 2
- ✓ OAuth 2.0 (Google, GitHub) — v1.0 Phase 6
- ✓ MFA via TOTP (Google Authenticator, Authy) — v1.0 Phase 6
- ✓ Recuperacao de senha via email — v1.0 Phase 2
- ✓ Verificacao de email para novas contas — v1.0 Phase 2
- ✓ Multi-tenancy com isolamento logico por tenant_id — v1.0 Phase 3
- ✓ Convite de usuarios por tenant — v1.0 Phase 3
- ✓ RBAC por tenant (Owner, Admin, Developer, Viewer) — v1.0 Phase 3
- ✓ CRUD de planos de cobranca mensal (super-admin) — v1.0 Phase 4
- ✓ Integracao Stripe (checkout, billing, customer portal, webhooks) — v1.0 Phase 4
- ✓ Super-admin: gestao de tenants (ver, suspender, deletar) — v1.0 Phase 8
- ✓ Super-admin: gestao de usuarios (ver, bloquear, resetar senha) — v1.0 Phase 8
- ✓ Super-admin: dashboard MRR — v1.0 Phase 8
- ✓ Audit log de acoes sensiveis — v1.0 Phase 5
- ✓ Rate limiting por IP e por usuario — v1.0 Phase 5
- ✓ Redirecionamento para wxcode com access token apos login — v1.0 Phase 7/9

### Active

<!-- v2.0 — Frontend UI -->

- [ ] UI de auth: login, signup, verificacao de email, reset de senha
- [ ] UI de OAuth: botoes Google/GitHub, callback handling
- [ ] UI de MFA: setup QR code, verificacao TOTP, backup codes, trusted device
- [ ] UI de onboarding: criacao de workspace apos primeiro login
- [ ] UI de perfil: edicao de nome, email, avatar, troca de senha
- [ ] UI de sessoes: lista de sessoes ativas, revogacao
- [ ] UI de tenant: convites, gestao de membros, roles, settings
- [ ] UI de billing: plano atual, checkout Stripe, portal do cliente
- [ ] UI super-admin: lista de tenants, gestao, suspensao
- [ ] UI super-admin: busca de usuarios, block/unblock, force reset
- [ ] UI super-admin: dashboard MRR com graficos
- [ ] Design system: Obsidian Studio (mesmo tema visual do wxcode)

### Out of Scope

### Out of Scope

- Executar operacoes do wxcode engine (import, conversao, parsing) — wxcode-adm nao faz isso
- Terminal interativo — pertence ao wxcode
- Geracao de diagramas, analise de dependencias — pertence ao wxcode
- Planos definidos por tenant (marketplace/whitelabel) — apenas super-admin gerencia planos
- Usuario pertencer a multiplos tenants simultaneamente — isolamento estrito

## Context

- **WXCODE** e um conversor universal de projetos WinDev/WebDev para stacks modernas
- O wxcode-adm e o gate de acesso: sign-up/sign-in/recovery -> wxcode -> wxcode-adm (account/billing)
- O wxcode valida JWT localmente via chave publica compartilhada (sem introspection)
- Cada servico tera seu proprio dominio (subdomains): auth.wxcode.io (adm), app.wxcode.io (wxcode)
- Frontend do wxcode-adm e uma aplicacao separada do frontend do wxcode
- O wxcode engine roda em localhost:8052, frontend wxcode em localhost:3052
- Super-admin da plataforma (Gilberto) gerencia planos, tenants, usuarios, metricas e configuracoes
- Tenants podem convidar usuarios, que ficam vinculados exclusivamente ao tenant que convidou

## Constraints

- **Tech stack**: Python 3.11+ / FastAPI / SQLAlchemy 2.0 / PostgreSQL — database relacional para SaaS admin
- **Auth**: JWT auto-contido (RS256 com par de chaves) para que wxcode valide sem chamar wxcode-adm
- **Payments**: Stripe (checkout, billing, metered billing, customer portal, webhooks)
- **Cache/Sessions**: Redis para rate limiting, blacklist de tokens, sessoes
- **Deploy**: Docker/VPS (container Docker, mesma infra do wxcode)
- **Frontend**: App separada (provavelmente Next.js, consistente com wxcode frontend)
- **Dominios**: Subdomains separados por servico (auth.wxcode.io, app.wxcode.io, api.wxcode.io)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| JWT auto-contido (RS256) | wxcode valida token localmente sem depender do wxcode-adm | — Pending |
| App separada para UI do adm | Separacao clara de responsabilidades, deploy independente | — Pending |
| Subdomains por servico | Facilita deploy independente, SSL por servico, separacao clara | — Pending |
| Super-admin gerencia planos (CRUD) | Planos nao sao hardcoded, flexibilidade para ajustar ofertas | — Pending |
| Usuario isolado a um tenant | Simplicidade, sem complexidade de multi-tenant switching | — Pending |
| PostgreSQL + SQLAlchemy (nao MongoDB) | wxcode-adm e SaaS admin com schema relacional; wxcode usa MongoDB por tenant | — Pending |
| Monorepo backend + frontend | Um repo, deploy independente, backend em /backend, frontend em /frontend | — Pending |
| Alembic para migrations | Schema versionado, auto-generate | — Pending |

---
*Last updated: 2026-03-04 after milestone v2.0 start*
