"use client";

/**
 * TanStack Query mutation hooks for all auth endpoints.
 *
 * All public auth endpoints use skipAuth: true — no token required.
 * useCreateWorkspace and useLogout require auth (token injected automatically).
 */

import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Request / Response type interfaces (matching backend auth schemas)
// ---------------------------------------------------------------------------

export interface SignupRequest {
  email: string;
  password: string;
}

export interface SignupResponse {
  message: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  token_type?: string;
  mfa_required: boolean;
  mfa_token?: string;
  mfa_setup_required: boolean;
  wxcode_redirect_url?: string;
  wxcode_code?: string;
}

export interface VerifyEmailRequest {
  email: string;
  code: string;
}

export interface VerifyEmailResponse {
  message: string;
}

export interface ResendVerificationRequest {
  email: string;
}

export interface ResendVerificationResponse {
  message: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ForgotPasswordResponse {
  message: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

export interface ResetPasswordResponse {
  message: string;
}

export interface MfaVerifyRequest {
  mfa_token: string;
  code: string;
  trust_device: boolean;
}

export interface MfaVerifyResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  wxcode_redirect_url?: string;
  wxcode_code?: string;
}

export interface CreateWorkspaceRequest {
  name: string;
}

export interface CreateWorkspaceResponse {
  id: string;
  name: string;
}

export interface LogoutRequest {
  refresh_token: string;
}

export interface LogoutResponse {
  message: string;
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useSignup() {
  return useMutation<SignupResponse, Error, SignupRequest>({
    mutationFn: (data) =>
      apiClient<SignupResponse>("/auth/signup", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuth: true,
      }),
  });
}

export function useLogin() {
  return useMutation<LoginResponse, Error, LoginRequest>({
    mutationFn: (data) =>
      apiClient<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuth: true,
      }),
  });
}

export function useVerifyEmail() {
  return useMutation<VerifyEmailResponse, Error, VerifyEmailRequest>({
    mutationFn: (data) =>
      apiClient<VerifyEmailResponse>("/auth/verify-email", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuth: true,
      }),
  });
}

export function useResendVerification() {
  return useMutation<ResendVerificationResponse, Error, ResendVerificationRequest>({
    mutationFn: (data) =>
      apiClient<ResendVerificationResponse>("/auth/resend-verification", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuth: true,
      }),
  });
}

export function useForgotPassword() {
  return useMutation<ForgotPasswordResponse, Error, ForgotPasswordRequest>({
    mutationFn: (data) =>
      apiClient<ForgotPasswordResponse>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuth: true,
      }),
  });
}

export function useResetPassword() {
  return useMutation<ResetPasswordResponse, Error, ResetPasswordRequest>({
    mutationFn: (data) =>
      apiClient<ResetPasswordResponse>("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuth: true,
      }),
  });
}

export function useMfaVerify() {
  return useMutation<MfaVerifyResponse, Error, MfaVerifyRequest>({
    mutationFn: (data) =>
      apiClient<MfaVerifyResponse>("/auth/mfa/verify", {
        method: "POST",
        body: JSON.stringify(data),
        skipAuth: true,
      }),
  });
}

export function useCreateWorkspace() {
  return useMutation<CreateWorkspaceResponse, Error, CreateWorkspaceRequest>({
    mutationFn: (data) =>
      apiClient<CreateWorkspaceResponse>("/onboarding/workspace", {
        method: "POST",
        body: JSON.stringify(data),
        // Requires auth — token injected automatically
      }),
  });
}

export function useLogout() {
  return useMutation<LogoutResponse, Error, LogoutRequest>({
    mutationFn: (data) =>
      apiClient<LogoutResponse>("/auth/logout", {
        method: "POST",
        body: JSON.stringify(data),
        // Requires auth — token injected automatically
      }),
  });
}
