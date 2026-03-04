"use client";

/**
 * Reset password page — sets a new password using a reset token.
 *
 * - Reads ?token= from query params; shows error if missing
 * - New password + confirm password fields with zod match validation
 * - Password visibility toggle on new_password field
 * - On success: redirects to /login?reset=success
 * - On error: shows inline API error (e.g., "Reset link has expired")
 * - Uses GlowButton and GlowInput from Obsidian Studio design system
 *
 * Note: useSearchParams() requires Suspense boundary in Next.js App Router.
 * The inner component reads search params; the exported default wraps it.
 */

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Lock, Eye, EyeOff } from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import { useResetPassword } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api-client";
import { resetPasswordSchema, type ResetPasswordFormData } from "@/lib/validations";

// ---------------------------------------------------------------------------
// Inner component — reads useSearchParams (must be inside Suspense)
// ---------------------------------------------------------------------------

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [showPassword, setShowPassword] = useState(false);

  const resetPasswordMutation = useResetPassword();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetPasswordFormData>({
    resolver: zodResolver(resetPasswordSchema),
  });

  const onSubmit = (data: ResetPasswordFormData) => {
    if (!token) return;

    resetPasswordMutation.mutate(
      { token, new_password: data.new_password },
      {
        onSuccess: () => {
          router.push("/login?reset=success");
        },
      }
    );
  };

  // Extract API error message
  const apiError = resetPasswordMutation.error
    ? resetPasswordMutation.error instanceof ApiError
      ? resetPasswordMutation.error.message
      : resetPasswordMutation.error.message || "Something went wrong. Please try again."
    : null;

  // If no token, show inline error state
  if (!token) {
    return (
      <div className="w-full max-w-sm mx-auto">
        <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
          <h1 className="text-xl font-semibold text-zinc-100 mb-2 text-center">
            Invalid reset link
          </h1>
          <p className="text-sm text-zinc-500 mb-6 text-center">
            This password reset link is invalid or missing. Please request a new one.
          </p>
          <Link
            href="/forgot-password"
            className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium rounded-lg border transition-all duration-200 bg-zinc-800 text-zinc-200 border-zinc-700 hover:bg-zinc-700 hover:border-zinc-600 hover:text-zinc-100"
          >
            Request new reset link
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm mx-auto">
      <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
        <h1 className="text-xl font-semibold text-zinc-100 mb-6 text-center">
          Set new password
        </h1>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {/* New password field */}
          <GlowInput
            {...register("new_password")}
            type={showPassword ? "text" : "password"}
            label="New password"
            placeholder="At least 8 characters"
            leftIcon={Lock}
            rightIcon={showPassword ? EyeOff : Eye}
            onRightIconClick={() => setShowPassword((prev) => !prev)}
            error={errors.new_password?.message}
            autoComplete="new-password"
            fullWidth
          />

          {/* Confirm password field */}
          <GlowInput
            {...register("confirm_password")}
            type="password"
            label="Confirm password"
            placeholder="Repeat your new password"
            leftIcon={Lock}
            error={errors.confirm_password?.message}
            autoComplete="new-password"
            fullWidth
          />

          {/* API error message */}
          {apiError && (
            <p className="text-sm text-rose-400 text-center">{apiError}</p>
          )}

          {/* Submit button */}
          <GlowButton
            type="submit"
            fullWidth
            isLoading={resetPasswordMutation.isPending}
            loadingText="Resetting password..."
            size="md"
          >
            Reset Password
          </GlowButton>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export — wraps content in Suspense (required by Next.js)
// ---------------------------------------------------------------------------

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordContent />
    </Suspense>
  );
}
