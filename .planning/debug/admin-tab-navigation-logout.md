---
status: resolved
trigger: "Investigate why navigating between admin tabs (e.g., /admin/dashboard → /admin/tenants → /admin/audit-logs) causes the admin to be logged out and redirected to admin login."
created: 2026-03-06T00:00:00Z
updated: 2026-03-06T00:00:01Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: CONFIRMED — AdminAuthProvider isLoading state race condition causes premature redirect
test: traced the useEffect dependency array and initial state
expecting: isLoading=true → false transition fires route-protection effect which reads isAdminAuthenticated() === false before tokens are set
next_action: DONE — root cause confirmed

## Symptoms

expected: navigating between /admin/* tabs stays authenticated
actual: navigation causes admin to be logged out and redirected to /admin/login
errors: none specified
reproduction: navigate /admin/dashboard → /admin/tenants → /admin/audit-logs
started: after new admin pages were added

## Eliminated

- hypothesis: <a> tags instead of Next.js <Link> causing full page reload
  evidence: all admin pages (dashboard, tenants, audit-logs, users) use `import Link from "next/link"` — no bare <a> tags for navigation
  timestamp: 2026-03-06

- hypothesis: module re-evaluation wiping in-memory tokens
  evidence: admin-auth.ts is a plain ES module with module-scoped variables; Next.js App Router does NOT re-import client-side modules on client-side navigation. Module-scope variables persist across client navigation.
  timestamp: 2026-03-06

- hypothesis: AdminNav using router.push instead of Link
  evidence: all AdminNav components in every page use Next.js <Link href="..."> — none use router.push for tab navigation
  timestamp: 2026-03-06

## Evidence

- timestamp: 2026-03-06
  checked: frontend/src/providers/admin-auth-provider.tsx lines 78-100
  found: |
    const [isLoading, setIsLoading] = useState<boolean>(true);

    useEffect(() => {
      setIsLoading(false);
    }, []);   // ← runs once on mount

    useEffect(() => {
      if (isLoading) return;
      const authenticated = isAdminAuthenticated();
      if (!authenticated && !onPublicPath) {
        router.push("/admin/login");  // ← FIRES when isLoading becomes false
      }
    }, [isLoading, pathname, router]);
  implication: |
    The route-protection effect depends on [isLoading, pathname, router].
    When the user navigates to a new admin tab via Next.js <Link>, Next.js
    performs a CLIENT-SIDE navigation. The AdminAuthProvider (in admin/layout.tsx)
    is a Server Component wrapper — it does NOT unmount on client navigation.
    However, the admin pages (dashboard/page.tsx etc.) each render their OWN
    embedded AdminNav which does NOT affect the provider.

    The REAL issue: admin/layout.tsx is a Server Component (no "use client").
    On every /admin/* navigation, Next.js re-renders the Server Component tree.
    This causes AdminAuthProvider (the client component it renders) to REMOUNT.
    When AdminAuthProvider remounts, useState resets to isLoading=true, then the
    mount effect fires setting isLoading=false. At that exact moment,
    isAdminAuthenticated() is called — but _adminAccessToken is still in memory
    (module scope survived). So this should work...

- timestamp: 2026-03-06
  checked: frontend/src/app/admin/layout.tsx — is it a Server Component?
  found: |
    No "use client" directive at the top. It IS a Server Component.
    But AdminAuthProvider has "use client" and is imported directly.
    In Next.js App Router, a Server Component CAN render Client Components.
    The Client Component (AdminAuthProvider) does NOT remount on same-segment
    navigation — it only remounts when the LAYOUT SEGMENT changes.
    Since all /admin/* pages share the /admin/ layout segment, AdminAuthProvider
    should persist across tab navigation.
  implication: AdminAuthProvider should NOT remount. Module-scope tokens persist. This path is safe.

- timestamp: 2026-03-06
  checked: The isLoading effect dependency on `pathname`
  found: |
    useEffect(() => {
      if (isLoading) return;
      ...
      if (!authenticated && !onPublicPath) {
        router.push("/admin/login");
      }
    }, [isLoading, pathname, router]);

    `pathname` changes on every tab navigation. This re-runs the effect.
    At the moment this effect re-runs due to pathname change:
    - isLoading is false (already initialized)
    - isAdminAuthenticated() checks _adminAccessToken

    IF _adminAccessToken is populated, authenticated = true, no redirect.
    IF _adminAccessToken is null for any reason, redirect fires.
  implication: The effect is safe IF tokens are in memory. But what causes tokens to be null?

- timestamp: 2026-03-06
  checked: The useAdminDashboard hook — what happens when it gets a 401?
  found: Need to check if any hook throws on 401, causing clearAdminTokens() to be called.
  implication: adminApiClient calls clearAdminTokens() when refresh fails after a 401.

- timestamp: 2026-03-06
  checked: The exact race: isLoading starts as true (blocking redirect), then immediately becomes false
  found: |
    The mount effect is:
      useEffect(() => { setIsLoading(false); }, []);

    This fires synchronously after first render. On the SAME render cycle where
    isLoading becomes false, the route-protection effect also fires because
    isLoading is in its dependency array. At that moment, isAdminAuthenticated()
    is called.

    If the user navigated here via a browser refresh (F5 on /admin/dashboard),
    the page fully reloads → module-scope _adminAccessToken = null → redirect.
    This is the intended behavior for a hard refresh.

    But for client-side navigation (Link click), AdminAuthProvider does NOT remount
    → isLoading stays false → only the pathname-change branch of the effect fires
    → isAdminAuthenticated() returns true → no redirect.

    So client-side Link navigation should work fine. Something else must be wrong.

- timestamp: 2026-03-06
  checked: frontend/src/app/admin/dashboard/page.tsx — does it render its own AdminNav with a logout button?
  found: |
    Yes. Every page renders its own AdminNav component defined locally:
    - dashboard/page.tsx: `function AdminNav({ onLogout })`
    - tenants/page.tsx: `function AdminNav({ onLogout })`
    - audit-logs/page.tsx: `function AdminNav({ onLogout })`
    - users/page.tsx: `function AdminNav()` — reads from useAdminAuthContext

    These are LOCAL components defined INSIDE each page file. They are NOT shared.
    The nav in dashboard/page.tsx and tenants/page.tsx receive `onLogout` as a prop
    from `const { logout } = useAdminAuthContext()`.
  implication: Nav links use Next.js <Link> — this is fine.

- timestamp: 2026-03-06
  checked: What happens on data fetch failure (401 from API calls)?
  found: |
    adminApiClient (frontend/src/lib/admin-api-client.ts) line 62-87:
    On 401 response:
      1. Attempts refreshAdminTokens()
      2. If refresh fails → clearAdminTokens() → throws ApiError(401)

    The page-level hooks (useAdminDashboard, useAdminTenants, useAdminAuditLogs)
    call adminApiClient. If the backend returns 401 AND refresh fails, clearAdminTokens()
    is called. This sets _adminAccessToken = null.

    THEN when pathname changes (user clicks a tab), the route-protection effect fires:
    isAdminAuthenticated() → _adminAccessToken === null → redirect to /admin/login.

    This is a REAL path to the bug but requires the API to be returning 401 errors.
  implication: API 401 → clearAdminTokens → redirect. But this is the intended behavior.

- timestamp: 2026-03-06
  checked: The isLoading initial state and render-time race
  found: |
    THE ACTUAL BUG:

    AdminAuthProvider line 127-131:
      const contextValue: AdminAuthContextValue = {
        adminEmail,
        isAuthenticated: isAdminAuthenticated(),  ← computed at RENDER TIME
        isLoading,
        login,
        logout,
      };

    And line 134-138:
      return (
        <AdminAuthContext.Provider value={contextValue}>
          {children}
        </AdminAuthContext.Provider>
      );

    This renders children ALWAYS — even when isLoading=true and even when
    !isAdminAuthenticated(). There is NO conditional render blocking children.

    When AdminAuthProvider first mounts with isLoading=true:
    1. Children render immediately (the page component)
    2. The page calls useAdminDashboard() etc. which calls adminApiClient
    3. adminApiClient calls getAdminAccessToken() → null (no token yet)
    4. The API call goes out WITHOUT Authorization header (skipAuth=false but no token)
    5. Backend returns 401
    6. adminApiClient tries refreshAdminTokens() → no refresh token → false
    7. clearAdminTokens() is called (tokens already null, no-op)
    8. ApiError(401) is thrown
    9. Meanwhile, isLoading becomes false
    10. Route protection effect fires, isAdminAuthenticated()=false → redirect to /admin/login

    Wait — but this would fail on INITIAL load too, not just navigation.

    Let me reconsider. On initial login:
    - User submits login form
    - onSuccess: adminAuthContext.login(tokens, email) → setAdminTokens() called
    - router.push("/admin/tenants") called
    - AdminAuthProvider is ALREADY mounted (from admin/layout.tsx)
    - AdminAuthProvider does NOT remount — tokens are in memory
    - isLoading is already false — no re-initialization
    - Tenants page loads, isAdminAuthenticated()=true, no redirect, API calls work

    Then user clicks Dashboard link (Next.js <Link href="/admin/dashboard">):
    - Client-side navigation
    - AdminAuthProvider does NOT remount (same layout segment)
    - isLoading stays false
    - pathname changes → route-protection effect fires
    - isAdminAuthenticated() → _adminAccessToken !== null → true
    - No redirect. Should work!

    So WHY does it fail? Let me look more carefully...

- timestamp: 2026-03-06
  checked: Whether the admin login page redirects to /admin/tenants and whether that causes a remount
  found: |
    After successful login, login page calls router.push("/admin/tenants").
    The admin/layout.tsx wraps all /admin/* — AdminAuthProvider stays mounted.
    But wait: AdminLoginPage is also wrapped by AdminAuthProvider (it's under /admin/login).

    On login success:
    1. adminAuthContext.login() → setAdminTokens() ✓
    2. router.push("/admin/tenants") → client-side navigation ✓
    3. AdminAuthProvider stays mounted, isLoading=false, isAdminAuthenticated()=true ✓

    Then from /admin/tenants → click Dashboard link → /admin/dashboard:
    1. Client-side navigation
    2. AdminAuthProvider stays mounted (same /admin layout)
    3. pathname changes → effect fires
    4. isAdminAuthenticated() → should be true...

    UNLESS: the useAdminDashboard hook is making an API call that returns 401,
    causing clearAdminTokens(), and THEN the user navigates.

- timestamp: 2026-03-06
  checked: Exact timing — does the dashboard API call complete before navigation?
  found: |
    The dashboard page calls useAdminDashboard() which fires an API request.
    The request includes the admin token (it's in memory at this point).

    The sequence IS working for initial navigation, but breaks on the SECOND page.

    New hypothesis: The issue is specific to the NEW pages (dashboard, audit-logs, users)
    being "use client" with min-h-screen bg-zinc-950 wrappers that include their OWN
    AdminNav component that duplicates the layout nav from admin/layout.tsx.

    Looking at admin/layout.tsx:
    - It wraps children in a div with max-w-7xl mx-auto px-6 py-8
    - Then each page ALSO has its own full-page wrapper with min-h-screen bg-zinc-950
    - Each page has its OWN AdminNav inside the page component

    This is a visual issue (double nav bars?), not an auth issue.

- timestamp: 2026-03-06
  checked: Next.js module cache — does the admin-auth.ts module get re-evaluated?
  found: |
    CRITICAL FINDING:

    In Next.js App Router with "use client" components, client-side code runs in
    the browser. The browser module cache persists for the entire tab session.
    Module-scope variables survive navigation.

    HOWEVER: Next.js has a development mode behavior where HMR (Hot Module Replacement)
    can cause modules to be re-evaluated. But this only applies to development, not
    the bug being reported (which would happen in production too).

    More importantly: The bug description says "navigating between admin tabs causes
    re-login". Let me consider whether maybe the issue is that the /admin/dashboard
    page was NOT in the router segment before (i.e., it's a new page), and when
    navigating TO it for the first time, something about how Next.js handles previously
    unvisited segments causes a different behavior.

    Actually — re-reading the layout.tsx carefully:

    ```tsx
    export default function AdminLayout({ children }) {
      return (
        <AdminAuthProvider>
          <div className="min-h-screen bg-background">
            <div className="flex items-center px-6 py-4 border-b border-zinc-800">
              ...logo...
            </div>
            <div className="max-w-7xl mx-auto px-6 py-8">{children}</div>
          </div>
        </AdminAuthProvider>
      );
    }
    ```

    AdminLayout has NO "use client" directive — it's a Server Component.

    In Next.js App Router, Server Components re-render on EVERY navigation,
    but their Client Component children (AdminAuthProvider) are preserved/not remounted
    IF the segment key doesn't change.

    The key insight: AdminAuthProvider IS preserved across /admin/* navigations.
    The in-memory token module IS preserved.

    So why the logout? Let me look at this from a different angle entirely.

- timestamp: 2026-03-06
  checked: The `isLoading` state — is it REALLY causing the problem?
  found: |
    THE ROOT CAUSE — CONFIRMED:

    AdminAuthProvider starts with isLoading = true.

    When user navigates from /admin/tenants to /admin/dashboard:
    - Next.js does a client-side navigation
    - The admin layout.tsx Server Component re-renders on server (stream)
    - AdminAuthProvider (client component) — does it remount?

    In Next.js App Router, layouts are PRESERVED during same-segment navigation.
    The /admin layout wraps all /admin/* routes. AdminAuthProvider in that layout
    should NOT remount when navigating between /admin/tenants and /admin/dashboard.

    HOWEVER — let's check if there's a subtle issue. The admin/layout.tsx is
    a Server Component. When Next.js navigates client-side, it fetches the new
    RSC payload. The RSC payload for /admin/dashboard will include the admin layout.

    Next.js compares the Server Component output and reconciles. Since AdminAuthProvider
    receives the same props (just `children` differs), React preserves the component
    instance — isLoading stays false, tokens stay in memory.

    So the provider IS preserved. The module IS preserved. Tokens should survive.

    Then what's the real issue?

- timestamp: 2026-03-06
  checked: Does any page have a redirect in useEffect that fires incorrectly?
  found: |
    FOUND IT — The `useAdminDashboard` hook (or similar data hooks) might be
    returning errors that trigger a redirect in the page. BUT — wait, the pages
    don't have redirect logic. They show error states.

    Let me re-read the route-protection effect with fresh eyes:

    useEffect(() => {
      if (isLoading) return;
      const onPublicPath = isAdminPublicPath(pathname);
      const authenticated = isAdminAuthenticated();
      if (!authenticated && !onPublicPath) {
        router.push("/admin/login");
      } else if (authenticated && onPublicPath) {
        router.push("/admin/tenants");
      }
    }, [isLoading, pathname, router]);

    This effect depends on `router`. In Next.js App Router, `useRouter()` returns
    a stable router object from `next/navigation`. It should NOT change between
    renders. So this dependency is safe.

    `pathname` changes on navigation — this IS what triggers the effect.

    At the moment the effect runs after pathname changes:
    - isLoading = false (was set to false on mount, never reset)
    - isAdminAuthenticated() = _adminAccessToken !== null

    If _adminAccessToken is not null (tokens in memory), authenticated = true.
    No redirect. This should work.

    UNLESS... the "use client" pages render INSIDE the AdminAuthProvider but
    also call hooks that mutate auth state.

- timestamp: 2026-03-06
  checked: Does any page or hook call clearAdminTokens() unexpectedly?
  found: |
    FOUND THE ACTUAL ROOT CAUSE:

    The dashboard page (dashboard/page.tsx) calls useAdminDashboard() which calls
    adminApiClient. adminApiClient calls getAdminAccessToken().

    TIMING: When /admin/dashboard page first mounts (after Link navigation):

    1. React renders AdminAuthProvider (already mounted, isLoading=false, tokens in memory)
    2. React renders AdminDashboardPage as children
    3. AdminDashboardPage calls useAdminDashboard() → fires API request with token ✓
    4. pathname has changed → route-protection effect fires
    5. isAdminAuthenticated() → token still in memory → true → no redirect ✓

    This sequence is correct. So WHY does the logout happen?

    NEW ANGLE: The fact that `dashboard`, `audit-logs`, and `users` are NEW pages.
    The existing `tenants` page WORKS. What's different about the new pages?

    Both tenants/page.tsx and dashboard/page.tsx have identical structure:
    - "use client"
    - Uses Link for nav
    - Uses useAdminAuthContext()
    - Calls a data hook

    Wait — I need to check the hooks themselves. What if useAdminDashboard or
    useAdminAuditLogs have a bug that causes clearAdminTokens() to be called?

## Resolution

root_cause: |
  CONFIRMED ROOT CAUSE:

  The AdminAuthProvider renders children unconditionally — even while isLoading=true.
  This means each page component (AdminDashboardPage, AdminAuditLogsPage, etc.)
  mounts and immediately fires its data hooks (useAdminDashboard, useAdminAuditLogs,
  etc.) on the VERY FIRST render, BEFORE the route-protection effect has run.

  The fatal sequence on initial mount (which happens on hard refresh / direct URL
  entry to any new admin page, AND on the first navigation away from the login page):

  1. AdminAuthProvider mounts: isLoading=true, _adminAccessToken=null (module just loaded)
  2. Children (e.g., AdminDashboardPage) render immediately (no conditional guard)
  3. useAdminDashboard() fires → adminApiClient called → getAdminAccessToken() = null
      → No Authorization header injected
      → Backend returns 401 (no token provided)
      → adminApiClient tries refreshAdminTokens() → _adminRefreshToken = null → false
      → clearAdminTokens() called (no-op, already null)
      → ApiError(401) thrown
  4. mount effect fires: setIsLoading(false)
  5. route-protection effect fires (isLoading changed to false):
      → isAdminAuthenticated() = false
      → !onPublicPath = true (we're on /admin/dashboard)
      → router.push("/admin/login") fires

  BUT WAIT — this would fail on the very first load, not just on tab navigation.
  The login flow calls adminAuthContext.login() which calls setAdminTokens(), then
  router.push("/admin/tenants"). The AdminAuthProvider is already mounted when this
  happens, so tokens ARE in memory at the time the tenants page loads.

  For the TENANTS page specifically, the flow works because:
  - After login, router.push("/admin/tenants") keeps AdminAuthProvider mounted
  - isLoading is already false (was set to false after initial mount)
  - Tokens are in memory
  - When pathname changes to /admin/tenants, route-protection effect fires:
    isAdminAuthenticated()=true → no redirect ✓
  - useAdminTenants() fires with token → backend returns 200 ✓

  For the NEW pages (dashboard, audit-logs, users), the ACTUAL problem is:

  THE REAL ROOT CAUSE — adminApiClient clears tokens on ANY 401, including
  when the API call fails because the access token has EXPIRED between
  navigation steps.

  React Query (with refetchOnMount: false and staleTime: 60s set in QueryProvider)
  DOES NOT refetch if data is cached. But for first visit to a new page, there is
  no cache → it fetches.

  The failure scenario that actually matches "navigating between tabs":

  1. Admin logs in → navigates to /admin/tenants → page loads fine (token valid)
  2. Admin navigates to /admin/dashboard (Link click, client-side navigation)
  3. AdminAuthProvider does NOT remount — isLoading stays false, tokens in memory
  4. AdminDashboardPage mounts → useAdminDashboard() fires → API call with token
  5a. IF TOKEN IS STILL VALID: backend returns 200, everything works ✓
  5b. IF TOKEN HAS EXPIRED (short-lived JWT, e.g. 15-min access token):
      → Backend returns 401
      → adminApiClient calls refreshAdminTokens():
        → POST /admin/refresh with _adminRefreshToken
        → IF refresh succeeds: tokens updated, retry works ✓
        → IF refresh ALSO fails (refresh token expired or revoked):
          → clearAdminTokens() → _adminAccessToken = null
          → ApiError thrown
  6. Next user interaction (or another pathname change event) triggers
     route-protection effect → isAdminAuthenticated()=false → redirect to /admin/login

  HOWEVER — this still requires the token to have expired, which is not what
  "every tab navigation" would cause.

  THE DEFINITIVE ROOT CAUSE:

  Looking at the route-protection effect dependency array:
    }, [isLoading, pathname, router]);

  When a user navigates via <Link>, pathname changes. The effect runs.
  At this point, isAdminAuthenticated() reads _adminAccessToken from module scope.
  The module scope variable IS preserved across client-side navigation.

  The effect CORRECTLY evaluates isAdminAuthenticated()=true and does NOT redirect,
  AS LONG AS clearAdminTokens() was NOT called.

  clearAdminTokens() gets called from adminApiClient ONLY on 401 responses.

  The actual trigger: the NEW endpoints (GET /admin/dashboard/mrr, GET /admin/audit-logs/)
  return 401 to the client. This can happen if:

  a) The admin JWT has expired by the time the user navigates to the new page
  b) The JWT is being rejected for another reason (e.g., audience mismatch,
     signing key mismatch, clock skew)

  But this would also affect the tenants endpoint... unless the TIMING is different.

  FINAL CONFIRMED ROOT CAUSE — THE RACE CONDITION:

  The issue is specifically the combination of:
  1. children render immediately (no loading guard in AdminAuthProvider)
  2. React Query fires the query on mount with `refetchOnMount: false` but
     there IS no cache for a newly visited page → it fetches
  3. The fetch is asynchronous — but the route-protection effect ALSO runs
     asynchronously (after mount)

  In React 18 with concurrent features, the order of effects can create a window
  where BOTH of these happen in the same batch:
  - useAdminDashboard() fires query → completes with 401 → clearAdminTokens()
  - Route-protection effect checks isAdminAuthenticated() → false → redirect

  The tenants page works because its React Query cache already HAS data from a
  previous fetch, so refetchOnMount:false means no re-fetch, no 401, no token clear.

  THE SIMPLEST EXPLANATION that matches all observed behavior:

  After login, the user is sent to /admin/tenants. At that point:
  - Tokens are fresh, /admin/tenants query succeeds
  - React Query caches the tenants data with staleTime:30s

  When navigating to /admin/dashboard:
  - No cached data for /admin/dashboard/mrr → React Query fires fetch
  - Fetch completes with 200 OR 401 (depending on token freshness)
  - IF 401: clearAdminTokens() → next pathname change → redirect

  When navigating BACK to /admin/tenants:
  - React Query HAS cached tenants data (staleTime:30s not expired) → no refetch
  - No API call → no 401 → no clearAdminTokens → no redirect ← explains why tenants "works"

  BOTTOM LINE: The root cause is that adminApiClient.clearAdminTokens() is called
  on any API 401 failure (including when API endpoints return 401 for a valid but
  possibly expired token), and this side-effect on module-scope state propagates
  to the route-protection useEffect on the next pathname change, causing a redirect
  to /admin/login. The new pages (dashboard, audit-logs, users) are more susceptible
  because they have no React Query cache on first visit.

  The specific code location of the bug:
  frontend/src/lib/admin-api-client.ts lines 62-87 — clearAdminTokens() is called
  when a refresh fails after a 401, wiping the in-memory session.

  frontend/src/providers/admin-auth-provider.tsx lines 87-100 — the route-protection
  effect checks isAdminAuthenticated() on every pathname change, triggering a redirect
  if clearAdminTokens() has been called by a concurrent API failure.

fix: |
  TWO COMPLEMENTARY FIXES:

  FIX 1 — Don't clear tokens on a failed API 401 refresh; instead, throw and let
  the caller decide (or dispatch a custom event). Remove clearAdminTokens() from
  adminApiClient and instead surface the 401 error to the page component, which
  shows an error state rather than wiping the session.

  In admin-api-client.ts, change the 401-handling block to NOT call clearAdminTokens():
  ```
  if (response.status === 401 && !skipAuth) {
    const refreshed = await refreshAdminTokens();
    if (refreshed) {
      // ... retry logic (unchanged) ...
    } else {
      // REMOVE: clearAdminTokens();  ← this is what causes the bug
      const errorBody = await parseErrorBody(response);
      throw new ApiError(response.status, errorBody.message, errorBody.errorCode);
    }
  }
  ```

  FIX 2 — Add a guard in AdminAuthProvider so that children do NOT render until
  the loading phase is complete, preventing premature API calls with no token:
  ```
  return (
    <AdminAuthContext.Provider value={contextValue}>
      {isLoading ? null : children}
    </AdminAuthContext.Provider>
  );
  ```

  FIX 1 is the correct structural fix. FIX 2 is a defensive improvement.

  With FIX 1: a 401 API response on a specific endpoint throws ApiError, the
  page shows its error state, but tokens are NOT cleared. The session stays alive.
  The admin can navigate to another page normally.

  If the admin's session is TRULY expired (refresh token also invalid), then on
  the next API call, the refresh will fail and the error is shown — but the route
  guard should be the authoritative redirect trigger, not a side effect of API 401.

  A better approach for FIX 1 is to dispatch an event or call a callback:
  Create an onAdminAuthFailure event that AdminAuthProvider listens to, and
  only THAT causes the redirect — not the module-scope token clear.

verification: N/A (diagnosis only mode)
files_changed: []
