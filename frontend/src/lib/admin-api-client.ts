/**
 * Typed fetch wrapper for admin API endpoints with admin token injection and refresh.
 *
 * - Prepends /api/v1 to all endpoints (same as apiClient)
 * - Injects Authorization: Bearer header from admin token store (NOT user tokens)
 * - On 401: attempts silent admin token refresh, retries once, then clears admin tokens
 * - Throws ApiError on non-ok responses with parsed error body
 *
 * IMPORTANT: This client uses getAdminAccessToken (NOT getAccessToken from auth.ts).
 * Admin tokens are completely isolated from tenant user tokens.
 */

import { ApiError } from "@/lib/api-client";
import {
  clearAdminTokens,
  getAdminAccessToken,
  refreshAdminTokens,
} from "@/lib/admin-auth";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8040";

// ---------------------------------------------------------------------------
// adminApiClient — typed fetch wrapper for admin endpoints
// ---------------------------------------------------------------------------

export async function adminApiClient<T>(
  endpoint: string,
  options: RequestInit & { skipAuth?: boolean } = {}
): Promise<T> {
  const { skipAuth, ...fetchOptions } = options;

  const url = `${API_BASE}/api/v1${endpoint}`;

  // Build headers
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Merge any caller-provided headers
  if (fetchOptions.headers) {
    const callerHeaders = new Headers(fetchOptions.headers);
    callerHeaders.forEach((value, key) => {
      headers[key] = value;
    });
  }

  // Inject admin auth token unless skipped
  if (!skipAuth) {
    const token = getAdminAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  // Handle 401 — attempt silent admin refresh and retry once
  if (response.status === 401 && !skipAuth) {
    const refreshed = await refreshAdminTokens();
    if (refreshed) {
      const newToken = getAdminAccessToken();
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
      }
      const retryResponse = await fetch(url, {
        ...fetchOptions,
        headers,
      });
      if (!retryResponse.ok) {
        clearAdminTokens();
        const errorBody = await parseErrorBody(retryResponse);
        throw new ApiError(
          retryResponse.status,
          errorBody.message,
          errorBody.errorCode
        );
      }
      return retryResponse.json() as Promise<T>;
    } else {
      clearAdminTokens();
      const errorBody = await parseErrorBody(response);
      throw new ApiError(response.status, errorBody.message, errorBody.errorCode);
    }
  }

  if (!response.ok) {
    const errorBody = await parseErrorBody(response);
    throw new ApiError(response.status, errorBody.message, errorBody.errorCode);
  }

  // Handle empty responses (204 No Content, etc.)
  const contentType = response.headers.get("content-type");
  if (!contentType || !contentType.includes("application/json")) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

interface ErrorBody {
  message: string;
  errorCode: string;
}

async function parseErrorBody(response: Response): Promise<ErrorBody> {
  try {
    const body = await response.json();
    // FastAPI returns { detail: string | object }
    const rawDetail = body?.detail || body?.message || body?.error_code;
    let message = "An error occurred";
    let errorCode = body?.error_code || "UNKNOWN_ERROR";

    if (typeof rawDetail === "string") {
      message = rawDetail;
    } else if (typeof rawDetail === "object" && rawDetail !== null) {
      // FastAPI validation errors return detail as array
      if (Array.isArray(rawDetail)) {
        message = rawDetail.map((e: { msg?: string }) => e.msg).join(", ");
      } else {
        message = JSON.stringify(rawDetail);
      }
    }

    if (body?.error_code) {
      errorCode = body.error_code;
    }

    return { message, errorCode };
  } catch {
    return {
      message: response.statusText || "Request failed",
      errorCode: "NETWORK_ERROR",
    };
  }
}
