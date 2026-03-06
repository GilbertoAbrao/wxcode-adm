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
  useAdminAuditLogs,
  AuditLogItem,
} from "@/hooks/useAdminAuditLogs";
import { useAdminAuthContext } from "@/providers/admin-auth-provider";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_LIMIT = 50;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function truncateUUID(id: string | null, fallback: string = "—"): string {
  if (!id) return fallback;
  return id.slice(0, 8) + "...";
}

function truncateDetails(details: Record<string, unknown>): string {
  const str = JSON.stringify(details);
  return str.length > 50 ? str.slice(0, 50) + "..." : str;
}

// ---------------------------------------------------------------------------
// Admin Nav (4 links — Audit Logs active)
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
          className="px-3 py-1.5 text-sm font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
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
          className="px-3 py-1.5 text-sm font-medium text-cyan-400 border-b-2 border-cyan-400 -mb-px"
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
// Audit Log Row
// ---------------------------------------------------------------------------

function AuditLogRow({ log }: { log: AuditLogItem }) {
  const resource =
    log.resource_type +
    (log.resource_id ? ": " + log.resource_id.slice(0, 8) + "..." : "");
  const detailsStr = truncateDetails(log.details);
  const fullDetails = JSON.stringify(log.details);

  return (
    <tr className="border-b border-zinc-800 hover:bg-zinc-900/30 transition-colors">
      <td className="px-4 py-3 text-xs text-zinc-500 whitespace-nowrap">
        {formatDate(log.created_at)}
      </td>
      <td className="px-4 py-3">
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium text-cyan-400 bg-cyan-400/10">
          {log.action}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-zinc-400">{resource}</td>
      <td className="px-4 py-3 text-xs font-mono text-zinc-500">
        {log.actor_id ? truncateUUID(log.actor_id, "—") : "System"}
      </td>
      <td className="px-4 py-3 text-xs font-mono text-zinc-500">
        {truncateUUID(log.tenant_id)}
      </td>
      <td className="px-4 py-3 text-xs text-zinc-500">
        {log.ip_address ?? "—"}
      </td>
      <td
        className="px-4 py-3 text-xs text-zinc-500 max-w-[160px] truncate cursor-default"
        title={fullDetails}
      >
        {detailsStr}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Audit Log Viewer Page
// ---------------------------------------------------------------------------

export default function AdminAuditLogsPage() {
  const { logout } = useAdminAuthContext();

  // Filter state
  const [actionFilter, setActionFilter] = useState("");
  const [tenantFilter, setTenantFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");

  // Pagination state
  const [page, setPage] = useState(0);
  const offset = page * PAGE_LIMIT;

  // Data fetching
  const { data, isLoading, isError, error, refetch } = useAdminAuditLogs({
    limit: PAGE_LIMIT,
    offset,
    action: actionFilter || null,
    tenant_id: tenantFilter || null,
    actor_id: actorFilter || null,
  });

  const handleFilterChange = () => {
    setPage(0);
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
            <h1 className="text-2xl font-bold text-foreground">Audit Logs</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Platform-wide audit trail of sensitive actions.
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
            <LoadingSkeleton lines={8} />
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
            <h1 className="text-2xl font-bold text-foreground">Audit Logs</h1>
          </div>
          <ErrorState
            title="Failed to load audit logs"
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
  const showingStart = total === 0 ? 0 : offset + 1;
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
          <h1 className="text-2xl font-bold text-foreground">Audit Logs</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Platform-wide audit trail of sensitive actions.
          </p>
        </div>

        {/* Filter bar */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <GlowInput
              value={actionFilter}
              onChange={(e) => {
                setActionFilter(e.target.value);
                handleFilterChange();
              }}
              placeholder="Filter by action..."
              fullWidth
            />
          </div>
          <div className="flex-1">
            <GlowInput
              value={tenantFilter}
              onChange={(e) => {
                setTenantFilter(e.target.value);
                handleFilterChange();
              }}
              placeholder="Filter by tenant ID..."
              fullWidth
            />
          </div>
          <div className="flex-1">
            <GlowInput
              value={actorFilter}
              onChange={(e) => {
                setActorFilter(e.target.value);
                handleFilterChange();
              }}
              placeholder="Filter by actor ID..."
              fullWidth
            />
          </div>
        </div>

        {/* Empty state */}
        {items.length === 0 ? (
          <EmptyState
            title="No audit logs found"
            description="No audit log entries match the current filters."
          />
        ) : (
          <div className="rounded-lg border border-zinc-800 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-zinc-900/50">
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Timestamp
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Action
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Resource
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Actor
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Tenant
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      IP
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Details
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((log) => (
                    <AuditLogRow key={log.id} log={log} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Pagination */}
        {total > 0 && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-zinc-500">
              Showing {showingStart}–{showingEnd} of {total} entries
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
