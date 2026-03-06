# Phase 5: Platform Security - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Harden the platform with rate limiting on all endpoints, an immutable audit log for every write operation, and branded HTML transactional email templates. API key management (PLAT-01, PLAT-02) is deferred to a future phase.

</domain>

<decisions>
## Implementation Decisions

### API Keys — DEFERRED
- API key creation, revocation, and scope enforcement are NOT part of this phase
- PLAT-01 and PLAT-02 deferred to a future phase — user changed mind on timing
- Phase 5 focuses on rate limiting (PLAT-03), audit log (PLAT-04), and email templates (PLAT-05)

### Rate Limiting
- Strict auth endpoint limits: 5 requests/minute per IP for login, sign-up, password reset
- Global rate limit for all authenticated endpoints: fixed limit for all tenants regardless of plan
- 429 response includes Retry-After header (standard HTTP)
- Rate limits stored in Redis sliding window — persist across restarts

### Audit Log
- Log ALL write operations (POST/PATCH/DELETE), not just sensitive ones
- Detail level: action + target only (who did what to whom) — no before/after diffs
- Query access: super-admin only for now — tenant-scoped query API comes later
- Retention: rolling window — auto-purge entries older than a configurable period (e.g., 12 months)
- Append-only: tenant users cannot modify or delete audit entries

### Email Templates
- Branded and polished HTML emails with full header/footer, colors, styled layout
- Brand colors: extract from WXCODE project's existing logo/UI — researcher should identify exact hex values
- Every email includes both HTML and plain-text versions for deliverability
- 4 templates: email verification, password reset, member invitation, payment failure notification
- Jinja2 HTML templates with a shared base layout

### Claude's Discretion
- Global rate limit threshold for authenticated endpoints (e.g., 60/min, 100/min)
- Audit log retention period (12 months suggested, Claude can adjust)
- Email template exact layout and spacing
- Jinja2 template inheritance structure
- Audit log table schema details (JSON column for details vs separate columns)

</decisions>

<specifics>
## Specific Ideas

- Rate limiting should use slowapi (research confirmed it over unmaintained fastapi-limiter)
- Audit log is append-only at the application level — no DELETE endpoint exposed, even for super-admin
- Email templates should feel like a polished SaaS product (not plain/minimal)

</specifics>

<deferred>
## Deferred Ideas

- API key management (PLAT-01, PLAT-02) — create, revoke, rotate scoped API keys — move to a future phase
- Tenant-scoped audit log query API — tenant owners querying their own logs
- Per-plan rate limits — different limits based on billing plan

</deferred>

---

*Phase: 05-platform-security*
*Context gathered: 2026-02-23*
