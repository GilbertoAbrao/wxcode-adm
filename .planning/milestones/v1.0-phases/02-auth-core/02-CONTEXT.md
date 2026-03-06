# Phase 2: Auth Core - Context

**Gathered:** 2026-02-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Email/password authentication with JWT RS256 tokens, email verification (6-digit code), password recovery (signed link), refresh token rotation, and JWKS endpoint for wxcode to validate tokens locally. OAuth and MFA are separate phases (Phase 6).

</domain>

<decisions>
## Implementation Decisions

### Token lifecycle
- Access token TTL: 24 hours
- Refresh token TTL: 7 days
- Single session policy: new login revokes all previous sessions (one device at a time)
- Refresh rotation: immediate revoke — old refresh token is invalidated the moment a new one is issued; replay detection triggers full logout

### Email verification
- 6-digit code expires in 10 minutes
- Max 3 wrong attempts — code invalidated after 3 failures, user must request a new one
- Unverified users are fully blocked — can only verify email or resend code, no other endpoint access

### Password reset
- Reset link expires in 24 hours
- Single-use enforcement (itsdangerous signed token, consumed on use)
- After successful reset: revoke ALL sessions (force re-login everywhere)
- Non-existent email returns same success response ("check your email") — prevents email enumeration

### Claude's Discretion
- Resend verification code cooldown (reasonable anti-abuse interval)
- Password reset request rate limit (reasonable anti-flooding interval)
- Error response format and HTTP status codes for auth failures
- RSA key size and rotation strategy for JWKS

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-auth-core*
*Context gathered: 2026-02-22*
