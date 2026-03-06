"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import {
  LoadingSkeleton,
  ErrorState,
} from "@/components/ui";
import {
  useAdminTenantDetail,
  type TenantDetailResponse,
} from "@/hooks/useAdminTenants";
import { useAdminAuthContext } from "@/providers/admin-auth-provider";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function statusBadge(tenant: TenantDetailResponse): {
  label: string;
  className: string;
} {
  if (tenant.is_deleted) {
    return { label: "Deleted", className: "bg-rose-400/10 text-rose-400" };
  }
  if (tenant.is_suspended) {
    return { label: "Suspended", className: "bg-amber-400/10 text-amber-400" };
  }
  return { label: "Active", className: "bg-emerald-400/10 text-emerald-400" };
}

function subscriptionBadgeClass(status: string | null): string {
  switch (status) {
    case "active":
      return "bg-emerald-400/10 text-emerald-400";
    case "past_due":
      return "bg-amber-400/10 text-amber-400";
    case "canceled":
      return "bg-rose-400/10 text-rose-400";
    case "free":
      return "bg-zinc-400/10 text-zinc-400";
    default:
      return "bg-zinc-400/10 text-zinc-400";
  }
}

// ---------------------------------------------------------------------------
// Admin Nav
// ---------------------------------------------------------------------------

function AdminNav({ onLogout }: { onLogout: () => void }) {
  return (
    <nav className="flex items-center justify-between px-6 py-3 border-b border-zinc-800 bg-zinc-950 mb-6">
      <div className="flex items-center gap-1">
        <Link
          href="/admin/dashboard"
          className="px-3 py-1.5 text-sm font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          Dashboard
        </Link>
        <Link
          href="/admin/tenants"
          className="px-3 py-1.5 text-sm font-medium text-cyan-400 border-b-2 border-cyan-400 -mb-px"
        >
          Tenants
        </Link>
        <Link
          href="/admin/users"
          className="px-3 py-1.5 text-sm font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          Users
        </Link>
        <Link
          href="/admin/audit-logs"
          className="px-3 py-1.5 text-sm font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          Audit Logs
        </Link>
      </div>
      <button
        type="button"
        onClick={onLogout}
        className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
      >
        Logout
      </button>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Tenant Detail Page
// ---------------------------------------------------------------------------

export default function TenantDetailPage() {
  const params = useParams();
  const tenantId = typeof params.tenantId === "string" ? params.tenantId : null;
  const { logout } = useAdminAuthContext();

  const { data: tenant, isLoading, isError, error, refetch } =
    useAdminTenantDetail(tenantId);

  return (
    <div className="min-h-screen bg-zinc-950">
      <AdminNav onLogout={logout} />

      <div className="max-w-5xl mx-auto px-6 space-y-6 pb-12">
        {/* Back link */}
        <Link
          href="/admin/tenants"
          className="inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Tenants
        </Link>

        {/* Loading state */}
        {isLoading && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
            <LoadingSkeleton lines={6} />
          </div>
        )}

        {/* Error state */}
        {isError && (
          <ErrorState
            title="Failed to load tenant"
            message={
              error instanceof Error
                ? error.message
                : "An unexpected error occurred"
            }
            onRetry={() => refetch()}
          />
        )}

        {/* Tenant content */}
        {tenant && (
          <>
            {/* Tenant header */}
            <div className="flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <h1 className="text-2xl font-bold text-zinc-100 truncate">
                  {tenant.name}
                </h1>
                <p className="text-sm font-mono text-zinc-500 mt-0.5">
                  {tenant.slug}
                </p>
              </div>
              {(() => {
                const badge = statusBadge(tenant);
                return (
                  <span
                    className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium flex-shrink-0 ${badge.className}`}
                  >
                    {badge.label}
                  </span>
                );
              })()}
            </div>

            {/* Info grid */}
            <div className="grid lg:grid-cols-2 gap-6">
              {/* Subscription & Plan card */}
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
                <h2 className="text-sm font-semibold text-zinc-300">
                  Subscription &amp; Plan
                </h2>
                <dl className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">Plan</dt>
                    <dd className="text-sm text-zinc-300 text-right">
                      {tenant.plan_name ?? (
                        <span className="text-zinc-600">No plan</span>
                      )}
                      {tenant.plan_slug && (
                        <span className="ml-1.5 font-mono text-xs text-zinc-600">
                          ({tenant.plan_slug})
                        </span>
                      )}
                    </dd>
                  </div>

                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">Status</dt>
                    <dd>
                      {tenant.subscription_status ? (
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${subscriptionBadgeClass(tenant.subscription_status)}`}
                        >
                          {tenant.subscription_status}
                        </span>
                      ) : (
                        <span className="text-sm text-zinc-600">—</span>
                      )}
                    </dd>
                  </div>

                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">wxcode URL</dt>
                    <dd className="text-sm text-right">
                      {tenant.wxcode_url ? (
                        <a
                          href={tenant.wxcode_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-cyan-400 hover:text-cyan-300 hover:underline transition-colors break-all"
                        >
                          {tenant.wxcode_url}
                        </a>
                      ) : (
                        <span className="text-zinc-600">Not configured</span>
                      )}
                    </dd>
                  </div>
                </dl>
              </div>

              {/* Security & Membership card */}
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
                <h2 className="text-sm font-semibold text-zinc-300">
                  Security &amp; Membership
                </h2>
                <dl className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">MFA Enforced</dt>
                    <dd>
                      {tenant.mfa_enforced ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-400/10 text-emerald-400">
                          Yes
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-400/10 text-zinc-400">
                          No
                        </span>
                      )}
                    </dd>
                  </div>

                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">Member Count</dt>
                    <dd className="text-sm text-zinc-300">{tenant.member_count}</dd>
                  </div>

                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">Created</dt>
                    <dd className="text-sm text-zinc-300">
                      {formatDate(tenant.created_at)}
                    </dd>
                  </div>

                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">Updated</dt>
                    <dd className="text-sm text-zinc-300">
                      {formatDate(tenant.updated_at)}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
