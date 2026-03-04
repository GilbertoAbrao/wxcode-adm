/**
 * In-memory token storage for auth state.
 *
 * Token strategy: store access_token and refresh_token in module-scoped
 * variables (NOT localStorage — XSS-safe). Tokens survive within a tab
 * session but are lost on full page reload (user re-logs in). This is the
 * simplest secure approach for an SPA that redirects to wxcode after login.
 */

const API_BASE_INTERNAL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8040";

// ---------------------------------------------------------------------------
// Module-scoped token store (in-memory, XSS-safe)
// ---------------------------------------------------------------------------

let _accessToken: string | null = null;
let _refreshToken: string | null = null;

// ---------------------------------------------------------------------------
// Public token accessors
// ---------------------------------------------------------------------------

export function getAccessToken(): string | null {
  return _accessToken;
}

export function getRefreshToken(): string | null {
  return _refreshToken;
}

export function setTokens(access: string, refresh: string): void {
  _accessToken = access;
  _refreshToken = refresh;
}

export function clearTokens(): void {
  _accessToken = null;
  _refreshToken = null;
}

export function isAuthenticated(): boolean {
  return _accessToken !== null;
}

// ---------------------------------------------------------------------------
// Token refresh — POST /api/v1/auth/refresh
// ---------------------------------------------------------------------------

/**
 * Attempt to refresh the access token using the stored refresh token.
 * Updates stored tokens on success. Returns true on success, false on failure.
 */
export async function refreshTokens(): Promise<boolean> {
  const currentRefreshToken = _refreshToken;
  if (!currentRefreshToken) {
    return false;
  }

  try {
    const response = await fetch(
      `${API_BASE_INTERNAL}/api/v1/auth/refresh`,
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
      setTokens(data.access_token, data.refresh_token);
      return true;
    }

    return false;
  } catch {
    return false;
  }
}
