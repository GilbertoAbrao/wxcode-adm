# Phase 8: Super-Admin - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Platform super-admin endpoints for managing all tenants and users, a live MRR dashboard with 30-day trends, and admin-isolated authentication — all through endpoints separated from the tenant-facing API by a distinct JWT audience claim.

</domain>

<decisions>
## Implementation Decisions

### Admin auth flow
- Dedicated /admin/login endpoint — separate from tenant /auth/login; only accepts super-admin credentials; only issues admin-audience JWTs (aud: "wxcode-adm-admin")
- IP allowlist is optional — if ADMIN_ALLOWED_IPS env var is set, enforce it; if empty/unset, skip IP check (dev-friendly)
- All admin endpoints live under /api/v1/admin/* — same API version prefix, clear admin namespace
- Admin session TTL same as regular users — use existing ACCESS_TOKEN_TTL_HOURS and REFRESH_TOKEN_TTL_DAYS settings

### Suspension & blocking
- Tenant suspension is immediate invalidation — all refresh tokens deleted, access tokens blacklisted; members kicked out within minutes
- Admin can reactivate suspended tenants — POST /api/v1/admin/tenants/{id}/reactivate restores access
- Tenant soft-delete has indefinite retention — is_deleted=True flag, data stays forever; no scheduled purge
- User block is per-tenant scope — admin blocks user within a specific tenant; user can still access other tenants; sessions for that tenant invalidated immediately

### User search & actions
- Admin sees full profile + memberships + sessions — email, name, avatar, MFA status, email verified, created date, all tenant memberships with roles, plus active sessions (device, IP, last active)
- Force password reset: invalidate + send email — current password invalidated immediately, reset email sent automatically; user must set new password to log in
- User search supports email + name + tenant — search by email, display name, or filter by tenant membership
- Admin actions require a reason — block and force-reset require a "reason" string stored in the audit log alongside the action

### MRR dashboard
- Data sourced from local DB (webhook-cached) — subscription data already in DB from webhook processing; dashboard aggregates local data; fast and reliable
- Snapshot + 30-day trend — current MRR numbers plus trend over last 30 days
- Trend computed on-demand — calculate from TenantSubscription history (created_at, canceled_at timestamps) when admin opens dashboard; no daily cron job needed
- Includes churn data — canceled subscription count and churn rate shown alongside MRR and plan distribution

### Claude's Discretion
- Admin login rate limiting specifics
- DashboardSnapshot response schema design
- Pagination defaults for tenant/user listing
- Exact IP allowlist parsing format

</decisions>

<specifics>
## Specific Ideas

- Per-tenant user blocking (not platform-wide ban) — preserves user access to other tenants they belong to
- Reason field on destructive admin actions — builds a traceable admin audit trail
- On-demand trend calculation avoids new infrastructure — reuses existing subscription data model

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-super-admin*
*Context gathered: 2026-02-26*
