"use client";

/**
 * MFA verify page — completes two-factor authentication after login.
 *
 * - Reads mfa_token from ?token= search param (if missing, redirects to /login)
 * - TOTP mode: 6-digit numeric code from authenticator app
 * - Backup mode: 8 or 11-character backup code (toggle via link)
 * - Trust device checkbox: 30-day device trust
 * - On success: stores tokens and redirects to wxcode or dashboard
 * - Uses GlowButton and GlowInput from the Obsidian Studio design system
 *
 * Note: useSearchParams() requires Suspense boundary in Next.js App Router.
 * The inner component reads search params; the exported default wraps it.
 */

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck, KeyRound } from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import { useMfaVerify } from "@/hooks/useAuth";
import { useAuthContext } from "@/providers/auth-provider";
import { ApiError } from "@/lib/api-client";
import { mfaCodeSchema, type MfaCodeFormData } from "@/lib/validations";

// ---------------------------------------------------------------------------
// Inner component — reads useSearchParams (must be inside Suspense)
// ---------------------------------------------------------------------------

function MfaVerifyForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const authContext = useAuthContext();

  const mfaToken = searchParams.get("token");

  const [useBackupCode, setUseBackupCode] = useState(false);
  const [trustDevice, setTrustDevice] = useState(false);

  const mfaVerifyMutation = useMfaVerify();

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<MfaCodeFormData>({
    resolver: zodResolver(mfaCodeSchema),
  });

  // Redirect to /login if no token is present
  useEffect(() => {
    if (!mfaToken) {
      router.replace("/login");
    }
  }, [mfaToken, router]);

  const toggleBackupCode = () => {
    setUseBackupCode((prev) => !prev);
    reset();
  };

  const onSubmit = (data: MfaCodeFormData) => {
    if (!mfaToken) return;

    mfaVerifyMutation.mutate(
      {
        mfa_token: mfaToken,
        code: data.code,
        trust_device: trustDevice,
      },
      {
        onSuccess: async (response) => {
          await authContext.login({
            access_token: response.access_token,
            refresh_token: response.refresh_token,
          });

          if (response.wxcode_redirect_url && response.wxcode_code) {
            window.location.href = `${response.wxcode_redirect_url}?code=${response.wxcode_code}`;
          } else {
            router.push("/");
          }
        },
      }
    );
  };

  // Extract API error message
  const apiError = mfaVerifyMutation.error
    ? mfaVerifyMutation.error instanceof ApiError
      ? mfaVerifyMutation.error.message
      : mfaVerifyMutation.error.message || "Something went wrong. Please try again."
    : null;

  // If no token, render nothing (redirect in progress)
  if (!mfaToken) {
    return null;
  }

  return (
    <div className="w-full max-w-sm mx-auto">
      <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
        <h1 className="text-xl font-semibold text-zinc-100 mb-2 text-center">
          Two-factor authentication
        </h1>
        <p className="text-sm text-zinc-500 mb-6 text-center">
          {useBackupCode
            ? "Enter one of your backup codes"
            : "Enter the 6-digit code from your authenticator app"}
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {/* Code input */}
          <GlowInput
            {...register("code")}
            type="text"
            inputMode={useBackupCode ? "text" : "numeric"}
            maxLength={useBackupCode ? 11 : 6}
            placeholder={useBackupCode ? "XXXXX-XXXXX" : "000000"}
            leftIcon={useBackupCode ? KeyRound : ShieldCheck}
            error={errors.code?.message}
            autoComplete="one-time-code"
            autoFocus
            fullWidth
            className="text-center tracking-widest text-lg font-mono"
          />

          {/* Trust device checkbox */}
          <label className="flex items-center gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={trustDevice}
              onChange={(e) => setTrustDevice(e.target.checked)}
              className="w-4 h-4 rounded border-zinc-600 accent-blue-500 cursor-pointer"
            />
            <span className="text-sm text-zinc-400">
              Trust this device for 30 days
            </span>
          </label>

          {/* API error message */}
          {apiError && (
            <p className="text-sm text-rose-400 text-center">{apiError}</p>
          )}

          {/* Submit button */}
          <GlowButton
            type="submit"
            fullWidth
            isLoading={mfaVerifyMutation.isPending}
            loadingText="Verifying..."
            size="md"
          >
            Verify
          </GlowButton>
        </form>

        {/* Toggle backup code link */}
        <p className="mt-4 text-center text-sm text-zinc-500">
          <button
            type="button"
            onClick={toggleBackupCode}
            className="text-blue-400 hover:text-blue-300 transition-colors underline-offset-2 hover:underline"
          >
            {useBackupCode
              ? "Use authenticator app instead"
              : "Use backup code instead"}
          </button>
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export — wraps inner component in Suspense (required by Next.js)
// ---------------------------------------------------------------------------

export default function MfaVerifyPage() {
  return (
    <Suspense fallback={null}>
      <MfaVerifyForm />
    </Suspense>
  );
}
