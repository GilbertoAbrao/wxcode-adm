"use client";

/**
 * TanStack Query hook for admin audit log endpoints.
 *
 * Covers: GET /admin/audit-logs/ (paginated + filterable)
 *
 * Uses adminApiClient (NOT apiClient) — admin tokens are injected automatically
 * and are completely isolated from tenant user tokens.
 */

import { useQuery } from "@tanstack/react-query";
import { adminApiClient } from "@/lib/admin-api-client";

// ---------------------------------------------------------------------------
// TypeScript interfaces (matching backend audit/schemas.py exactly)
// ---------------------------------------------------------------------------

export interface AuditLogItem {
  id: string;
  created_at: string;
  actor_id: string | null;
  tenant_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip_address: string | null;
  details: Record<string, unknown>;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
}

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const ADMIN_AUDIT_KEYS = {
  list: (params: {
    limit?: number;
    offset?: number;
    action?: string | null;
    tenant_id?: string | null;
    actor_id?: string | null;
  }) => ["admin", "audit-logs", params] as const,
};

// ---------------------------------------------------------------------------
// Query hook
// ---------------------------------------------------------------------------

/**
 * Fetch a paginated, filterable list of audit log entries.
 *
 * Builds a URL with URLSearchParams, skipping null/undefined/empty values so that
 * the query key changes only when filters actually change — ensuring proper
 * cache keying per filter combination.
 *
 * staleTime: 30s
 */
export function useAdminAuditLogs(params: {
  limit?: number;
  offset?: number;
  action?: string | null;
  tenant_id?: string | null;
  actor_id?: string | null;
}) {
  return useQuery<AuditLogListResponse, Error>({
    queryKey: ADMIN_AUDIT_KEYS.list(params),
    queryFn: () => {
      const searchParams = new URLSearchParams();
      if (params.limit != null) {
        searchParams.set("limit", String(params.limit));
      }
      if (params.offset != null) {
        searchParams.set("offset", String(params.offset));
      }
      if (params.action != null && params.action !== "") {
        searchParams.set("action", params.action);
      }
      if (params.tenant_id != null && params.tenant_id !== "") {
        searchParams.set("tenant_id", params.tenant_id);
      }
      if (params.actor_id != null && params.actor_id !== "") {
        searchParams.set("actor_id", params.actor_id);
      }
      const qs = searchParams.toString();
      // Trailing slash required — backend audit_router prefix is "/admin/audit-logs"
      // and the list endpoint is "/", so the full path is "/admin/audit-logs/"
      const endpoint = qs ? `/admin/audit-logs/?${qs}` : "/admin/audit-logs/";
      return adminApiClient<AuditLogListResponse>(endpoint);
    },
    staleTime: 30_000,
  });
}
