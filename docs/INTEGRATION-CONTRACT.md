# wxcode-adm Integration Contract

> **Audience:** wxcode engine developers integrating with wxcode-adm.
>
> **Version:** 0.1.0 — Updated 2026-03-09

---

## 1. Overview

**wxcode-adm** is the authentication and tenant management layer for the WXCODE platform. It handles:

- User identity and JWT issuance
- Tenant lifecycle (onboarding, activation, suspension)
- Per-tenant configuration storage (database name, Claude settings, operational limits)
- Token exchange for seamless wxcode engine sessions

**wxcode engine** consumes wxcode-adm for:

- JWT validation (via JWKS public key)
- Tenant configuration retrieval
- Token exchange from one-time codes

**Key boundary:** wxcode-adm never executes wxcode engine operations. wxcode-adm stores configuration *about* the wxcode engine; the engine executes it.

---

## 2. Authentication: JWT RS256 via JWKS

wxcode engine validates JWTs **locally** without calling wxcode-adm on every request.

### 2.1 Fetch the Public Key

```http
GET /.well-known/jwks.json
```

**No authentication required.** This is a public discovery endpoint.

**Response:**

```json
{
  "keys": [
    {
      "kty": "RSA",
      "n": "<base64url-encoded modulus>",
      "e": "<base64url-encoded exponent>",
      "use": "sig",
      "alg": "RS256",
      "kid": "v1"
    }
  ]
}
```

### 2.2 JWT Structure

| Claim       | Type   | Description                                      |
| ----------- | ------ | ------------------------------------------------ |
| `sub`       | string | User ID (UUID)                                   |
| `tenant_id` | string | Tenant ID (UUID)                                 |
| `role`      | string | Member role: `VIEWER`, `DEVELOPER`, `ADMIN`      |
| `aud`       | string | Always `"wxcode-adm"`                            |
| `exp`       | int    | Expiration timestamp (Unix)                      |
| `jti`       | string | Unique token ID (for blacklisting on logout)     |

**Algorithm:** RS256
**Key rotation:** The `kid` header in the JWT matches the `kid` in the JWKS response. Cache the key by `kid`; re-fetch only on `kid` miss.

### 2.3 Validation Rules

1. Verify signature using RSA public key from JWKS.
2. Check `aud == "wxcode-adm"`.
3. Check `exp` has not passed.
4. Extract `tenant_id` from claims for tenant-scoped operations.

**No token introspection endpoint.** Tokens are fully self-contained.

---

## 3. Tenant Context

All tenant-scoped requests must include:

```http
X-Tenant-ID: <tenant-uuid>
```

wxcode engine extracts `tenant_id` from JWT claims and passes it as the `X-Tenant-ID` header. The wxcode-adm API validates that the header matches the JWT claim to prevent cross-tenant reads.

**Tenant isolation:** Each active tenant has its own database (`Tenant.database_name`). wxcode engine uses `database_name` from the config endpoint (section 4) to route requests to the correct database.

---

## 4. Configuration Endpoint

Retrieve per-tenant wxcode engine configuration.

```http
GET /api/v1/tenants/{tenant_id}/wxcode-config
Authorization: Bearer <access_token>
X-Tenant-ID: <tenant_id>
```

**Required role:** `DEVELOPER` or above.

**Path constraint:** `tenant_id` in path must match `tenant_id` in JWT and `X-Tenant-ID` header.

**Response (200):**

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "database_name": "wxcode_tenant_acme",
  "default_target_stack": "python",
  "neo4j_enabled": false,
  "claude_default_model": "claude-opus-4-6",
  "max_concurrent_sessions": 5
}
```

| Field                    | Type            | Description                                           |
| ------------------------ | --------------- | ----------------------------------------------------- |
| `tenant_id`              | string (UUID)   | Tenant identifier                                     |
| `database_name`          | string or null  | Target database name; null = not yet provisioned      |
| `default_target_stack`   | string or null  | Default execution stack (e.g., `"python"`, `"node"`)  |
| `neo4j_enabled`          | boolean         | Whether Neo4j is enabled for this tenant              |
| `claude_default_model`   | string or null  | Default Claude model slug                             |
| `max_concurrent_sessions`| integer         | Maximum concurrent wxcode sessions allowed            |

**NOT returned:** `claude_oauth_token` — the encrypted OAuth token never leaves wxcode-adm.

**Error responses:**

| Status | Error Code       | Condition                                         |
| ------ | ---------------- | ------------------------------------------------- |
| 404    | TENANT_NOT_FOUND | Tenant does not exist                             |
| 404    | TENANT_MISMATCH  | Path tenant_id does not match X-Tenant-ID header  |
| 403    | FORBIDDEN        | User role is below DEVELOPER                      |

---

## 5. Token Exchange

Convert a one-time authorization code into JWT tokens after wxcode-adm login.

**Flow:**
1. User authenticates at wxcode-adm UI.
2. wxcode-adm redirects to wxcode engine with `?code=<one-time-code>`.
3. wxcode engine backend (server-to-server) exchanges the code for tokens.

```http
POST /api/v1/auth/wxcode/exchange
Content-Type: application/json

{
  "code": "<one-time-code>"
}
```

**No Authorization header required.** The code itself is the credential.

**Response (200):**

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer"
}
```

**Code properties:**

- **Single-use:** Atomically consumed via `GETDEL` in Redis. Cannot be replayed.
- **TTL:** 30 seconds (configurable via `WXCODE_CODE_TTL` environment variable).
- **Scope:** Code is bound to a specific user session.

**Error responses:**

| Status | Error Code    | Condition                                    |
| ------ | ------------- | -------------------------------------------- |
| 400    | INVALID_CODE  | Code not found, already used, or malformed   |
| 410    | TOKEN_EXPIRED | Code TTL exceeded                            |

---

## 6. Discovery

### 6.1 Integration Health

```http
GET /api/v1/integration/health
```

**No authentication required.**

**Response (200):**

```json
{
  "service": "wxcode-adm",
  "version": "0.1.0",
  "status": "healthy",
  "jwks_url": "/.well-known/jwks.json",
  "endpoints": {
    "wxcode_config": "/api/v1/tenants/{tenant_id}/wxcode-config",
    "token_exchange": "/api/v1/auth/wxcode/exchange",
    "health": "/api/v1/health"
  }
}
```

| `status` value | Meaning                                    |
| -------------- | ------------------------------------------ |
| `"healthy"`    | PostgreSQL and Redis are operational       |
| `"degraded"`   | PostgreSQL is up, Redis is unavailable     |
| `"unhealthy"`  | PostgreSQL is unavailable                  |

### 6.2 Infrastructure Health

```http
GET /api/v1/health
```

**No authentication required.**

**Response (200):**

```json
{
  "status": "healthy",
  "checks": {
    "postgresql": "ok",
    "redis": "ok"
  }
}
```

Returns HTTP 503 if any check fails.

---

## 7. Error Format

All error responses use a consistent structure:

```json
{
  "error_code": "SNAKE_CASE_CODE",
  "message": "Human-readable description of the error"
}
```

**Common error codes:**

| Error Code       | HTTP Status | Description                                     |
| ---------------- | ----------- | ----------------------------------------------- |
| TENANT_NOT_FOUND | 404         | Tenant does not exist or is not accessible      |
| TENANT_MISMATCH  | 404         | Path tenant_id does not match header context    |
| FORBIDDEN        | 403         | Authenticated but insufficient role/permissions |
| INVALID_CODE     | 400         | One-time exchange code is invalid or used       |
| TOKEN_EXPIRED    | 410         | Code or token TTL has expired                   |
| UNAUTHORIZED     | 401         | No valid JWT provided or JWT is invalid         |

---

## 8. Rate Limits

| Endpoint Category               | Limit          |
| ------------------------------- | -------------- |
| Auth endpoints (login, signup)  | 5 req/min/IP   |
| Global default                  | 60 req/min/IP  |
| Health and integration/health   | Exempt         |
| JWKS endpoint                   | Exempt         |

Rate limit exceeded responses return HTTP 429 with a `Retry-After` header.
