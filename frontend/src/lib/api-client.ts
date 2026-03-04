/**
 * Typed fetch wrapper for backend API with token injection and refresh.
 *
 * - Prepends /api/v1 to all endpoints
 * - Injects Authorization: Bearer header (unless skipAuth: true)
 * - On 401: attempts silent token refresh, retries once, then clears tokens
 * - Throws ApiError on non-ok responses with parsed error body
 */

import { clearTokens, getAccessToken, refreshTokens } from "@/lib/auth";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8040";

// ---------------------------------------------------------------------------
// ApiError — thrown for non-2xx responses
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  errorCode: string;

  constructor(status: number, message: string, errorCode: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = errorCode;
  }
}

// ---------------------------------------------------------------------------
// apiClient — main typed fetch wrapper
// ---------------------------------------------------------------------------

export async function apiClient<T>(
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

  // Inject auth token unless skipped
  if (!skipAuth) {
    const token = getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  // Handle 401 — attempt silent refresh and retry once
  if (response.status === 401 && !skipAuth) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      const newToken = getAccessToken();
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
      }
      const retryResponse = await fetch(url, {
        ...fetchOptions,
        headers,
      });
      if (!retryResponse.ok) {
        await clearTokens();
        const errorBody = await parseErrorBody(retryResponse);
        throw new ApiError(
          retryResponse.status,
          errorBody.message,
          errorBody.errorCode
        );
      }
      return retryResponse.json() as Promise<T>;
    } else {
      clearTokens();
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
