"use client";

/**
 * Forgot password page — requests a password reset email.
 *
 * - Email form with zod validation
 * - On success: shows enumeration-safe success message (always shows success
 *   regardless of whether the email exists — prevents user enumeration attacks)
 * - Footer: link back to /login
 * - Uses GlowButton and GlowInput from Obsidian Studio design system
 */

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Mail, ArrowLeft } from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import { useForgotPassword } from "@/hooks/useAuth";
import { forgotPasswordSchema, type ForgotPasswordFormData } from "@/lib/validations";

export default function ForgotPasswordPage() {
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  const forgotPasswordMutation = useForgotPassword();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotPasswordFormData>({
    resolver: zodResolver(forgotPasswordSchema),
  });

  const onSubmit = (data: ForgotPasswordFormData) => {
    forgotPasswordMutation.mutate(data, {
      onSuccess: () => {
        setSubmittedEmail(data.email);
      },
    });
  };

  // Success state — show enumeration-safe message
  if (submittedEmail) {
    return (
      <div className="w-full max-w-sm mx-auto">
        <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
          <h1 className="text-xl font-semibold text-zinc-100 mb-2 text-center">
            Check your email
          </h1>
          <p className="text-sm text-zinc-500 mb-6 text-center">
            If an account exists for{" "}
            <span className="text-zinc-300 font-medium">{submittedEmail}</span>
            {", we've sent a password reset link. Check your email."}
          </p>

          <Link
            href="/login"
            className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium rounded-lg border transition-all duration-200 bg-zinc-800 text-zinc-200 border-zinc-700 hover:bg-zinc-700 hover:border-zinc-600 hover:text-zinc-100"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Login
          </Link>
        </div>
      </div>
    );
  }

  // Extract API error message
  const apiError = forgotPasswordMutation.error
    ? forgotPasswordMutation.error.message || "Something went wrong. Please try again."
    : null;

  return (
    <div className="w-full max-w-sm mx-auto">
      <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
        <h1 className="text-xl font-semibold text-zinc-100 mb-2 text-center">
          Reset your password
        </h1>
        <p className="text-sm text-zinc-500 mb-6 text-center">
          Enter your email and we&apos;ll send you a reset link
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {/* Email field */}
          <GlowInput
            {...register("email")}
            type="email"
            label="Email"
            placeholder="you@example.com"
            leftIcon={Mail}
            error={errors.email?.message}
            autoComplete="email"
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
            isLoading={forgotPasswordMutation.isPending}
            loadingText="Sending reset link..."
            size="md"
          >
            Send Reset Link
          </GlowButton>
        </form>

        {/* Footer */}
        <p className="mt-4 text-center text-sm text-zinc-500">
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 text-blue-400 hover:text-blue-300 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Login
          </Link>
        </p>
      </div>
    </div>
  );
}
