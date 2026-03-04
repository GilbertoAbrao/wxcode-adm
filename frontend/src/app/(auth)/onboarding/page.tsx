"use client";

/**
 * Workspace onboarding page — creates the user's first workspace.
 *
 * - Shown after email verification (signup flow) or when user has no workspace
 * - Workspace name form with validation via Zod workspaceSchema
 * - On success: redirects to / (authenticated dashboard)
 * - On error: shows inline API error
 * - Uses GlowButton and GlowInput from the Obsidian Studio design system
 *
 * Note: The createWorkspace mutation requires authentication.
 * If the user arrives without tokens, AuthProvider redirects them to /login.
 * /onboarding is excluded from authenticated-user redirect (see auth-provider.tsx).
 */

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Building2 } from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import { useCreateWorkspace } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api-client";
import { workspaceSchema, type WorkspaceFormData } from "@/lib/validations";

export default function OnboardingPage() {
  const router = useRouter();

  const createWorkspaceMutation = useCreateWorkspace();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<WorkspaceFormData>({
    resolver: zodResolver(workspaceSchema),
  });

  const onSubmit = (data: WorkspaceFormData) => {
    createWorkspaceMutation.mutate(
      { name: data.name },
      {
        onSuccess: () => {
          router.push("/");
        },
      }
    );
  };

  // Extract API error message
  const apiError = createWorkspaceMutation.error
    ? createWorkspaceMutation.error instanceof ApiError
      ? createWorkspaceMutation.error.message
      : createWorkspaceMutation.error.message || "Something went wrong. Please try again."
    : null;

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="border border-zinc-800 bg-zinc-950/50 rounded-lg p-6">
        <h1 className="text-xl font-semibold text-zinc-100 mb-2 text-center">
          Create your workspace
        </h1>
        <p className="text-sm text-zinc-500 mb-6 text-center">
          Give your workspace a name. You can change this later.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {/* Workspace name field */}
          <GlowInput
            {...register("name")}
            type="text"
            label="Workspace name"
            placeholder="My Workspace"
            leftIcon={Building2}
            error={errors.name?.message}
            autoFocus
            autoComplete="organization"
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
            isLoading={createWorkspaceMutation.isPending}
            loadingText="Creating workspace..."
            size="md"
          >
            Create Workspace
          </GlowButton>
        </form>

        {/* Helper text */}
        <p className="mt-4 text-xs text-zinc-600 text-center">
          This will be your team&apos;s home base for managing users, billing, and settings.
        </p>
      </div>
    </div>
  );
}
