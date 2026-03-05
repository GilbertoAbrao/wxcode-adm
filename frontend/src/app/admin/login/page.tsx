"use client";

/**
 * Admin login page — authenticates platform administrators.
 *
 * Calls POST /api/v1/admin/login via the useAdminLogin mutation.
 * On success: stores admin tokens in the isolated admin memory store,
 * sets email in AdminAuthContext, and redirects to /admin/tenants.
 *
 * API error handling:
 *   - 401 → "Invalid admin credentials"
 *   - 403 → "Access denied — admin accounts only"
 *   - Default → error.message
 *
 * No "Forgot password?" or sign-up links — admin accounts are seeded, not self-service.
 */

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Mail, Lock, Eye, EyeOff } from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import { useAdminLogin } from "@/hooks/useAdminAuth";
import { useAdminAuthContext } from "@/providers/admin-auth-provider";
import { ApiError } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Admin login schema — local to this page (no shared validation needed)
// ---------------------------------------------------------------------------

const adminLoginSchema = z.object({
  email: z.string().email("Please enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

type AdminLoginFormData = z.infer<typeof adminLoginSchema>;

// ---------------------------------------------------------------------------
// AdminLoginPage component
// ---------------------------------------------------------------------------

export default function AdminLoginPage() {
  const router = useRouter();
  const adminAuthContext = useAdminAuthContext();
  const [showPassword, setShowPassword] = useState(false);

  const adminLoginMutation = useAdminLogin();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AdminLoginFormData>({
    resolver: zodResolver(adminLoginSchema),
  });

  const onSubmit = (data: AdminLoginFormData) => {
    adminLoginMutation.mutate(data, {
      onSuccess: (response) => {
        // Store admin tokens in the isolated admin memory store and set email
        adminAuthContext.login(
          {
            access_token: response.access_token,
            refresh_token: response.refresh_token,
          },
          data.email
        );
        router.push("/admin/tenants");
      },
    });
  };

  // Derive contextual error message
  const renderApiError = () => {
    if (!adminLoginMutation.error) return null;

    if (adminLoginMutation.error instanceof ApiError) {
      if (adminLoginMutation.error.status === 401) {
        return (
          <p className="text-sm text-rose-400 text-center">
            Invalid admin credentials
          </p>
        );
      }

      if (adminLoginMutation.error.status === 403) {
        return (
          <p className="text-sm text-rose-400 text-center">
            Access denied &mdash; admin accounts only
          </p>
        );
      }

      return (
        <p className="text-sm text-rose-400 text-center">
          {adminLoginMutation.error.message}
        </p>
      );
    }

    return (
      <p className="text-sm text-rose-400 text-center">
        {adminLoginMutation.error.message || "Something went wrong. Please try again."}
      </p>
    );
  };

  return (
    <div className="min-h-[calc(100vh-73px)] flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm mx-auto">
        <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
          {/* Header */}
          <div className="mb-6 text-center">
            <h1 className="text-xl font-semibold text-zinc-100">
              Admin Portal
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Platform administration access
            </p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            {/* Email field */}
            <GlowInput
              {...register("email")}
              type="email"
              label="Email"
              placeholder="admin@example.com"
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
              placeholder="Admin password"
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
              isLoading={adminLoginMutation.isPending}
              loadingText="Signing in..."
              size="md"
            >
              Sign in to Admin
            </GlowButton>
          </form>

          {/* Back to app link */}
          <div className="mt-4 text-center">
            <p className="text-sm text-zinc-600">
              <Link
                href="/login"
                className="text-zinc-500 hover:text-zinc-400 transition-colors"
              >
                Back to app
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
