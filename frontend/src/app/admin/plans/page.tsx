"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Plus, Pencil, X } from "lucide-react";
import {
  GlowButton,
  GlowInput,
  LoadingSkeleton,
  ErrorState,
  EmptyState,
} from "@/components/ui";
import {
  useAdminPlans,
  useCreatePlan,
  useUpdatePlan,
  useDeletePlan,
  PlanResponse,
} from "@/hooks/useAdminPlans";
import { useAdminAuthContext } from "@/providers/admin-auth-provider";
import { ApiError } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
}

// ---------------------------------------------------------------------------
// Admin Nav (Plans active)
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
          href="/admin/plans"
          className="px-3 py-1.5 text-sm font-medium text-cyan-400 border-b-2 border-cyan-400 -mb-px"
        >
          Plans
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
// Plans Management Page
// ---------------------------------------------------------------------------

export default function AdminPlansPage() {
  const { logout } = useAdminAuthContext();

  // Create form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createSlug, setCreateSlug] = useState("");
  const [createFee, setCreateFee] = useState("");
  const [createQuota5h, setCreateQuota5h] = useState("");
  const [createQuotaWeekly, setCreateQuotaWeekly] = useState("");
  const [createOverage, setCreateOverage] = useState("0");
  const [createMemberCap, setCreateMemberCap] = useState("1");
  const [createMaxProjects, setCreateMaxProjects] = useState("5");
  const [createMaxOutputProjects, setCreateMaxOutputProjects] = useState("20");
  const [createMaxStorage, setCreateMaxStorage] = useState("10");
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit form state
  const [editingPlan, setEditingPlan] = useState<PlanResponse | null>(null);
  const [editName, setEditName] = useState("");
  const [editFee, setEditFee] = useState("");
  const [editTokenQuota5h, setEditTokenQuota5h] = useState("");
  const [editTokenQuotaWeekly, setEditTokenQuotaWeekly] = useState("");
  const [editOverage, setEditOverage] = useState("");
  const [editMemberCap, setEditMemberCap] = useState("");
  const [editMaxProjects, setEditMaxProjects] = useState("");
  const [editMaxOutputProjects, setEditMaxOutputProjects] = useState("");
  const [editMaxStorage, setEditMaxStorage] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  // Data fetching
  const { data: plans, isLoading, isError, error, refetch } = useAdminPlans();
  const createMutation = useCreatePlan();
  const updateMutation = useUpdatePlan();
  const deleteMutation = useDeletePlan();

  // Pre-populate edit form when a plan is selected for editing
  useEffect(() => {
    if (editingPlan) {
      setEditName(editingPlan.name);
      setEditFee(String(editingPlan.monthly_fee_cents));
      setEditTokenQuota5h(String(editingPlan.token_quota_5h));
      setEditTokenQuotaWeekly(String(editingPlan.token_quota_weekly));
      setEditOverage(String(editingPlan.overage_rate_cents_per_token));
      setEditMemberCap(String(editingPlan.member_cap));
      setEditMaxProjects(String(editingPlan.max_projects));
      setEditMaxOutputProjects(String(editingPlan.max_output_projects));
      setEditMaxStorage(String(editingPlan.max_storage_gb));
      setEditError(null);
    }
  }, [editingPlan]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleCreateNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const name = e.target.value;
    setCreateName(name);
    setCreateSlug(slugify(name));
  };

  const resetCreateForm = () => {
    setCreateName("");
    setCreateSlug("");
    setCreateFee("");
    setCreateQuota5h("");
    setCreateQuotaWeekly("");
    setCreateOverage("0");
    setCreateMemberCap("1");
    setCreateMaxProjects("5");
    setCreateMaxOutputProjects("20");
    setCreateMaxStorage("10");
    setCreateError(null);
  };

  const handleCreate = async () => {
    if (!createName.trim() || !createSlug.trim() || !createFee) return;
    setCreateError(null);
    try {
      await createMutation.mutateAsync({
        name: createName.trim(),
        slug: createSlug.trim(),
        monthly_fee_cents: parseInt(createFee, 10),
        token_quota_5h: parseInt(createQuota5h, 10) || 0,
        token_quota_weekly: parseInt(createQuotaWeekly, 10) || 0,
        overage_rate_cents_per_token: parseInt(createOverage || "0", 10),
        member_cap: parseInt(createMemberCap || "1", 10),
        max_projects: parseInt(createMaxProjects || "5", 10),
        max_output_projects: parseInt(createMaxOutputProjects || "20", 10),
        max_storage_gb: parseInt(createMaxStorage || "10", 10),
      });
      resetCreateForm();
      setShowCreateForm(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setCreateError(err.message);
      } else if (err instanceof Error) {
        setCreateError(err.message);
      } else {
        setCreateError("Failed to create plan. Please try again.");
      }
    }
  };

  const handleEdit = (plan: PlanResponse) => {
    if (editingPlan?.id === plan.id) {
      setEditingPlan(null);
    } else {
      setEditingPlan(plan);
      setShowCreateForm(false);
    }
  };

  const handleUpdate = async () => {
    if (!editingPlan) return;
    setEditError(null);

    const payload: { plan_id: string } & Record<string, unknown> = {
      plan_id: editingPlan.id,
    };

    if (editName !== editingPlan.name) payload.name = editName;
    if (editFee !== String(editingPlan.monthly_fee_cents))
      payload.monthly_fee_cents = parseInt(editFee, 10);
    if (editTokenQuota5h !== String(editingPlan.token_quota_5h))
      payload.token_quota_5h = parseInt(editTokenQuota5h, 10);
    if (editTokenQuotaWeekly !== String(editingPlan.token_quota_weekly))
      payload.token_quota_weekly = parseInt(editTokenQuotaWeekly, 10);
    if (editOverage !== String(editingPlan.overage_rate_cents_per_token))
      payload.overage_rate_cents_per_token = parseInt(editOverage, 10);
    if (editMemberCap !== String(editingPlan.member_cap))
      payload.member_cap = parseInt(editMemberCap, 10);
    if (editMaxProjects !== String(editingPlan.max_projects))
      payload.max_projects = parseInt(editMaxProjects, 10);
    if (editMaxOutputProjects !== String(editingPlan.max_output_projects))
      payload.max_output_projects = parseInt(editMaxOutputProjects, 10);
    if (editMaxStorage !== String(editingPlan.max_storage_gb))
      payload.max_storage_gb = parseInt(editMaxStorage, 10);

    try {
      await updateMutation.mutateAsync(
        payload as Parameters<typeof updateMutation.mutateAsync>[0]
      );
      setEditingPlan(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setEditError(err.message);
      } else if (err instanceof Error) {
        setEditError(err.message);
      } else {
        setEditError("Failed to update plan. Please try again.");
      }
    }
  };

  const handleDelete = async (plan: PlanResponse) => {
    if (!window.confirm(`Delete plan "${plan.name}"? This cannot be undone.`)) return;
    try {
      await deleteMutation.mutateAsync({ plan_id: plan.id });
    } catch (err) {
      // Surface error in a simple way — no inline error needed for delete
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
          ? err.message
          : "Failed to delete plan.";
      window.alert(msg);
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
              Plan Management
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Manage billing plans and wxcode operational limits.
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
              Plan Management
            </h1>
          </div>
          <ErrorState
            title="Failed to load plans"
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

  const items = plans ?? [];

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-zinc-950">
      <AdminNav onLogout={logout} />

      <div className="max-w-7xl mx-auto px-6 space-y-6 pb-12">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Plan Management
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Manage billing plans and wxcode operational limits.
            </p>
          </div>
          <GlowButton
            size="sm"
            onClick={() => {
              setShowCreateForm(!showCreateForm);
              setEditingPlan(null);
              if (!showCreateForm) resetCreateForm();
            }}
          >
            <Plus className="h-4 w-4 mr-1.5" />
            New Plan
          </GlowButton>
        </div>

        {/* Create form */}
        {showCreateForm && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-zinc-300">
                Create New Plan
              </h2>
              <button
                type="button"
                onClick={() => {
                  setShowCreateForm(false);
                  resetCreateForm();
                }}
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <GlowInput
                label="Name"
                value={createName}
                onChange={handleCreateNameChange}
                placeholder="Pro Plan"
                fullWidth
              />
              <GlowInput
                label="Slug"
                value={createSlug}
                onChange={(e) => setCreateSlug(e.target.value)}
                placeholder="pro-plan"
                fullWidth
              />
              <GlowInput
                label="Monthly Fee (cents)"
                type="number"
                value={createFee}
                onChange={(e) => setCreateFee(e.target.value)}
                placeholder="2900"
                fullWidth
              />
              <GlowInput
                label="Token Quota (5h)"
                type="number"
                value={createQuota5h}
                onChange={(e) => setCreateQuota5h(e.target.value)}
                placeholder="0"
                fullWidth
              />
              <GlowInput
                label="Token Quota (Weekly)"
                type="number"
                value={createQuotaWeekly}
                onChange={(e) => setCreateQuotaWeekly(e.target.value)}
                placeholder="0"
                fullWidth
              />
              <GlowInput
                label="Overage Rate (cents/token)"
                type="number"
                value={createOverage}
                onChange={(e) => setCreateOverage(e.target.value)}
                placeholder="0"
                fullWidth
              />
              <GlowInput
                label="Member Cap (-1 = unlimited)"
                type="number"
                value={createMemberCap}
                onChange={(e) => setCreateMemberCap(e.target.value)}
                placeholder="1"
                fullWidth
              />
              <GlowInput
                label="Max Projects"
                type="number"
                value={createMaxProjects}
                onChange={(e) => setCreateMaxProjects(e.target.value)}
                placeholder="5"
                fullWidth
              />
              <GlowInput
                label="Max Output Projects"
                type="number"
                value={createMaxOutputProjects}
                onChange={(e) => setCreateMaxOutputProjects(e.target.value)}
                placeholder="20"
                fullWidth
              />
              <GlowInput
                label="Max Storage (GB)"
                type="number"
                value={createMaxStorage}
                onChange={(e) => setCreateMaxStorage(e.target.value)}
                placeholder="10"
                fullWidth
              />
            </div>

            {createError && (
              <p className="text-sm text-rose-400">{createError}</p>
            )}

            <div className="flex items-center gap-3">
              <GlowButton
                variant="success"
                size="sm"
                onClick={handleCreate}
                disabled={
                  !createName.trim() ||
                  !createSlug.trim() ||
                  !createFee ||
                  createMutation.isPending
                }
                isLoading={createMutation.isPending}
                loadingText="Creating..."
              >
                Create Plan
              </GlowButton>
              <button
                type="button"
                onClick={() => {
                  setShowCreateForm(false);
                  resetCreateForm();
                }}
                disabled={createMutation.isPending}
                className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Table */}
        {items.length === 0 ? (
          <EmptyState
            title="No plans found"
            description="Create your first billing plan to get started."
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
                      Fee/mo
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Quota 5h
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Quota Weekly
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Max Projects
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Max Output
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Storage (GB)
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((plan) => {
                    const isEditRow = editingPlan?.id === plan.id;

                    return (
                      <React.Fragment key={plan.id}>
                        <tr className="border-b border-zinc-800 hover:bg-zinc-900/30 transition-colors">
                          <td className="px-4 py-3 text-sm font-medium text-zinc-200">
                            {plan.name}
                          </td>
                          <td className="px-4 py-3 text-sm font-mono text-zinc-500">
                            {plan.slug}
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-300">
                            {formatCurrency(plan.monthly_fee_cents)}
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-300">
                            {plan.token_quota_5h.toLocaleString()}
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-300">
                            {plan.token_quota_weekly.toLocaleString()}
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-300">
                            {plan.max_projects}
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-300">
                            {plan.max_output_projects}
                          </td>
                          <td className="px-4 py-3 text-sm text-zinc-300">
                            {plan.max_storage_gb}
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                plan.is_active
                                  ? "bg-emerald-400/10 text-emerald-400"
                                  : "bg-zinc-400/10 text-zinc-400"
                              }`}
                            >
                              {plan.is_active ? "Active" : "Inactive"}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={async () => {
                                  try {
                                    await updateMutation.mutateAsync({
                                      plan_id: plan.id,
                                      is_active: !plan.is_active,
                                    });
                                  } catch (err) {
                                    window.alert(
                                      err instanceof Error
                                        ? err.message
                                        : "Failed to update plan status"
                                    );
                                  }
                                }}
                                disabled={updateMutation.isPending}
                                className={`text-xs font-medium px-2 py-1 rounded transition-colors disabled:opacity-50 ${
                                  plan.is_active
                                    ? "text-amber-400 hover:bg-amber-400/10"
                                    : "text-emerald-400 hover:bg-emerald-400/10"
                                }`}
                              >
                                {plan.is_active ? "Inactivate" : "Activate"}
                              </button>
                              <button
                                type="button"
                                onClick={() => handleEdit(plan)}
                                className="text-xs font-medium text-cyan-400 hover:bg-cyan-400/10 px-2 py-1 rounded transition-colors"
                              >
                                <Pencil className="h-3.5 w-3.5 inline mr-0.5" />
                                Edit
                              </button>
                              {!plan.is_active && (
                                <button
                                  type="button"
                                  onClick={() => handleDelete(plan)}
                                  disabled={deleteMutation.isPending}
                                  className="text-xs font-medium text-rose-400 hover:bg-rose-400/10 px-2 py-1 rounded transition-colors disabled:opacity-50"
                                >
                                  <X className="h-3.5 w-3.5 inline mr-0.5" />
                                  Delete
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>

                        {/* Inline edit row */}
                        {isEditRow && (
                          <tr className="bg-zinc-900/60">
                            <td colSpan={10} className="px-4 py-4">
                              <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                  <h3 className="text-sm font-semibold text-zinc-300">
                                    Edit: {plan.name}
                                  </h3>
                                  <button
                                    type="button"
                                    onClick={() => setEditingPlan(null)}
                                    className="text-zinc-500 hover:text-zinc-300 transition-colors"
                                  >
                                    <X className="h-4 w-4" />
                                  </button>
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                                  <GlowInput
                                    label="Name"
                                    value={editName}
                                    onChange={(e) =>
                                      setEditName(e.target.value)
                                    }
                                    fullWidth
                                  />
                                  <GlowInput
                                    label="Monthly Fee (cents)"
                                    type="number"
                                    value={editFee}
                                    onChange={(e) => setEditFee(e.target.value)}
                                    fullWidth
                                  />
                                  <GlowInput
                                    label="Token Quota (5h)"
                                    type="number"
                                    value={editTokenQuota5h}
                                    onChange={(e) =>
                                      setEditTokenQuota5h(e.target.value)
                                    }
                                    fullWidth
                                  />
                                  <GlowInput
                                    label="Token Quota (Weekly)"
                                    type="number"
                                    value={editTokenQuotaWeekly}
                                    onChange={(e) =>
                                      setEditTokenQuotaWeekly(e.target.value)
                                    }
                                    fullWidth
                                  />
                                  <GlowInput
                                    label="Overage Rate (cents/token)"
                                    type="number"
                                    value={editOverage}
                                    onChange={(e) =>
                                      setEditOverage(e.target.value)
                                    }
                                    fullWidth
                                  />
                                  <GlowInput
                                    label="Member Cap"
                                    type="number"
                                    value={editMemberCap}
                                    onChange={(e) =>
                                      setEditMemberCap(e.target.value)
                                    }
                                    fullWidth
                                  />
                                  <GlowInput
                                    label="Max Projects"
                                    type="number"
                                    value={editMaxProjects}
                                    onChange={(e) =>
                                      setEditMaxProjects(e.target.value)
                                    }
                                    fullWidth
                                  />
                                  <GlowInput
                                    label="Max Output Projects"
                                    type="number"
                                    value={editMaxOutputProjects}
                                    onChange={(e) =>
                                      setEditMaxOutputProjects(e.target.value)
                                    }
                                    fullWidth
                                  />
                                  <GlowInput
                                    label="Max Storage (GB)"
                                    type="number"
                                    value={editMaxStorage}
                                    onChange={(e) =>
                                      setEditMaxStorage(e.target.value)
                                    }
                                    fullWidth
                                  />
                                </div>

                                {editError && (
                                  <p className="text-sm text-rose-400">
                                    {editError}
                                  </p>
                                )}

                                <div className="flex items-center gap-3">
                                  <GlowButton
                                    size="sm"
                                    onClick={handleUpdate}
                                    disabled={updateMutation.isPending}
                                    isLoading={updateMutation.isPending}
                                    loadingText="Saving..."
                                  >
                                    Save Changes
                                  </GlowButton>
                                  <button
                                    type="button"
                                    onClick={() => setEditingPlan(null)}
                                    disabled={updateMutation.isPending}
                                    className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-50"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Summary */}
        {items.length > 0 && (
          <p className="text-sm text-zinc-500">
            {items.length} plan{items.length !== 1 ? "s" : ""} total (
            {items.filter((p) => p.is_active).length} active)
          </p>
        )}
      </div>
    </div>
  );
}
