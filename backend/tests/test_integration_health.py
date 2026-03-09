"""
Integration tests for Phase 24 — Integration Health Endpoint.

Covers the GET /api/v1/integration/health endpoint:
1. Returns 200 with expected fields (service, version, status, jwks_url, endpoints)
2. jwks_url is "/.well-known/jwks.json"
3. endpoints dict contains wxcode_config, token_exchange, and health keys
4. No authentication required (200 without Authorization header)
5. Status is "healthy" when PostgreSQL and Redis are up (test environment)

Notes:
- conftest `client` fixture yields (http_client, fake_redis, app, test_db)
- All infrastructure dependencies are mocked in the shared conftest.py
- Rate limiter is disabled in tests via app.state.limiter.enabled = False
"""

import pytest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_integration_health_returns_200(client):
    """GET /api/v1/integration/health returns 200 with all expected top-level fields."""
    c, _, _, _ = client
    resp = await c.get("/api/v1/integration/health")

    assert resp.status_code == 200

    data = resp.json()
    assert "service" in data
    assert "version" in data
    assert "status" in data
    assert "jwks_url" in data
    assert "endpoints" in data


@pytest.mark.anyio
async def test_integration_health_includes_jwks_url(client):
    """integration/health response contains jwks_url pointing to /.well-known/jwks.json."""
    c, _, _, _ = client
    resp = await c.get("/api/v1/integration/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["jwks_url"] == "/.well-known/jwks.json"


@pytest.mark.anyio
async def test_integration_health_includes_endpoints(client):
    """integration/health endpoints dict contains all required discovery keys."""
    c, _, _, _ = client
    resp = await c.get("/api/v1/integration/health")

    assert resp.status_code == 200
    endpoints = resp.json()["endpoints"]
    assert "wxcode_config" in endpoints
    assert "token_exchange" in endpoints
    assert "health" in endpoints


@pytest.mark.anyio
async def test_integration_health_no_auth_required(client):
    """GET /api/v1/integration/health returns 200 without any Authorization header."""
    c, _, _, _ = client

    # Explicitly send request without any Authorization header
    resp = await c.get(
        "/api/v1/integration/health",
        headers={},  # No Authorization header
    )

    assert resp.status_code == 200
    assert resp.json()["service"] == "wxcode-adm"


@pytest.mark.anyio
async def test_integration_health_status_healthy(client):
    """integration/health reports status=healthy when DB and Redis are operational."""
    c, _, _, _ = client
    resp = await c.get("/api/v1/integration/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "wxcode-adm"
    assert data["version"] == "0.1.0"
