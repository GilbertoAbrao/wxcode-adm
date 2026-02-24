# Phase 6: OAuth and MFA - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can authenticate with Google or GitHub without creating a password, and tenants can require two-factor authentication for all members. This phase delivers OAuth social login (Google, GitHub), TOTP MFA enrollment/verification, tenant MFA enforcement, and remember-device. Account linking is handled here; profile management (set password from settings) is Phase 7.

</domain>

<decisions>
## Implementation Decisions

### Account Linking
- When OAuth email matches an existing password account, **prompt the user to enter their existing password** to confirm ownership, then link the OAuth provider to that account in the same flow
- **One OAuth provider per account** — user must unlink current provider before linking a different one
- User can **unlink OAuth only if a password is set** — prevents account lockout
- Email sync from provider changes: Claude's discretion (link by provider user ID, not email)

### OAuth-only Users
- OAuth-only users **can set a password later** from account settings (implemented in Phase 7)
- Same onboarding flow as email/password users, but **skip workspace creation if already invited to a tenant** — go straight to that tenant
- **Still require email OTP verification** even though OAuth provider verified the email — extra security layer
- If OAuth provider account is deleted/suspended and no password set, user can **use the password reset flow** to set a password and regain access

### MFA Enrollment
- Number of backup codes: **Claude's discretion** (industry standard)
- All backup codes exhausted + authenticator lost: **contact super-admin** for manual identity verification and MFA reset — no self-service recovery
- **No backup code regeneration** — user must disable MFA and re-enable it to get new codes
- User can **disable MFA with a valid TOTP code or backup code**; if tenant enforcement is on, they will be re-prompted to enroll on next login

### Tenant Enforcement
- **Immediate lockout** when enforcement is turned on — active sessions are revoked, members without MFA must enroll on next login
- **Owner must have MFA enabled** on their own account before they can turn on enforcement for the tenant
- **No remember-device when tenant enforces MFA** — TOTP required on every login for enforced tenants
- **Per-tenant trust evaluation** — a user in multiple tenants gets remember-device in non-enforcing tenants even if another tenant enforces MFA

### Claude's Discretion
- OAuth email sync behavior (recommended: link by provider user ID, not email)
- Number of backup codes (standard: 8-10)
- TOTP window tolerance (standard: 1 step = 30 seconds)
- Remember-device cookie implementation details

</decisions>

<specifics>
## Specific Ideas

- Password reset flow doubles as recovery mechanism for OAuth-only users who lose provider access
- Disable-then-reenable MFA as the only way to get fresh backup codes (simpler, avoids partial state)
- Tenant enforcement is binary (on/off) — no grace period complexity

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-oauth-and-mfa*
*Context gathered: 2026-02-24*
