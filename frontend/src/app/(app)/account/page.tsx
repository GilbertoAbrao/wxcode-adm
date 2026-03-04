"use client";

import { useRef, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { User } from "lucide-react";
import {
  GlowButton,
  GlowInput,
  LoadingSkeleton,
  ErrorState,
} from "@/components/ui";
import {
  useCurrentUser,
  useUpdateProfile,
  useUploadAvatar,
} from "@/hooks/useUserAccount";
import { ApiError } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Validation schema for display name form
// ---------------------------------------------------------------------------

const profileSchema = z.object({
  display_name: z
    .string()
    .min(1, "Display name cannot be empty")
    .max(100, "Display name too long"),
});

type ProfileFormValues = z.infer<typeof profileSchema>;

// ---------------------------------------------------------------------------
// Profile section
// ---------------------------------------------------------------------------

function ProfileSection() {
  const { data: user, isLoading, isError, error } = useCurrentUser();
  const updateMutation = useUpdateProfile();
  const uploadMutation = useUploadAvatar();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showSaved, setShowSaved] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { display_name: "" },
  });

  // Populate form when user data loads
  useEffect(() => {
    if (user) {
      reset({ display_name: user.display_name ?? "" });
    }
  }, [user?.display_name, reset]);

  if (isLoading) {
    return <LoadingSkeleton lines={3} />;
  }

  if (isError) {
    return (
      <ErrorState
        title="Failed to load profile"
        message={error?.message ?? "An unexpected error occurred"}
      />
    );
  }

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
    // Reset so the same file can be re-selected
    e.target.value = "";
  };

  const onSubmit = (data: ProfileFormValues) => {
    updateMutation.mutate(
      { display_name: data.display_name },
      {
        onSuccess: () => {
          setShowSaved(true);
          setTimeout(() => setShowSaved(false), 2000);
        },
      }
    );
  };

  const initials = (user?.display_name || user?.email || "?")
    .charAt(0)
    .toUpperCase();

  return (
    <section className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-6">
      <h2 className="text-xl font-semibold text-zinc-100 mb-1">Profile</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Update your display name and profile picture.
      </p>

      {/* Avatar + upload */}
      <div className="flex items-center gap-5 mb-6">
        {user?.avatar_url ? (
          <img
            src={user.avatar_url}
            alt="Profile avatar"
            className="h-16 w-16 rounded-full object-cover"
          />
        ) : (
          <div className="h-16 w-16 rounded-full bg-zinc-700 flex items-center justify-center text-lg font-medium text-zinc-200">
            {initials}
          </div>
        )}

        {/* Hidden file input */}
        <input
          type="file"
          ref={fileInputRef}
          accept="image/*"
          onChange={handleAvatarChange}
          className="sr-only"
        />

        <div className="flex flex-col gap-2">
          <GlowButton
            variant="secondary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            isLoading={uploadMutation.isPending}
            loadingText="Uploading..."
            type="button"
          >
            Change avatar
          </GlowButton>
          {uploadMutation.error && (
            <p className="text-xs text-rose-400">
              {uploadMutation.error.message}
            </p>
          )}
        </div>
      </div>

      {/* Display name form */}
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <GlowInput
          {...register("display_name")}
          label="Display name"
          leftIcon={User}
          error={errors.display_name?.message}
          fullWidth
          placeholder="Your display name"
        />

        {/* Update error */}
        {updateMutation.error && (
          <p className="text-sm text-rose-400">
            {updateMutation.error instanceof ApiError
              ? updateMutation.error.message
              : updateMutation.error?.message}
          </p>
        )}

        {/* Success feedback */}
        {showSaved && (
          <p className="text-sm text-emerald-400">Changes saved successfully.</p>
        )}

        <div>
          <GlowButton
            type="submit"
            size="sm"
            isLoading={updateMutation.isPending}
            loadingText="Saving..."
          >
            Save changes
          </GlowButton>
        </div>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Account settings page
// ---------------------------------------------------------------------------

export default function AccountPage() {
  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Account Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage your profile, password, and active sessions
        </p>
      </div>

      {/* Profile section */}
      <ProfileSection />

      {/* Password section — TODO: Plan 14-02 */}
      <div className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-6">
        <h2 className="text-xl font-semibold text-zinc-100 mb-1">Password</h2>
        <p className="text-sm text-muted-foreground">
          Change password — coming in Plan 14-02.
        </p>
      </div>

      {/* Sessions section — TODO: Plan 14-02 */}
      <div className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-6">
        <h2 className="text-xl font-semibold text-zinc-100 mb-1">
          Active Sessions
        </h2>
        <p className="text-sm text-muted-foreground">
          Manage active sessions — coming in Plan 14-02.
        </p>
      </div>
    </div>
  );
}
