"use client";

/**
 * AuthProvider — provides current user state and auth actions to the component tree.
 *
 * - On mount: if tokens are in-memory (isAuthenticated()), fetches /users/me to restore user state
 * - login(): stores tokens and fetches /users/me to populate user
 * - logout(): calls POST /auth/logout, clears tokens, redirects to /login
 * - Route protection: if not authenticated and not on a public path, redirects to /login
 * - If authenticated and on a public auth path, redirects to /
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import {
  isAuthenticated,
  setTokens,
  clearTokens,
  getRefreshToken,
} from "@/lib/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  email_verified: boolean;
  mfa_enabled: boolean;
}

export interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (tokens: { access_token: string; refresh_token: string }) => Promise<void>;
  logout: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Public paths that do not require authentication
// ---------------------------------------------------------------------------

const PUBLIC_PATHS = [
  "/login",
  "/signup",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
  "/mfa-verify",
  "/onboarding",
  "/admin", // Admin portal has its own AdminAuthProvider — tenant auth must not interfere
];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`)
  );
}

// ---------------------------------------------------------------------------
// AuthProvider component
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Fetch the current authenticated user from /users/me
  const fetchCurrentUser = useCallback(async (): Promise<AuthUser | null> => {
    try {
      const userData = await apiClient<AuthUser>("/users/me");
      return userData;
    } catch {
      return null;
    }
  }, []);

  // On mount: restore user state if tokens are present in memory
  useEffect(() => {
    let mounted = true;

    async function initAuth() {
      if (isAuthenticated()) {
        const userData = await fetchCurrentUser();
        if (mounted) {
          setUser(userData);
        }
      }
      if (mounted) {
        setIsLoading(false);
      }
    }

    initAuth();

    return () => {
      mounted = false;
    };
  }, [fetchCurrentUser]);

  // Route protection: redirect unauthenticated users away from protected routes
  useEffect(() => {
    if (isLoading) return;

    const onPublicPath = isPublicPath(pathname);

    if (!isAuthenticated() && !onPublicPath) {
      // Unauthenticated on protected route — redirect to login
      router.push("/login");
    } else if (isAuthenticated() && onPublicPath && pathname !== "/onboarding") {
      // Authenticated on public auth page (not onboarding) — redirect to app
      router.push("/");
    }
  }, [isLoading, pathname, router]);

  // Login: store tokens, fetch user, update state
  const login = useCallback(
    async (tokens: { access_token: string; refresh_token: string }) => {
      setTokens(tokens.access_token, tokens.refresh_token);
      const userData = await fetchCurrentUser();
      setUser(userData);
    },
    [fetchCurrentUser]
  );

  // Logout: call backend, clear tokens, redirect to login
  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await apiClient("/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      } catch {
        // Ignore errors — clear tokens regardless
      }
    }
    clearTokens();
    setUser(null);
    router.push("/login");
  }, [router]);

  const contextValue: AuthContextValue = {
    user,
    isAuthenticated: isAuthenticated(),
    isLoading,
    login,
    logout,
  };

  return (
    <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// useAuthContext hook
// ---------------------------------------------------------------------------

export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuthContext must be used within an AuthProvider");
  }
  return ctx;
}
