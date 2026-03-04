/**
 * Shared Zod validation schemas for all auth forms.
 *
 * Used by signup, login, verify-email, forgot-password, reset-password,
 * MFA verify, and onboarding workspace pages.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Primitive schemas
// ---------------------------------------------------------------------------

export const emailSchema = z
  .string()
  .email("Please enter a valid email address");

export const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .max(128, "Password must be at most 128 characters");

// ---------------------------------------------------------------------------
// Form schemas
// ---------------------------------------------------------------------------

export const signupSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
});

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Password is required"),
});

export const forgotPasswordSchema = z.object({
  email: emailSchema,
});

export const resetPasswordSchema = z
  .object({
    new_password: passwordSchema,
    confirm_password: z.string(),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

export const verifyEmailSchema = z.object({
  code: z
    .string()
    .length(6, "Code must be 6 digits")
    .regex(/^\d{6}$/, "Code must be 6 digits"),
});

export const workspaceSchema = z.object({
  name: z
    .string()
    .min(2, "Workspace name must be at least 2 characters")
    .max(255, "Workspace name must be at most 255 characters"),
});

export const mfaCodeSchema = z.object({
  code: z
    .string()
    .min(6, "Code must be at least 6 characters")
    .max(11, "Code must be at most 11 characters"),
});

// ---------------------------------------------------------------------------
// Type aliases (inferred from schemas)
// ---------------------------------------------------------------------------

export type SignupFormData = z.infer<typeof signupSchema>;
export type LoginFormData = z.infer<typeof loginSchema>;
export type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordFormData = z.infer<typeof resetPasswordSchema>;
export type VerifyEmailFormData = z.infer<typeof verifyEmailSchema>;
export type WorkspaceFormData = z.infer<typeof workspaceSchema>;
export type MfaCodeFormData = z.infer<typeof mfaCodeSchema>;
