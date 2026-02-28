"""
Integration tests for Phase 6 OAuth and MFA success criteria.

Covers all 6 Phase 6 success criteria:
SC1 (AUTH-08): Google OAuth sign-in — new user creation, existing user login,
               email conflict link flow, link confirm with password
SC2 (AUTH-09): GitHub OAuth sign-in — private email extraction, public email
SC3 (AUTH-10): MFA enrollment — begin returns QR/secret, confirm with TOTP,
               confirm with invalid code, disable with TOTP, disable with backup code
SC4 (AUTH-11): MFA login two-stage flow — mfa_required on login, verify with TOTP,
               verify with backup code, TOTP replay prevention, expired mfa_token
SC5 (AUTH-12): Tenant MFA enforcement — owner without MFA cannot enable, owner with
               MFA enables enforcement, non-MFA session revocation, setup_required signal
SC6 (AUTH-13): Remember-device — cookie set on verify with trust_device=True,
               trusted device skips MFA, trusted device suppressed for enforcing tenant

Notes:
- OAuth tests mock the authlib client (cannot redirect to Google/GitHub in tests)
- MFA enrollment tests use pyotp for deterministic TOTP codes
- conftest `client` fixture yields (http_client, fake_redis, app, test_db)
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pyotp
import pytest
from sqlalchemy import select

from wxcode_adm.auth.models import MfaBackupCode, OAuthAccount, RefreshToken, TrustedDevice, User
from wxcode_adm.auth.password import hash_password
from wxcode_adm.tenants.models import MemberRole, Tenant, TenantMembership


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _signup_verify_login(
    client, redis, email: str, password: str = "securepass"
) -> tuple[str, str]:
    """
    Sign up, verify email, and log in.

    Tracks which OTP keys existed BEFORE signup to handle multi-user tests.
    Returns (access_token, refresh_token).
    """
    keys_before: set[str] = set()
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys_before.add(k)

    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
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

    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    data = r.json()
    return data["access_token"], data.get("refresh_token", "")


async def _create_user_with_mfa(test_db, email: str = "mfauser@test.com") -> tuple[User, str]:
    """
    Create a verified user with MFA already enabled (bypass enrollment flow).
    Returns (user, mfa_secret) tuple.
    """
    secret = pyotp.random_base32()
    async with test_db() as session:
        user = User(
            email=email,
            password_hash=hash_password("securepass"),
            email_verified=True,
            is_active=True,
            mfa_enabled=True,
            mfa_secret=secret,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, secret


async def _create_verified_user(
    test_db, email: str, password: str = "securepass"
) -> User:
    """Create a verified user directly in the DB (no HTTP flow)."""
    async with test_db() as session:
        user = User(
            email=email,
            password_hash=hash_password(password),
            email_verified=True,
            is_active=True,
            mfa_enabled=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_workspace_for_user(
    client, access_token: str, workspace_name: str = "Test Workspace"
) -> str:
    """Create a workspace and return the tenant_id."""
    r = await client.post(
        "/api/v1/onboarding/workspace",
        json={"name": workspace_name},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 201, f"Workspace creation failed: {r.text}"
    # WorkspaceCreatedResponse has tenant: TenantResponse, not tenant_id directly
    return r.json()["tenant"]["id"]


async def _enroll_mfa(client, access_token: str) -> tuple[str, list[str]]:
    """
    Perform full MFA enrollment via API.
    Returns (mfa_secret, backup_codes).
    """
    r = await client.post(
        "/api/v1/auth/mfa/enroll",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, f"MFA enroll begin failed: {r.text}"
    data = r.json()
    secret = data["secret"]

    # Get valid TOTP code
    code = pyotp.TOTP(secret).now()

    r = await client.post(
        "/api/v1/auth/mfa/confirm",
        json={"code": code},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, f"MFA confirm failed: {r.text}"
    backup_codes = r.json()["backup_codes"]
    return secret, backup_codes


# ---------------------------------------------------------------------------
# SC1: Google OAuth sign-in (AUTH-08)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_oauth_new_user_creates_account(client):
    """
    Mock Google OAuth callback creates a new user and OAuthAccount.
    Returns access_token, is_new_user=True.
    """
    c, redis, app, test_db = client

    mock_token = {
        "userinfo": {
            "email": "newgoogle@test.com",
            "sub": "google-sub-12345",
            "email_verified": True,
        }
    }

    mock_client = MagicMock()
    mock_client.authorize_access_token = AsyncMock(return_value=mock_token)

    with patch("wxcode_adm.auth.router.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client

        r = await c.get("/api/v1/auth/oauth/google/callback?code=fake&state=fake")

    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data.get("is_new_user") is True

    # Verify User was created
    async with test_db() as session:
        result = await session.execute(
            select(User).where(User.email == "newgoogle@test.com")
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.email_verified is False  # Requires OTP verification
        assert user.password_hash is None  # OAuth-only account

        # Verify OAuthAccount was created
        oauth_result = await session.execute(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user.id,
                OAuthAccount.provider == "google",
            )
        )
        oauth_account = oauth_result.scalar_one_or_none()
        assert oauth_account is not None
        assert oauth_account.provider_user_id == "google-sub-12345"


@pytest.mark.asyncio
async def test_google_oauth_existing_linked_user_logs_in(client):
    """
    Google callback with existing OAuthAccount returns is_new_user=False with tokens.
    """
    c, redis, app, test_db = client

    # Create user + OAuthAccount directly in DB
    user_id = uuid.uuid4()
    async with test_db() as session:
        user = User(
            id=user_id,
            email="existing_oauth@test.com",
            password_hash=None,
            email_verified=True,
            is_active=True,
        )
        oauth_acc = OAuthAccount(
            user_id=user_id,
            provider="google",
            provider_user_id="google-existing-sub",
        )
        session.add(user)
        session.add(oauth_acc)
        await session.commit()

    mock_token = {
        "userinfo": {
            "email": "existing_oauth@test.com",
            "sub": "google-existing-sub",
            "email_verified": True,
        }
    }

    mock_client = MagicMock()
    mock_client.authorize_access_token = AsyncMock(return_value=mock_token)

    with patch("wxcode_adm.auth.router.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client

        r = await c.get("/api/v1/auth/oauth/google/callback?code=fake&state=fake")

    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data.get("is_new_user") is False


@pytest.mark.asyncio
async def test_google_oauth_email_conflict_returns_link_required(client):
    """
    Google callback with email matching existing password account returns link_required.
    """
    c, redis, app, test_db = client

    # Create a user with password (not OAuth)
    await _create_verified_user(test_db, "conflict@test.com", "securepass")

    mock_token = {
        "userinfo": {
            "email": "conflict@test.com",
            "sub": "google-conflict-sub",
            "email_verified": True,
        }
    }

    mock_client = MagicMock()
    mock_client.authorize_access_token = AsyncMock(return_value=mock_token)

    with patch("wxcode_adm.auth.router.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client

        r = await c.get("/api/v1/auth/oauth/google/callback?code=fake&state=fake")

    assert r.status_code == 200, r.text
    data = r.json()
    assert "link_token" in data
    assert data.get("email") == "conflict@test.com"
    assert data.get("provider") == "google"


@pytest.mark.asyncio
async def test_google_oauth_link_confirm_with_password(client):
    """
    After getting a link_token, POST /oauth/link/confirm creates OAuthAccount.
    """
    c, redis, app, test_db = client

    # Create a user with password
    await _create_verified_user(test_db, "linkme@test.com", "securepass")

    # Get a link_token via OAuth callback
    mock_token = {
        "userinfo": {
            "email": "linkme@test.com",
            "sub": "google-link-sub",
            "email_verified": True,
        }
    }

    mock_client = MagicMock()
    mock_client.authorize_access_token = AsyncMock(return_value=mock_token)

    with patch("wxcode_adm.auth.router.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client

        r = await c.get("/api/v1/auth/oauth/google/callback?code=fake&state=fake")

    assert r.status_code == 200, r.text
    link_token = r.json()["link_token"]

    # Confirm link with correct password
    r = await c.post(
        "/api/v1/auth/oauth/link/confirm",
        json={"link_token": link_token, "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data.get("is_new_user") is False

    # Verify OAuthAccount was created
    async with test_db() as session:
        result = await session.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == "google",
                OAuthAccount.provider_user_id == "google-link-sub",
            )
        )
        assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# SC2: GitHub OAuth sign-in (AUTH-09)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_oauth_new_user_private_email(client):
    """
    GitHub callback where /user returns email=None, /user/emails provides primary email.
    """
    c, redis, app, test_db = client

    mock_token = {"access_token": "github-token"}

    # Mock user profile (email=None) and user/emails endpoint
    mock_user_resp = MagicMock()
    mock_user_resp.json.return_value = {"id": 99001, "email": None}

    mock_emails_resp = MagicMock()
    mock_emails_resp.json.return_value = [
        {"email": "private@github.com", "primary": True, "verified": True},
        {"email": "secondary@github.com", "primary": False, "verified": True},
    ]

    mock_client = MagicMock()
    mock_client.authorize_access_token = AsyncMock(return_value=mock_token)

    async def mock_get(url, token=None):
        if url == "user":
            return mock_user_resp
        elif url == "user/emails":
            return mock_emails_resp
        raise ValueError(f"Unexpected URL: {url}")

    mock_client.get = mock_get

    with patch("wxcode_adm.auth.router.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client

        r = await c.get("/api/v1/auth/oauth/github/callback?code=fake&state=fake")

    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data.get("is_new_user") is True

    # Verify user was created with correct email
    async with test_db() as session:
        result = await session.execute(
            select(User).where(User.email == "private@github.com")
        )
        user = result.scalar_one_or_none()
        assert user is not None

        oauth_result = await session.execute(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user.id,
                OAuthAccount.provider == "github",
            )
        )
        assert oauth_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_github_oauth_new_user_public_email(client):
    """
    GitHub callback where /user returns email directly — user created with that email.
    """
    c, redis, app, test_db = client

    mock_token = {"access_token": "github-token"}

    mock_user_resp = MagicMock()
    mock_user_resp.json.return_value = {
        "id": 99002,
        "email": "public@github.com",
    }

    mock_client = MagicMock()
    mock_client.authorize_access_token = AsyncMock(return_value=mock_token)
    mock_client.get = AsyncMock(return_value=mock_user_resp)

    with patch("wxcode_adm.auth.router.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client

        r = await c.get("/api/v1/auth/oauth/github/callback?code=fake&state=fake")

    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data.get("is_new_user") is True

    async with test_db() as session:
        result = await session.execute(
            select(User).where(User.email == "public@github.com")
        )
        assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# SC3: MFA enrollment (AUTH-10)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mfa_enroll_begin_returns_qr(client):
    """
    Authenticated user calls POST /mfa/enroll — returns secret, qr_code, provisioning_uri.
    """
    c, redis, app, test_db = client
    access_token, _ = await _signup_verify_login(c, redis, "enroll@test.com")

    r = await c.post(
        "/api/v1/auth/mfa/enroll",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "secret" in data
    assert "qr_code" in data
    assert "provisioning_uri" in data
    assert len(data["secret"]) > 0
    assert len(data["qr_code"]) > 0
    assert "otpauth://" in data["provisioning_uri"]


@pytest.mark.asyncio
async def test_mfa_confirm_with_valid_totp(client):
    """
    After begin, POST /mfa/confirm with valid TOTP sets mfa_enabled=True
    and returns exactly 10 backup codes.
    """
    c, redis, app, test_db = client
    access_token, _ = await _signup_verify_login(c, redis, "confirm@test.com")

    # Begin enrollment
    r = await c.post(
        "/api/v1/auth/mfa/enroll",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]

    # Confirm with valid TOTP
    code = pyotp.TOTP(secret).now()
    r = await c.post(
        "/api/v1/auth/mfa/confirm",
        json={"code": code},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "backup_codes" in data
    assert len(data["backup_codes"]) == 10

    # Verify user.mfa_enabled = True in DB
    async with test_db() as session:
        result = await session.execute(
            select(User).where(User.email == "confirm@test.com")
        )
        user = result.scalar_one()
        assert user.mfa_enabled is True

        # Verify backup code rows exist
        bc_result = await session.execute(
            select(MfaBackupCode).where(MfaBackupCode.user_id == user.id)
        )
        backup_rows = bc_result.scalars().all()
        assert len(backup_rows) == 10


@pytest.mark.asyncio
async def test_mfa_confirm_with_invalid_code_fails(client):
    """POST /mfa/confirm with wrong code returns 401."""
    c, redis, app, test_db = client
    access_token, _ = await _signup_verify_login(c, redis, "badconfirm@test.com")

    # Begin enrollment
    r = await c.post(
        "/api/v1/auth/mfa/enroll",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, r.text

    # Confirm with wrong code
    r = await c.post(
        "/api/v1/auth/mfa/confirm",
        json={"code": "000000"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_mfa_disable_with_totp(client):
    """Enrolled user calls DELETE /mfa with valid TOTP — mfa_enabled becomes False."""
    c, redis, app, test_db = client
    access_token, _ = await _signup_verify_login(c, redis, "disabletotp@test.com")

    # Full enrollment
    secret, _ = await _enroll_mfa(c, access_token)

    # Disable with TOTP
    code = pyotp.TOTP(secret).now()
    r = await c.request(
        "DELETE",
        "/api/v1/auth/mfa",
        json={"code": code},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, r.text

    # Verify mfa_enabled = False
    async with test_db() as session:
        result = await session.execute(
            select(User).where(User.email == "disabletotp@test.com")
        )
        user = result.scalar_one()
        assert user.mfa_enabled is False
        assert user.mfa_secret is None


@pytest.mark.asyncio
async def test_mfa_disable_with_backup_code(client):
    """Enrolled user calls DELETE /mfa with backup code — mfa_enabled becomes False."""
    c, redis, app, test_db = client
    access_token, _ = await _signup_verify_login(c, redis, "disablebackup@test.com")

    # Full enrollment
    secret, backup_codes = await _enroll_mfa(c, access_token)

    # Use first backup code to disable MFA
    r = await c.request(
        "DELETE",
        "/api/v1/auth/mfa",
        json={"code": backup_codes[0]},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, r.text

    # Verify mfa_enabled = False
    async with test_db() as session:
        result = await session.execute(
            select(User).where(User.email == "disablebackup@test.com")
        )
        user = result.scalar_one()
        assert user.mfa_enabled is False


@pytest.mark.asyncio
async def test_mfa_status(client):
    """GET /mfa/status returns correct mfa_enabled before and after enrollment."""
    c, redis, app, test_db = client
    access_token, _ = await _signup_verify_login(c, redis, "status@test.com")

    # Before enrollment
    r = await c.get(
        "/api/v1/auth/mfa/status",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mfa_enabled"] is False

    # Enroll
    await _enroll_mfa(c, access_token)

    # After enrollment
    r = await c.get(
        "/api/v1/auth/mfa/status",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mfa_enabled"] is True


# ---------------------------------------------------------------------------
# SC4: MFA login two-stage flow (AUTH-11)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_mfa_enabled_returns_mfa_required(client):
    """Login with MFA-enabled user returns mfa_required=True, mfa_token, no access_token."""
    c, redis, app, test_db = client

    user, secret = await _create_user_with_mfa(test_db, "mfalogin@test.com")

    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "mfalogin@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("mfa_required") is True
    assert "mfa_token" in data
    assert "access_token" not in data or data.get("access_token") is None


@pytest.mark.asyncio
async def test_mfa_verify_with_valid_totp(client):
    """Use mfa_token + valid TOTP code → returns access_token and refresh_token."""
    c, redis, app, test_db = client

    user, secret = await _create_user_with_mfa(test_db, "mfaverify@test.com")

    # Login to get mfa_token
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "mfaverify@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    mfa_token = r.json()["mfa_token"]

    # Verify with valid TOTP
    code = pyotp.TOTP(secret).now()
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": code},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_mfa_verify_with_backup_code(client):
    """Use mfa_token + backup code → returns tokens, backup code marked as used."""
    c, redis, app, test_db = client

    user, secret = await _create_user_with_mfa(test_db, "mfabackup@test.com")

    # Add backup codes directly in DB
    backup_plaintext = "ABCDE-FGHIJ"
    backup_stripped = "ABCDEFGHIJ"
    backup_hash = hash_password(backup_stripped)
    async with test_db() as session:
        session.add(
            MfaBackupCode(user_id=user.id, code_hash=backup_hash, used_at=None)
        )
        await session.commit()

    # Login to get mfa_token
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "mfabackup@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    mfa_token = r.json()["mfa_token"]

    # Verify with backup code
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": backup_plaintext},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data

    # Verify backup code marked as used
    async with test_db() as session:
        result = await session.execute(
            select(MfaBackupCode).where(
                MfaBackupCode.user_id == user.id,
                MfaBackupCode.code_hash == backup_hash,
            )
        )
        row = result.scalar_one()
        assert row.used_at is not None


@pytest.mark.asyncio
async def test_mfa_verify_replay_rejected(client):
    """Verify with TOTP, then immediately use the same code → second attempt fails."""
    c, redis, app, test_db = client

    user, secret = await _create_user_with_mfa(test_db, "mfareplay@test.com")

    # Login to get mfa_token
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "mfareplay@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    mfa_token = r.json()["mfa_token"]

    code = pyotp.TOTP(secret).now()

    # First verify — succeeds
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": code},
    )
    assert r.status_code == 200, r.text

    # Second login to get a new mfa_token (first one was consumed)
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "mfareplay@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    new_mfa_token = r.json()["mfa_token"]

    # Try the same code again with new mfa_token — replay prevention kicks in
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": new_mfa_token, "code": code},
    )
    assert r.status_code == 401, r.text
    assert r.json().get("error_code") == "MFA_INVALID_CODE"


@pytest.mark.asyncio
async def test_mfa_verify_expired_token_fails(client):
    """Expired (deleted) mfa_pending key → mfa_verify returns 401 INVALID_TOKEN."""
    c, redis, app, test_db = client

    user, secret = await _create_user_with_mfa(test_db, "mfaexpired@test.com")

    # Login to get mfa_token
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "mfaexpired@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    mfa_token = r.json()["mfa_token"]

    # Manually delete the pending key (simulate expiry)
    await redis.delete(f"auth:mfa_pending:{mfa_token}")

    # Verify should fail
    code = pyotp.TOTP(secret).now()
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": code},
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_mfa_verify_includes_wxcode_redirect(client):
    """After MFA verify with tenant wxcode_url set, response includes
    wxcode_redirect_url and wxcode_code; code can be exchanged; code is single-use."""
    c, redis, app, test_db = client

    user, secret = await _create_user_with_mfa(test_db, "mfawxcode@test.com")

    # Create tenant with wxcode_url and membership directly in DB
    async with test_db() as session:
        tenant = Tenant(
            name="MFA Wxcode Tenant",
            slug="mfa-wxcode-tenant",
            wxcode_url="https://app.wxcode.io",
        )
        session.add(tenant)
        await session.flush()  # Required: assign tenant.id before FK reference
        membership = TenantMembership(
            user_id=user.id, tenant_id=tenant.id, role=MemberRole.OWNER
        )
        session.add(membership)
        await session.commit()

    # Login to get mfa_token
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "mfawxcode@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    mfa_token = r.json()["mfa_token"]

    # MFA verify with valid TOTP
    code = pyotp.TOTP(secret).now()
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": code},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("wxcode_redirect_url") == "https://app.wxcode.io"
    assert data.get("wxcode_code") is not None

    # Exchange code for tokens
    exchange_resp = await c.post(
        "/api/v1/auth/wxcode/exchange",
        json={"code": data["wxcode_code"]},
    )
    assert exchange_resp.status_code == 200
    assert "access_token" in exchange_resp.json()

    # Code is single-use
    exchange_resp2 = await c.post(
        "/api/v1/auth/wxcode/exchange",
        json={"code": data["wxcode_code"]},
    )
    assert exchange_resp2.status_code == 401


# ---------------------------------------------------------------------------
# SC5: Tenant MFA enforcement (AUTH-12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_without_mfa_cannot_enable_enforcement(client):
    """Owner without MFA calls PATCH /tenants/current/mfa-enforcement {enforce: true} → 403."""
    c, redis, app, test_db = client

    access_token, _ = await _signup_verify_login(c, redis, "ownernofa@test.com")
    tenant_id = await _create_workspace_for_user(c, access_token, "No MFA Workspace")

    r = await c.patch(
        "/api/v1/tenants/current/mfa-enforcement",
        json={"enforce": True},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 403, r.text
    assert r.json().get("error_code") == "MFA_REQUIRED"


@pytest.mark.asyncio
async def test_owner_with_mfa_enables_enforcement(client):
    """Owner with MFA enabled calls PATCH mfa-enforcement → tenant.mfa_enforced=True."""
    c, redis, app, test_db = client

    access_token, _ = await _signup_verify_login(c, redis, "ownermfa@test.com")
    tenant_id = await _create_workspace_for_user(c, access_token, "MFA Workspace")

    # Enroll MFA for owner
    await _enroll_mfa(c, access_token)

    r = await c.patch(
        "/api/v1/tenants/current/mfa-enforcement",
        json={"enforce": True},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["mfa_enforced"] is True


@pytest.mark.asyncio
async def test_enforcement_revokes_non_mfa_sessions(client):
    """
    Enable enforcement: non-MFA members' refresh tokens are deleted.
    MFA-enabled owner's tokens remain.
    """
    c, redis, app, test_db = client

    # Owner signs up and gets access token
    owner_token, owner_refresh = await _signup_verify_login(c, redis, "owner_enforce@test.com")
    tenant_id = await _create_workspace_for_user(c, owner_token, "Enforced Workspace")

    # Create a member without MFA directly in DB
    member_id = uuid.uuid4()
    async with test_db() as session:
        member = User(
            id=member_id,
            email="member_nomfa@test.com",
            password_hash=hash_password("securepass"),
            email_verified=True,
            is_active=True,
            mfa_enabled=False,
        )
        # Add tenant membership
        tm = TenantMembership(
            user_id=member_id,
            tenant_id=uuid.UUID(tenant_id),
            role=MemberRole.DEVELOPER,
            billing_access=False,
        )
        # Add refresh token for member (simulates active session)
        rt = RefreshToken(
            token="member-refresh-token-12345",
            user_id=member_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add(member)
        session.add(tm)
        session.add(rt)
        await session.commit()

    # Enroll MFA for owner
    await _enroll_mfa(c, owner_token)

    # Enable enforcement
    r = await c.patch(
        "/api/v1/tenants/current/mfa-enforcement",
        json={"enforce": True},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 200, r.text

    # Verify member's refresh token was revoked
    async with test_db() as session:
        rt_result = await session.execute(
            select(RefreshToken).where(RefreshToken.user_id == member_id)
        )
        assert rt_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_enforcement_login_without_mfa_signals_setup_required(client):
    """User in enforcing tenant without MFA logs in → mfa_setup_required=True."""
    c, redis, app, test_db = client

    # Owner sets up enforcing tenant
    owner_token, _ = await _signup_verify_login(c, redis, "owner_setup@test.com")
    tenant_id = await _create_workspace_for_user(c, owner_token, "Setup Required Workspace")
    await _enroll_mfa(c, owner_token)

    r = await c.patch(
        "/api/v1/tenants/current/mfa-enforcement",
        json={"enforce": True},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 200, r.text

    # Create a member without MFA
    member_id = uuid.uuid4()
    async with test_db() as session:
        member = User(
            id=member_id,
            email="nomfa_member@test.com",
            password_hash=hash_password("securepass"),
            email_verified=True,
            is_active=True,
            mfa_enabled=False,
        )
        tm = TenantMembership(
            user_id=member_id,
            tenant_id=uuid.UUID(tenant_id),
            role=MemberRole.DEVELOPER,
            billing_access=False,
        )
        session.add(member)
        session.add(tm)
        await session.commit()

    # Member logs in → should get mfa_setup_required signal
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "nomfa_member@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("mfa_required") is True
    # mfa_setup_required field may be in response — check Redis key is JSON
    mfa_token = data.get("mfa_token")
    assert mfa_token is not None
    raw = await redis.get(f"auth:mfa_pending:{mfa_token}")
    assert raw is not None
    pending_data = json.loads(raw)
    assert pending_data.get("setup_required") is True


# ---------------------------------------------------------------------------
# SC6: Remember-device (AUTH-13)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trusted_device_cookie_set_on_mfa_verify(client):
    """POST /mfa/verify with trust_device=True sets wxcode_trusted_device cookie."""
    c, redis, app, test_db = client

    user, secret = await _create_user_with_mfa(test_db, "trustdevice@test.com")

    # Login
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "trustdevice@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    mfa_token = r.json()["mfa_token"]

    # Verify with trust_device=True
    code = pyotp.TOTP(secret).now()
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": code, "trust_device": True},
    )
    assert r.status_code == 200, r.text
    assert "wxcode_trusted_device" in r.cookies


@pytest.mark.asyncio
async def test_trusted_device_skips_mfa_on_next_login(client):
    """Login with trusted device cookie → tokens returned directly (no mfa_required)."""
    c, redis, app, test_db = client

    user, secret = await _create_user_with_mfa(test_db, "skipdevice@test.com")

    # Login to get mfa_token
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "skipdevice@test.com", "password": "securepass"},
    )
    assert r.status_code == 200, r.text
    mfa_token = r.json()["mfa_token"]

    # Verify and get trusted device cookie
    code = pyotp.TOTP(secret).now()
    r = await c.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": code, "trust_device": True},
    )
    assert r.status_code == 200, r.text
    device_cookie = r.cookies.get("wxcode_trusted_device")
    assert device_cookie is not None

    # Login again with the trusted device cookie
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "skipdevice@test.com", "password": "securepass"},
        cookies={"wxcode_trusted_device": device_cookie},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Should get tokens directly without MFA prompt
    assert data.get("mfa_required") is False
    assert "access_token" in data


@pytest.mark.asyncio
async def test_trusted_device_ignored_for_enforcing_tenant(client):
    """User in enforcing tenant with trusted device still gets mfa_required=True."""
    c, redis, app, test_db = client

    # Set up owner and enforcing tenant
    owner_token, _ = await _signup_verify_login(c, redis, "owner_trust_enforce@test.com")
    tenant_id = await _create_workspace_for_user(c, owner_token, "Enforcing Trust Workspace")
    await _enroll_mfa(c, owner_token)

    r = await c.patch(
        "/api/v1/tenants/current/mfa-enforcement",
        json={"enforce": True},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 200, r.text

    # Create a member WITH MFA who has a trusted device
    member_secret = pyotp.random_base32()
    member_id = uuid.uuid4()
    device_token_plain = "trusted-device-token-value-xyz123"
    device_token_hash = hashlib.sha256(device_token_plain.encode()).hexdigest()
    async with test_db() as session:
        member = User(
            id=member_id,
            email="trusted_enforced@test.com",
            password_hash=hash_password("securepass"),
            email_verified=True,
            is_active=True,
            mfa_enabled=True,
            mfa_secret=member_secret,
        )
        tm = TenantMembership(
            user_id=member_id,
            tenant_id=uuid.UUID(tenant_id),
            role=MemberRole.DEVELOPER,
            billing_access=False,
        )
        # Add a trusted device record for this member
        td = TrustedDevice(
            user_id=member_id,
            token_hash=device_token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add(member)
        session.add(tm)
        session.add(td)
        await session.commit()

    # Login with trusted device cookie — should still require TOTP because enforcement is on
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "trusted_enforced@test.com", "password": "securepass"},
        cookies={"wxcode_trusted_device": device_token_plain},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Enforcing tenant overrides trusted device
    assert data.get("mfa_required") is True
    assert "access_token" not in data or data.get("access_token") is None
