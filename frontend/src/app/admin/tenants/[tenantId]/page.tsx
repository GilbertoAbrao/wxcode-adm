"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Key, Settings, Zap } from "lucide-react";
import {
  GlowButton,
  GlowInput,
  LoadingSkeleton,
  ErrorState,
} from "@/components/ui";
import {
  useAdminTenantDetail,
  useSetClaudeToken,
  useRevokeClaudeToken,
  useUpdateClaudeConfig,
  useActivateTenant,
  type TenantDetailResponse,
} from "@/hooks/useAdminTenants";
import { useAdminAuthContext } from "@/providers/admin-auth-provider";
import { ApiError } from "@/lib/api-client";

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

function wxcodeStatusBadge(status: string): { label: string; className: string } {
  switch (status) {
    case "pending_setup":
      return { label: "Pending Setup", className: "bg-amber-400/10 text-amber-400" };
    case "active":
      return { label: "Active", className: "bg-emerald-400/10 text-emerald-400" };
    case "suspended":
      return { label: "Suspended", className: "bg-amber-400/10 text-amber-400" };
    case "cancelled":
      return { label: "Cancelled", className: "bg-rose-400/10 text-rose-400" };
    default:
      return { label: status, className: "bg-zinc-400/10 text-zinc-400" };
  }
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
          href="/admin/plans"
          className="px-3 py-1.5 text-sm font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
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
// Tenant Detail Page
// ---------------------------------------------------------------------------

export default function TenantDetailPage() {
  const params = useParams();
  const tenantId = typeof params.tenantId === "string" ? params.tenantId : null;
  const { logout } = useAdminAuthContext();

  const { data: tenant, isLoading, isError, error, refetch } =
    useAdminTenantDetail(tenantId);

  // Claude token form state
  const [showTokenForm, setShowTokenForm] = useState(false);
  const [tokenValue, setTokenValue] = useState("");
  const [tokenReason, setTokenReason] = useState("");
  const [tokenError, setTokenError] = useState<string | null>(null);

  // Revoke token form state
  const [showRevokeForm, setShowRevokeForm] = useState(false);
  const [revokeReason, setRevokeReason] = useState("");
  const [revokeError, setRevokeError] = useState<string | null>(null);

  // Claude config form state
  const [showConfigForm, setShowConfigForm] = useState(false);
  const [configModel, setConfigModel] = useState("");
  const [configSessions, setConfigSessions] = useState("");
  const [configBudget, setConfigBudget] = useState("");
  const [configError, setConfigError] = useState<string | null>(null);

  // Activate form state
  const [showActivateForm, setShowActivateForm] = useState(false);
  const [activateReason, setActivateReason] = useState("");
  const [activateError, setActivateError] = useState<string | null>(null);

  // Mutation hooks
  const setTokenMutation = useSetClaudeToken();
  const revokeTokenMutation = useRevokeClaudeToken();
  const updateConfigMutation = useUpdateClaudeConfig();
  const activateMutation = useActivateTenant();

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleSetToken = async () => {
    if (!tenant || !tokenValue.trim() || !tokenReason.trim()) return;
    setTokenError(null);
    try {
      await setTokenMutation.mutateAsync({
        tenant_id: tenant.id,
        token: tokenValue.trim(),
        reason: tokenReason.trim(),
      });
      setShowTokenForm(false);
      setTokenValue("");
      setTokenReason("");
    } catch (err) {
      if (err instanceof ApiError) {
        setTokenError(err.message);
      } else if (err instanceof Error) {
        setTokenError(err.message);
      } else {
        setTokenError("Failed to set token. Please try again.");
      }
    }
  };

  const handleRevokeToken = async () => {
    if (!tenant || !revokeReason.trim()) return;
    setRevokeError(null);
    try {
      await revokeTokenMutation.mutateAsync({
        tenant_id: tenant.id,
        reason: revokeReason.trim(),
      });
      setShowRevokeForm(false);
      setRevokeReason("");
    } catch (err) {
      if (err instanceof ApiError) {
        setRevokeError(err.message);
      } else if (err instanceof Error) {
        setRevokeError(err.message);
      } else {
        setRevokeError("Failed to revoke token. Please try again.");
      }
    }
  };

  const handleUpdateConfig = async () => {
    if (!tenant) return;
    if (!configModel && !configSessions && !configBudget) return;
    setConfigError(null);

    const payload: {
      tenant_id: string;
      claude_default_model?: string;
      claude_max_concurrent_sessions?: number;
      claude_monthly_token_budget?: number;
    } = { tenant_id: tenant.id };

    if (configModel) {
      payload.claude_default_model = configModel.trim();
    }
    if (configSessions) {
      payload.claude_max_concurrent_sessions = parseInt(configSessions, 10);
    }
    if (configBudget) {
      // 0 means unlimited (maps to NULL in DB)
      payload.claude_monthly_token_budget = parseInt(configBudget, 10);
    }

    try {
      await updateConfigMutation.mutateAsync(payload);
      setShowConfigForm(false);
      setConfigModel("");
      setConfigSessions("");
      setConfigBudget("");
    } catch (err) {
      if (err instanceof ApiError) {
        setConfigError(err.message);
      } else if (err instanceof Error) {
        setConfigError(err.message);
      } else {
        setConfigError("Failed to update config. Please try again.");
      }
    }
  };

  const handleActivate = async () => {
    if (!tenant || !activateReason.trim()) return;
    setActivateError(null);
    try {
      await activateMutation.mutateAsync({
        tenant_id: tenant.id,
        reason: activateReason.trim(),
      });
      setShowActivateForm(false);
      setActivateReason("");
    } catch (err) {
      if (err instanceof ApiError) {
        setActivateError(err.message);
      } else if (err instanceof Error) {
        setActivateError(err.message);
      } else {
        setActivateError("Failed to activate tenant. Please try again.");
      }
    }
  };

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

            {/* WXCODE Integration card — full width */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-zinc-300">WXCODE Integration</h2>
                <span
                  className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${wxcodeStatusBadge(tenant.status).className}`}
                >
                  {wxcodeStatusBadge(tenant.status).label}
                </span>
              </div>

              {/* Claude Token subsection */}
              <div className="space-y-3 border-t border-zinc-800 pt-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
                    <Key className="h-3.5 w-3.5" /> Claude Token
                  </h3>
                  <div className="flex items-center gap-2">
                    {tenant.has_claude_token ? (
                      <>
                        <span className="text-xs text-zinc-500 font-mono">****-****-****</span>
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-emerald-900/30 text-emerald-400 border border-emerald-800">
                          Set
                        </span>
                      </>
                    ) : (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-zinc-800 text-zinc-500 border border-zinc-700">
                        Not Set
                      </span>
                    )}
                  </div>
                </div>

                {/* Action buttons row */}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setShowTokenForm(!showTokenForm);
                      setShowRevokeForm(false);
                      setTokenError(null);
                    }}
                    className="text-xs font-medium text-cyan-400 hover:bg-cyan-400/10 px-2 py-1 rounded transition-colors"
                  >
                    {tenant.has_claude_token ? "Update Token" : "Set Token"}
                  </button>
                  {tenant.has_claude_token && (
                    <button
                      type="button"
                      onClick={() => {
                        setShowRevokeForm(!showRevokeForm);
                        setShowTokenForm(false);
                        setRevokeError(null);
                      }}
                      className="text-xs font-medium text-rose-400 hover:bg-rose-400/10 px-2 py-1 rounded transition-colors"
                    >
                      Revoke
                    </button>
                  )}
                </div>

                {/* Inline Set Token form */}
                {showTokenForm && (
                  <div className="space-y-3 bg-zinc-900/80 rounded-lg p-4 border border-zinc-800">
                    <GlowInput
                      label="Claude Token"
                      type="password"
                      value={tokenValue}
                      onChange={(e) => setTokenValue(e.target.value)}
                      placeholder="sk-ant-..."
                      fullWidth
                      autoFocus
                    />
                    <GlowInput
                      label="Reason"
                      value={tokenReason}
                      onChange={(e) => setTokenReason(e.target.value)}
                      placeholder="Reason for setting token..."
                      fullWidth
                    />
                    <div className="flex items-center gap-2">
                      <GlowButton
                        size="sm"
                        onClick={handleSetToken}
                        disabled={!tokenValue.trim() || !tokenReason.trim() || setTokenMutation.isPending}
                        isLoading={setTokenMutation.isPending}
                        loadingText="Saving..."
                      >
                        {tenant.has_claude_token ? "Update Token" : "Set Token"}
                      </GlowButton>
                      <button
                        type="button"
                        onClick={() => {
                          setShowTokenForm(false);
                          setTokenValue("");
                          setTokenReason("");
                          setTokenError(null);
                        }}
                        className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                    {tokenError && <p className="text-xs text-rose-400">{tokenError}</p>}
                  </div>
                )}

                {/* Inline Revoke Token form */}
                {showRevokeForm && (
                  <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
                    <div className="flex-1 max-w-md">
                      <GlowInput
                        value={revokeReason}
                        onChange={(e) => setRevokeReason(e.target.value)}
                        placeholder="Reason for revoking token..."
                        fullWidth
                        autoFocus
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <GlowButton
                        size="sm"
                        variant="danger"
                        onClick={handleRevokeToken}
                        disabled={!revokeReason.trim() || revokeTokenMutation.isPending}
                        isLoading={revokeTokenMutation.isPending}
                        loadingText="Revoking..."
                      >
                        Confirm Revoke
                      </GlowButton>
                      <button
                        type="button"
                        onClick={() => {
                          setShowRevokeForm(false);
                          setRevokeReason("");
                          setRevokeError(null);
                        }}
                        className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                    {revokeError && <p className="text-sm text-rose-400 sm:ml-2">{revokeError}</p>}
                  </div>
                )}
              </div>

              {/* Claude Config subsection */}
              <div className="space-y-3 border-t border-zinc-800 pt-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
                    <Settings className="h-3.5 w-3.5" /> Claude Configuration
                  </h3>
                  <button
                    type="button"
                    onClick={() => {
                      setShowConfigForm(!showConfigForm);
                      setConfigError(null);
                    }}
                    className="text-xs font-medium text-cyan-400 hover:bg-cyan-400/10 px-2 py-1 rounded transition-colors"
                  >
                    Edit
                  </button>
                </div>

                {/* Current config display */}
                <dl className="space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">Model</dt>
                    <dd className="text-sm text-zinc-300">{tenant.claude_default_model}</dd>
                  </div>
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">Max Sessions</dt>
                    <dd className="text-sm text-zinc-300">{tenant.claude_max_concurrent_sessions}</dd>
                  </div>
                  <div className="flex items-start justify-between gap-3">
                    <dt className="text-sm text-zinc-500">Monthly Budget</dt>
                    <dd className="text-sm text-zinc-300">
                      {tenant.claude_monthly_token_budget != null
                        ? tenant.claude_monthly_token_budget.toLocaleString() + " tokens"
                        : "Unlimited"}
                    </dd>
                  </div>
                </dl>

                {/* Inline Config edit form */}
                {showConfigForm && (
                  <div className="space-y-3 bg-zinc-900/80 rounded-lg p-4 border border-zinc-800">
                    <GlowInput
                      label="Model"
                      value={configModel}
                      onChange={(e) => setConfigModel(e.target.value)}
                      placeholder={tenant.claude_default_model}
                      fullWidth
                    />
                    <GlowInput
                      label="Max Sessions"
                      type="number"
                      value={configSessions}
                      onChange={(e) => setConfigSessions(e.target.value)}
                      placeholder={String(tenant.claude_max_concurrent_sessions)}
                      fullWidth
                    />
                    <GlowInput
                      label="Monthly Budget (0 = unlimited)"
                      type="number"
                      value={configBudget}
                      onChange={(e) => setConfigBudget(e.target.value)}
                      placeholder={
                        tenant.claude_monthly_token_budget != null
                          ? String(tenant.claude_monthly_token_budget)
                          : "Unlimited"
                      }
                      fullWidth
                    />
                    <div className="flex items-center gap-2">
                      <GlowButton
                        size="sm"
                        onClick={handleUpdateConfig}
                        disabled={(!configModel && !configSessions && !configBudget) || updateConfigMutation.isPending}
                        isLoading={updateConfigMutation.isPending}
                        loadingText="Saving..."
                      >
                        Save Config
                      </GlowButton>
                      <button
                        type="button"
                        onClick={() => {
                          setShowConfigForm(false);
                          setConfigModel("");
                          setConfigSessions("");
                          setConfigBudget("");
                          setConfigError(null);
                        }}
                        className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                    {configError && <p className="text-xs text-rose-400">{configError}</p>}
                  </div>
                )}
              </div>

              {/* Activate Tenant subsection — only visible when status=pending_setup */}
              {tenant.status === "pending_setup" && (
                <div className="space-y-3 border-t border-zinc-800 pt-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
                      <Zap className="h-3.5 w-3.5" /> Activate Tenant
                    </h3>
                    <button
                      type="button"
                      onClick={() => {
                        setShowActivateForm(!showActivateForm);
                        setActivateError(null);
                      }}
                      className="text-xs font-medium text-emerald-400 hover:bg-emerald-400/10 px-2 py-1 rounded transition-colors"
                    >
                      Activate
                    </button>
                  </div>
                  <p className="text-xs text-zinc-500">
                    Transition tenant from pending_setup to active. Requires database_name to be configured.
                  </p>
                  {showActivateForm && (
                    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
                      <div className="flex-1 max-w-md">
                        <GlowInput
                          value={activateReason}
                          onChange={(e) => setActivateReason(e.target.value)}
                          placeholder="Reason for activation..."
                          fullWidth
                          autoFocus
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <GlowButton
                          size="sm"
                          variant="success"
                          onClick={handleActivate}
                          disabled={!activateReason.trim() || activateMutation.isPending}
                          isLoading={activateMutation.isPending}
                          loadingText="Activating..."
                        >
                          Confirm Activate
                        </GlowButton>
                        <button
                          type="button"
                          onClick={() => {
                            setShowActivateForm(false);
                            setActivateReason("");
                            setActivateError(null);
                          }}
                          className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-50"
                        >
                          Cancel
                        </button>
                      </div>
                      {activateError && (
                        <p className="text-sm text-rose-400 sm:ml-2">{activateError}</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
