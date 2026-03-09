# Phase 26: Billing UI Dual Quota Fix - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix tenant-facing billing UI (`useBilling.ts` + `billing/page.tsx`) and test fixtures (`conftest.py`) to use dual quota fields (`token_quota_5h`, `token_quota_weekly`) after migration 010 removed the single `token_quota` column. Gap closure for BREAK-01 and FLOW-DISPLAY-01.

</domain>

<decisions>
## Implementation Decisions

### Quota display layout — Plan cards
- Two separate lines in plan cards (not combined into one line)
- Each quota on its own line with its window label
- Both lines always visible, even if one is unlimited

### Quota display layout — Current Plan section
- Show quota limits as text only (no usage progress bars)
- Remove the existing usage bar since backend `tokens_used_this_period` doesn't map to per-window usage
- Display both quota values (5h and weekly) as text info

### Unlimited/null handling
- When both quotas are 0 or null, show "Unlimited" for both lines (consistent with current behavior)
- When only one is unlimited, still show both lines — one with the limit, one with "Unlimited"
- Always show both quota lines regardless of values

### Claude's Discretion
- Quota label wording (technical vs descriptive — fit the card's compact style)
- Exact spacing and icon choice for the two quota lines
- How to phrase the "Current Plan" quota display (text-only, no bars)

</decisions>

<specifics>
## Specific Ideas

- Backend `PlanResponse` already returns `token_quota_5h` and `token_quota_weekly` (no backend changes needed for plan data)
- Backend subscription response still has `tokens_used_this_period` as a single value — per-window usage tracking is a future concern
- The `BillingPlan` TypeScript interface in `useBilling.ts` must replace `token_quota: number` with `token_quota_5h: number` + `token_quota_weekly: number`
- `conftest.py` Plan fixture uses `token_quota=10000` — must update to `token_quota_5h` + `token_quota_weekly`

</specifics>

<deferred>
## Deferred Ideas

- Per-window usage tracking (5h usage vs weekly usage) with dual progress bars — requires backend changes to track usage per window
- Adding `max_projects`, `max_output_projects`, `max_storage_gb` to tenant-facing billing display — separate scope

</deferred>

---

*Phase: 26-billing-ui-dual-quota-fix*
*Context gathered: 2026-03-09*
