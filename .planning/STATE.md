# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-04)

**Core value:** Controlar acesso seguro a plataforma WXCODE com identidade, permissoes por tenant e cobranca recorrente — sem executar nenhuma operacao do wxcode engine.
**Current focus:** Milestone v2.0 — Phase 16: Billing UI — Plan 1 of 2 complete

## Current Position

Phase: 16 of 17 (Billing UI) — fifth phase of v2.0 Frontend UI milestone
Plan: 1 of 2 complete (16-01 complete)
Status: Phase 16 in progress — 16-01 done (useBilling.ts hooks + /billing page), ready for 16-02 (Stripe Checkout + Portal)
Last activity: 2026-03-05 — 16-01 complete (TanStack Query billing hooks and /billing page with subscription card and plan catalog)

Progress: [████████████████████░░░░░░░░░░] 64% (v1.0 complete; v2.0 Phase 12 complete 3/3, Phase 13 complete 4/4, Phase 14 complete 2/2, Phase 15 complete 3/3, Phase 16 in progress 1/2)

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 38 (v1.0 all phases)
- Average duration: 5 min
- Total execution time: ~3.2 hours

**By Phase (v1.0 summary):**

| Phase | Plans | Status |
|-------|-------|--------|
| 01-foundation | 4/4 | Complete |
| 02-auth-core | 5/5 | Complete |
| 03-multi-tenancy-and-rbac | 5/5 | Complete |
| 04-billing-core | 5/5 | Complete |
| 05-platform-security | 4/4 | Complete |
| 06-oauth-and-mfa | 5/5 | Complete |
| 07-user-account | 4/4 | Complete |
| 08-super-admin | 4/4 | Complete |
| 09-mfa-redirect-fix | 1/1 | Complete |
| 10-api-key-management | 0/1 | Pending |
| 11-billing-fixes | 1/1 | Complete |

*Updated after each plan completion*

**v2.0 Metrics:**

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 16-billing-ui | 01 | 1 min | 2 | 2 |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting v2.0:

- [v2.0 start]: Stack confirmed — Next.js 16, React 19, Tailwind CSS v4, shadcn/ui new-york, TypeScript, TanStack React Query
- [v2.0 start]: Design system ported from /Users/gilberto/projetos/wxk/wxcode/frontend/ — Obsidian Studio dark theme, GlowButton, GlowInput, LoadingSkeleton, EmptyState, ErrorState, AnimatedList
- [v2.0 start]: Backend API already live at localhost:8040 — frontend is pure UI, no backend changes required
- [v2.0 start]: Phase 17 (Super-Admin UI) depends only on Phase 12 (design system), not on Phases 13-16 — can run in parallel with tenant/billing phases if needed
- [v1.0]: ALL v1.0 phases complete EXCEPT Phase 10 (API Key Management, PLAT-01/PLAT-02 — pending)
- [12-01]: Port 3040 for wxcode-adm frontend (distinct from wxcode:3052 and backend:8040)
- [12-01]: Tailwind v4 uses @theme inline CSS-first config — no tailwind.config.js needed
- [12-01]: oklch color tokens for shadcn CSS variables (perceptually uniform, Tailwind v4 native)
- [12-02]: globals.css ported exactly from wxcode source — Obsidian Studio is the authoritative design token set
- [12-02]: Dark mode is primary/default mode for wxcode-adm (html element has dark class in layout.tsx)
- [12-02]: button.tsx (shadcn base) co-exists with GlowButton — they serve different purposes
- [12-02]: All 6 components importable from @/components/ui barrel export; animation variants from @/lib/animations
- [12-03]: Custom sidebar built from scratch — shadcn/ui Sidebar component too complex for simple admin nav
- [12-03]: wxCode brand logo-icon.png used with natural 2:1 aspect ratio (w-auto), not forced square
- [12-03]: Cyan-400 active nav border matches wxCode brand identity (cyan + purple palette)
- [12-03]: Root page.tsx removed — (app)/page.tsx handles / directly (route groups are URL-invisible)
- [12-03]: TanStack React Query browser singleton pattern ported verbatim from wxcode source
- [13-01]: In-memory token storage (module-scoped variables, not localStorage) — XSS-safe. Tokens lost on page reload; user re-logs in. Acceptable for SPA that redirects to wxcode after login.
- [13-01]: Client-side route protection via AuthProvider useEffect — not Next.js middleware. Middleware cannot read in-memory tokens (no cookie). Can upgrade to middleware if tokens move to httpOnly cookies.
- [13-01]: apiClient injects Authorization header from memory token; on 401 attempts silent refresh once then clears tokens
- [13-01]: (auth) route group has no sidebar — completely separate layout from (app) group
- [13-02]: Suspense boundary required for all pages using useSearchParams() in Next.js App Router — inner component pattern (<Suspense fallback={null}><Content /></Suspense>)
- [13-02]: Login page uses contextual error messages: 401 = wrong credentials, 403 = unverified email with /verify-email link, default = error.message
- [13-02]: Shared validation schemas in validations.ts — all auth forms import from @/lib/validations, not inline zod
- [13-04]: Suspense wrapper pattern for useSearchParams() established across all auth pages (inner form component + outer Suspense export)
- [13-04]: MFA page dual-mode: single mfaCodeSchema (min 6, max 11 chars) handles both TOTP (6-digit) and backup codes (XXXXX-XXXXX); toggle resets form
- [13-03]: Enumeration-safe forgot-password: always shows success state after submit regardless of whether email exists — prevents user enumeration attacks
- [13-03]: reset-password shows inline error state with recovery link when token is missing (not a redirect) — better UX for confused users
- [13-04]: Trust device stored in local state only — not validated by Zod, passed directly as boolean to mutation
- [14-01]: Avatar upload uses direct fetch (not apiClient) — apiClient forces Content-Type: application/json which breaks multipart/form-data boundary; direct fetch with only Authorization header lets browser set correct Content-Type
- [14-01]: Account page inline ProfileSection component — keeps form state (fileInputRef, showSaved, react-hook-form register) co-located, appropriate for plan scope
- [14-01]: Password/Sessions sections stubbed as visible placeholder cards — maintains 3-section page structure for Plan 14-02 to populate
- [14-02]: Password change 400 error shows "Current password is incorrect" (not generic message) — ApiError.status === 400 check differentiates auth failure from server errors
- [14-02]: confirm_password shares showNewPassword toggle state with new_password — avoids redundant third toggle
- [14-02]: Sessions section and password section rendered in AccountPage root (not sub-components) — single use-client component per plan spec
- [15-01]: tenantHeaders helper encapsulates X-Tenant-ID injection — all tenant-scoped hooks use it via spread onto apiClient options
- [15-01]: useTenantInvitations conditionally enabled on isAdminOrOwner check at page level — avoids 403 for non-admin users
- [15-01]: ChangeRoleVariables type extends ChangeRoleRequest with user_id for dynamic URL mutation
- [15-01]: inviteMemberSchema role enum excludes owner — only admin/developer/viewer are valid invite roles per backend validation
- [15-01]: Zod v4 z.enum uses message param not required_error (breaking change from Zod v3)
- [15-02]: confirmRemove string|null state for inline per-row remove confirmation — replaces trash icon with "Remove? Yes/No" without a modal
- [15-02]: mfaEnforced local state initialized to false — TenantResponse schema did not expose mfa_enforced; state synced from PATCH response; reset on page reload (known limitation — resolved in 15-03)
- [15-02]: Role dropdown onChange is async with try/catch; errors surface per-row via changeRoleMutation.variables?.user_id === member.user_id
- [15-03]: mfa_enforced exposed in get_user_tenants via membership.tenant.mfa_enforced — selectinload already eager-loads full Tenant, no extra query needed
- [15-03]: Frontend MyTenantItem.mfa_enforced declared optional (?) for backward compatibility with cached responses
- [15-03]: useEffect([tenantsData]) syncs toggle state on load and after PATCH invalidation — toggle stays consistent with server state
- [Phase 16-billing-ui]: useQueryClient included in useCreateCheckout/useCreatePortal for Plan 16-02 readiness (post-Stripe polling)
- [Phase 16-billing-ui]: PlanCard co-located as inline sub-component in billing/page.tsx — keeps subscription state accessible

### Pending Todos

None yet.

### Blockers/Concerns

- [v1.0 carry-over]: Phase 10 (API Key Management) still pending — PLAT-01 and PLAT-02 not implemented in backend. Not a blocker for v2.0 UI work.

## Session Continuity

Last session: 2026-03-05
Stopped at: Completed 16-01-PLAN.md — useBilling.ts TanStack Query billing hooks + /billing page with subscription card and plan catalog (Phase 16 in progress — 1/2 plans done)
Resume file: None — continue with Phase 16 Plan 02 (Stripe Checkout + Portal wiring)
