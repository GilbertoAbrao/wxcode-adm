/**
 * In-memory admin token storage — completely isolated from tenant user auth.
 *
 * Token strategy: store access_token and refresh_token in module-scoped
 * variables (NOT localStorage — XSS-safe). These variables are separate from
 * the user auth store in auth.ts — admin login does NOT affect user login
 * state and vice versa.
 *
 * Admin tokens use a separate "admin" audience, issued by POST /api/v1/admin/login.
 */

const API_BASE_INTERNAL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8040";

// ---------------------------------------------------------------------------
// Module-scoped admin token store (in-memory, XSS-safe, isolated from user store)
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
}

export function clearAdminTokens(): void {
  _adminAccessToken = null;
  _adminRefreshToken = null;
}

export function isAdminAuthenticated(): boolean {
  return _adminAccessToken !== null;
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
  const currentRefreshToken = _adminRefreshToken;
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
