# Phase 7: User Account - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can manage their own profile and sessions, and are seamlessly redirected to the wxcode application after login with their access token embedded in the redirect. Covers: profile editing (display name, email, avatar), password change, session listing/revocation, and post-login redirect to wxcode.

</domain>

<decisions>
## Implementation Decisions

### Session visibility
- Rich session metadata: IP address, device type (Desktop/Mobile/Tablet), browser name/version, and approximate city from IP geolocation
- "Last active" updated on every authenticated API request (Redis write per request)
- Session revocation is immediate: blacklist active access tokens in Redis so revoked sessions are rejected within seconds
- Current session is tagged as "Current session" in the list to prevent accidental self-revocation

### wxcode redirect
- One-time code exchange pattern: after login, redirect to wxcode with a short-lived authorization code; wxcode backend exchanges the code for the JWT via a server-to-server call — token never appears in URL
- wxcode application URL is a per-tenant setting stored in the database — allows custom domains / whitelabel
- Multi-tenant users auto-redirect to their last-used or primary tenant's wxcode URL after login; tenant switching happens from within wxcode

### Claude's Discretion
- Profile fields and avatar handling (upload storage, size limits, validation)
- Password change session behavior (which other sessions to invalidate)
- Email change re-verification flow
- One-time code TTL (recommend 30-60 seconds based on security best practices)
- How "default tenant" is determined (last-used vs primary vs most recent membership)
- IP geolocation approach (library or service choice)
- User-Agent parsing strategy for device/browser extraction

</decisions>

<specifics>
## Specific Ideas

- User preferred header-based token passing but accepted code exchange after learning redirects can't carry custom headers
- The code exchange pattern aligns with OAuth authorization code flow — familiar and proven secure

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-user-account*
*Context gathered: 2026-02-25*
