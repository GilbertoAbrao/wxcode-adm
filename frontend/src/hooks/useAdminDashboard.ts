"use client";

/**
 * TanStack Query hook for admin MRR dashboard endpoint.
 *
 * Covers: GET /admin/dashboard/mrr
 *
 * Uses adminApiClient (NOT apiClient) — admin tokens are injected automatically
 * and are completely isolated from tenant user tokens.
 */

import { useQuery } from "@tanstack/react-query";
import { adminApiClient } from "@/lib/admin-api-client";

// ---------------------------------------------------------------------------
// TypeScript interfaces (matching backend admin/schemas.py exactly)
// ---------------------------------------------------------------------------

export interface PlanDistributionItem {
  plan_slug: string;
  plan_name: string;
  count: number;
}

export interface MRRTrendPoint {
  date: string;
  mrr_cents: number;
  active_count: number;
}

export interface MRRDashboardResponse {
  active_subscription_count: number;
  mrr_cents: number;
  plan_distribution: PlanDistributionItem[];
  canceled_count_30d: number;
  churn_rate: number;
  trend: MRRTrendPoint[];
  computed_at: string;
}

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const ADMIN_DASHBOARD_KEYS = {
  mrr: () => ["admin", "dashboard", "mrr"] as const,
};

// ---------------------------------------------------------------------------
// Query hook
// ---------------------------------------------------------------------------

/**
 * Fetch MRR dashboard data from /admin/dashboard/mrr.
 *
 * staleTime: 60s — dashboard data changes less frequently than list queries.
 */
export function useAdminDashboard() {
  return useQuery<MRRDashboardResponse, Error>({
    queryKey: ADMIN_DASHBOARD_KEYS.mrr(),
    queryFn: () => adminApiClient<MRRDashboardResponse>("/admin/dashboard/mrr"),
    staleTime: 60_000,
  });
}
