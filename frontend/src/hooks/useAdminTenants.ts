"use client";

/**
 * TanStack Query hooks for admin tenant management endpoints.
 *
 * Covers: GET /admin/tenants (paginated + filterable),
 *         POST /admin/tenants/{id}/suspend,
 *         POST /admin/tenants/{id}/reactivate
 *
 * All hooks use adminApiClient (NOT apiClient) — admin tokens are injected
 * automatically and are completely isolated from tenant user tokens.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApiClient } from "@/lib/admin-api-client";

// ---------------------------------------------------------------------------
// TypeScript interfaces (matching backend admin/schemas.py exactly)
// ---------------------------------------------------------------------------

export interface TenantListItem {
  id: string;
  name: string;
  slug: string;
  is_suspended: boolean;
  is_deleted: boolean;
  plan_name: string | null;
  plan_slug: string | null;
  member_count: number;
  created_at: string;
}

export interface TenantListResponse {
  items: TenantListItem[];
  total: number;
}

export interface AdminActionRequest {
  reason: string;
}

// ---------------------------------------------------------------------------
// Query key constants — used for targeted invalidation on mutations
// ---------------------------------------------------------------------------

export const ADMIN_TENANT_KEYS = {
  list: (params: {
    limit?: number;
    offset?: number;
    plan_slug?: string | null;
    status?: string | null;
  }) => ["admin", "tenants", params] as const,
};

// ---------------------------------------------------------------------------
// Query hooks
// ---------------------------------------------------------------------------

/**
 * Fetch a paginated, filterable list of tenants.
 *
 * Builds a URL with URLSearchParams, skipping null/undefined params so that
 * the query key changes only when filters actually change — ensuring proper
 * cache keying per filter combination.
 *
 * staleTime: 30s
 */
export function useAdminTenants(params: {
  limit?: number;
  offset?: number;
  plan_slug?: string | null;
  status?: string | null;
}) {
  return useQuery<TenantListResponse, Error>({
    queryKey: ADMIN_TENANT_KEYS.list(params),
    queryFn: () => {
      const searchParams = new URLSearchParams();
      if (params.limit != null) {
        searchParams.set("limit", String(params.limit));
      }
      if (params.offset != null) {
        searchParams.set("offset", String(params.offset));
      }
      if (params.plan_slug != null && params.plan_slug !== "") {
        searchParams.set("plan_slug", params.plan_slug);
      }
      if (params.status != null && params.status !== "") {
        searchParams.set("status", params.status);
      }
      const qs = searchParams.toString();
      const endpoint = qs ? `/admin/tenants?${qs}` : "/admin/tenants";
      return adminApiClient<TenantListResponse>(endpoint);
    },
    staleTime: 30_000,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

/**
 * Suspend an active tenant.
 *
 * Calls POST /admin/tenants/{tenant_id}/suspend with { reason }.
 * On success: invalidates all admin tenant queries to refresh the list.
 *
 * Variables: { tenant_id: string, reason: string }
 */
export function useSuspendTenant() {
  const queryClient = useQueryClient();
  return useMutation<unknown, Error, { tenant_id: string; reason: string }>({
    mutationFn: ({ tenant_id, reason }) =>
      adminApiClient(`/admin/tenants/${tenant_id}/suspend`, {
        method: "POST",
        body: JSON.stringify({ reason } satisfies AdminActionRequest),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
}

/**
 * Reactivate a suspended tenant.
 *
 * Calls POST /admin/tenants/{tenant_id}/reactivate with { reason }.
 * On success: invalidates all admin tenant queries to refresh the list.
 *
 * Variables: { tenant_id: string, reason: string }
 */
export function useReactivateTenant() {
  const queryClient = useQueryClient();
  return useMutation<unknown, Error, { tenant_id: string; reason: string }>({
    mutationFn: ({ tenant_id, reason }) =>
      adminApiClient(`/admin/tenants/${tenant_id}/reactivate`, {
        method: "POST",
        body: JSON.stringify({ reason } satisfies AdminActionRequest),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
}
