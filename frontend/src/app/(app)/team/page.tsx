"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Users, UserPlus, Mail, Shield, Trash2, Clock } from "lucide-react";
import {
  GlowButton,
  GlowInput,
  LoadingSkeleton,
  ErrorState,
  EmptyState,
  AnimatedList,
  AnimatedListItem,
} from "@/components/ui";
import {
  useMyTenants,
  useTenantMembers,
  useTenantInvitations,
  useInviteMember,
  useCancelInvitation,
} from "@/hooks/useTenant";
import { ApiError } from "@/lib/api-client";
import { inviteMemberSchema, InviteMemberFormData } from "@/lib/validations";

// ---------------------------------------------------------------------------
// Helper: role badge color
// ---------------------------------------------------------------------------

function roleBadgeClass(role: string): string {
  if (role === "owner") return "bg-cyan-400/10 text-cyan-400";
  if (role === "admin") return "bg-purple-400/10 text-purple-400";
  return "bg-zinc-800 text-zinc-400";
}

// ---------------------------------------------------------------------------
// Helper: format join date
// ---------------------------------------------------------------------------

function formatJoinDate(isoString: string | null): string {
  if (!isoString) return "Unknown";
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Team page
// ---------------------------------------------------------------------------

export default function TeamPage() {
  const [inviteSuccess, setInviteSuccess] = useState(false);

  // Resolve tenant context (user belongs to exactly one tenant)
  const { data: tenantsData, isLoading: tenantsLoading } = useMyTenants();
  const tenantId = tenantsData?.tenants?.[0]?.id;
  const currentRole = tenantsData?.tenants?.[0]?.role;
  const isAdminOrOwner = currentRole === "owner" || currentRole === "admin";

  // Data fetching
  const {
    data: members,
    isLoading: membersLoading,
    isError: membersError,
    error: membersErrorObj,
    refetch: refetchMembers,
  } = useTenantMembers(tenantId);

  const { data: invitations, isLoading: invitationsLoading } =
    useTenantInvitations(isAdminOrOwner ? tenantId : undefined);

  const inviteMutation = useInviteMember(tenantId);
  const cancelInvitationMutation = useCancelInvitation(tenantId);

  // Invite form
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<InviteMemberFormData>({
    resolver: zodResolver(inviteMemberSchema),
    defaultValues: { email: "", role: "developer" },
  });

  const onInviteSubmit = async (data: InviteMemberFormData) => {
    try {
      await inviteMutation.mutateAsync({ email: data.email, role: data.role });
      reset();
      setInviteSuccess(true);
      setTimeout(() => setInviteSuccess(false), 3000);
    } catch {
      // Error is displayed via inviteMutation.error
    }
  };

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (tenantsLoading || membersLoading) {
    return (
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Users className="h-6 w-6 text-cyan-400" />
            Team
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage workspace members and invitations.
          </p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <LoadingSkeleton lines={4} />
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Error state
  // ---------------------------------------------------------------------------

  if (membersError) {
    return (
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Users className="h-6 w-6 text-cyan-400" />
            Team
          </h1>
        </div>
        <ErrorState
          title="Failed to load members"
          message={membersErrorObj?.message ?? "An unexpected error occurred"}
          onRetry={() => refetchMembers()}
        />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Users className="h-6 w-6 text-cyan-400" />
          Team
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage workspace members and invitations.
        </p>
      </div>

      {/* Invite member form — Owner/Admin only */}
      {isAdminOrOwner && (
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="text-base font-semibold text-zinc-100 mb-1 flex items-center gap-2">
            <UserPlus className="h-4 w-4 text-purple-400" />
            Invite member
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Send an invitation by email to add a new member to your workspace.
          </p>

          <form
            onSubmit={handleSubmit(onInviteSubmit)}
            className="flex flex-col gap-4 sm:flex-row sm:items-end"
            noValidate
          >
            <div className="flex-1">
              <GlowInput
                {...register("email")}
                type="email"
                label="Email address"
                leftIcon={Mail}
                error={errors.email?.message}
                placeholder="colleague@example.com"
                fullWidth
                autoComplete="off"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-zinc-400 flex items-center gap-1">
                <Shield className="h-3 w-3" />
                Role
              </label>
              <select
                {...register("role")}
                className="bg-zinc-900 border border-zinc-700 text-foreground rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              >
                <option value="admin">Admin</option>
                <option value="developer">Developer</option>
                <option value="viewer">Viewer</option>
              </select>
              {errors.role && (
                <p className="text-xs text-rose-400">{errors.role.message}</p>
              )}
            </div>

            <div>
              <GlowButton
                type="submit"
                size="sm"
                isLoading={inviteMutation.isPending}
                loadingText="Inviting..."
              >
                Send invite
              </GlowButton>
            </div>
          </form>

          {/* Invite error */}
          {inviteMutation.error && (
            <p className="mt-3 text-sm text-rose-400">
              {inviteMutation.error instanceof ApiError
                ? inviteMutation.error.status === 409
                  ? "This email is already a member or has a pending invitation."
                  : inviteMutation.error.status === 402
                    ? "Member limit reached for your current plan."
                    : inviteMutation.error.message
                : inviteMutation.error.message}
            </p>
          )}

          {/* Invite success */}
          {inviteSuccess && (
            <p className="mt-3 text-sm text-emerald-400">
              Invitation sent successfully.
            </p>
          )}
        </section>
      )}

      {/* Members section */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="text-base font-semibold text-zinc-100 mb-4 flex items-center gap-2">
          <Users className="h-4 w-4 text-cyan-400" />
          Members
          {members && members.length > 0 && (
            <span className="text-xs font-normal text-zinc-500 ml-1">
              {members.length} {members.length === 1 ? "member" : "members"}
            </span>
          )}
        </h2>

        {!members || members.length === 0 ? (
          <EmptyState
            title="No members yet"
            description="Invite teammates to start collaborating."
          />
        ) : (
          <AnimatedList>
            {members.map((member) => (
              <AnimatedListItem key={member.id}>
                <div className="flex items-center justify-between gap-4 py-3 border-b border-zinc-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-foreground truncate">
                        {member.email}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full capitalize ${roleBadgeClass(member.role)}`}
                      >
                        {member.role}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      Joined {formatJoinDate(member.created_at)}
                    </p>
                  </div>
                </div>
              </AnimatedListItem>
            ))}
          </AnimatedList>
        )}
      </section>

      {/* Pending invitations — Owner/Admin only, only shown if any exist */}
      {isAdminOrOwner && !invitationsLoading && invitations && invitations.length > 0 && (
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="text-base font-semibold text-zinc-100 mb-4 flex items-center gap-2">
            <Clock className="h-4 w-4 text-yellow-400" />
            Pending Invitations
            <span className="text-xs font-normal text-zinc-500 ml-1">
              {invitations.length}
            </span>
          </h2>

          <AnimatedList>
            {invitations.map((invitation) => (
              <AnimatedListItem key={invitation.id}>
                <div className="flex items-center justify-between gap-4 py-3 border-b border-zinc-800 last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-foreground truncate">
                        {invitation.email}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full capitalize ${roleBadgeClass(invitation.role)}`}
                      >
                        {invitation.role}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-400/10 text-yellow-400">
                        Pending
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      Expires{" "}
                      {new Date(invitation.expires_at).toLocaleDateString(
                        undefined,
                        { year: "numeric", month: "short", day: "numeric" }
                      )}
                    </p>
                  </div>

                  <GlowButton
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      cancelInvitationMutation.mutate(invitation.id)
                    }
                    isLoading={
                      cancelInvitationMutation.isPending &&
                      cancelInvitationMutation.variables === invitation.id
                    }
                    loadingText="Cancelling..."
                    type="button"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-red-400" />
                    <span className="text-red-400">Cancel</span>
                  </GlowButton>
                </div>
              </AnimatedListItem>
            ))}
          </AnimatedList>
        </section>
      )}
    </div>
  );
}
