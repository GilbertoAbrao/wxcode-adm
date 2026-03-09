"use client";

/**
 * Billing page — subscription display, plan catalog, and Stripe Checkout/Portal wiring.
 *
 * - Displays current subscription (status badge, renewal date, token usage bar)
 * - Lists all available plans with contextual CTAs (Subscribe/Upgrade)
 * - Plan card CTA → POST /billing/checkout → window.location.href to Stripe Checkout
 * - Manage Billing button → POST /billing/portal → window.location.href to Stripe Portal
 * - Detects ?session_id= on return from Stripe Checkout → polls subscription every 2s
 *   until status changes from "free"; shows success banner and clears URL param
 * - Poll timeout: 20 seconds; shows "refresh in a moment" message if timed out
 *
 * Note: useSearchParams() requires Suspense boundary in Next.js App Router.
 * The inner BillingPageContent reads search params; the exported default wraps it.
 */

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CreditCard,
  Zap,
  Users as UsersIcon,
  ExternalLink,
  Crown,
  CheckCircle2,
  Loader2,
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
import { ApiError } from "@/lib/api-client";
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
  onCheckout: (planId: string) => void;
  checkoutPlanId: string | null; // which plan card is currently loading
}

function PlanCard({
  plan,
  subscription,
  hasBillingAccess,
  onCheckout,
  checkoutPlanId,
}: PlanCardProps) {
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

  const quota5hLabel =
    plan.token_quota_5h > 0
      ? `${plan.token_quota_5h.toLocaleString()} tokens`
      : "Unlimited";

  const quotaWeeklyLabel =
    plan.token_quota_weekly > 0
      ? `${plan.token_quota_weekly.toLocaleString()} tokens`
      : "Unlimited";

  const isThisCardLoading = checkoutPlanId === plan.id;
  const anyCheckoutInProgress = checkoutPlanId !== null;

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
          5h: {quota5hLabel}
        </li>
        <li className="flex items-center gap-1.5">
          <Zap className="h-3.5 w-3.5 shrink-0" />
          Weekly: {quotaWeeklyLabel}
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
            onClick={() => onCheckout(plan.id)}
            isLoading={isThisCardLoading}
            loadingText="Redirecting..."
            disabled={anyCheckoutInProgress}
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
// Billing loading skeleton (used as Suspense fallback)
// ---------------------------------------------------------------------------

function BillingLoadingFallback() {
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
// Inner content component — reads useSearchParams (must be inside Suspense)
// ---------------------------------------------------------------------------

function BillingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session_id");

  // Resolve tenant context (user belongs to exactly one tenant)
  const { data: tenantsData, isLoading: tenantsLoading } = useMyTenants();

  const tenantId = tenantsData?.tenants?.[0]?.id;
  const currentRole = tenantsData?.tenants?.[0]?.role;
  const billingAccess = tenantsData?.tenants?.[0]?.billing_access;
  const hasBillingAccess =
    currentRole === "owner" || billingAccess === true;

  // Post-checkout polling state
  const [checkoutComplete, setCheckoutComplete] = useState(false);
  const [pollTimedOut, setPollTimedOut] = useState(false);
  const [successPlanName, setSuccessPlanName] = useState<string | null>(null);

  // Poll subscription while session_id present and status is still "free"
  const isPolling =
    !!sessionId && !checkoutComplete && !pollTimedOut;

  // Data fetching
  const {
    data: subscription,
    isLoading: subscriptionLoading,
    isError: subscriptionError,
    error: subscriptionErrorObj,
    refetch: refetchSubscription,
  } = useSubscription(tenantId, {
    refetchInterval: isPolling ? 2000 : false,
  });

  const { data: plans, isLoading: plansLoading } = usePlans();

  // Checkout mutation
  const createCheckoutMutation = useCreateCheckout(tenantId);
  // Portal mutation
  const createPortalMutation = useCreatePortal(tenantId);

  // Per-card loading state (which plan card is mid-checkout)
  const [checkoutPlanId, setCheckoutPlanId] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Post-checkout polling: detect status change from "free"
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!sessionId) return;
    if (!subscription) return;
    if (subscription.status !== "free") {
      // Payment processed — clean up URL and show success
      setSuccessPlanName(subscription.plan?.name ?? null);
      setCheckoutComplete(true);
      router.replace("/billing", { scroll: false });
    }
  }, [sessionId, subscription, router]);

  // ---------------------------------------------------------------------------
  // Poll timeout: stop polling after 20 seconds
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!sessionId || pollTimedOut || checkoutComplete) return;
    const timeout = setTimeout(() => setPollTimedOut(true), 20_000);
    return () => clearTimeout(timeout);
  }, [sessionId, pollTimedOut, checkoutComplete]);

  // ---------------------------------------------------------------------------
  // Auto-dismiss success banner after 5 seconds
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!checkoutComplete) return;
    const dismiss = setTimeout(() => setCheckoutComplete(false), 5_000);
    return () => clearTimeout(dismiss);
  }, [checkoutComplete]);

  // ---------------------------------------------------------------------------
  // Checkout handler
  // ---------------------------------------------------------------------------

  async function handleCheckout(planId: string) {
    setCheckoutPlanId(planId);
    try {
      const result = await createCheckoutMutation.mutateAsync({ plan_id: planId });
      // Redirect to Stripe Checkout (external URL — must use window.location.href)
      window.location.href = result.checkout_url;
    } catch {
      setCheckoutPlanId(null);
      // Error displayed via createCheckoutMutation.isError
    }
  }

  // ---------------------------------------------------------------------------
  // Portal handler
  // ---------------------------------------------------------------------------

  async function handlePortal() {
    try {
      const result = await createPortalMutation.mutateAsync(undefined);
      // Redirect to Stripe Customer Portal (external URL — must use window.location.href)
      window.location.href = result.portal_url;
    } catch {
      // Error displayed via createPortalMutation.isError
    }
  }

  // ---------------------------------------------------------------------------
  // Checkout error message helpers
  // ---------------------------------------------------------------------------

  function getCheckoutErrorMessage(): string | null {
    if (!createCheckoutMutation.isError) return null;
    const err = createCheckoutMutation.error;
    if (err instanceof ApiError) {
      if (err.status === 409) return "You already have an active subscription.";
      if (err.status === 402) return "Billing setup incomplete. Please contact support.";
      return err.message;
    }
    return err?.message ?? "Failed to start checkout. Please try again.";
  }

  function getPortalErrorMessage(): string | null {
    if (!createPortalMutation.isError) return null;
    const err = createPortalMutation.error;
    if (err instanceof ApiError) return err.message;
    return err?.message ?? "Failed to open billing portal. Please try again.";
  }

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (tenantsLoading || subscriptionLoading || plansLoading) {
    return <BillingLoadingFallback />;
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
  const quota5h = subscription?.plan?.token_quota_5h ?? 0;
  const quotaWeekly = subscription?.plan?.token_quota_weekly ?? 0;

  const checkoutErrorMessage = getCheckoutErrorMessage();
  const portalErrorMessage = getPortalErrorMessage();

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

      {/* Post-checkout: processing banner */}
      {sessionId && !checkoutComplete && (
        <div
          className={`rounded-lg border p-4 flex items-start gap-3 ${
            pollTimedOut
              ? "bg-amber-400/10 border-amber-400/30"
              : "bg-cyan-400/10 border-cyan-400/30"
          }`}
        >
          {!pollTimedOut && (
            <Loader2 className="h-5 w-5 text-cyan-400 shrink-0 mt-0.5 animate-spin" />
          )}
          <div className="space-y-1">
            {pollTimedOut ? (
              <>
                <p className="text-sm font-medium text-amber-400">
                  Payment received
                </p>
                <p className="text-sm text-zinc-400">
                  Your subscription may take a moment to activate. Please refresh the page shortly.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-cyan-400">
                  Processing your payment...
                </p>
                <p className="text-sm text-zinc-400">
                  Waiting for subscription to activate. This usually takes a few seconds.
                </p>
              </>
            )}
          </div>
        </div>
      )}

      {/* Post-checkout: success banner (auto-dismisses after 5s) */}
      {checkoutComplete && (
        <div className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-4 flex items-center gap-3">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <p className="text-sm text-emerald-400 font-medium">
            Subscription activated!
            {successPlanName && (
              <span className="font-normal text-zinc-300">
                {" "}
                You are now on the {successPlanName} plan.
              </span>
            )}
          </p>
        </div>
      )}

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

          {/* Token quotas */}
          <div className="flex flex-col gap-1">
            <p className="text-sm text-zinc-400">
              5h quota:{" "}
              <span className="text-foreground font-medium">
                {quota5h > 0 ? quota5h.toLocaleString() + " tokens" : "Unlimited"}
              </span>
            </p>
            <p className="text-sm text-zinc-400">
              Weekly quota:{" "}
              <span className="text-foreground font-medium">
                {quotaWeekly > 0 ? quotaWeekly.toLocaleString() + " tokens" : "Unlimited"}
              </span>
            </p>
          </div>

          {/* Manage Billing button — billing_access users only, for paid plans */}
          {hasBillingAccess &&
            (subscription?.status === "active" ||
              subscription?.status === "past_due") && (
              <div className="flex flex-col gap-2">
                <div>
                  <GlowButton
                    variant="secondary"
                    size="sm"
                    onClick={handlePortal}
                    isLoading={createPortalMutation.isPending}
                    loadingText="Opening..."
                  >
                    <ExternalLink className="h-4 w-4" />
                    Manage Billing
                  </GlowButton>
                </div>
                {portalErrorMessage && (
                  <p className="text-sm text-rose-400">{portalErrorMessage}</p>
                )}
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
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {plans.map((plan) => (
                <PlanCard
                  key={plan.id}
                  plan={plan}
                  subscription={subscription}
                  hasBillingAccess={hasBillingAccess}
                  onCheckout={handleCheckout}
                  checkoutPlanId={checkoutPlanId}
                />
              ))}
            </div>

            {/* Checkout error */}
            {checkoutErrorMessage && (
              <p className="mt-4 text-sm text-rose-400">{checkoutErrorMessage}</p>
            )}
          </>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export — wraps content in Suspense (required by Next.js for useSearchParams)
// ---------------------------------------------------------------------------

export default function BillingPage() {
  return (
    <Suspense fallback={<BillingLoadingFallback />}>
      <BillingPageContent />
    </Suspense>
  );
}
