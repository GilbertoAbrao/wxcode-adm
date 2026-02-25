"""
Integration tests for Phase 7 User Account management success criteria.

Covers all 4 Phase 7 success criteria:
SC1 (USER-01): Profile view and update — GET /users/me returns all fields;
               PATCH /users/me updates display_name and reflects immediately;
               email change resets email_verified to False.
SC2 (USER-02): Password change — POST /users/me/change-password with correct
               current password succeeds; old password rejected on login;
               wrong current password returns 401.
SC3 (USER-03): Session listing and revocation — GET /users/me/sessions returns
               session list with is_current tag; DELETE /users/me/sessions/{id}
               cannot revoke current session (400); DELETE /users/me/sessions
               revokes all others, keeps current.
SC4 (USER-04): wxcode one-time code redirect — login with tenant wxcode_url set
               returns wxcode_code and wxcode_redirect_url; POST /auth/wxcode/exchange
               consumes code and returns tokens; code is single-use; invalid code
               returns 401.

Notes:
- conftest `client` fixture yields (http_client, fake_redis, app, test_db)
- _signup_verify_login helper creates an authenticated user via full HTTP flow
- arq, Stripe, and Redis dependencies are mocked in the shared conftest.py
"""

import uuid

import pytest
from sqlalchemy import update

from wxcode_adm.auth.models import User
from wxcode_adm.tenants.models import Tenant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _signup_verify_login(
    client, redis, email: str, password: str = "SecurePass1"
) -> tuple[str, str]:
    """
    Sign up, verify email, and log in.

    Tracks which OTP keys existed BEFORE signup to correctly identify the
    new user's OTP key even when multiple users exist in the test DB.
    Returns (access_token, refresh_token).
    """
    keys_before: set[str] = set()
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys_before.add(k)

    r = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password},
    )
    assert r.status_code == 201, f"Signup failed: {r.text}"

    new_key = None
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k and k not in keys_before:
            new_key = k
            break
    assert new_key is not None, f"No new OTP key after signup for {email}"
    code = await redis.get(new_key)
    assert code is not None

    r = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": code},
    )
    assert r.status_code == 200, f"Verify failed: {r.text}"

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    data = r.json()
    return data["access_token"], data.get("refresh_token", "")


# ---------------------------------------------------------------------------
# SC1: Profile view and update (USER-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_profile(client):
    """GET /users/me returns profile with display_name, avatar_url, mfa_enabled."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "getprofile@test.com")

    resp = await c.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "display_name" in data
    assert "avatar_url" in data
    assert "mfa_enabled" in data
    assert data["email_verified"] is True
    assert data["email"] == "getprofile@test.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_update_display_name(client):
    """PATCH /users/me updates display_name; change reflected in subsequent GET."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "updatedisplay@test.com")

    resp = await c.patch(
        "/api/v1/users/me",
        json={"display_name": "Test User"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["profile"]["display_name"] == "Test User"

    # Verify persistence — GET should reflect the updated name
    resp2 = await c.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["display_name"] == "Test User"


@pytest.mark.asyncio
async def test_update_email_resets_verification(client):
    """PATCH /users/me with new email sets email_verified=False."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "emailchange@test.com")

    resp = await c.patch(
        "/api/v1/users/me",
        json={"email": "newemail_unique123@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["profile"]["email_verified"] is False


@pytest.mark.asyncio
async def test_patch_no_fields_returns_400(client):
    """PATCH /users/me with empty body returns 400 NO_FIELDS_TO_UPDATE."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "nofields@test.com")

    resp = await c.patch(
        "/api/v1/users/me",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json().get("error_code") == "NO_FIELDS_TO_UPDATE"


@pytest.mark.asyncio
async def test_get_profile_requires_auth(client):
    """GET /users/me without token returns 401."""
    c, redis, app, test_db = client

    resp = await c.get("/api/v1/users/me")
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# SC2: Password change (USER-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_success(client):
    """POST /users/me/change-password with correct current password succeeds."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "pw@test.com", "OldPassword1")

    resp = await c.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "OldPassword1", "new_password": "NewPassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert "message" in resp.json()


@pytest.mark.asyncio
async def test_change_password_old_rejected(client):
    """After password change, old password is rejected on login; new password works."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "pwold@test.com", "OldPassword1")

    # Change the password
    resp = await c.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "OldPassword1", "new_password": "NewPassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    # Attempt login with old password — should fail
    resp = await c.post(
        "/api/v1/auth/login",
        json={"email": "pwold@test.com", "password": "OldPassword1"},
    )
    assert resp.status_code == 401, resp.text

    # Login with new password — should succeed
    resp = await c.post(
        "/api/v1/auth/login",
        json={"email": "pwold@test.com", "password": "NewPassword1"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_change_password_wrong_current(client):
    """POST /users/me/change-password with wrong current password returns 401."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "pwwrong@test.com", "CorrectPw1")

    resp = await c.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "WrongPassword", "new_password": "NewPassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# SC3: Session listing and revocation (USER-03)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions(client):
    """GET /users/me/sessions returns session list with current session tagged."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "listsessions@test.com")

    resp = await c.get(
        "/api/v1/users/me/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "sessions" in data
    sessions = data["sessions"]
    assert len(sessions) >= 1

    # Exactly one current session
    current = [s for s in sessions if s["is_current"]]
    assert len(current) == 1

    # Session object has expected fields
    session_obj = sessions[0]
    assert "id" in session_obj
    assert "is_current" in session_obj
    assert "created_at" in session_obj


@pytest.mark.asyncio
async def test_cannot_revoke_current_session(client):
    """DELETE /users/me/sessions/{id} attempting to revoke current session returns 400."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "revokeself@test.com")

    # List sessions to find current session id
    resp = await c.get(
        "/api/v1/users/me/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    sessions = resp.json()["sessions"]
    current_session = [s for s in sessions if s["is_current"]][0]

    # Attempt to revoke own current session — should be rejected
    resp = await c.delete(
        f"/api/v1/users/me/sessions/{current_session['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json().get("error_code") == "CANNOT_REVOKE_CURRENT"


@pytest.mark.asyncio
async def test_revoke_all_other_sessions(client):
    """DELETE /users/me/sessions revokes all other sessions, keeps current."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "revokeall@test.com")

    resp = await c.delete(
        "/api/v1/users/me/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "revoked_count" in data
    assert "message" in data

    # After revoking all others, listing should show only current session
    sessions_resp = await c.get(
        "/api/v1/users/me/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sessions_resp.status_code == 200, sessions_resp.text
    sessions = sessions_resp.json()["sessions"]
    # All remaining sessions should be current
    assert all(s["is_current"] for s in sessions)


@pytest.mark.asyncio
async def test_revoke_nonexistent_session_returns_404(client):
    """DELETE /users/me/sessions/{id} with unknown UUID returns 404."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "revokenotfound@test.com")

    fake_id = str(uuid.uuid4())
    resp = await c.delete(
        f"/api/v1/users/me/sessions/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# SC4: wxcode one-time code redirect (USER-04)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wxcode_exchange_invalid_code(client):
    """POST /auth/wxcode/exchange with invalid code returns 401."""
    c, redis, app, test_db = client

    resp = await c.post(
        "/api/v1/auth/wxcode/exchange",
        json={"code": "nonexistent-code-value-12345"},
    )
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_wxcode_code_exchange(client):
    """
    After login with tenant wxcode_url configured, code can be exchanged for JWT.
    Login returns wxcode_code and wxcode_redirect_url; exchange returns tokens;
    code is single-use — second exchange fails.
    """
    c, redis, app, test_db = client

    # Create user and log in to get a token for workspace creation
    email = "wxcode_user@test.com"
    password = "WxcodePass1"
    token, _ = await _signup_verify_login(c, redis, email, password)

    # Create a workspace for the user
    ws_resp = await c.post(
        "/api/v1/onboarding/workspace",
        json={"name": "Wxcode Workspace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ws_resp.status_code == 201, f"Workspace creation failed: {ws_resp.text}"

    # Set wxcode_url on the tenant directly in the database
    async with test_db() as session:
        await session.execute(
            update(Tenant).values(wxcode_url="https://app.wxcode.io")
        )
        await session.commit()

    # Log in again — should get wxcode_code and wxcode_redirect_url in response
    login_resp = await c.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()

    assert data.get("wxcode_code") is not None, "Expected wxcode_code in login response"
    assert data.get("wxcode_redirect_url") == "https://app.wxcode.io", (
        f"Expected wxcode_redirect_url='https://app.wxcode.io', got: {data.get('wxcode_redirect_url')}"
    )

    wxcode_code = data["wxcode_code"]

    # Exchange the code for tokens
    exchange_resp = await c.post(
        "/api/v1/auth/wxcode/exchange",
        json={"code": wxcode_code},
    )
    assert exchange_resp.status_code == 200, exchange_resp.text
    exchange_data = exchange_resp.json()
    assert "access_token" in exchange_data
    assert "refresh_token" in exchange_data

    # Code is single-use — second exchange must fail
    exchange_resp2 = await c.post(
        "/api/v1/auth/wxcode/exchange",
        json={"code": wxcode_code},
    )
    assert exchange_resp2.status_code == 401, (
        f"Expected 401 on second exchange, got {exchange_resp2.status_code}: {exchange_resp2.text}"
    )


@pytest.mark.asyncio
async def test_login_without_wxcode_url_has_no_code(client):
    """Login when tenant has no wxcode_url returns no wxcode_code in response."""
    c, redis, app, test_db = client

    email = "nowxcode@test.com"
    password = "NoWxcode1"
    token, _ = await _signup_verify_login(c, redis, email, password)

    # Create workspace (tenant will have no wxcode_url by default)
    ws_resp = await c.post(
        "/api/v1/onboarding/workspace",
        json={"name": "No Wxcode Workspace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ws_resp.status_code == 201, ws_resp.text

    # Login again — wxcode_url is not set, so no code should be returned
    login_resp = await c.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()
    # wxcode_code should be None or absent when tenant has no wxcode_url
    assert data.get("wxcode_code") is None
    assert data.get("wxcode_redirect_url") is None
