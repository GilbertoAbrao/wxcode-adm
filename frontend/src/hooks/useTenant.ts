"use client";

/**
 * TanStack Query hooks for tenant management.
 *
 * Covers: GET /tenants/me, GET /tenants/current/members,
 *         GET /tenants/current/invitations, POST /tenants/current/invitations,
 *         DELETE /tenants/current/invitations/{id},
 *         PATCH /tenants/current/members/{user_id}/role,
 *         DELETE /tenants/current/members/{user_id},
 *         PATCH /tenants/current/mfa-enforcement
 *
 * All tenant-scoped hooks (except useMyTenants) require an X-Tenant-ID header,
 * injected via the tenantHeaders helper. They accept tenantId as first parameter
 * and use enabled: !!tenantId to prevent firing before tenant context resolves.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// TypeScript interfaces (matching backend schemas.py)
// ---------------------------------------------------------------------------

export interface MyTenantItem {
  id: string;
  name: string;
  slug: string;
  role: string;
  billing_access: boolean;
  mfa_enforced?: boolean;
}

export interface MyTenantsResponse {
  tenants: MyTenantItem[];
}

export interface TenantMember {
  id: string;
  user_id: string;
  email: string;
  role: string;
  billing_access: boolean;
  created_at: string | null;
}

export interface TenantInvitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  created_at: string;
}

export interface InviteMemberRequest {
  email: string;
  role: string;
  billing_access?: boolean;
}

export interface ChangeRoleRequest {
  role: string;
  billing_access?: boolean;
}

export interface ChangeRoleVariables extends ChangeRoleRequest {
  user_id: string;
}

export interface MfaEnforcementRequest {
  enforce: boolean;
}

export interface MfaEnforcementResponse {
  mfa_enforced: boolean;
}

export interface MembershipResponse {
  id: string;
  user_id: string;
  email: string;
  role: string;
  billing_access: boolean;
  created_at: string;
}

export interface MessageResponse {
  message: string;
}

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
 * Fetch all tenants the current user belongs to.
 * Does NOT require X-Tenant-ID — used before tenant context is established.
 * staleTime: 60s
 */
export function useMyTenants() {
  return useQuery<MyTenantsResponse, Error>({
    queryKey: ["tenants", "me"],
    queryFn: () => apiClient<MyTenantsResponse>("/tenants/me"),
    staleTime: 60_000,
  });
}

/**
 * Fetch the member list for the current tenant.
 * Requires X-Tenant-ID header. Any tenant member can view.
 * staleTime: 15s
 */
export function useTenantMembers(tenantId: string | undefined) {
  return useQuery<TenantMember[], Error>({
    queryKey: ["tenant", tenantId, "members"],
    queryFn: () =>
      apiClient<TenantMember[]>("/tenants/current/members", {
        ...tenantHeaders(tenantId!),
      }),
    enabled: !!tenantId,
    staleTime: 15_000,
  });
}

/**
 * Fetch the pending invitations list for the current tenant.
 * Requires X-Tenant-ID header. Requires ADMIN role or above.
 * staleTime: 15s
 */
export function useTenantInvitations(tenantId: string | undefined) {
  return useQuery<TenantInvitation[], Error>({
    queryKey: ["tenant", tenantId, "invitations"],
    queryFn: () =>
      apiClient<TenantInvitation[]>("/tenants/current/invitations", {
        ...tenantHeaders(tenantId!),
      }),
    enabled: !!tenantId,
    staleTime: 15_000,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

/**
 * Invite a new member to the current tenant.
 * Requires ADMIN role or above.
 * Invalidates members and invitations queries on success.
 */
export function useInviteMember(tenantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<MembershipResponse, Error, InviteMemberRequest>({
    mutationFn: (data) =>
      apiClient<MembershipResponse>("/tenants/current/invitations", {
        method: "POST",
        body: JSON.stringify(data),
        ...tenantHeaders(tenantId!),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["tenant", tenantId, "members"],
      });
      queryClient.invalidateQueries({
        queryKey: ["tenant", tenantId, "invitations"],
      });
    },
  });
}

/**
 * Cancel a pending invitation by ID.
 * Requires ADMIN role or above.
 * Invalidates invitations query on success.
 */
export function useCancelInvitation(tenantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<MessageResponse, Error, string>({
    mutationFn: (invitationId: string) =>
      apiClient<MessageResponse>(
        `/tenants/current/invitations/${invitationId}`,
        {
          method: "DELETE",
          ...tenantHeaders(tenantId!),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["tenant", tenantId, "invitations"],
      });
    },
  });
}

/**
 * Change the role (and optionally billing access) of a tenant member.
 * Requires ADMIN role or above.
 * Invalidates members query on success.
 */
export function useChangeRole(tenantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<MembershipResponse, Error, ChangeRoleVariables>({
    mutationFn: ({ user_id, role, billing_access }) =>
      apiClient<MembershipResponse>(
        `/tenants/current/members/${user_id}/role`,
        {
          method: "PATCH",
          body: JSON.stringify({ role, billing_access }),
          ...tenantHeaders(tenantId!),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["tenant", tenantId, "members"],
      });
    },
  });
}

/**
 * Remove a member from the current tenant.
 * Requires ADMIN role or above.
 * Invalidates members query on success.
 */
export function useRemoveMember(tenantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<MessageResponse, Error, string>({
    mutationFn: (userId: string) =>
      apiClient<MessageResponse>(`/tenants/current/members/${userId}`, {
        method: "DELETE",
        ...tenantHeaders(tenantId!),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["tenant", tenantId, "members"],
      });
    },
  });
}

/**
 * Toggle MFA enforcement for the current tenant.
 * Requires OWNER role.
 * Invalidates ["tenants", "me"] on success (mfa_enforced is on the tenant).
 */
export function useMfaEnforcement(tenantId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<MfaEnforcementResponse, Error, MfaEnforcementRequest>({
    mutationFn: (data) =>
      apiClient<MfaEnforcementResponse>("/tenants/current/mfa-enforcement", {
        method: "PATCH",
        body: JSON.stringify(data),
        ...tenantHeaders(tenantId!),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tenants", "me"] });
    },
  });
}
