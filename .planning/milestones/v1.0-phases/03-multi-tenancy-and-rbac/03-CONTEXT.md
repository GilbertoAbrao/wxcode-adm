# Phase 3: Multi-Tenancy and RBAC - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Every authenticated user belongs to one or more tenants, every action is scoped to the current tenant, and roles determine what each user can do within each tenant. Tenant creation, invitations, role enforcement, member management, and ownership transfer.

**Key change from roadmap:** Users are NOT exclusively bound to one tenant. Multi-tenant membership is supported with per-tenant roles and a header-based tenant context switcher.

</domain>

<decisions>
## Implementation Decisions

### Tenant identity & onboarding
- Tenant is NOT created during sign-up — sign-up stays lean (email/password only)
- After sign-up + email verification, a separate onboarding step asks for workspace name
- Only workspace name is collected (single field) — slug is auto-generated from it
- Display name can be changed anytime; slug is permanent once set
- Users in "no tenant" state (just signed up, haven't created or joined a workspace) can access profile/account endpoints but tenant-scoped operations return 403 with clear message

### Invitation rules
- Multi-tenant membership: a user can belong to multiple tenants simultaneously
- Per-tenant roles: role is per membership, not global (Owner in Tenant A, Viewer in Tenant B)
- Current tenant context determined by `X-Tenant-ID` (or slug) header on each request — stateless, explicit
- New user invitation flow: invite link → sign-up → email verification → auto-join tenant (no separate accept step)
- Existing user invitation: standard accept flow (user already has account, accepts to join the new tenant)
- 7-day expiry on invitation tokens (from roadmap)

### Role permission boundaries
- Role hierarchy: Owner > Admin > Developer > Viewer (4 roles, not 5)
- Billing is NOT a role — it's a permission toggle ("billing access") that can be added to any role
- Role changes are immediate — Owner/Admin changes a member's role, takes effect instantly, no confirmation needed
- Owner cannot demote themselves — must transfer ownership first (prevents lockout)
- Claude's Discretion: exact Developer vs Viewer permission boundary (Developer can likely manage API keys and sensitive config; Viewer is read-only)

### Member removal & re-entry
- Removed member's account persists — they just lose membership in that tenant, can still access other tenants
- Re-invitation is allowed immediately — no cooldown after removal, clean slate with new role
- Members can voluntarily leave a tenant (self-service), except Owner who must transfer ownership first
- Ownership transfer requires acceptance — target member gets a transfer request and must accept; current Owner retains ownership until accepted; upon acceptance, previous Owner is downgraded to Admin

### Claude's Discretion
- Developer vs Viewer exact permission matrix
- Slug generation algorithm (from workspace name)
- Invitation email content and formatting
- How "no tenant" state is communicated in API responses
- Tenant context validation (what happens if header references a tenant the user doesn't belong to)

</decisions>

<specifics>
## Specific Ideas

- Multi-tenant model resembles Slack/Discord where one user can be in multiple workspaces with different roles in each
- Onboarding should feel lightweight — just a workspace name, get started immediately
- Ownership transfer is a two-step process (request + accept) unlike role changes (immediate)

</specifics>

<deferred>
## Deferred Ideas

- Tenant subdomain routing (my-company.wxcode.com) — future consideration, slug is prepared for it
- Tenant settings/preferences page — Phase 7 or later
- Team/group-based permissions within a tenant — not in scope, individual roles only

</deferred>

---

*Phase: 03-multi-tenancy-and-rbac*
*Context gathered: 2026-02-23*
