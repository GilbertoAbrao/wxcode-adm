---
status: complete
phase: 23-admin-ui-claude-management
source: [23-03-SUMMARY.md, 23-04-SUMMARY.md, 23-05-SUMMARY.md, 23-06-SUMMARY.md]
started: 2026-03-08T18:45:00Z
updated: 2026-03-08T19:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Tenant Detail — Dual Budget Display
expected: On the tenant detail page (/admin/tenants/{id}), the WXCODE Integration card shows "5h Budget" and "Weekly Budget" rows (NOT "Monthly Budget"). Each shows the configured value with " tokens" suffix, or "Unlimited" if not set.
result: pass

### 2. Tenant Detail — Dual Budget Edit
expected: Clicking "Edit" on Claude Configuration reveals two budget inputs labeled "5h Budget (0 = unlimited)" and "Weekly Budget (0 = unlimited)". Entering values in each and saving sends a PATCH with both fields. The displayed values update after save. Setting either to 0 shows "Unlimited".
result: pass

### 3. Admin Session Persistence
expected: After logging in to the admin panel, refreshing the browser page (F5 or Ctrl+R) does NOT redirect to the login page. The admin remains authenticated and sees the same page content. No re-login required.
result: pass

### 4. Plan Inactivate Toggle
expected: On the /admin/plans page, each plan row has an "Inactivate" button (amber text) in the Actions column. Clicking it toggles the plan to inactive — the button changes to "Activate" (green text) and the status badge changes to "Inactive". Clicking "Activate" toggles it back to active.
result: pass

### 5. Delete Inactive Plan
expected: When a plan is inactive, a "Delete" button appears in the Actions column. Clicking it shows a browser confirmation dialog. Confirming deletes the plan from the table. Active plans do NOT show a Delete button.
result: pass

### 6. Delete Plan with Tenant Guard
expected: If you try to delete an inactive plan that has tenants subscribed to it, the backend returns an error message like "Cannot delete plan — N tenant(s) are currently using it" which is shown via a browser alert. The plan is NOT deleted.
result: pass

### 7. Plans Table — Dual Quota Columns
expected: The plans table on /admin/plans shows "Quota 5h" and "Quota Weekly" columns (NOT a single "Token Quota" column). Each plan row displays both quota values.
result: pass

### 8. Create Plan — Dual Quota Inputs
expected: The "Create Plan" form has two quota inputs: "Token Quota (5h)" and "Token Quota (Weekly)". Submitting creates a plan with both quota values visible in the table.
result: pass

### 9. Edit Plan — Dual Quota Inputs
expected: Clicking "Edit" on a plan row shows an inline edit form with two quota inputs pre-populated with the plan's current quota values. Changing one quota and saving only sends the modified field.
result: pass

### 10. WXCODE Provisioning Section (pending_setup tenant)
expected: On the tenant detail page for a tenant with status "pending_setup", a "WXCODE Provisioning" section is visible below Claude Configuration. It shows Database Name (amber "Not configured" if null), Target Stack, and Neo4j Enabled status. An "Edit" button reveals an inline form with inputs for all three fields.
result: pass

### 11. WXCODE Provisioning — Set Database Name and Activate
expected: In the WXCODE Provisioning edit form, enter a database name (e.g. "tenant_test_db"), save it. The display updates to show the configured database name. Then clicking "Activate Tenant" should succeed and change the tenant status to "active" (no more MISSING_DATABASE_NAME error).
result: pass

## Summary

total: 11
passed: 11
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
