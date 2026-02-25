"""
Integration tests for the auth domain — Phase 2 success criteria.

Covers all 7 Phase 2 success criteria:
SC1: Signup creates user and sends OTP (code in Redis)
SC2: Email verification with correct/wrong codes
SC3: Login returns tokens, rejects unverified users, rejects wrong passwords
SC4: Refresh token rotation (new tokens, old token rejected after use)
SC5: Logout invalidates tokens (blacklisted access token returns 401)
SC6: Password reset flow (forgot + reset with itsdangerous token)
SC7: JWKS endpoint returns valid RSA public key

Additional:
- Duplicate signup returns 409
- Protected /users/me endpoint requires auth and email verification (moved from /auth/me in Phase 7)
- Single-session enforcement on login

Note: The `client` fixture yields a 4-tuple: (http_client, fake_redis, app, test_db).
Each test destructures it as needed.
"""

import pytest
from sqlalchemy import select

from wxcode_adm.auth.models import User
from wxcode_adm.auth.jwt import create_access_token
from wxcode_adm.auth.service import generate_reset_token
from wxcode_adm.dependencies import get_session


# ---------------------------------------------------------------------------
# Helper: signup + verify + login sequence
# ---------------------------------------------------------------------------


async def _signup_verify_login(client, redis, email="user@test.com", password="securepass"):
    """
    Helper: sign up, verify email, and log in.
    Returns the TokenResponse dict with access_token and refresh_token.
    """
    # Signup
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    assert "Check your email" in r.json()["message"]

    # Find user_id in Redis by scanning OTP keys
    keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys.append(k)
    assert len(keys) == 1, f"Expected 1 OTP key, found: {keys}"
    user_id = keys[0].replace("auth:otp:", "")

    # Get OTP code
    code = await redis.get(f"auth:otp:{user_id}")
    assert code is not None

    # Verify email
    r = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": code},
    )
    assert r.status_code == 200, r.text

    # Login
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


async def _get_user_from_db(app, test_db, email: str) -> User:
    """Helper: fetch a User from the test DB by email."""
    override_fn = app.dependency_overrides.get(get_session)
    assert override_fn is not None, "get_session override not found in app"
    async for session in override_fn():
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one()


# ---------------------------------------------------------------------------
# SC1: Signup
# ---------------------------------------------------------------------------


async def test_signup_creates_user_and_sends_code(client):
    """SC1: POST /signup creates user and stores OTP in Redis."""
    c, redis, app, db = client

    r = await c.post(
        "/api/v1/auth/signup",
        json={"email": "new@test.com", "password": "password123"},
    )
    assert r.status_code == 201
    data = r.json()
    assert "Check your email" in data["message"]

    # Verify OTP exists in Redis
    keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys.append(k)
    assert len(keys) == 1
    code = await redis.get(keys[0])
    assert code is not None
    assert len(code) == 6
    assert code.isdigit()


async def test_signup_duplicate_email_returns_409(client):
    """Duplicate email signup returns HTTP 409."""
    c, redis, app, db = client

    await c.post(
        "/api/v1/auth/signup",
        json={"email": "dup@test.com", "password": "password123"},
    )
    r = await c.post(
        "/api/v1/auth/signup",
        json={"email": "dup@test.com", "password": "anotherpass"},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "EMAIL_ALREADY_EXISTS"


# ---------------------------------------------------------------------------
# SC2: Email verification
# ---------------------------------------------------------------------------


async def test_verify_email_with_correct_code(client):
    """SC2: Correct OTP verifies email successfully."""
    c, redis, app, db = client

    await c.post(
        "/api/v1/auth/signup",
        json={"email": "verify@test.com", "password": "password123"},
    )

    keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys.append(k)
    user_id = keys[0].replace("auth:otp:", "")
    code = await redis.get(f"auth:otp:{user_id}")

    r = await c.post(
        "/api/v1/auth/verify-email",
        json={"email": "verify@test.com", "code": code},
    )
    assert r.status_code == 200
    assert "verified" in r.json()["message"].lower()

    # OTP should be deleted after use
    leftover = await redis.get(f"auth:otp:{user_id}")
    assert leftover is None


async def test_verify_email_wrong_code_returns_400(client):
    """SC2: Wrong OTP returns 400."""
    c, redis, app, db = client

    await c.post(
        "/api/v1/auth/signup",
        json={"email": "wrongcode@test.com", "password": "password123"},
    )

    r = await c.post(
        "/api/v1/auth/verify-email",
        json={"email": "wrongcode@test.com", "code": "000000"},
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "AUTH_INVALID_CODE"


async def test_verify_email_fails_after_3_wrong_attempts(client):
    """SC2: After 3 wrong attempts, OTP is invalidated (lockout)."""
    c, redis, app, db = client

    await c.post(
        "/api/v1/auth/signup",
        json={"email": "lockout@test.com", "password": "password123"},
    )

    keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys.append(k)
    user_id = keys[0].replace("auth:otp:", "")

    # 3 wrong attempts
    for _ in range(3):
        r = await c.post(
            "/api/v1/auth/verify-email",
            json={"email": "lockout@test.com", "code": "000000"},
        )
        assert r.status_code == 400

    # OTP key should be deleted after 3 failures
    code = await redis.get(f"auth:otp:{user_id}")
    assert code is None


# ---------------------------------------------------------------------------
# SC3: Login
# ---------------------------------------------------------------------------


async def test_login_returns_tokens(client):
    """SC3: Login after verification returns access_token and refresh_token."""
    c, redis, app, db = client

    tokens = await _signup_verify_login(c, redis, "login@test.com", "password123")

    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert len(tokens["access_token"]) > 10
    assert len(tokens["refresh_token"]) > 10


async def test_login_rejects_unverified_user(client):
    """SC3: Login without email verification returns 403 EMAIL_NOT_VERIFIED."""
    c, redis, app, db = client

    await c.post(
        "/api/v1/auth/signup",
        json={"email": "unverified@test.com", "password": "password123"},
    )

    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "unverified@test.com", "password": "password123"},
    )
    assert r.status_code == 403
    assert r.json()["error_code"] == "EMAIL_NOT_VERIFIED"


async def test_login_rejects_wrong_password(client):
    """SC3: Login with wrong password returns 401."""
    c, redis, app, db = client

    await _signup_verify_login(c, redis, "wrongpw@test.com", "password123")

    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@test.com", "password": "wrongpassword"},
    )
    assert r.status_code == 401
    assert r.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# SC4: Refresh token rotation
# ---------------------------------------------------------------------------


async def test_refresh_returns_new_tokens(client):
    """SC4: Refresh token rotation returns new tokens."""
    c, redis, app, db = client

    tokens = await _signup_verify_login(c, redis, "refresh@test.com", "password123")
    old_access = tokens["access_token"]
    old_refresh = tokens["refresh_token"]

    r = await c.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert r.status_code == 200, r.text
    new_tokens = r.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    # New tokens should be different from old ones
    assert new_tokens["access_token"] != old_access
    assert new_tokens["refresh_token"] != old_refresh


async def test_refresh_rejects_consumed_token(client):
    """SC4: Using a consumed refresh token returns 401."""
    c, redis, app, db = client

    tokens = await _signup_verify_login(c, redis, "consumed@test.com", "password123")
    old_refresh = tokens["refresh_token"]

    # First refresh — consumes the token
    r = await c.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200, r.text

    # Second attempt with the same old token — should fail
    r = await c.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# SC5: Logout and blacklist
# ---------------------------------------------------------------------------


async def test_logout_invalidates_tokens(client):
    """SC5: After logout, access token is blacklisted and /me returns 401."""
    c, redis, app, db = client

    tokens = await _signup_verify_login(c, redis, "logout@test.com", "password123")
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Verify /me works before logout (now at /users/me per Phase 7)
    r = await c.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200

    # Logout
    r = await c.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200

    # /me should now return 401 (access token blacklisted)
    r = await c.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# SC6: Password reset
# ---------------------------------------------------------------------------


async def test_forgot_password_always_returns_success(client):
    """SC6: forgot-password returns 200 even for non-existent email (enumeration-safe)."""
    c, redis, app, db = client

    r = await c.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nonexistent@test.com"},
    )
    assert r.status_code == 200
    # Must return the same message regardless of whether email exists
    assert "account" in r.json()["message"].lower() or "reset" in r.json()["message"].lower()


async def test_reset_password_works_and_revokes_sessions(client):
    """SC6: Password reset with valid token updates password and revokes sessions."""
    c, redis, app, db = client

    tokens = await _signup_verify_login(c, redis, "resetme@test.com", "oldpassword")
    refresh_token = tokens["refresh_token"]

    # Trigger forgot-password to exercise the flow path
    await c.post(
        "/api/v1/auth/forgot-password",
        json={"email": "resetme@test.com"},
    )

    # Generate a valid reset token directly using the service (plan spec option b:
    # call generate_reset_token directly to avoid mocking email delivery)
    user = await _get_user_from_db(app, db, "resetme@test.com")
    reset_token = generate_reset_token("resetme@test.com", user.password_hash)

    # Reset password
    r = await c.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "newpassword123"},
    )
    assert r.status_code == 200, r.text
    assert "reset" in r.json()["message"].lower()

    # Old refresh token should now be invalid (sessions revoked)
    r = await c.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 401

    # Can login with new password
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "resetme@test.com", "password": "newpassword123"},
    )
    assert r.status_code == 200
    assert "access_token" in r.json()


# ---------------------------------------------------------------------------
# SC7: JWKS endpoint
# ---------------------------------------------------------------------------


async def test_jwks_endpoint_returns_valid_key(client):
    """SC7: GET /.well-known/jwks.json returns JWKS with RSA public key."""
    c, redis, app, db = client

    r = await c.get("/.well-known/jwks.json")
    assert r.status_code == 200

    data = r.json()
    assert "keys" in data
    keys = data["keys"]
    assert len(keys) == 1

    key = keys[0]
    assert "kid" in key
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert "n" in key
    assert "e" in key


# ---------------------------------------------------------------------------
# Protected /users/me endpoint (moved from /auth/me in Phase 7)
# ---------------------------------------------------------------------------


async def test_me_endpoint_requires_auth(client):
    """GET /users/me without token returns 401."""
    c, redis, app, db = client

    r = await c.get("/api/v1/users/me")
    assert r.status_code == 401


async def test_me_endpoint_returns_user_info(client):
    """GET /users/me with valid token returns correct user info."""
    c, redis, app, db = client

    tokens = await _signup_verify_login(c, redis, "metest@test.com", "password123")

    r = await c.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "metest@test.com"
    assert data["email_verified"] is True
    assert "id" in data
    # Phase 7: also includes display_name, avatar_url, mfa_enabled
    assert "display_name" in data
    assert "avatar_url" in data
    assert "mfa_enabled" in data


async def test_me_endpoint_rejects_unverified_user(client):
    """GET /users/me returns 403 when email is not verified (require_verified enforcement)."""
    c, redis, app, db = client

    # Signup without verifying
    await c.post(
        "/api/v1/auth/signup",
        json={"email": "unver_me@test.com", "password": "password123"},
    )

    # Get the user's ID from the DB to create a valid JWT for an unverified user
    user = await _get_user_from_db(app, db, "unver_me@test.com")
    access_token = create_access_token(str(user.id))

    r = await c.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 403
    assert r.json()["error_code"] == "EMAIL_NOT_VERIFIED"


# ---------------------------------------------------------------------------
# Single-session enforcement
# ---------------------------------------------------------------------------


async def test_login_revokes_previous_sessions(client):
    """Login revokes all previous refresh tokens (single-session policy)."""
    c, redis, app, db = client

    # Login twice — second login should invalidate first refresh token
    tokens1 = await _signup_verify_login(c, redis, "singlesess@test.com", "password123")
    refresh_token1 = tokens1["refresh_token"]

    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "singlesess@test.com", "password": "password123"},
    )
    assert r.status_code == 200

    # First refresh token should now be invalid (revoked by second login)
    r = await c.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token1})
    assert r.status_code == 401
