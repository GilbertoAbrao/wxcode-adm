# WXCODE ADM

## What This Is

Camada SaaS do WXCODE — o porteiro da plataforma. Gerencia autenticacao, identidade, multi-tenancy, billing e administracao da plataforma. O usuario faz sign-up/sign-in no wxcode-adm, recebe um JWT auto-contido, e e redirecionado para o wxcode (app principal). O wxcode-adm reaparece quando o usuario acessa "My Account" ou "Settings" dentro do wxcode.

## Core Value

Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Sign-up com email + senha
- [ ] Sign-in com email + senha, retornando JWT auto-contido
- [ ] OAuth 2.0 (Google, GitHub, Microsoft)
- [ ] MFA via TOTP (Google Authenticator, Authy)
- [ ] Recuperacao de senha via email
- [ ] Verificacao de email para novas contas
- [ ] Multi-tenancy com isolamento logico por tenant_id
- [ ] Convite de usuarios por tenant (usuario pertence a um unico tenant)
- [ ] RBAC por tenant (Owner, Admin, Developer, Viewer, Billing)
- [ ] CRUD de planos de cobranca mensal (super-admin)
- [ ] Integracao Stripe (checkout, billing recorrente, customer portal, webhooks)
- [ ] Usage-based billing complementar (conversoes excedentes, tokens LLM, storage, API calls)
- [ ] API keys por tenant com escopos granulares
- [ ] Super-admin: gestao de tenants (ver, suspender, deletar)
- [ ] Super-admin: gestao de usuarios (ver, bloquear, resetar senha)
- [ ] Super-admin: dashboard de metricas (MRR, churn, conversoes totais, uso por tenant)
- [ ] Super-admin: configuracoes da plataforma (feature flags, limites globais, manutencao)
- [ ] Audit log de acoes sensíveis
- [ ] Rate limiting por IP e por usuario
- [ ] Redirecionamento para wxcode com access token apos login
- [ ] UI propria (app separada) para auth, account settings e billing

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

- **Tech stack**: Python 3.11+ / FastAPI / Beanie ODM / MongoDB — consistencia com wxcode
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
| Mesma stack Python/FastAPI/Beanie | Consistencia com wxcode, reuso de conhecimento e patterns | — Pending |

---
*Last updated: 2026-02-22 after initialization*
