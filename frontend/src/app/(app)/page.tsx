"use client";

import { LayoutDashboard, Building2, CreditCard, Users, CalendarClock } from "lucide-react";
import {
  SkeletonCard,
  EmptyState,
} from "@/components/ui";
import { useMyTenants, useTenantMembers } from "@/hooks/useTenant";
import { useSubscription } from "@/hooks/useBilling";
import { useAuthContext } from "@/providers/auth-provider";

// ---------------------------------------------------------------------------
// Format date helper
// ---------------------------------------------------------------------------

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Stat card component
// ---------------------------------------------------------------------------

function StatCard({
  icon: Icon,
  label,
  value,
  subtitle,
  isLoading,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  subtitle: string;
  isLoading: boolean;
}) {
  if (isLoading) {
    return <SkeletonCard className="h-32" />;
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-5">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="h-4 w-4 text-cyan-400" />
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const { user } = useAuthContext();

  const tenantsQuery = useMyTenants();
  const firstTenant = tenantsQuery.data?.tenants[0];
  const tenantId = firstTenant?.id;

  const subscriptionQuery = useSubscription(tenantId);
  const membersQuery = useTenantMembers(tenantId);

  const isTenantsLoading = tenantsQuery.isLoading;
  const isSubscriptionLoading = subscriptionQuery.isLoading;
  const isMembersLoading = membersQuery.isLoading;

  const subscription = subscriptionQuery.data;
  const members = membersQuery.data;

  // No tenants found — show empty state
  if (!isTenantsLoading && (!tenantsQuery.data?.tenants || tenantsQuery.data.tenants.length === 0)) {
    return (
      <div className="flex flex-col gap-6">
        {/* Page header */}
        <div className="flex items-center gap-3">
          <LayoutDashboard className="h-6 w-6 text-blue-500" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
            <p className="text-sm text-muted-foreground">Your workspace overview</p>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-8">
          <EmptyState
            title="No workspace found"
            description="You are not a member of any workspace yet. Ask your workspace owner to invite you, or create a new workspace."
          />
        </div>
      </div>
    );
  }

  // Plan status badge value
  const planStatus = subscription?.status ?? "—";
  const planName = subscription?.plan?.name ?? "—";
  const memberCount = members?.length ?? "—";
  const renewalDate =
    subscription?.current_period_end
      ? formatDate(subscription.current_period_end)
      : "No renewal";

  const displayName = user?.display_name || "there";

  return (
    <div className="flex flex-col gap-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <LayoutDashboard className="h-6 w-6 text-blue-500" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            {firstTenant?.name ?? "Your workspace overview"}
          </p>
        </div>
      </div>

      {/* Welcome section */}
      <div className="rounded-lg border border-zinc-800 bg-obsidian-900/50 px-6 py-5">
        <h2 className="text-lg font-semibold text-foreground">
          Welcome back, {displayName}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your workspace, team, and billing from the sidebar.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Building2}
          label="Workspace"
          value={isTenantsLoading ? "—" : (firstTenant?.name ?? "—")}
          subtitle={isTenantsLoading ? "Loading…" : (firstTenant?.slug ?? "")}
          isLoading={isTenantsLoading}
        />
        <StatCard
          icon={CreditCard}
          label="Plan"
          value={isSubscriptionLoading ? "—" : planName}
          subtitle={isSubscriptionLoading ? "Loading…" : planStatus}
          isLoading={isSubscriptionLoading}
        />
        <StatCard
          icon={Users}
          label="Members"
          value={isMembersLoading ? "—" : memberCount}
          subtitle="team members"
          isLoading={isMembersLoading}
        />
        <StatCard
          icon={CalendarClock}
          label="Renewal"
          value={isSubscriptionLoading ? "—" : renewalDate}
          subtitle="next billing date"
          isLoading={isSubscriptionLoading}
        />
      </div>
    </div>
  );
}
