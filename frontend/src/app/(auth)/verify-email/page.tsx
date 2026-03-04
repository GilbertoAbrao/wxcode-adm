"use client";

/**
 * Email verification page — shown after signup.
 *
 * - Reads ?email= from query params; redirects to /signup if missing
 * - 6-digit OTP input with submit button
 * - On success: redirects to /onboarding
 * - On error: shows inline API error (e.g., "Invalid or expired code")
 * - Resend code button with 60-second cooldown timer
 * - Uses GlowButton and GlowInput from Obsidian Studio design system
 *
 * Note: useSearchParams() requires Suspense boundary in Next.js App Router.
 * The inner component reads search params; the exported default wraps it.
 */

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound, RotateCcw } from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import { useVerifyEmail, useResendVerification } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api-client";
import { verifyEmailSchema, type VerifyEmailFormData } from "@/lib/validations";

const RESEND_COOLDOWN_SECONDS = 60;

// ---------------------------------------------------------------------------
// Inner component — reads useSearchParams (must be inside Suspense)
// ---------------------------------------------------------------------------

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get("email");

  const [resendCooldown, setResendCooldown] = useState(0);
  const [resendSuccess, setResendSuccess] = useState(false);

  const verifyEmailMutation = useVerifyEmail();
  const resendMutation = useResendVerification();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<VerifyEmailFormData>({
    resolver: zodResolver(verifyEmailSchema),
  });

  // Redirect to /signup if email param is missing
  useEffect(() => {
    if (!email) {
      router.replace("/signup");
    }
  }, [email, router]);

  // Countdown timer for resend cooldown
  useEffect(() => {
    if (resendCooldown <= 0) return;

    const interval = setInterval(() => {
      setResendCooldown((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [resendCooldown]);

  const onSubmit = (data: VerifyEmailFormData) => {
    if (!email) return;

    verifyEmailMutation.mutate(
      { email, code: data.code },
      {
        onSuccess: () => {
          router.push("/onboarding");
        },
      }
    );
  };

  const handleResend = () => {
    if (!email || resendCooldown > 0) return;

    resendMutation.mutate(
      { email },
      {
        onSuccess: () => {
          setResendSuccess(true);
          setResendCooldown(RESEND_COOLDOWN_SECONDS);
        },
      }
    );
  };

  // Extract API error messages
  const verifyApiError = verifyEmailMutation.error
    ? verifyEmailMutation.error instanceof ApiError
      ? verifyEmailMutation.error.message
      : verifyEmailMutation.error.message || "Something went wrong. Please try again."
    : null;

  const resendApiError = resendMutation.error
    ? resendMutation.error instanceof ApiError
      ? resendMutation.error.message
      : resendMutation.error.message || "Failed to resend code. Please try again."
    : null;

  if (!email) {
    return null; // Redirect in progress
  }

  return (
    <div className="w-full max-w-sm mx-auto">
      <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
        <h1 className="text-xl font-semibold text-zinc-100 mb-2 text-center">
          Verify your email
        </h1>
        <p className="text-sm text-zinc-500 mb-6 text-center">
          We sent a 6-digit code to{" "}
          <span className="text-zinc-300 font-medium">{email}</span>
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {/* OTP code input */}
          <GlowInput
            {...register("code")}
            type="text"
            inputMode="numeric"
            maxLength={6}
            placeholder="000000"
            leftIcon={KeyRound}
            error={errors.code?.message}
            autoFocus
            autoComplete="one-time-code"
            className="text-center tracking-widest text-lg font-mono"
            fullWidth
          />

          {/* API error message */}
          {verifyApiError && (
            <p className="text-sm text-rose-400 text-center">{verifyApiError}</p>
          )}

          {/* Submit button */}
          <GlowButton
            type="submit"
            fullWidth
            isLoading={verifyEmailMutation.isPending}
            loadingText="Verifying..."
            size="md"
          >
            Verify Email
          </GlowButton>
        </form>

        {/* Resend section */}
        <div className="mt-6 text-center space-y-2">
          <p className="text-sm text-zinc-500">Didn&apos;t receive the code?</p>

          {resendSuccess && resendCooldown > 0 && (
            <p className="text-sm text-emerald-400">New code sent!</p>
          )}

          {resendApiError && (
            <p className="text-sm text-rose-400">{resendApiError}</p>
          )}

          <GlowButton
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleResend}
            disabled={resendCooldown > 0 || resendMutation.isPending}
            isLoading={resendMutation.isPending}
            loadingText="Sending..."
            leftIcon={RotateCcw}
          >
            {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend Code"}
          </GlowButton>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export — wraps content in Suspense (required by Next.js)
// ---------------------------------------------------------------------------

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
