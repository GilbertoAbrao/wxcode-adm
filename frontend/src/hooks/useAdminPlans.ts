"use client";

/**
 * TanStack Query hooks for admin billing plan management endpoints.
 *
 * Covers: GET /admin/billing/plans (list — non-paginated array),
 *         POST /admin/billing/plans (create),
 *         PATCH /admin/billing/plans/{plan_id} (update),
 *         DELETE /admin/billing/plans/{plan_id} (delete/deactivate)
 *
 * All hooks use adminApiClient (NOT apiClient) — admin tokens are injected
 * automatically and are completely isolated from tenant user tokens.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApiClient } from "@/lib/admin-api-client";

// ---------------------------------------------------------------------------
// TypeScript interfaces (matching backend billing/schemas.py exactly)
// ---------------------------------------------------------------------------

export interface PlanResponse {
  id: string;
  name: string;
  slug: string;
  monthly_fee_cents: number;
  token_quota_5h: number;
  token_quota_weekly: number;
  overage_rate_cents_per_token: number;
  member_cap: number;
  max_projects: number;
  max_output_projects: number;
  max_storage_gb: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreatePlanData {
  name: string;
  slug: string;
  monthly_fee_cents: number;
  token_quota_5h: number;
  token_quota_weekly: number;
  overage_rate_cents_per_token?: number;
  member_cap?: number;
  max_projects?: number;
  max_output_projects?: number;
  max_storage_gb?: number;
}

export interface UpdatePlanData {
  name?: string;
  monthly_fee_cents?: number;
  token_quota_5h?: number;
  token_quota_weekly?: number;
  overage_rate_cents_per_token?: number;
  member_cap?: number;
  max_projects?: number;
  max_output_projects?: number;
  max_storage_gb?: number;
  is_active?: boolean;
}

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const ADMIN_PLAN_KEYS = {
  list: () => ["admin", "plans"] as const,
  detail: (planId: string) => ["admin", "plans", planId] as const,
};

// ---------------------------------------------------------------------------
// Query hooks
// ---------------------------------------------------------------------------

/**
 * Fetch the full list of billing plans (non-paginated).
 *
 * - Calls GET /admin/billing/plans
 * - Returns PlanResponse[] (array, not paginated)
 * - staleTime: 30s
 */
export function useAdminPlans() {
  return useQuery<PlanResponse[], Error>({
    queryKey: ADMIN_PLAN_KEYS.list(),
    queryFn: () => adminApiClient<PlanResponse[]>("/admin/billing/plans"),
    staleTime: 30_000,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

/**
 * Create a new billing plan.
 *
 * Calls POST /admin/billing/plans with CreatePlanData body.
 * On success: invalidates ["admin", "plans"] to refresh the list.
 *
 * Variables: CreatePlanData
 */
export function useCreatePlan() {
  const queryClient = useQueryClient();
  return useMutation<PlanResponse, Error, CreatePlanData>({
    mutationFn: (data) =>
      adminApiClient<PlanResponse>("/admin/billing/plans", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
    },
  });
}

/**
 * Update an existing billing plan (partial update).
 *
 * Calls PATCH /admin/billing/plans/{plan_id} with UpdatePlanData body.
 * On success: invalidates ["admin", "plans"] to refresh the list.
 *
 * Variables: { plan_id: string } & UpdatePlanData
 */
export function useUpdatePlan() {
  const queryClient = useQueryClient();
  return useMutation<PlanResponse, Error, { plan_id: string } & UpdatePlanData>({
    mutationFn: ({ plan_id, ...data }) =>
      adminApiClient<PlanResponse>(`/admin/billing/plans/${plan_id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
    },
  });
}

/**
 * Delete (soft-delete/deactivate) a billing plan.
 *
 * Calls DELETE /admin/billing/plans/{plan_id}.
 * On success: invalidates ["admin", "plans"] to refresh the list.
 *
 * Variables: { plan_id: string }
 */
export function useDeletePlan() {
  const queryClient = useQueryClient();
  return useMutation<unknown, Error, { plan_id: string }>({
    mutationFn: ({ plan_id }) =>
      adminApiClient(`/admin/billing/plans/${plan_id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
    },
  });
}
