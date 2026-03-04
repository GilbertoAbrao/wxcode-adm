"use client";

/**
 * TanStack Query hooks for user account management.
 *
 * Covers: GET /users/me, PATCH /users/me, POST /users/me/avatar,
 *         POST /users/me/change-password, GET/DELETE /users/me/sessions
 *
 * Avatar upload bypasses apiClient to avoid Content-Type override issues with
 * multipart/form-data — uses a direct fetch call with Authorization header.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, API_BASE } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Request / Response type interfaces (matching backend Phase 7 schemas)
// ---------------------------------------------------------------------------

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  email_verified: boolean;
  mfa_enabled: boolean;
}

export interface UpdateProfileRequest {
  display_name?: string;
  email?: string;
}

export interface UpdateProfileResponse {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
}

export interface UploadAvatarResponse {
  avatar_url: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface ChangePasswordResponse {
  message: string;
}

export interface UserSession {
  id: string;
  device_info: string | null;
  ip_address: string | null;
  last_active_at: string;
  created_at: string;
  is_current: boolean;
}

export interface SessionListResponse {
  sessions: UserSession[];
}

// ---------------------------------------------------------------------------
// Query hooks
// ---------------------------------------------------------------------------

/**
 * Fetch the current authenticated user's profile.
 * staleTime: 30s — avoids excessive refetches while user edits profile.
 */
export function useCurrentUser() {
  return useQuery<UserProfile, Error>({
    queryKey: ["user", "me"],
    queryFn: () => apiClient<UserProfile>("/users/me"),
    staleTime: 30_000,
  });
}

/**
 * Fetch the current user's active sessions.
 * staleTime: 10s — sessions can change more frequently.
 */
export function useUserSessions() {
  return useQuery<SessionListResponse, Error>({
    queryKey: ["user", "sessions"],
    queryFn: () => apiClient<SessionListResponse>("/users/me/sessions"),
    staleTime: 10_000,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

/**
 * Update the current user's profile (display_name, email).
 * Invalidates ["user", "me"] on success.
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient();

  return useMutation<UpdateProfileResponse, Error, UpdateProfileRequest>({
    mutationFn: (data) =>
      apiClient<UpdateProfileResponse>("/users/me", {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", "me"] });
    },
  });
}

/**
 * Upload a new avatar image for the current user.
 *
 * Uses a direct fetch call (not apiClient) because multipart/form-data
 * requires the browser to set Content-Type with the boundary — apiClient
 * always sets "application/json" which breaks file uploads.
 *
 * Invalidates ["user", "me"] on success.
 */
export function useUploadAvatar() {
  const queryClient = useQueryClient();

  return useMutation<UploadAvatarResponse, Error, File>({
    mutationFn: async (file: File) => {
      const token = getAccessToken();
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_BASE}/api/v1/users/me/avatar`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body?.detail || "Avatar upload failed");
      }

      return response.json() as Promise<UploadAvatarResponse>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", "me"] });
    },
  });
}

/**
 * Change the current user's password.
 */
export function useChangePassword() {
  return useMutation<ChangePasswordResponse, Error, ChangePasswordRequest>({
    mutationFn: (data) =>
      apiClient<ChangePasswordResponse>("/users/me/change-password", {
        method: "POST",
        body: JSON.stringify(data),
      }),
  });
}

/**
 * Revoke a specific session by ID.
 * Invalidates ["user", "sessions"] on success.
 */
export function useRevokeSession() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (sessionId: string) =>
      apiClient<void>(`/users/me/sessions/${sessionId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", "sessions"] });
    },
  });
}

/**
 * Revoke all active sessions for the current user.
 * Invalidates ["user", "sessions"] on success.
 */
export function useRevokeAllSessions() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, void>({
    mutationFn: () =>
      apiClient<void>("/users/me/sessions", {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user", "sessions"] });
    },
  });
}
