"use client";

import {
  CreditCard,
  Zap,
  Users as UsersIcon,
  ExternalLink,
  Crown,
  CheckCircle2,
} from "lucide-react";
import {
  GlowButton,
  LoadingSkeleton,
  ErrorState,
  EmptyState,
} from "@/components/ui";
import { useMyTenants } from "@/hooks/useTenant";
import {
  usePlans,
  useSubscription,
  useCreateCheckout,
  useCreatePortal,
} from "@/hooks/useBilling";
import type { BillingPlan, Subscription } from "@/hooks/useBilling";

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

function formatCents(cents: number): string {
  if (cents === 0) return "Free";
  return `$${(cents / 100).toFixed(2)}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "No renewal date";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function statusBadge(status: string): { className: string; label: string } {
  switch (status) {
    case "active":
      return {
        className: "bg-emerald-400/10 text-emerald-400",
        label: "Active",
      };
    case "free":
      return { className: "bg-zinc-800 text-zinc-400", label: "Free" };
    case "past_due":
      return {
        className: "bg-amber-400/10 text-amber-400",
        label: "Past Due",
      };
    case "canceled":
      return {
        className: "bg-rose-400/10 text-rose-400",
        label: "Canceled",
      };
    case "trialing":
      return {
        className: "bg-blue-400/10 text-blue-400",
        label: "Trialing",
      };
    default:
      return { className: "bg-zinc-800 text-zinc-400", label: status };
  }
}

// ---------------------------------------------------------------------------
// Plan card component
// ---------------------------------------------------------------------------

interface PlanCardProps {
  plan: BillingPlan;
  subscription: Subscription | undefined;
  hasBillingAccess: boolean;
}

function PlanCard({ plan, subscription, hasBillingAccess }: PlanCardProps) {
  const currentPlanId = subscription?.plan?.id;
  const isCurrent = plan.id === currentPlanId;
  const currentStatus = subscription?.status ?? "free";
  const isPaidCurrent =
    currentStatus === "active" ||
    currentStatus === "trialing" ||
    currentStatus === "past_due";

  const ctaLabel = isCurrent
    ? "Current Plan"
    : isPaidCurrent
      ? "Upgrade"
      : "Subscribe";

  const overageLabel =
    plan.overage_rate_cents_per_token > 0
      ? `Overage: $${(plan.overage_rate_cents_per_token / 10000).toFixed(4)}/token`
      : null;

  const memberLabel =
    plan.member_cap === -1
      ? "Unlimited members"
      : plan.member_cap > 0
        ? `Up to ${plan.member_cap} members`
        : "1 member";

  const tokenLabel =
    plan.token_quota > 0
      ? `${plan.token_quota.toLocaleString()} tokens/month`
      : "No token quota";

  return (
    <div
      className={`rounded-lg border p-5 flex flex-col gap-3 ${
        isCurrent ? "border-cyan-400" : "border-zinc-800"
      }`}
    >
      {/* Plan name + current badge */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-foreground">{plan.name}</span>
        {isCurrent && (
          <CheckCircle2 className="h-4 w-4 text-cyan-400 shrink-0" />
        )}
      </div>

      {/* Price */}
      <p className="text-xl font-bold text-foreground">
        {formatCents(plan.monthly_fee_cents)}
        {plan.monthly_fee_cents > 0 && (
          <span className="text-sm font-normal text-zinc-400">/mo</span>
        )}
      </p>

      {/* Feature bullets */}
      <ul className="text-sm text-zinc-400 space-y-1 flex-1">
        <li className="flex items-center gap-1.5">
          <UsersIcon className="h-3.5 w-3.5 shrink-0" />
          {memberLabel}
        </li>
        <li className="flex items-center gap-1.5">
          <Zap className="h-3.5 w-3.5 shrink-0" />
          {tokenLabel}
        </li>
        {overageLabel && (
          <li className="flex items-center gap-1.5">
            <span className="h-3.5 w-3.5 shrink-0 text-center text-xs">+</span>
            {overageLabel}
          </li>
        )}
      </ul>

      {/* CTA */}
      <div className="mt-2">
        {isCurrent ? (
          <GlowButton
            variant="secondary"
            size="sm"
            disabled
            className="w-full justify-center"
          >
            Current Plan
          </GlowButton>
        ) : hasBillingAccess ? (
          <GlowButton
            size="sm"
            className="w-full justify-center"
            onClick={() => {
              // Plan 16-02: wire useCreateCheckout
            }}
          >
            {ctaLabel}
          </GlowButton>
        ) : (
          <p className="text-xs text-zinc-500">
            Contact your workspace owner for billing changes
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Billing page
// ---------------------------------------------------------------------------

export default function BillingPage() {
  // Resolve tenant context (user belongs to exactly one tenant)
  const { data: tenantsData, isLoading: tenantsLoading } = useMyTenants();

  const tenantId = tenantsData?.tenants?.[0]?.id;
  const currentRole = tenantsData?.tenants?.[0]?.role;
  const billingAccess = tenantsData?.tenants?.[0]?.billing_access;
  const hasBillingAccess =
    currentRole === "owner" || billingAccess === true;

  // Data fetching
  const {
    data: subscription,
    isLoading: subscriptionLoading,
    isError: subscriptionError,
    error: subscriptionErrorObj,
    refetch: refetchSubscription,
  } = useSubscription(tenantId);

  const { data: plans, isLoading: plansLoading } = usePlans();

  // Mutations available for Plan 16-02 wiring
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _createCheckout = useCreateCheckout(tenantId);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _createPortal = useCreatePortal(tenantId);

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (tenantsLoading || subscriptionLoading || plansLoading) {
    return (
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <CreditCard className="h-6 w-6 text-cyan-400" />
            Billing
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your subscription and billing.
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

  if (subscriptionError) {
    return (
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <CreditCard className="h-6 w-6 text-cyan-400" />
            Billing
          </h1>
        </div>
        <ErrorState
          title="Failed to load subscription"
          message={
            subscriptionErrorObj?.message ?? "An unexpected error occurred"
          }
          onRetry={() => refetchSubscription()}
        />
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------

  const badge = statusBadge(subscription?.status ?? "free");
  const tokenQuota = subscription?.plan?.token_quota ?? 0;
  const tokensUsed = subscription?.tokens_used_this_period ?? 0;
  const usagePercent =
    tokenQuota > 0 ? Math.min(100, (tokensUsed / tokenQuota) * 100) : 0;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <CreditCard className="h-6 w-6 text-cyan-400" />
          Billing
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage your subscription and billing.
        </p>
      </div>

      {/* Current Plan section */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="text-base font-semibold text-zinc-100 mb-4 flex items-center gap-2">
          <Crown className="h-4 w-4 text-cyan-400" />
          Current Plan
        </h2>

        <div className="flex flex-col gap-4">
          {/* Plan name + status */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-lg font-semibold text-foreground">
              {subscription?.plan?.name ?? "Free"}
            </span>
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${badge.className}`}
            >
              {badge.label}
            </span>
          </div>

          {/* Renewal date */}
          <p className="text-sm text-zinc-400">
            {subscription?.current_period_end
              ? `Renews ${formatDate(subscription.current_period_end)}`
              : "No renewal date"}
          </p>

          {/* Token usage */}
          {tokenQuota > 0 ? (
            <div className="flex flex-col gap-1.5">
              <p className="text-sm text-zinc-400">
                <span className="text-foreground font-medium">
                  {tokensUsed.toLocaleString()}
                </span>{" "}
                /{" "}
                <span className="text-foreground font-medium">
                  {tokenQuota.toLocaleString()}
                </span>{" "}
                tokens used this period
              </p>
              <div className="h-2 w-full rounded-full bg-zinc-800 overflow-hidden">
                <div
                  className="h-full bg-cyan-400 rounded-full transition-all"
                  style={{ width: `${usagePercent}%` }}
                />
              </div>
            </div>
          ) : (
            <p className="text-sm text-zinc-400">
              Token usage: <span className="text-foreground">Unlimited</span>
            </p>
          )}

          {/* Manage Billing button — billing_access users only, for paid plans */}
          {hasBillingAccess &&
            (subscription?.status === "active" ||
              subscription?.status === "past_due") && (
              <div>
                <GlowButton
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    // Plan 16-02: wire useCreatePortal
                  }}
                >
                  <ExternalLink className="h-4 w-4" />
                  Manage Billing
                </GlowButton>
              </div>
            )}
        </div>
      </section>

      {/* Available Plans section */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="text-base font-semibold text-zinc-100 mb-4 flex items-center gap-2">
          <Zap className="h-4 w-4 text-purple-400" />
          Available Plans
        </h2>

        {!plans || plans.length === 0 ? (
          <EmptyState
            title="No plans available"
            description="There are currently no billing plans configured."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                subscription={subscription}
                hasBillingAccess={hasBillingAccess}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
