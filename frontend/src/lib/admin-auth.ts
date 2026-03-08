/**
 * Admin token storage — completely isolated from tenant user auth.
 *
 * Token strategy:
 * - Access token: stored in module-scoped variable only (short-lived, in-memory).
 * - Refresh token: stored in both module-scoped variable AND localStorage so that
 *   session survives page refresh. On mount, AdminAuthProvider calls
 *   refreshAdminTokens() which reads from localStorage if the in-memory token
 *   is null — this restores the session without requiring re-login.
 *
 * Admin tokens use a separate "admin" audience, issued by POST /api/v1/admin/login.
 */

const API_BASE_INTERNAL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8040";

// ---------------------------------------------------------------------------
// localStorage keys
// ---------------------------------------------------------------------------

const ADMIN_REFRESH_KEY = "wxk_admin_refresh";
const ADMIN_EMAIL_KEY = "wxk_admin_email";

// ---------------------------------------------------------------------------
// Module-scoped admin token store (in-memory, isolated from user store)
// ---------------------------------------------------------------------------

let _adminAccessToken: string | null = null;
let _adminRefreshToken: string | null = null;

// ---------------------------------------------------------------------------
// Public token accessors
// ---------------------------------------------------------------------------

export function getAdminAccessToken(): string | null {
  return _adminAccessToken;
}

export function getAdminRefreshToken(): string | null {
  return _adminRefreshToken;
}

export function setAdminTokens(access: string, refresh: string): void {
  _adminAccessToken = access;
  _adminRefreshToken = refresh;
  if (typeof window !== "undefined") {
    localStorage.setItem(ADMIN_REFRESH_KEY, refresh);
  }
}

export function clearAdminTokens(): void {
  _adminAccessToken = null;
  _adminRefreshToken = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem(ADMIN_REFRESH_KEY);
    localStorage.removeItem(ADMIN_EMAIL_KEY);
  }
}

export function isAdminAuthenticated(): boolean {
  return _adminAccessToken !== null;
}

// ---------------------------------------------------------------------------
// Admin email persistence (for session restore display)
// ---------------------------------------------------------------------------

export function setAdminEmail(email: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(ADMIN_EMAIL_KEY, email);
  }
}

export function getStoredAdminEmail(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem(ADMIN_EMAIL_KEY);
  }
  return null;
}

// ---------------------------------------------------------------------------
// Admin token refresh — POST /api/v1/admin/refresh
// ---------------------------------------------------------------------------

/**
 * Attempt to refresh the admin access token using the stored admin refresh token.
 * Updates stored admin tokens on success. Returns true on success, false on failure.
 * Completely separate from the user refreshTokens() function in auth.ts.
 */
export async function refreshAdminTokens(): Promise<boolean> {
  let currentRefreshToken = _adminRefreshToken;
  if (!currentRefreshToken && typeof window !== "undefined") {
    currentRefreshToken = localStorage.getItem(ADMIN_REFRESH_KEY);
  }
  if (!currentRefreshToken) {
    return false;
  }

  try {
    const response = await fetch(
      `${API_BASE_INTERNAL}/api/v1/admin/refresh`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      }
    );

    if (!response.ok) {
      return false;
    }

    const data = await response.json();
    if (data.access_token && data.refresh_token) {
      setAdminTokens(data.access_token, data.refresh_token);
      return true;
    }

    return false;
  } catch {
    return false;
  }
}
