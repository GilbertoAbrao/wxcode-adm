"use client";

/**
 * /admin/users — Admin user management page.
 *
 * Features:
 * - Email search with 300ms debounce
 * - Paginated user list (20 per page) with columns: Email, Display Name,
 *   Verified, MFA, Created
 * - Clicking a row opens a slide-out detail drawer from the right
 * - Drawer shows: user profile, memberships (with block/unblock per tenant),
 *   and read-only sessions
 * - Block/unblock: inline reason input, calls POST /admin/users/{id}/block|unblock
 *   which invalidates queries so the drawer refreshes immediately
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Search,
  X,
  CheckCircle2,
  XCircle,
  Shield,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { GlowButton } from "@/components/ui/GlowButton";
import { GlowInput } from "@/components/ui/GlowInput";
import {
  SkeletonList,
  SkeletonTable,
} from "@/components/ui/LoadingSkeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { useAdminAuthContext } from "@/providers/admin-auth-provider";
import {
  useAdminUsers,
  useAdminUserDetail,
  useBlockUser,
  useUnblockUser,
  type UserListItem,
  type UserMembershipItem,
  type UserSessionItem,
  type UserDetailResponse,
} from "@/hooks/useAdminUsers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_LIMIT = 20;

// ---------------------------------------------------------------------------
// Admin navigation bar (shared across admin pages)
// ---------------------------------------------------------------------------

function AdminNav() {
  const { logout, adminEmail } = useAdminAuthContext();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
    } finally {
      setIsLoggingOut(false);
    }
  };

  return (
    <div className="flex items-center justify-between mb-6 pb-4 border-b border-zinc-800">
      <nav className="flex items-center gap-1">
        <Link
          href="/admin/tenants"
          className="px-3 py-1.5 rounded text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-colors"
        >
          Tenants
        </Link>
        <Link
          href="/admin/users"
          className="px-3 py-1.5 rounded text-sm text-cyan-400 border-b-2 border-cyan-400 font-medium"
        >
          Users
        </Link>
      </nav>
      <div className="flex items-center gap-3">
        {adminEmail && (
          <span className="text-xs text-zinc-600">{adminEmail}</span>
        )}
        <GlowButton
          variant="ghost"
          size="sm"
          onClick={handleLogout}
          isLoading={isLoggingOut}
          loadingText="Logging out..."
        >
          Logout
        </GlowButton>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Role badge helper
// ---------------------------------------------------------------------------

function roleBadgeClass(role: string): string {
  switch (role) {
    case "owner":
      return "bg-cyan-900/40 text-cyan-400 border border-cyan-800";
    case "admin":
      return "bg-purple-900/40 text-purple-400 border border-purple-800";
    default:
      return "bg-zinc-800 text-zinc-400 border border-zinc-700";
  }
}

// ---------------------------------------------------------------------------
// Format date helper
// ---------------------------------------------------------------------------

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatDatetime(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// User avatar / initials helper
// ---------------------------------------------------------------------------

function UserAvatar({
  avatarUrl,
  email,
  size = "md",
}: {
  avatarUrl: string | null;
  email: string;
  size?: "sm" | "md";
}) {
  const initials = email.slice(0, 2).toUpperCase();
  const sizeClass = size === "sm" ? "w-7 h-7 text-xs" : "w-10 h-10 text-sm";

  if (avatarUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatarUrl}
        alt={email}
        className={`${sizeClass} rounded-full object-cover`}
      />
    );
  }

  return (
    <div
      className={`${sizeClass} rounded-full bg-zinc-800 flex items-center justify-center text-zinc-400 font-medium flex-shrink-0`}
    >
      {initials}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Block/unblock inline form state type
// ---------------------------------------------------------------------------

interface BlockAction {
  user_id: string;
  tenant_id: string;
  action: "block" | "unblock";
}

// ---------------------------------------------------------------------------
// Membership row — handles block/unblock inline form
// ---------------------------------------------------------------------------

function MembershipRow({ membership, userId }: { membership: UserMembershipItem; userId: string }) {
  const [blockAction, setBlockAction] = useState<BlockAction | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState("");

  const blockMutation = useBlockUser();
  const unblockMutation = useUnblockUser();

  const isActingOnThis =
    blockAction?.user_id === userId &&
    blockAction?.tenant_id === membership.tenant_id;

  const isPending = blockMutation.isPending || unblockMutation.isPending;

  const handleActionClick = (action: "block" | "unblock") => {
    setBlockAction({ user_id: userId, tenant_id: membership.tenant_id, action });
    setReason("");
    setReasonError("");
  };

  const handleCancel = () => {
    setBlockAction(null);
    setReason("");
    setReasonError("");
  };

  const handleConfirm = () => {
    if (!reason.trim()) {
      setReasonError("Reason is required");
      return;
    }
    if (!blockAction) return;

    const vars = {
      user_id: blockAction.user_id,
      tenant_id: blockAction.tenant_id,
      reason: reason.trim(),
    };

    if (blockAction.action === "block") {
      blockMutation.mutate(vars, {
        onSuccess: () => {
          setBlockAction(null);
          setReason("");
        },
      });
    } else {
      unblockMutation.mutate(vars, {
        onSuccess: () => {
          setBlockAction(null);
          setReason("");
        },
      });
    }
  };

  return (
    <div className="py-3 border-b border-zinc-800/60 last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-zinc-200 font-medium truncate">
              {membership.tenant_name}
            </span>
            <span className="text-xs text-zinc-600">/{membership.tenant_slug}</span>
            <span
              className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${roleBadgeClass(membership.role)}`}
            >
              {membership.role}
            </span>
            {membership.billing_access && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-zinc-800 text-zinc-400 border border-zinc-700">
                billing
              </span>
            )}
            {membership.is_blocked && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-rose-900/40 text-rose-400 border border-rose-800">
                Blocked
              </span>
            )}
          </div>
        </div>
        <div className="flex-shrink-0">
          {!membership.is_blocked ? (
            <button
              onClick={() => handleActionClick("block")}
              className="text-xs text-rose-400 hover:text-rose-300 transition-colors cursor-pointer disabled:opacity-50"
              disabled={isActingOnThis && isPending}
            >
              Block
            </button>
          ) : (
            <button
              onClick={() => handleActionClick("unblock")}
              className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors cursor-pointer disabled:opacity-50"
              disabled={isActingOnThis && isPending}
            >
              Unblock
            </button>
          )}
        </div>
      </div>

      {/* Inline reason form */}
      {isActingOnThis && (
        <div className="mt-2 space-y-2">
          <input
            type="text"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (reasonError) setReasonError("");
            }}
            placeholder={`Reason for ${blockAction.action}ing...`}
            className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
          />
          {reasonError && (
            <p className="text-xs text-rose-400">{reasonError}</p>
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={handleConfirm}
              disabled={isPending}
              className={`text-xs px-2.5 py-1 rounded font-medium transition-colors disabled:opacity-50 ${
                blockAction.action === "block"
                  ? "bg-rose-900/50 text-rose-400 hover:bg-rose-900/70 border border-rose-800"
                  : "bg-emerald-900/50 text-emerald-400 hover:bg-emerald-900/70 border border-emerald-800"
              }`}
            >
              {isPending
                ? "..."
                : blockAction.action === "block"
                ? "Confirm Block"
                : "Confirm Unblock"}
            </button>
            <button
              onClick={handleCancel}
              disabled={isPending}
              className="text-xs text-zinc-500 hover:text-zinc-400 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
          {(blockMutation.error || unblockMutation.error) && (
            <p className="text-xs text-rose-400">
              {(blockMutation.error || unblockMutation.error)?.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session row
// ---------------------------------------------------------------------------

function SessionRow({ session }: { session: UserSessionItem }) {
  return (
    <div className="py-2.5 border-b border-zinc-800/60 last:border-0">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm text-zinc-300">
          {session.device_type || "Unknown device"}
          {session.browser_name && (
            <span className="text-zinc-500"> · {session.browser_name}</span>
          )}
        </div>
        <div className="text-xs text-zinc-600 text-right flex-shrink-0">
          {formatDatetime(session.last_active_at)}
        </div>
      </div>
      <div className="text-xs text-zinc-600 mt-0.5">
        {session.ip_address || "—"}
        {session.city && ` · ${session.city}`}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// User detail drawer
// ---------------------------------------------------------------------------

function UserDetailDrawer({
  userId,
  onClose,
}: {
  userId: string | null;
  onClose: () => void;
}) {
  const { data: user, isLoading, error } = useAdminUserDetail(userId);

  const isVisible = !!userId;

  return (
    <>
      {/* Backdrop */}
      {isVisible && (
        <div
          className="fixed inset-0 bg-black/50 z-40"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Drawer panel */}
      <div
        className={`fixed right-0 top-0 h-full w-full sm:w-96 bg-zinc-950 border-l border-zinc-800 z-50 flex flex-col transition-transform duration-300 ${
          isVisible ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 flex-shrink-0">
          <h2 className="text-sm font-semibold text-zinc-200">User Details</h2>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 transition-colors"
            aria-label="Close drawer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Drawer content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
          {isLoading && (
            <SkeletonList count={3} />
          )}

          {error && (
            <ErrorState
              title="Failed to load user"
              message={error.message}
            />
          )}

          {user && (
            <>
              {/* User header */}
              <div className="flex items-start gap-3">
                <UserAvatar avatarUrl={user.avatar_url} email={user.email} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-zinc-100 truncate">
                    {user.email}
                  </p>
                  {user.display_name && (
                    <p className="text-xs text-zinc-500 truncate">
                      {user.display_name}
                    </p>
                  )}
                  <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                    {user.email_verified && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-emerald-900/30 text-emerald-400 border border-emerald-800">
                        Verified
                      </span>
                    )}
                    {user.mfa_enabled && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-cyan-900/30 text-cyan-400 border border-cyan-800">
                        MFA
                      </span>
                    )}
                    {user.is_superuser && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-amber-900/30 text-amber-400 border border-amber-800">
                        Superuser
                      </span>
                    )}
                    {!user.is_active && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-rose-900/30 text-rose-400 border border-rose-800">
                        Inactive
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Account info */}
              <div className="space-y-1">
                <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Account Info
                </h3>
                <div className="bg-zinc-900/50 rounded-lg p-3 space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-500">ID</span>
                    <span className="text-zinc-300 font-mono truncate max-w-[160px]">
                      {user.id.slice(0, 8)}...
                    </span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-500">Created</span>
                    <span className="text-zinc-300">{formatDate(user.created_at)}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-500">Updated</span>
                    <span className="text-zinc-300">{formatDate(user.updated_at)}</span>
                  </div>
                </div>
              </div>

              {/* Memberships */}
              <div className="space-y-1">
                <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Memberships ({user.memberships.length})
                </h3>
                {user.memberships.length === 0 ? (
                  <p className="text-xs text-zinc-600 py-2">No tenant memberships</p>
                ) : (
                  <div className="bg-zinc-900/50 rounded-lg px-3">
                    {user.memberships.map((m) => (
                      <MembershipRow
                        key={m.tenant_id}
                        membership={m}
                        userId={user.id}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Sessions */}
              <div className="space-y-1">
                <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Active Sessions ({user.sessions.length})
                </h3>
                {user.sessions.length === 0 ? (
                  <p className="text-xs text-zinc-600 py-2">No active sessions</p>
                ) : (
                  <div className="bg-zinc-900/50 rounded-lg px-3">
                    {user.sessions.map((s) => (
                      <SessionRow key={s.id} session={s} />
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// User table row
// ---------------------------------------------------------------------------

function UserTableRow({
  user,
  isSelected,
  onSelect,
}: {
  user: UserListItem;
  isSelected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <tr
      onClick={() => onSelect(user.id)}
      className={`cursor-pointer transition-colors border-b border-zinc-800/50 last:border-0 ${
        isSelected ? "bg-zinc-900/60" : "hover:bg-zinc-900/30"
      }`}
    >
      {/* Email */}
      <td className="px-4 py-3 text-sm text-cyan-400 font-medium max-w-[200px] truncate">
        {user.email}
      </td>

      {/* Display Name */}
      <td className="px-4 py-3 text-sm text-zinc-300 max-w-[160px] truncate">
        {user.display_name ?? <span className="text-zinc-600">—</span>}
      </td>

      {/* Verified */}
      <td className="px-4 py-3 text-center">
        {user.email_verified ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-400 inline" />
        ) : (
          <XCircle className="h-4 w-4 text-rose-500 inline" />
        )}
      </td>

      {/* MFA */}
      <td className="px-4 py-3 text-center">
        <Shield
          className={`h-4 w-4 inline ${
            user.mfa_enabled ? "text-cyan-400" : "text-zinc-600"
          }`}
        />
      </td>

      {/* Created */}
      <td className="px-4 py-3 text-sm text-zinc-500 whitespace-nowrap">
        {formatDate(user.created_at)}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function AdminUsersPage() {
  // Search state
  const [searchInput, setSearchInput] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  // Pagination
  const [page, setPage] = useState(0);

  // Selected user for detail drawer
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchInput);
      setPage(0); // Reset to page 0 on new search
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const offset = page * PAGE_LIMIT;

  const {
    data,
    isLoading,
    error,
  } = useAdminUsers({
    limit: PAGE_LIMIT,
    offset,
    q: debouncedQuery || null,
  });

  const users = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_LIMIT);

  const handleClearSearch = () => {
    setSearchInput("");
    setDebouncedQuery("");
    setPage(0);
  };

  const handleSelectUser = (id: string) => {
    setSelectedUserId(id === selectedUserId ? null : id);
  };

  const showingFrom = total === 0 ? 0 : offset + 1;
  const showingTo = Math.min(offset + PAGE_LIMIT, total);

  return (
    <>
      <div className="space-y-6">
        {/* Admin nav bar */}
        <AdminNav />

        {/* Page header */}
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">
            User Management
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Search and moderate users across the platform.
          </p>
        </div>

        {/* Search bar */}
        <div className="relative max-w-md">
          <GlowInput
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by email..."
            leftIcon={Search}
            rightIcon={searchInput ? X : undefined}
            onRightIconClick={searchInput ? handleClearSearch : undefined}
            fullWidth
          />
        </div>

        {/* User table */}
        <div className="border border-zinc-800 rounded-lg overflow-hidden">
          {/* Loading */}
          {isLoading && (
            <div className="p-6">
              <SkeletonTable rows={5} cols={5} />
            </div>
          )}

          {/* Error */}
          {error && !isLoading && (
            <div className="p-6">
              <ErrorState
                title="Failed to load users"
                message={error.message}
              />
            </div>
          )}

          {/* Empty */}
          {!isLoading && !error && users.length === 0 && (
            <div className="p-12">
              <EmptyState
                title="No users found"
                description={
                  debouncedQuery
                    ? `No users matching "${debouncedQuery}"`
                    : "No users have registered yet."
                }
              />
            </div>
          )}

          {/* Table */}
          {!isLoading && !error && users.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-zinc-900/50 border-b border-zinc-800">
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                      Email
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                      Display Name
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-zinc-500 uppercase tracking-wider">
                      Verified
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-zinc-500 uppercase tracking-wider">
                      MFA
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                      Created
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <UserTableRow
                      key={user.id}
                      user={user}
                      isSelected={user.id === selectedUserId}
                      onSelect={handleSelectUser}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination */}
        {!isLoading && !error && total > 0 && (
          <div className="flex items-center justify-between text-sm text-zinc-500">
            <span>
              Showing {showingFrom}–{showingTo} of {total} users
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Previous
              </button>
              <span className="px-2 text-zinc-600">
                {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* User detail drawer (outside main content for z-index) */}
      <UserDetailDrawer
        userId={selectedUserId}
        onClose={() => setSelectedUserId(null)}
      />
    </>
  );
}
