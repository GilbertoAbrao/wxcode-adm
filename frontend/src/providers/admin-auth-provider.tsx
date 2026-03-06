"use client";

/**
 * AdminAuthProvider — provides admin auth state and route protection for /admin/* paths.
 *
 * - Completely isolated from the tenant user AuthProvider in auth-provider.tsx
 * - On mount: checks isAdminAuthenticated() to detect in-memory session
 * - Route protection:
 *     - Unauthenticated user on /admin/* (except /admin/login) → redirect to /admin/login
 *     - Authenticated admin on /admin/login → redirect to /admin/dashboard
 * - login(tokens, email): stores admin tokens and email in state
 * - logout(): calls useAdminLogout mutation, then clears admin tokens, redirects to /admin/login
 *
 * IMPORTANT: This provider is NOT in the root layout. It wraps only /admin/* routes
 * via the admin layout.tsx — tenant users never encounter AdminAuthProvider.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  isAdminAuthenticated,
  setAdminTokens,
  clearAdminTokens,
  getAdminRefreshToken,
} from "@/lib/admin-auth";
import { adminApiClient } from "@/lib/admin-api-client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AdminTokens {
  access_token: string;
  refresh_token: string;
}

export interface AdminAuthContextValue {
  adminEmail: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (tokens: AdminTokens, email: string) => void;
  logout: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AdminAuthContext = createContext<AdminAuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Admin public paths (no admin auth required)
// ---------------------------------------------------------------------------

const ADMIN_PUBLIC_PATHS = ["/admin/login"];

function isAdminPublicPath(pathname: string): boolean {
  return ADMIN_PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`)
  );
}

// ---------------------------------------------------------------------------
// AdminAuthProvider component
// ---------------------------------------------------------------------------

export function AdminAuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const [adminEmail, setAdminEmail] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // On mount: check if admin tokens are in memory (in-memory session restore)
  useEffect(() => {
    // No /users/me equivalent for admin — just check token presence
    setIsLoading(false);
  }, []);

  // Route protection: redirect unauthenticated admins from protected admin routes
  useEffect(() => {
    if (isLoading) return;

    const onPublicPath = isAdminPublicPath(pathname);
    const authenticated = isAdminAuthenticated();

    if (!authenticated && !onPublicPath) {
      // Unauthenticated on protected admin route — redirect to admin login
      router.push("/admin/login");
    } else if (authenticated && onPublicPath) {
      // Authenticated admin on /admin/login — redirect to admin dashboard
      router.push("/admin/dashboard");
    }
  }, [isLoading, pathname, router]);

  // Login: store admin tokens and email in state
  const login = useCallback((tokens: AdminTokens, email: string) => {
    setAdminTokens(tokens.access_token, tokens.refresh_token);
    setAdminEmail(email);
  }, []);

  // Logout: call backend logout, clear admin tokens, redirect to admin login
  const logout = useCallback(async () => {
    const refreshToken = getAdminRefreshToken();
    if (refreshToken) {
      try {
        await adminApiClient("/admin/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      } catch {
        // Ignore errors — clear tokens regardless
      }
    }
    clearAdminTokens();
    setAdminEmail(null);
    router.push("/admin/login");
  }, [router]);

  const contextValue: AdminAuthContextValue = {
    adminEmail,
    isAuthenticated: isAdminAuthenticated(),
    isLoading,
    login,
    logout,
  };

  return (
    <AdminAuthContext.Provider value={contextValue}>
      {children}
    </AdminAuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// useAdminAuthContext hook
// ---------------------------------------------------------------------------

export function useAdminAuthContext(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) {
    throw new Error(
      "useAdminAuthContext must be used within an AdminAuthProvider"
    );
  }
  return ctx;
}
