"use client";

import React from "react";
import Link from "next/link";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { LoadingSkeleton, ErrorState } from "@/components/ui";
import {
  useAdminDashboard,
  MRRDashboardResponse,
  PlanDistributionItem,
} from "@/hooks/useAdminDashboard";
import { useAdminAuthContext } from "@/providers/admin-auth-provider";

// ---------------------------------------------------------------------------
// Admin Nav (4 links)
// ---------------------------------------------------------------------------

function AdminNav({ onLogout }: { onLogout: () => void }) {
  return (
    <nav className="flex items-center justify-between px-6 py-3 border-b border-zinc-800 bg-zinc-950 mb-6">
      <div className="flex items-center gap-1">
        <Link
          href="/admin/dashboard"
          className="px-3 py-1.5 text-sm font-medium text-cyan-400 border-b-2 border-cyan-400 -mb-px"
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
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(cents: number): string {
  return (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function formatTrendDate(val: string): string {
  return new Date(val).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Plan Distribution bar row
// ---------------------------------------------------------------------------

function PlanDistributionRow({
  item,
  maxCount,
}: {
  item: PlanDistributionItem;
  maxCount: number;
}) {
  const pct = maxCount > 0 ? (item.count / maxCount) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm text-zinc-300 truncate">{item.plan_name}</span>
          <span className="text-sm font-medium text-zinc-400 ml-3 flex-shrink-0">
            {item.count}
          </span>
        </div>
        <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-cyan-400/60 transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metric Card
// ---------------------------------------------------------------------------

function MetricCard({
  label,
  value,
  valueClassName = "text-zinc-100",
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
      <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
        {label}
      </p>
      <p className={`text-3xl font-bold ${valueClassName}`}>{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Content (rendered after data loads)
// ---------------------------------------------------------------------------

function DashboardContent({ data }: { data: MRRDashboardResponse }) {
  const churnPct = (data.churn_rate * 100).toFixed(1);
  const churnClass =
    data.churn_rate > 0.05 ? "text-amber-400" : "text-emerald-400";

  const trendData = data.trend.map((p) => ({
    ...p,
    mrr_dollars: p.mrr_cents / 100,
  }));

  const maxPlanCount =
    data.plan_distribution.length > 0
      ? Math.max(...data.plan_distribution.map((p) => p.count))
      : 1;

  return (
    <div className="space-y-6">
      {/* Metric cards — 4-up grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Active Subscriptions"
          value={data.active_subscription_count.toLocaleString()}
          valueClassName="text-emerald-400"
        />
        <MetricCard
          label="Monthly Revenue"
          value={formatCurrency(data.mrr_cents)}
          valueClassName="text-cyan-400"
        />
        <MetricCard
          label="Churn Rate"
          value={`${churnPct}%`}
          valueClassName={churnClass}
        />
        <MetricCard
          label="Canceled (30d)"
          value={data.canceled_count_30d.toLocaleString()}
          valueClassName="text-rose-400"
        />
      </div>

      {/* 30-day MRR Trend chart */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">
          MRR Trend (30 days)
        </h2>
        {trendData.length === 0 ? (
          <p className="text-sm text-zinc-500">No trend data available.</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
              <XAxis
                dataKey="date"
                tickFormatter={formatTrendDate}
                tick={{ fill: "#a1a1aa", fontSize: 11 }}
                axisLine={{ stroke: "#3f3f46" }}
                tickLine={{ stroke: "#3f3f46" }}
              />
              <YAxis
                tickFormatter={(val: number) => `$${val.toLocaleString()}`}
                tick={{ fill: "#a1a1aa", fontSize: 11 }}
                axisLine={{ stroke: "#3f3f46" }}
                tickLine={{ stroke: "#3f3f46" }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: "8px",
                }}
                labelStyle={{ color: "#a1a1aa" }}
                formatter={(value) => {
                  const num = typeof value === "number" ? value : 0;
                  return [
                    `$${num.toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
                    "MRR",
                  ];
                }}
                labelFormatter={(label) => {
                  const str = String(label);
                  return new Date(str).toLocaleDateString(undefined, {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  });
                }}
              />
              <Line
                type="monotone"
                dataKey="mrr_dollars"
                stroke="#22d3ee"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: "#22d3ee" }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Plan Distribution */}
      {data.plan_distribution.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">
            Plan Distribution
          </h2>
          <div className="space-y-4">
            {data.plan_distribution.map((item) => (
              <PlanDistributionRow
                key={item.plan_slug}
                item={item}
                maxCount={maxPlanCount}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Revenue Dashboard Page
// ---------------------------------------------------------------------------

export default function AdminDashboardPage() {
  const { logout } = useAdminAuthContext();
  const { data, isLoading, isError, error, refetch } = useAdminDashboard();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-zinc-950">
        <AdminNav onLogout={logout} />
        <div className="max-w-7xl mx-auto px-6 space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Revenue Dashboard
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Monthly recurring revenue and subscription metrics.
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
            <LoadingSkeleton lines={8} />
          </div>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="min-h-screen bg-zinc-950">
        <AdminNav onLogout={logout} />
        <div className="max-w-7xl mx-auto px-6 space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Revenue Dashboard
            </h1>
          </div>
          <ErrorState
            title="Failed to load dashboard"
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

  return (
    <div className="min-h-screen bg-zinc-950">
      <AdminNav onLogout={logout} />

      <div className="max-w-7xl mx-auto px-6 space-y-6 pb-12">
        {/* Page header */}
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Revenue Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Monthly recurring revenue and subscription metrics.
          </p>
        </div>

        {data && <DashboardContent data={data} />}
      </div>
    </div>
  );
}
