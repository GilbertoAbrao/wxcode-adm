"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  GlowButton,
  GlowInput,
  LoadingSkeleton,
  ErrorState,
  EmptyState,
} from "@/components/ui";
import {
  useAdminTenants,
  useSuspendTenant,
  useReactivateTenant,
  TenantListItem,
} from "@/hooks/useAdminTenants";
import { useAdminAuthContext } from "@/providers/admin-auth-provider";
import { ApiError } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_LIMIT = 20;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadge(item: TenantListItem): { label: string; className: string } {
  if (item.is_deleted) {
    return { label: "Deleted", className: "bg-rose-400/10 text-rose-400" };
  }
  if (item.is_suspended) {
    return { label: "Suspended", className: "bg-amber-400/10 text-amber-400" };
  }
  return { label: "Active", className: "bg-emerald-400/10 text-emerald-400" };
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
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
// Inline action row for suspend/reactivate confirmation
// ---------------------------------------------------------------------------

interface ActionRowProps {
  tenantId: string;
  action: "suspend" | "reactivate";
  onConfirm: (reason: string) => Promise<void>;
  onCancel: () => void;
  isPending: boolean;
  error: string | null;
}

function ActionRow({
  action,
  onConfirm,
  onCancel,
  isPending,
  error,
}: ActionRowProps) {
  const [reason, setReason] = useState("");

  const label = action === "suspend" ? "Suspend" : "Reactivate";
  const confirmClass =
    action === "suspend"
      ? "text-amber-400 border-amber-400/30"
      : "text-emerald-400 border-emerald-400/30";

  return (
    <tr className="bg-zinc-900/60">
      <td colSpan={7} className="px-4 py-3">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          <div className="flex-1 max-w-md">
            <GlowInput
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={`Reason for ${action.toLowerCase()}...`}
              fullWidth
              autoFocus
            />
          </div>
          <div className="flex items-center gap-2">
            <GlowButton
              size="sm"
              onClick={() => onConfirm(reason)}
              disabled={!reason.trim() || isPending}
              isLoading={isPending}
              loadingText="Saving..."
              className={`border ${confirmClass}`}
            >
              {label}
            </GlowButton>
            <button
              type="button"
              onClick={onCancel}
              disabled={isPending}
              className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
          {error && (
            <p className="text-sm text-rose-400 sm:ml-2">{error}</p>
          )}
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Tenant Management Page
// ---------------------------------------------------------------------------

export default function AdminTenantsPage() {
  const { logout } = useAdminAuthContext();

  // Filter state
  const [planSlug, setPlanSlug] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // Pagination state
  const [page, setPage] = useState(0);
  const offset = page * PAGE_LIMIT;

  // Inline action state
  const [actionTenant, setActionTenant] = useState<{
    id: string;
    action: "suspend" | "reactivate";
  } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Data fetching
  const { data, isLoading, isError, error, refetch } = useAdminTenants({
    limit: PAGE_LIMIT,
    offset,
    plan_slug: planSlug || null,
    status: statusFilter || null,
  });

  const suspendMutation = useSuspendTenant();
  const reactivateMutation = useReactivateTenant();

  const isMutationPending =
    suspendMutation.isPending || reactivateMutation.isPending;

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleFilterChange = () => {
    // Reset to page 0 when filters change
    setPage(0);
    setActionTenant(null);
    setActionError(null);
  };

  const handleAction = (id: string, action: "suspend" | "reactivate") => {
    setActionTenant({ id, action });
    setActionError(null);
  };

  const handleConfirmAction = async (reason: string) => {
    if (!actionTenant) return;
    setActionError(null);
    try {
      if (actionTenant.action === "suspend") {
        await suspendMutation.mutateAsync({
          tenant_id: actionTenant.id,
          reason,
        });
      } else {
        await reactivateMutation.mutateAsync({
          tenant_id: actionTenant.id,
          reason,
        });
      }
      setActionTenant(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(err.message);
      } else if (err instanceof Error) {
        setActionError(err.message);
      } else {
        setActionError("Action failed. Please try again.");
      }
    }
  };

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950">
        <AdminNav onLogout={logout} />
        <div className="max-w-7xl mx-auto px-6 space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Tenant Management
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              View and moderate all tenants on the platform.
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
            <LoadingSkeleton lines={6} />
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Error state
  // ---------------------------------------------------------------------------

  if (isError) {
    return (
      <div className="min-h-screen bg-zinc-950">
        <AdminNav onLogout={logout} />
        <div className="max-w-7xl mx-auto px-6 space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Tenant Management
            </h1>
          </div>
          <ErrorState
            title="Failed to load tenants"
            message={
              error instanceof Error
                ? error.message
                : "An unexpected error occurred"
            }
            onRetry={() => refetch()}
          />
        </div>
      </div>
    );
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const showingStart = offset + 1;
  const showingEnd = Math.min(offset + PAGE_LIMIT, total);
  const hasPrev = page > 0;
  const hasNext = offset + PAGE_LIMIT < total;

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-zinc-950">
      <AdminNav onLogout={logout} />

      <div className="max-w-7xl mx-auto px-6 space-y-6 pb-12">
        {/* Page header */}
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Tenant Management
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            View and moderate all tenants on the platform.
          </p>
        </div>

        {/* Filter bar */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="w-full sm:w-64">
            <GlowInput
              value={planSlug}
              onChange={(e) => {
                setPlanSlug(e.target.value);
                handleFilterChange();
              }}
              placeholder="Filter by plan slug..."
              fullWidth
            />
          </div>
          <div>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                handleFilterChange();
              }}
              className="bg-zinc-900 border border-zinc-700 text-zinc-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400 h-[42px]"
            >
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="deleted">Deleted</option>
            </select>
          </div>
        </div>

        {/* Table */}
        {items.length === 0 ? (
          <EmptyState
            title="No tenants found"
            description="No tenants match the current filters."
          />
        ) : (
          <div className="rounded-lg border border-zinc-800 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-zinc-900/50">
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Slug
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Plan
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Members
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((tenant) => {
                    const badge = statusBadge(tenant);
                    const isActionRow =
                      actionTenant?.id === tenant.id;
                    const isPendingThis =
                      isMutationPending && actionTenant?.id === tenant.id;

                    return (
                      <React.Fragment key={tenant.id}>
                        <tr
                          className="border-b border-zinc-800 hover:bg-zinc-900/30 transition-colors"
                        >
                          <td className="px-4 py-3 text-sm font-medium">
                            <Link
                              href={`/admin/tenants/${tenant.id}`}
                              className="text-cyan-400 hover:text-cyan-300 hover:underline transition-colors"
                            >
                              {tenant.name}
                            </Link>
                          </td>
                          <td className="px-4 py-3 text-sm font-mono text-zinc-500">
                            {tenant.slug}
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-500">
                            {tenant.plan_name ?? "No plan"}
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${badge.className}`}
                            >
                              {badge.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-300">
                            {tenant.member_count}
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-500">
                            {formatDate(tenant.created_at)}
                          </td>
                          <td className="px-4 py-3">
                            {/* Active → show Suspend button */}
                            {!tenant.is_suspended && !tenant.is_deleted && (
                              <button
                                type="button"
                                disabled={isMutationPending}
                                onClick={() =>
                                  isActionRow
                                    ? setActionTenant(null)
                                    : handleAction(tenant.id, "suspend")
                                }
                                className="text-xs font-medium text-amber-400 hover:bg-amber-400/10 px-2 py-1 rounded transition-colors disabled:opacity-50"
                              >
                                Suspend
                              </button>
                            )}

                            {/* Suspended → show Reactivate button */}
                            {tenant.is_suspended && !tenant.is_deleted && (
                              <button
                                type="button"
                                disabled={isMutationPending}
                                onClick={() =>
                                  isActionRow
                                    ? setActionTenant(null)
                                    : handleAction(tenant.id, "reactivate")
                                }
                                className="text-xs font-medium text-emerald-400 hover:bg-emerald-400/10 px-2 py-1 rounded transition-colors disabled:opacity-50"
                              >
                                Reactivate
                              </button>
                            )}

                            {/* Deleted → no actions */}
                          </td>
                        </tr>

                        {/* Inline action row */}
                        {isActionRow && actionTenant && (
                          <ActionRow
                            key={`action-${tenant.id}`}
                            tenantId={tenant.id}
                            action={actionTenant.action}
                            onConfirm={handleConfirmAction}
                            onCancel={() => {
                              setActionTenant(null);
                              setActionError(null);
                            }}
                            isPending={isPendingThis}
                            error={actionError}
                          />
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Pagination */}
        {total > 0 && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-zinc-500">
              Showing {showingStart}–{showingEnd} of {total} tenants
            </p>
            <div className="flex items-center gap-2">
              <GlowButton
                variant="ghost"
                size="sm"
                disabled={!hasPrev}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </GlowButton>
              <span className="text-sm text-zinc-500 px-2">
                Page {page + 1}
              </span>
              <GlowButton
                variant="ghost"
                size="sm"
                disabled={!hasNext}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </GlowButton>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
