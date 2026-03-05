"use client";

/**
 * TanStack Query mutation hooks for admin auth endpoints.
 *
 * Uses adminApiClient (NOT apiClient) to ensure admin tokens are used.
 * Admin auth endpoints are completely isolated from tenant user auth.
 */

import { useMutation } from "@tanstack/react-query";
import { adminApiClient } from "@/lib/admin-api-client";
import { getAdminRefreshToken } from "@/lib/admin-auth";

// ---------------------------------------------------------------------------
// Request / Response type interfaces (matching backend admin schemas)
// ---------------------------------------------------------------------------

export interface AdminLoginRequest {
  email: string;
  password: string;
}

export interface AdminTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AdminLogoutRequest {
  refresh_token: string;
}

export interface AdminLogoutResponse {
  message: string;
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

/**
 * Admin login mutation — calls POST /admin/login with skipAuth: true.
 * No admin token required to log in.
 */
export function useAdminLogin() {
  return useMutation<AdminTokenResponse, Error, AdminLoginRequest>({
    mutationFn: (data) =>
      adminApiClient<AdminTokenResponse>("/admin/login", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuth: true,
      }),
  });
}

/**
 * Admin logout mutation — calls POST /admin/logout with the admin refresh token.
 * Requires admin auth (token injected automatically by adminApiClient).
 */
export function useAdminLogout() {
  return useMutation<AdminLogoutResponse, Error, void>({
    mutationFn: () => {
      const refreshToken = getAdminRefreshToken();
      return adminApiClient<AdminLogoutResponse>("/admin/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken ?? "" }),
        // Requires auth — token injected automatically
      });
    },
  });
}
