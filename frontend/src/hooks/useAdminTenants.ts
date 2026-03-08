"use client";

/**
 * TanStack Query hooks for admin tenant management endpoints.
 *
 * Covers: GET /admin/tenants (paginated + filterable),
 *         GET /admin/tenants/{id} (tenant detail),
 *         POST /admin/tenants/{id}/suspend,
 *         POST /admin/tenants/{id}/reactivate,
 *         PUT  /admin/tenants/{id}/claude-token,
 *         DELETE /admin/tenants/{id}/claude-token,
 *         PATCH /admin/tenants/{id}/claude-config,
 *         POST /admin/tenants/{id}/activate
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

export interface TenantDetailResponse {
  id: string;
  name: string;
  slug: string;
  is_suspended: boolean;
  is_deleted: boolean;
  mfa_enforced: boolean;
  wxcode_url: string | null;
  plan_name: string | null;
  plan_slug: string | null;
  subscription_status: string | null;
  member_count: number;
  created_at: string;
  updated_at: string;
  // Phase 20 wxcode engine fields
  status: string;                            // "pending_setup" | "active" | "suspended" | "cancelled"
  database_name: string | null;
  default_target_stack: string;
  neo4j_enabled: boolean;
  claude_default_model: string;
  claude_max_concurrent_sessions: number;
  claude_monthly_token_budget: number | null; // null = unlimited
  has_claude_token: boolean;
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
  detail: (tenantId: string) => ["admin", "tenants", tenantId] as const,
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

/**
 * Fetch full detail for a single tenant by ID.
 *
 * - Only enabled when tenantId is truthy
 * - staleTime: 30s
 */
export function useAdminTenantDetail(tenantId: string | null) {
  return useQuery<TenantDetailResponse, Error>({
    queryKey: ADMIN_TENANT_KEYS.detail(tenantId ?? ""),
    queryFn: () =>
      adminApiClient<TenantDetailResponse>(`/admin/tenants/${tenantId}`),
    enabled: !!tenantId,
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

/**
 * Set (or replace) the Claude OAuth token for a tenant.
 *
 * Calls PUT /admin/tenants/{tenant_id}/claude-token with { token, reason }.
 * On success: invalidates all admin tenant queries.
 *
 * Variables: { tenant_id: string; token: string; reason: string }
 */
export function useSetClaudeToken() {
  const queryClient = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { tenant_id: string; token: string; reason: string }
  >({
    mutationFn: ({ tenant_id, token, reason }) =>
      adminApiClient(`/admin/tenants/${tenant_id}/claude-token`, {
        method: "PUT",
        body: JSON.stringify({ token, reason }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
}

/**
 * Revoke the Claude OAuth token for a tenant.
 *
 * Calls DELETE /admin/tenants/{tenant_id}/claude-token with body { reason }.
 * On success: invalidates all admin tenant queries.
 *
 * Variables: { tenant_id: string; reason: string }
 */
export function useRevokeClaudeToken() {
  const queryClient = useQueryClient();
  return useMutation<unknown, Error, { tenant_id: string; reason: string }>({
    mutationFn: ({ tenant_id, reason }) =>
      adminApiClient(`/admin/tenants/${tenant_id}/claude-token`, {
        method: "DELETE",
        body: JSON.stringify({ reason } satisfies AdminActionRequest),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
}

/**
 * Update Claude configuration for a tenant.
 *
 * Calls PATCH /admin/tenants/{tenant_id}/claude-config with optional fields.
 * Only includes fields that are provided (partial update).
 * On success: invalidates all admin tenant queries.
 *
 * Variables: { tenant_id: string; claude_default_model?: string;
 *   claude_max_concurrent_sessions?: number; claude_monthly_token_budget?: number }
 */
export interface ClaudeConfigUpdate {
  claude_default_model?: string;
  claude_max_concurrent_sessions?: number;
  claude_monthly_token_budget?: number;
}

export function useUpdateClaudeConfig() {
  const queryClient = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { tenant_id: string } & ClaudeConfigUpdate
  >({
    mutationFn: ({ tenant_id, ...configFields }) =>
      adminApiClient(`/admin/tenants/${tenant_id}/claude-config`, {
        method: "PATCH",
        body: JSON.stringify(configFields),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
}

/**
 * Update wxcode provisioning config for a tenant.
 *
 * Calls PATCH /admin/tenants/{tenant_id}/wxcode-config.
 * On success: invalidates all admin tenant queries.
 */
export interface WxcodeConfigUpdate {
  database_name?: string;
  default_target_stack?: string;
  neo4j_enabled?: boolean;
}

export function useUpdateWxcodeConfig() {
  const queryClient = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { tenant_id: string } & WxcodeConfigUpdate
  >({
    mutationFn: ({ tenant_id, ...configFields }) =>
      adminApiClient(`/admin/tenants/${tenant_id}/wxcode-config`, {
        method: "PATCH",
        body: JSON.stringify(configFields),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
}

/**
 * Activate a tenant that is in pending_setup status.
 *
 * Calls POST /admin/tenants/{tenant_id}/activate with { reason }.
 * On success: invalidates all admin tenant queries.
 *
 * Variables: { tenant_id: string; reason: string }
 */
export function useActivateTenant() {
  const queryClient = useQueryClient();
  return useMutation<unknown, Error, { tenant_id: string; reason: string }>({
    mutationFn: ({ tenant_id, reason }) =>
      adminApiClient(`/admin/tenants/${tenant_id}/activate`, {
        method: "POST",
        body: JSON.stringify({ reason } satisfies AdminActionRequest),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
  });
}
