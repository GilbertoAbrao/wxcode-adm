"use client";

import { GlowButton } from "@/components/ui";
import { LayoutDashboard } from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <LayoutDashboard className="h-6 w-6 text-blue-500" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Welcome to wxCode Admin
            </p>
          </div>
        </div>
        <GlowButton variant="primary" size="sm">
          Get Started
        </GlowButton>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Tenants", value: "—", desc: "Active tenants" },
          { label: "Users", value: "—", desc: "Total users" },
          { label: "Revenue", value: "—", desc: "Monthly recurring" },
          { label: "API Keys", value: "—", desc: "Active keys" },
        ].map(({ label, value, desc }) => (
          <div
            key={label}
            className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-5"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {label}
            </p>
            <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">{desc}</p>
          </div>
        ))}
      </div>

      {/* Placeholder content */}
      <div className="rounded-lg border border-zinc-800 bg-obsidian-900/50 p-8 text-center">
        <p className="text-sm text-muted-foreground">
          Phase 12 design system complete — app shell with sidebar navigation,
          Obsidian Studio dark theme, and TanStack Query ready.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Phases 13–17 will populate this dashboard with live data.
        </p>
      </div>
    </div>
  );
}
