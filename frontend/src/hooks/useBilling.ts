"use client";

/**
 * TanStack Query hooks for billing management.
 *
 * Covers: GET /billing/plans, GET /billing/subscription,
 *         POST /billing/checkout, POST /billing/portal
 *
 * Tenant-scoped hooks (useSubscription, useCreateCheckout, useCreatePortal)
 * require an X-Tenant-ID header injected via the tenantHeaders helper.
 * They accept tenantId as a parameter and use enabled: !!tenantId to prevent
 * firing before tenant context resolves.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// TypeScript interfaces (matching backend schemas.py)
// ---------------------------------------------------------------------------

export interface BillingPlan {
  id: string;
  name: string;
  slug: string;
  monthly_fee_cents: number;
  token_quota_5h: number;
  token_quota_weekly: number;
  overage_rate_cents_per_token: number;
  member_cap: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Subscription {
  id: string;
  tenant_id: string;
  plan: BillingPlan;
  status: string; // "free", "active", "past_due", "canceled", "trialing"
  current_period_start: string | null;
  current_period_end: string | null;
  tokens_used_this_period: number;
  created_at: string;
  updated_at: string;
}

export interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export interface PortalResponse {
  portal_url: string;
}

// ---------------------------------------------------------------------------
// Query key constants — used by polling logic in billing/page.tsx
// ---------------------------------------------------------------------------

export const BILLING_QUERY_KEYS = {
  plans: ["billing", "plans"] as const,
  subscription: (tenantId: string) =>
    ["billing", "subscription", tenantId] as const,
};

// ---------------------------------------------------------------------------
// Internal helper: inject X-Tenant-ID header
// ---------------------------------------------------------------------------

function tenantHeaders(tenantId: string): { headers: Record<string, string> } {
  return { headers: { "X-Tenant-ID": tenantId } };
}

// ---------------------------------------------------------------------------
// Query hooks
// ---------------------------------------------------------------------------

/**
 * Fetch all active billing plans.
 * Does NOT require X-Tenant-ID — any authenticated user can view plans.
 * staleTime: 5 minutes
 */
export function usePlans() {
  return useQuery<BillingPlan[], Error>({
    queryKey: BILLING_QUERY_KEYS.plans,
    queryFn: () => apiClient<BillingPlan[]>("/billing/plans"),
    staleTime: 5 * 60_000,
  });
}

/**
 * Fetch the current subscription for the tenant.
 * Requires X-Tenant-ID header. Any tenant member can view.
 * staleTime: 30s
 *
 * Accepts an optional options param to support refetchInterval for polling
 * after Stripe Checkout return (post-checkout subscription status update).
 */
export function useSubscription(
  tenantId: string | undefined,
  options?: { refetchInterval?: number | false }
) {
  return useQuery<Subscription, Error>({
    queryKey: BILLING_QUERY_KEYS.subscription(tenantId ?? ""),
    queryFn: () =>
      apiClient<Subscription>("/billing/subscription", {
        ...tenantHeaders(tenantId!),
      }),
    enabled: !!tenantId,
    staleTime: 30_000,
    refetchInterval: options?.refetchInterval,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

/**
 * Create a Stripe Checkout session for the given plan.
 * Requires billing_access or Owner role.
 * Does NOT invalidate queries — the redirect will leave the page.
 * Returns CheckoutResponse with checkout_url and session_id.
 */
export function useCreateCheckout(tenantId: string | undefined) {
  // useQueryClient available for post-checkout query invalidation if needed
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const queryClient = useQueryClient();
  return useMutation<CheckoutResponse, Error, { plan_id: string }>({
    mutationFn: (data) =>
      apiClient<CheckoutResponse>("/billing/checkout", {
        method: "POST",
        body: JSON.stringify(data),
        ...tenantHeaders(tenantId!),
      }),
  });
}

/**
 * Open the Stripe Customer Portal for the current tenant.
 * Requires billing_access or Owner role.
 * Returns PortalResponse with portal_url.
 */
export function useCreatePortal(tenantId: string | undefined) {
  // useQueryClient available if post-portal invalidation needed
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const queryClient = useQueryClient();
  return useMutation<PortalResponse, Error, void>({
    mutationFn: () =>
      apiClient<PortalResponse>("/billing/portal", {
        method: "POST",
        ...tenantHeaders(tenantId!),
      }),
  });
}
