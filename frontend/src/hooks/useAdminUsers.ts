"use client";

/**
 * TanStack Query hooks for admin user management endpoints.
 *
 * Uses adminApiClient (NOT apiClient) — all requests use admin tokens.
 *
 * Exports:
 *   - useAdminUsers(params)        — paginated user list with optional email search
 *   - useAdminUserDetail(userId)   — full user profile with memberships + sessions
 *   - useBlockUser()               — mutation: POST /admin/users/{id}/block
 *   - useUnblockUser()             — mutation: POST /admin/users/{id}/unblock
 *   - useForcePasswordReset()      — mutation: POST /admin/users/{id}/force-reset
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApiClient } from "@/lib/admin-api-client";

// ---------------------------------------------------------------------------
// TypeScript interfaces (matching backend admin/schemas.py exactly)
// ---------------------------------------------------------------------------

export interface UserListItem {
  id: string;
  email: string;
  display_name: string | null;
  email_verified: boolean;
  is_active: boolean;
  mfa_enabled: boolean;
  created_at: string;
}

export interface UserListResponse {
  items: UserListItem[];
  total: number;
}

export interface UserMembershipItem {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: string;
  billing_access: boolean;
  is_blocked: boolean;
}

export interface UserSessionItem {
  id: string;
  device_type: string | null;
  browser_name: string | null;
  ip_address: string | null;
  city: string | null;
  last_active_at: string | null;
}

export interface UserDetailResponse {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  email_verified: boolean;
  is_active: boolean;
  is_superuser: boolean;
  mfa_enabled: boolean;
  created_at: string;
  updated_at: string;
  memberships: UserMembershipItem[];
  sessions: UserSessionItem[];
}

export interface UserBlockRequest {
  tenant_id: string;
  reason: string;
}

export interface UserUnblockRequest {
  tenant_id: string;
  reason: string;
}

export interface ForceResetResponse {
  message: string;
  user_id: string;
}

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const ADMIN_USER_KEYS = {
  list: (params: { limit?: number; offset?: number; q?: string | null }) =>
    ["admin", "users", params] as const,
  detail: (userId: string) => ["admin", "users", userId] as const,
};

// ---------------------------------------------------------------------------
// Query hooks
// ---------------------------------------------------------------------------

/**
 * Paginated user list with optional email/name search.
 *
 * - Passes `q` to the backend for case-insensitive email/display_name search
 * - Always enabled (shows all users when q is empty/null)
 * - staleTime: 30s to reduce redundant requests during search interactions
 */
export function useAdminUsers(params: {
  limit?: number;
  offset?: number;
  q?: string | null;
}) {
  return useQuery<UserListResponse, Error>({
    queryKey: ADMIN_USER_KEYS.list(params),
    queryFn: async () => {
      const searchParams = new URLSearchParams();

      if (params.limit !== undefined) {
        searchParams.set("limit", String(params.limit));
      }
      if (params.offset !== undefined && params.offset > 0) {
        searchParams.set("offset", String(params.offset));
      }
      if (params.q) {
        searchParams.set("q", params.q);
      }

      const qs = searchParams.toString();
      const endpoint = `/admin/users${qs ? `?${qs}` : ""}`;
      return adminApiClient<UserListResponse>(endpoint);
    },
    staleTime: 30 * 1000,
  });
}

/**
 * Full user detail including memberships and sessions.
 *
 * - Only enabled when userId is truthy
 * - staleTime: 30s
 */
export function useAdminUserDetail(userId: string | null) {
  return useQuery<UserDetailResponse, Error>({
    queryKey: ADMIN_USER_KEYS.detail(userId ?? ""),
    queryFn: () =>
      adminApiClient<UserDetailResponse>(`/admin/users/${userId}`),
    enabled: !!userId,
    staleTime: 30 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

/**
 * Block a user in a specific tenant.
 *
 * Variables: { user_id, tenant_id, reason }
 * On success: invalidates all ["admin", "users"] queries (list + detail).
 */
export function useBlockUser() {
  const queryClient = useQueryClient();

  return useMutation<
    void,
    Error,
    { user_id: string; tenant_id: string; reason: string }
  >({
    mutationFn: ({ user_id, tenant_id, reason }) =>
      adminApiClient(`/admin/users/${user_id}/block`, {
        method: "POST",
        body: JSON.stringify({ tenant_id, reason } satisfies UserBlockRequest),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

/**
 * Unblock a user in a specific tenant.
 *
 * Variables: { user_id, tenant_id, reason }
 * On success: invalidates all ["admin", "users"] queries (list + detail).
 */
export function useUnblockUser() {
  const queryClient = useQueryClient();

  return useMutation<
    void,
    Error,
    { user_id: string; tenant_id: string; reason: string }
  >({
    mutationFn: ({ user_id, tenant_id, reason }) =>
      adminApiClient(`/admin/users/${user_id}/unblock`, {
        method: "POST",
        body: JSON.stringify({ tenant_id, reason } satisfies UserUnblockRequest),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

/**
 * Force a password reset for a user.
 *
 * Invalidates all sessions and sends a password reset email.
 *
 * Variables: { user_id, reason }
 * On success: invalidates all ["admin", "users"] queries (list + detail).
 */
export function useForcePasswordReset() {
  const queryClient = useQueryClient();

  return useMutation<
    ForceResetResponse,
    Error,
    { user_id: string; reason: string }
  >({
    mutationFn: ({ user_id, reason }) =>
      adminApiClient<ForceResetResponse>(
        `/admin/users/${user_id}/force-reset`,
        {
          method: "POST",
          body: JSON.stringify({ reason }),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}
