"use client";

import { useRef, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { User, Lock, Eye, EyeOff, Monitor } from "lucide-react";
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
  useChangePassword,
  useUserSessions,
  useRevokeSession,
} from "@/hooks/useUserAccount";
import { ApiError } from "@/lib/api-client";
import {
  changePasswordSchema,
  ChangePasswordFormData,
} from "@/lib/validations";

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
// Helper: relative time formatter
// ---------------------------------------------------------------------------

function formatRelativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

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
  // ---------------------------------------------------------------------------
  // Password section state + form
  // ---------------------------------------------------------------------------
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [passwordSaved, setPasswordSaved] = useState(false);

  const changePasswordMutation = useChangePassword();

  const {
    register: registerPassword,
    handleSubmit: handlePasswordSubmit,
    formState: { errors: passwordErrors },
    reset: resetPasswordForm,
  } = useForm<ChangePasswordFormData>({
    resolver: zodResolver(changePasswordSchema),
  });

  const onPasswordSubmit = (data: ChangePasswordFormData) => {
    changePasswordMutation.mutate(
      { current_password: data.current_password, new_password: data.new_password },
      {
        onSuccess: () => {
          resetPasswordForm();
          setPasswordSaved(true);
          setTimeout(() => setPasswordSaved(false), 3000);
        },
      }
    );
  };

  // ---------------------------------------------------------------------------
  // Sessions section state + hooks
  // ---------------------------------------------------------------------------
  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    isError: sessionsError,
    error: sessionsErrorObj,
  } = useUserSessions();

  const revokeSessionMutation = useRevokeSession();

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

      {/* Password section */}
      <section className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-6">
        <h2 className="text-base font-semibold text-zinc-100 mb-4">Change password</h2>
        <form
          onSubmit={handlePasswordSubmit(onPasswordSubmit)}
          className="space-y-4 max-w-sm"
          noValidate
        >
          <GlowInput
            {...registerPassword("current_password")}
            type={showCurrentPassword ? "text" : "password"}
            label="Current password"
            leftIcon={Lock}
            rightIcon={showCurrentPassword ? EyeOff : Eye}
            onRightIconClick={() => setShowCurrentPassword((prev) => !prev)}
            error={passwordErrors.current_password?.message}
            autoComplete="current-password"
            fullWidth
          />
          <GlowInput
            {...registerPassword("new_password")}
            type={showNewPassword ? "text" : "password"}
            label="New password"
            leftIcon={Lock}
            rightIcon={showNewPassword ? EyeOff : Eye}
            onRightIconClick={() => setShowNewPassword((prev) => !prev)}
            error={passwordErrors.new_password?.message}
            autoComplete="new-password"
            fullWidth
          />
          <GlowInput
            {...registerPassword("confirm_password")}
            type={showNewPassword ? "text" : "password"}
            label="Confirm new password"
            leftIcon={Lock}
            error={passwordErrors.confirm_password?.message}
            autoComplete="new-password"
            fullWidth
          />

          {/* API error */}
          {changePasswordMutation.error && (
            <p className="text-sm text-rose-400">
              {changePasswordMutation.error instanceof ApiError
                ? changePasswordMutation.error.status === 400
                  ? "Current password is incorrect"
                  : changePasswordMutation.error.message
                : changePasswordMutation.error.message || "Something went wrong"}
            </p>
          )}

          {/* Success message */}
          {passwordSaved && (
            <p className="text-sm text-emerald-400">Password changed successfully</p>
          )}

          <GlowButton
            type="submit"
            size="sm"
            isLoading={changePasswordMutation.isPending}
            loadingText="Changing..."
          >
            Change password
          </GlowButton>
        </form>
      </section>

      {/* Sessions section */}
      <section className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-6">
        <h2 className="text-base font-semibold text-zinc-100 mb-4">Active sessions</h2>

        {sessionsLoading && <LoadingSkeleton lines={3} />}

        {sessionsError && (
          <ErrorState
            title="Failed to load sessions"
            message={sessionsErrorObj?.message ?? "An unexpected error occurred"}
          />
        )}

        {!sessionsLoading && !sessionsError && (
          <>
            {!sessionsData?.sessions || sessionsData.sessions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No active sessions found.</p>
            ) : (
              <div>
                {sessionsData.sessions.map((session) => (
                  <div
                    key={session.id}
                    className="flex items-start justify-between gap-4 py-3 border-b border-zinc-800 last:border-0"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Monitor className="h-4 w-4 shrink-0 text-zinc-500" />
                        <span className="text-sm font-medium text-zinc-200 truncate">
                          {session.device_info || "Unknown device"}
                        </span>
                        {session.is_current && (
                          <span className="shrink-0 text-xs font-medium text-cyan-400 bg-cyan-400/10 px-1.5 py-0.5 rounded">
                            Current
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
                        {session.ip_address && <span>{session.ip_address}</span>}
                        <span>Last active {formatRelativeTime(session.last_active_at)}</span>
                      </div>
                    </div>
                    {!session.is_current && (
                      <GlowButton
                        variant="secondary"
                        size="sm"
                        onClick={() => revokeSessionMutation.mutate(session.id)}
                        isLoading={
                          revokeSessionMutation.isPending &&
                          revokeSessionMutation.variables === session.id
                        }
                        loadingText="Revoking..."
                      >
                        Revoke
                      </GlowButton>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
