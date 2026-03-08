---
status: diagnosed
trigger: "When the user refreshes the page in the admin UI, they are forced to log in again. The session should persist across page refreshes."
created: 2026-03-08T00:00:00Z
updated: 2026-03-08T00:00:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: CONFIRMED — Both admin and user tokens are stored in module-scoped JS variables (in-memory), which are wiped on every page reload.
test: Read admin-auth.ts, auth.ts, admin-auth-provider.tsx, admin login page
expecting: Confirmed in-memory-only storage with no localStorage/cookie read-back on mount
next_action: Return diagnosis

## Symptoms

expected: Admin user stays logged in after refreshing the page
actual: Admin user is redirected to login page on page refresh
errors: (not specified — likely just redirect to /admin/login)
reproduction: Log in to admin UI, then press F5 or navigate directly to any admin URL
started: Likely always broken — cross-cutting auth issue

## Eliminated

- hypothesis: Token stored in localStorage but not read back on mount
  evidence: admin-auth.ts confirms NO localStorage is used at all — pure module-scoped variables
  timestamp: 2026-03-08

- hypothesis: Provider mount effect re-hydrates session from some storage
  evidence: AdminAuthProvider useEffect on mount only calls setIsLoading(false) — does NOT read any stored token or attempt session restore
  timestamp: 2026-03-08

## Evidence

- timestamp: 2026-03-08
  checked: frontend/src/lib/admin-auth.ts — module-level token store
  found: _adminAccessToken and _adminRefreshToken are plain JS module-scoped variables (let). setAdminTokens() writes to these. isAdminAuthenticated() reads from these. No localStorage, sessionStorage, or cookie interaction anywhere in this file.
  implication: Any page reload reinitializes the JS module, setting both variables back to null.

- timestamp: 2026-03-08
  checked: frontend/src/lib/auth.ts — user token store (same pattern)
  found: Identical pattern — _accessToken and _refreshToken are module-scoped variables. The file comment explicitly states "Tokens survive within a tab session but are lost on full page reload (user re-logs in). This is the simplest secure approach for an SPA that redirects to wxcode after login." — this was a DELIBERATE DESIGN DECISION for the tenant user flow.
  implication: The design intent for tenant users is that they re-auth via redirect. Admin users have no such redirect fallback, so the same pattern causes a broken UX for admins.

- timestamp: 2026-03-08
  checked: frontend/src/providers/admin-auth-provider.tsx — session restore on mount
  found: The mount useEffect contains only `setIsLoading(false)`. The comment reads "No /users/me equivalent for admin — just check token presence". It calls isAdminAuthenticated() which returns false because _adminAccessToken is null after reload. Route guard immediately redirects to /admin/login.
  implication: There is no session restore mechanism at all. Even if a refresh token were persisted somewhere, the mount effect would never read it.

- timestamp: 2026-03-08
  checked: frontend/src/app/admin/login/page.tsx — login success path
  found: On successful login, calls adminAuthContext.login(tokens, email) which calls setAdminTokens() — writing only to the in-memory module variables. No secondary persistence (localStorage, cookie) is written.
  implication: The token is never written to any durable storage, confirming it cannot survive a page reload.

- timestamp: 2026-03-08
  checked: frontend/src/app/admin/layout.tsx — provider wiring
  found: AdminAuthProvider wraps all /admin/* routes. No middleware.ts or Next.js server-side auth check exists (would need to check separately). Route protection is entirely client-side via the useEffect in AdminAuthProvider.
  implication: No server-side session or cookie could be intercepting and restoring the session.

## Resolution

root_cause: |
  Admin tokens are stored exclusively in JavaScript module-scoped variables
  (`_adminAccessToken`, `_adminRefreshToken` in `frontend/src/lib/admin-auth.ts`).
  These variables live in JS heap memory. A full page reload (F5, URL navigation,
  browser restart) reinitializes all JS modules, resetting both variables to null.
  The AdminAuthProvider mount effect does not attempt to restore the session from
  any persistent storage — it only calls setIsLoading(false). The route guard then
  reads isAdminAuthenticated() (which returns false) and immediately redirects to
  /admin/login. The refresh token also lives only in memory and cannot be used to
  silently re-authenticate on reload because it is also lost. This is a deliberate
  design choice for tenant users (who redirect to wxcode after login) but is
  inappropriate for the admin UI, which needs persistent sessions.

fix: (not applied — diagnose-only mode)
verification: (not applied)
files_changed: []
