"use client";

/**
 * Login page — authenticates a wxCode account.
 *
 * After successful login, handles three branches:
 *   1. mfa_required === true → redirect to /mfa-verify?token=... (or /mfa-setup?token=... if mfa_setup_required)
 *   2. wxcode_redirect_url is set → store tokens, redirect to wxcode with ?code=...
 *   3. Normal login → store tokens, redirect to / dashboard
 *
 * API error handling:
 *   - 401 → "Invalid email or password"
 *   - 403 → "Please verify your email first" + link to /verify-email
 *   - Default → error.message
 */

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Mail, Lock, Eye, EyeOff } from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import { useLogin } from "@/hooks/useAuth";
import { useAuthContext } from "@/providers/auth-provider";
import { ApiError } from "@/lib/api-client";
import { loginSchema, type LoginFormData } from "@/lib/validations";

export default function LoginPage() {
  const router = useRouter();
  const authContext = useAuthContext();
  const [showPassword, setShowPassword] = useState(false);

  const loginMutation = useLogin();

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  // Watch email for 403 error link
  const watchedEmail = watch("email", "");

  const onSubmit = (data: LoginFormData) => {
    loginMutation.mutate(data, {
      onSuccess: async (response) => {
        if (response.mfa_required) {
          // MFA is required — redirect to setup or verify
          if (response.mfa_setup_required) {
            router.push(
              `/mfa-setup?token=${encodeURIComponent(response.mfa_token ?? "")}`
            );
          } else {
            router.push(
              `/mfa-verify?token=${encodeURIComponent(response.mfa_token ?? "")}`
            );
          }
        } else if (response.wxcode_redirect_url && response.wxcode_code) {
          // wxcode redirect — store tokens then redirect to wxcode with code
          await authContext.login({
            access_token: response.access_token!,
            refresh_token: response.refresh_token!,
          });
          window.location.href = `${response.wxcode_redirect_url}?code=${response.wxcode_code}`;
        } else {
          // Normal login — store tokens and go to dashboard
          await authContext.login({
            access_token: response.access_token!,
            refresh_token: response.refresh_token!,
          });
          router.push("/");
        }
      },
    });
  };

  // Derive API error message with contextual messages
  const renderApiError = () => {
    if (!loginMutation.error) return null;

    if (loginMutation.error instanceof ApiError) {
      if (loginMutation.error.status === 401) {
        return (
          <p className="text-sm text-rose-400 text-center">
            Invalid email or password
          </p>
        );
      }

      if (loginMutation.error.status === 403) {
        return (
          <p className="text-sm text-rose-400 text-center">
            Please verify your email first.{" "}
            <Link
              href={`/verify-email?email=${encodeURIComponent(watchedEmail)}`}
              className="text-blue-400 hover:text-blue-300 transition-colors underline"
            >
              Resend verification
            </Link>
          </p>
        );
      }

      return (
        <p className="text-sm text-rose-400 text-center">
          {loginMutation.error.message}
        </p>
      );
    }

    return (
      <p className="text-sm text-rose-400 text-center">
        {loginMutation.error.message || "Something went wrong. Please try again."}
      </p>
    );
  };

  return (
    <div className="w-full max-w-sm mx-auto">
      <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
        <h1 className="text-xl font-semibold text-zinc-100 mb-6 text-center">
          Sign in to wxCode
        </h1>

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

          {/* Password field */}
          <GlowInput
            {...register("password")}
            type={showPassword ? "text" : "password"}
            label="Password"
            placeholder="Your password"
            leftIcon={Lock}
            rightIcon={showPassword ? EyeOff : Eye}
            onRightIconClick={() => setShowPassword((prev) => !prev)}
            error={errors.password?.message}
            autoComplete="current-password"
            fullWidth
          />

          {/* API error message */}
          {renderApiError()}

          {/* Submit button */}
          <GlowButton
            type="submit"
            fullWidth
            isLoading={loginMutation.isPending}
            loadingText="Signing in..."
            size="md"
          >
            Sign in
          </GlowButton>
        </form>

        {/* Footer links */}
        <div className="mt-4 flex flex-col gap-2 text-center">
          <p className="text-sm text-zinc-500">
            <Link
              href="/forgot-password"
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              Forgot password?
            </Link>
          </p>
          <p className="text-sm text-zinc-500">
            Don&apos;t have an account?{" "}
            <Link
              href="/signup"
              className="text-blue-400 hover:text-blue-300 transition-colors"
            >
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
