"use client";

/**
 * Signup page — creates a new wxCode account.
 *
 * - Email + password form with zod validation
 * - On success: redirects to /verify-email?email=... for email verification
 * - On API error: shows inline error message below the form
 * - Uses GlowButton and GlowInput from the Obsidian Studio design system
 */

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Mail, Lock, Eye, EyeOff } from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import { useSignup } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api-client";
import { signupSchema, type SignupFormData } from "@/lib/validations";

export default function SignupPage() {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);

  const signupMutation = useSignup();

  const {
    register,
    handleSubmit,
    formState: { errors },
    getValues,
  } = useForm<SignupFormData>({
    resolver: zodResolver(signupSchema),
  });

  const onSubmit = (data: SignupFormData) => {
    signupMutation.mutate(data, {
      onSuccess: () => {
        router.push(
          `/verify-email?email=${encodeURIComponent(data.email)}`
        );
      },
    });
  };

  // Extract API error message
  const apiError = signupMutation.error
    ? signupMutation.error instanceof ApiError
      ? signupMutation.error.message
      : signupMutation.error.message || "Something went wrong. Please try again."
    : null;

  return (
    <div className="w-full max-w-sm mx-auto">
      <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
        <h1 className="text-xl font-semibold text-zinc-100 mb-6 text-center">
          Create your account
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
            placeholder="At least 8 characters"
            leftIcon={Lock}
            rightIcon={showPassword ? EyeOff : Eye}
            onRightIconClick={() => setShowPassword((prev) => !prev)}
            error={errors.password?.message}
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
            isLoading={signupMutation.isPending}
            loadingText="Creating account..."
            size="md"
          >
            Create account
          </GlowButton>
        </form>

        {/* Footer */}
        <p className="mt-4 text-center text-sm text-zinc-500">
          Already have an account?{" "}
          <Link
            href="/login"
            className="text-blue-400 hover:text-blue-300 transition-colors"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
