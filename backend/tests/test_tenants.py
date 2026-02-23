"""
Integration tests for the tenant domain — Phase 3 success criteria.

Covers all 6 Phase 3 success criteria:
SC1: Workspace creation returns slug, creator is Owner with billing_access=True
SC2: Invitation flow — BOTH paths:
     - Existing user: explicit POST /invitations/accept with token
     - New user: auto-join at email verification (no separate accept step)
SC3: RBAC enforcement — role hierarchy prevents unauthorized actions
SC4: Member management — role changes, removal, voluntary leave
SC5: Ownership transfer — initiate, accept, role swap
SC6: Tenant context — UUID/slug lookup, missing header 403, cross-tenant isolation

Note: The `client` fixture yields a 4-tuple: (http_client, fake_redis, app, test_db).
Each test destructures it as needed.
"""

import pytest

from wxcode_adm.tenants.service import generate_invitation_token


# ---------------------------------------------------------------------------
# Helper: signup + verify + login sequence
# ---------------------------------------------------------------------------


async def _signup_verify_login(client, redis, email: str, password: str = "securepass") -> tuple[str, str]:
    """
    Sign up, verify email, and log in.

    Tracks which OTP keys existed BEFORE signup, then finds the new key created
    for the just-registered user. This avoids ambiguity when multiple users exist.

    Returns:
        (access_token, user_id) tuple.
    """
    # Record OTP keys that exist BEFORE signup to identify the new one
    keys_before = set()
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys_before.add(k)

    # Signup
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, f"Signup failed: {r.text}"

    # Find the NEW OTP key (wasn't there before signup)
    new_key = None
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k and k not in keys_before:
            new_key = k
            break

    assert new_key is not None, f"Expected new OTP key after signup for {email}, keys_before={keys_before}"
    code = await redis.get(new_key)
    assert code is not None, f"OTP code missing for key {new_key}"

    # Verify email
    r = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "code": code},
    )
    assert r.status_code == 200, f"Verify failed for {email}: {r.text}"

    # Login
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    data = r.json()
    return data["access_token"], data.get("user_id", "")


async def _get_otp_for_email(client, redis, email: str, password: str = "securepass") -> str:
    """
    Sign up a new user and return the OTP code without verifying.
    Scans Redis to find the single OTP key after signup.
    Returns the OTP code.
    """
    # Clear all existing OTP keys to isolate this signup
    existing_keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            existing_keys.append(k)
    # Delete all existing OTP keys before signup
    for k in existing_keys:
        await redis.delete(k)

    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, f"Signup failed: {r.text}"

    keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys.append(k)
    assert len(keys) == 1, f"Expected 1 OTP key after signup, found: {keys}"
    code = await redis.get(keys[0])
    assert code is not None
    return code


async def _create_workspace(client, token: str, name: str = "Test Workspace") -> dict:
    """
    POST /api/v1/onboarding/workspace, return response JSON.
    """
    r = await client.post(
        "/api/v1/onboarding/workspace",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"Create workspace failed: {r.text}"
    return r.json()


async def _invite_user(client, token: str, tenant_id: str, email: str, role: str = "developer") -> dict:
    """
    POST /api/v1/tenants/current/invitations, return response JSON.
    """
    r = await client.post(
        "/api/v1/tenants/current/invitations",
        json={"email": email, "role": role, "billing_access": False},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 201, f"Invite failed: {r.text}"
    return r.json()


async def _accept_invitation_for_existing_user(
    client, token: str, email: str, tenant_id: str
) -> dict:
    """
    Accept an invitation for an existing user.
    Regenerates the itsdangerous token using the monkeypatched serializer.
    """
    inv_token = generate_invitation_token(email, tenant_id)
    r = await client.post(
        "/api/v1/invitations/accept",
        json={"token": inv_token},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, f"Accept invitation failed: {r.text}"
    return r.json()


async def _setup_member_with_role(
    client, redis, owner_token: str, tenant_id: str, role: str
) -> tuple[str, str]:
    """
    Invite and onboard a new user with a given role. Returns (member_token, user_id).
    Helper for RBAC tests that need a member with a specific role.
    Uses _signup_verify_login which correctly tracks new OTP keys after signup.
    """
    email = f"member_{role}_{tenant_id[:8]}@test.com"
    member_token, _ = await _signup_verify_login(client, redis, email)

    # Owner invites this user
    inv_r = await client.post(
        "/api/v1/tenants/current/invitations",
        json={"email": email, "role": role, "billing_access": False},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert inv_r.status_code == 201, f"Invite failed: {inv_r.text}"

    # Accept invitation
    membership = await _accept_invitation_for_existing_user(client, member_token, email, tenant_id)
    return member_token, str(membership["user_id"])


# ---------------------------------------------------------------------------
# SC1: Workspace creation and slug (TNNT-01, TNNT-02)
# ---------------------------------------------------------------------------


async def test_create_workspace_returns_slug(client):
    """SC1: POST /onboarding/workspace with 'My Workspace' returns 201 with slug 'my-workspace'."""
    c, redis, app, db = client

    token, _ = await _signup_verify_login(c, redis, "owner1@test.com")
    workspace = await _create_workspace(c, token, "My Workspace")

    assert workspace["tenant"]["slug"] == "my-workspace"
    assert workspace["tenant"]["name"] == "My Workspace"
    assert "membership_id" in workspace


async def test_create_workspace_user_is_owner(client):
    """SC1: After creating workspace, GET /tenants/me shows user as Owner with billing_access=True."""
    c, redis, app, db = client

    token, _ = await _signup_verify_login(c, redis, "owner2@test.com")
    workspace = await _create_workspace(c, token, "My Corp")
    tenant_id = workspace["tenant"]["id"]

    r = await c.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    tenants = r.json()["tenants"]
    assert len(tenants) == 1
    assert tenants[0]["id"] == tenant_id
    assert tenants[0]["role"] == "owner"
    assert tenants[0]["billing_access"] is True


async def test_create_workspace_slug_uniqueness(client):
    """SC1/TNNT-02: Two users creating 'Same Name' get different slugs (second gets 'same-name-2')."""
    c, redis, app, db = client

    token1, _ = await _signup_verify_login(c, redis, "owner_slug1@test.com")
    token2, _ = await _signup_verify_login(c, redis, "owner_slug2@test.com")

    ws1 = await _create_workspace(c, token1, "Same Name")
    ws2 = await _create_workspace(c, token2, "Same Name")

    assert ws1["tenant"]["slug"] == "same-name"
    assert ws2["tenant"]["slug"] == "same-name-2"


async def test_create_workspace_requires_verified_user(client):
    """SC1: Unverified user cannot create workspace (403 EMAIL_NOT_VERIFIED)."""
    c, redis, app, db = client

    # Signup but do NOT verify
    r = await c.post(
        "/api/v1/auth/signup",
        json={"email": "unverified_ws@test.com", "password": "securepass"},
    )
    assert r.status_code == 201

    # Create a JWT manually — but require_verified dependency blocks unverified users
    from wxcode_adm.auth.jwt import create_access_token
    from wxcode_adm.auth.models import User
    from wxcode_adm.dependencies import get_session
    from sqlalchemy import select

    override_fn = app.dependency_overrides.get(get_session)
    async for session in override_fn():
        result = await session.execute(select(User).where(User.email == "unverified_ws@test.com"))
        user = result.scalar_one()
        break

    token = create_access_token(str(user.id))

    r = await c.post(
        "/api/v1/onboarding/workspace",
        json={"name": "Test Workspace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert r.json()["error_code"] == "EMAIL_NOT_VERIFIED"


# ---------------------------------------------------------------------------
# SC2: Invitation flow — Existing user (TNNT-03)
# ---------------------------------------------------------------------------


async def test_invite_user_by_email(client):
    """SC2: Owner invites user2@test.com, returns 201 with invitation details."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_inv1@test.com")
    workspace = await _create_workspace(c, owner_token, "Invite Test Corp")
    tenant_id = workspace["tenant"]["id"]

    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "invitee1@test.com", "role": "developer", "billing_access": False},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "invitee1@test.com"
    assert data["role"] == "developer"
    assert "id" in data
    assert "expires_at" in data


async def test_existing_user_accept_invitation(client):
    """SC2: Existing user (already verified BEFORE invite) calls POST /invitations/accept and becomes member."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_existinv@test.com")
    workspace = await _create_workspace(c, owner_token, "Existing User Invite Corp")
    tenant_id = workspace["tenant"]["id"]

    # user2 already has verified account BEFORE invitation
    user2_token, _ = await _signup_verify_login(c, redis, "existinguser@test.com")

    # Owner invites user2
    inv = await _invite_user(c, owner_token, tenant_id, "existinguser@test.com", "admin")

    # user2 accepts invitation
    inv_token = generate_invitation_token("existinguser@test.com", tenant_id)
    r = await c.post(
        "/api/v1/invitations/accept",
        json={"token": inv_token},
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["role"] == "admin"
    assert data["email"] == "existinguser@test.com"

    # Verify membership appears in /tenants/me
    r = await c.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {user2_token}"})
    assert r.status_code == 200
    tenants = r.json()["tenants"]
    tenant_ids = [t["id"] for t in tenants]
    assert tenant_id in tenant_ids


async def test_invite_duplicate_email_rejected(client):
    """SC2: Inviting same email twice returns 409 INVITATION_ALREADY_EXISTS."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_dup@test.com")
    workspace = await _create_workspace(c, owner_token, "Dup Invite Corp")
    tenant_id = workspace["tenant"]["id"]

    await _invite_user(c, owner_token, tenant_id, "dupinvitee@test.com")

    # Second invite — same email, same tenant
    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "dupinvitee@test.com", "role": "viewer", "billing_access": False},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "INVITATION_ALREADY_EXISTS"


async def test_invite_already_member_rejected(client):
    """SC2: Inviting existing member returns 409 ALREADY_MEMBER."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_alreadymem@test.com")
    workspace = await _create_workspace(c, owner_token, "Already Member Corp")
    tenant_id = workspace["tenant"]["id"]

    # Add user2 as member first
    member_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "developer")

    # Get user2's email from /tenants/current/members
    r = await c.get(
        "/api/v1/tenants/current/members",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 200
    members = r.json()
    # Find non-owner member
    member_email = next(m["email"] for m in members if m["role"] == "developer")

    # Try inviting existing member
    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": member_email, "role": "viewer", "billing_access": False},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "ALREADY_MEMBER"


async def test_invite_requires_admin_role(client):
    """SC2: Viewer trying to invite gets 403 INSUFFICIENT_ROLE."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_rbac_inv@test.com")
    workspace = await _create_workspace(c, owner_token, "RBAC Invite Corp")
    tenant_id = workspace["tenant"]["id"]

    viewer_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "viewer")

    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "newperson@test.com", "role": "developer", "billing_access": False},
        headers={
            "Authorization": f"Bearer {viewer_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 403
    assert r.json()["error_code"] == "INSUFFICIENT_ROLE"


async def test_cancel_invitation(client):
    """SC2: Admin cancels pending invitation, returns 200."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_cancel@test.com")
    workspace = await _create_workspace(c, owner_token, "Cancel Invite Corp")
    tenant_id = workspace["tenant"]["id"]

    inv = await _invite_user(c, owner_token, tenant_id, "cancelme@test.com")
    invitation_id = inv["id"]

    r = await c.delete(
        f"/api/v1/tenants/current/invitations/{invitation_id}",
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 200
    assert "cancelled" in r.json()["message"].lower()


# ---------------------------------------------------------------------------
# SC2: New user auto-join at email verification (TNNT-03, TNNT-04)
# ---------------------------------------------------------------------------


async def test_new_user_auto_joins_on_email_verification(client):
    """SC2 (CRITICAL): New user is auto-joined to tenant at email verification — no separate accept step.

    Flow:
    1. Owner invites newuser@test.com
    2. newuser@test.com signs up (POST /signup) — NOT verified yet, no join
    3. newuser@test.com verifies email (POST /verify-email)
    4. IMMEDIATELY after verification, user is a member (auto_join_pending_invitations called)
    5. Login + GET /tenants/me shows the tenant — user NEVER called POST /invitations/accept
    """
    c, redis, app, db = client

    # Step 1: Owner creates workspace and invites newuser@test.com
    owner_token, _ = await _signup_verify_login(c, redis, "owner_autojoin@test.com")
    workspace = await _create_workspace(c, owner_token, "Auto Join Corp")
    tenant_id = workspace["tenant"]["id"]

    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "autojoin_new@test.com", "role": "developer", "billing_access": False},
        headers={
            "Authorization": f"Bearer {owner_token}",
            "X-Tenant-ID": tenant_id,
        },
    )
    assert r.status_code == 201

    # Step 2: newuser signs up (not yet verified — no auto-join yet)
    # Clear OTP keys first to get clean state for this user
    otp_keys_to_clear = [k async for k in redis.scan_iter("auth:otp:*") if "attempts" not in k and "cooldown" not in k]
    for k in otp_keys_to_clear:
        await redis.delete(k)

    r = await c.post(
        "/api/v1/auth/signup",
        json={"email": "autojoin_new@test.com", "password": "securepass"},
    )
    assert r.status_code == 201

    # Step 3: Get OTP and verify email — this triggers auto_join_pending_invitations
    keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys.append(k)
    assert len(keys) >= 1
    code = await redis.get(keys[-1])  # Get the most recent OTP
    assert code is not None

    r = await c.post(
        "/api/v1/auth/verify-email",
        json={"email": "autojoin_new@test.com", "code": code},
    )
    assert r.status_code == 200, f"Verify email failed: {r.text}"

    # Step 4: Login
    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "autojoin_new@test.com", "password": "securepass"},
    )
    assert r.status_code == 200
    new_user_token = r.json()["access_token"]

    # Step 5: Check /tenants/me — user should already be a member without calling /accept
    r = await c.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {new_user_token}"})
    assert r.status_code == 200
    tenants = r.json()["tenants"]
    tenant_ids = [t["id"] for t in tenants]
    assert tenant_id in tenant_ids, (
        f"Expected tenant_id {tenant_id} in user's tenants after auto-join, but got: {tenant_ids}"
    )

    # Verify correct role was assigned
    user_tenant = next(t for t in tenants if t["id"] == tenant_id)
    assert user_tenant["role"] == "developer"


async def test_new_user_auto_joins_multiple_invitations(client):
    """SC2 (TNNT-04): New user invited to multiple tenants joins all at email verification."""
    c, redis, app, db = client

    # Owner A creates workspace and invites newuser
    owner_a_token, _ = await _signup_verify_login(c, redis, "owner_a_multi@test.com")
    ws_a = await _create_workspace(c, owner_a_token, "Multi Join Corp A")
    tenant_a_id = ws_a["tenant"]["id"]

    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "multi_new@test.com", "role": "developer", "billing_access": False},
        headers={"Authorization": f"Bearer {owner_a_token}", "X-Tenant-ID": tenant_a_id},
    )
    assert r.status_code == 201

    # Owner B creates workspace and invites same newuser
    owner_b_token, _ = await _signup_verify_login(c, redis, "owner_b_multi@test.com")
    ws_b = await _create_workspace(c, owner_b_token, "Multi Join Corp B")
    tenant_b_id = ws_b["tenant"]["id"]

    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "multi_new@test.com", "role": "viewer", "billing_access": False},
        headers={"Authorization": f"Bearer {owner_b_token}", "X-Tenant-ID": tenant_b_id},
    )
    assert r.status_code == 201

    # Newuser signs up and verifies — triggers auto-join for BOTH tenants
    # Clear existing OTP keys
    otp_keys = [k async for k in redis.scan_iter("auth:otp:*") if "attempts" not in k and "cooldown" not in k]
    for k in otp_keys:
        await redis.delete(k)

    r = await c.post(
        "/api/v1/auth/signup",
        json={"email": "multi_new@test.com", "password": "securepass"},
    )
    assert r.status_code == 201

    keys = []
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys.append(k)
    code = await redis.get(keys[-1])

    r = await c.post(
        "/api/v1/auth/verify-email",
        json={"email": "multi_new@test.com", "code": code},
    )
    assert r.status_code == 200

    r = await c.post(
        "/api/v1/auth/login",
        json={"email": "multi_new@test.com", "password": "securepass"},
    )
    new_user_token = r.json()["access_token"]

    r = await c.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {new_user_token}"})
    assert r.status_code == 200
    tenants = r.json()["tenants"]
    tenant_ids = [t["id"] for t in tenants]

    assert tenant_a_id in tenant_ids, "Expected user to be in tenant A"
    assert tenant_b_id in tenant_ids, "Expected user to be in tenant B"

    # Verify correct roles per tenant
    tenant_a_membership = next(t for t in tenants if t["id"] == tenant_a_id)
    tenant_b_membership = next(t for t in tenants if t["id"] == tenant_b_id)
    assert tenant_a_membership["role"] == "developer"
    assert tenant_b_membership["role"] == "viewer"


# ---------------------------------------------------------------------------
# SC3: RBAC enforcement (RBAC-01)
# ---------------------------------------------------------------------------


async def test_viewer_cannot_invite(client):
    """SC3: Viewer POSTs to /invitations gets 403."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_viewer_inv@test.com")
    workspace = await _create_workspace(c, owner_token, "Viewer Invite Corp")
    tenant_id = workspace["tenant"]["id"]

    viewer_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "viewer")

    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "newperson2@test.com", "role": "developer", "billing_access": False},
        headers={"Authorization": f"Bearer {viewer_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 403


async def test_viewer_cannot_change_roles(client):
    """SC3: Viewer PATCHes /members/{id}/role gets 403."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_viewer_role@test.com")
    workspace = await _create_workspace(c, owner_token, "Viewer Role Corp")
    tenant_id = workspace["tenant"]["id"]

    viewer_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "viewer")

    # Get owner's user_id to attempt role change
    r = await c.get(
        "/api/v1/tenants/current/members",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    members = r.json()
    owner_user_id = next(m["user_id"] for m in members if m["role"] == "owner")

    r = await c.patch(
        f"/api/v1/tenants/current/members/{owner_user_id}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {viewer_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 403


async def test_developer_cannot_invite(client):
    """SC3: Developer POSTs to /invitations gets 403."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_dev_inv@test.com")
    workspace = await _create_workspace(c, owner_token, "Dev Invite Corp")
    tenant_id = workspace["tenant"]["id"]

    dev_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "developer")

    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "anotherdev@test.com", "role": "developer", "billing_access": False},
        headers={"Authorization": f"Bearer {dev_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 403


async def test_admin_can_invite(client):
    """SC3: Admin can invite users (201)."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_admin_inv@test.com")
    workspace = await _create_workspace(c, owner_token, "Admin Invite Corp")
    tenant_id = workspace["tenant"]["id"]

    admin_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "admin")

    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "newmember_admin@test.com", "role": "viewer", "billing_access": False},
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 201


async def test_admin_can_change_roles(client):
    """SC3: Admin can change Developer to Viewer (200)."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_admin_role@test.com")
    workspace = await _create_workspace(c, owner_token, "Admin Role Corp")
    tenant_id = workspace["tenant"]["id"]

    admin_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "admin")
    dev_token, dev_user_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "developer")

    r = await c.patch(
        f"/api/v1/tenants/current/members/{dev_user_id}/role",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "viewer"


async def test_role_hierarchy_enforcement(client):
    """SC3: Verify role hierarchy Owner > Admin > Developer > Viewer."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_hier@test.com")
    workspace = await _create_workspace(c, owner_token, "Hierarchy Corp")
    tenant_id = workspace["tenant"]["id"]

    # Developer cannot change roles
    dev_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "developer")
    viewer_token, viewer_uid = await _setup_member_with_role(c, redis, owner_token, tenant_id, "viewer")

    r = await c.patch(
        f"/api/v1/tenants/current/members/{viewer_uid}/role",
        json={"role": "developer"},
        headers={"Authorization": f"Bearer {dev_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 403

    # Owner CAN change roles
    r = await c.patch(
        f"/api/v1/tenants/current/members/{viewer_uid}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


# ---------------------------------------------------------------------------
# SC4: Member management (RBAC-02, RBAC-03)
# ---------------------------------------------------------------------------


async def test_change_member_role(client):
    """SC4: Owner changes member from Developer to Admin."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_chgrole@test.com")
    workspace = await _create_workspace(c, owner_token, "Change Role Corp")
    tenant_id = workspace["tenant"]["id"]

    dev_token, dev_user_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "developer")

    r = await c.patch(
        f"/api/v1/tenants/current/members/{dev_user_id}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "admin"
    assert data["user_id"] == dev_user_id


async def test_remove_member(client):
    """SC4: Admin removes a Viewer, Viewer's account persists."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_remove@test.com")
    workspace = await _create_workspace(c, owner_token, "Remove Corp")
    tenant_id = workspace["tenant"]["id"]

    viewer_token, viewer_user_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "viewer")

    r = await c.delete(
        f"/api/v1/tenants/current/members/{viewer_user_id}",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 200

    # Viewer's account still exists — they can still log in
    r = await c.get(
        "/api/v1/tenants/me",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert r.status_code == 200
    # But they're no longer a member of this tenant
    tenants = r.json()["tenants"]
    tenant_ids = [t["id"] for t in tenants]
    assert tenant_id not in tenant_ids


async def test_owner_cannot_self_demote(client):
    """SC4: Owner trying to change own role gets 403 OWNER_CANNOT_SELF_DEMOTE."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_selfdemote@test.com")
    workspace = await _create_workspace(c, owner_token, "Self Demote Corp")
    tenant_id = workspace["tenant"]["id"]

    # Get owner's user_id from members
    r = await c.get(
        "/api/v1/tenants/current/members",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    members = r.json()
    owner_user_id = next(m["user_id"] for m in members if m["role"] == "owner")

    # Owner tries to change own role to admin
    r = await c.patch(
        f"/api/v1/tenants/current/members/{owner_user_id}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 403
    assert r.json()["error_code"] == "OWNER_CANNOT_SELF_DEMOTE"


async def test_member_voluntary_leave(client):
    """SC4: Developer leaves tenant, membership deleted, user account preserved."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_leave@test.com")
    workspace = await _create_workspace(c, owner_token, "Leave Corp")
    tenant_id = workspace["tenant"]["id"]

    dev_token, _ = await _setup_member_with_role(c, redis, owner_token, tenant_id, "developer")

    r = await c.post(
        "/api/v1/tenants/current/leave",
        headers={"Authorization": f"Bearer {dev_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 200

    # Developer no longer sees this tenant
    r = await c.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {dev_token}"})
    tenants = r.json()["tenants"]
    assert tenant_id not in [t["id"] for t in tenants]


async def test_owner_cannot_leave(client):
    """SC4: Owner trying to leave gets 403 OWNER_CANNOT_LEAVE."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_cantleave@test.com")
    workspace = await _create_workspace(c, owner_token, "Cant Leave Corp")
    tenant_id = workspace["tenant"]["id"]

    r = await c.post(
        "/api/v1/tenants/current/leave",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 403
    assert r.json()["error_code"] == "OWNER_CANNOT_LEAVE"


# ---------------------------------------------------------------------------
# SC5: Ownership transfer (TNNT-05)
# ---------------------------------------------------------------------------


async def test_initiate_ownership_transfer(client):
    """SC5: Owner creates transfer request, returns 201."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_transfer1@test.com")
    workspace = await _create_workspace(c, owner_token, "Transfer Corp")
    tenant_id = workspace["tenant"]["id"]

    target_token, target_user_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "admin")

    r = await c.post(
        "/api/v1/tenants/current/transfer",
        json={"to_user_id": target_user_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["to_user_id"] == target_user_id
    assert "expires_at" in data


async def test_accept_ownership_transfer(client):
    """SC5: Target accepts, old Owner becomes Admin, target becomes Owner."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_transfer2@test.com")
    workspace = await _create_workspace(c, owner_token, "Accept Transfer Corp")
    tenant_id = workspace["tenant"]["id"]

    target_token, target_user_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "admin")

    # Initiate transfer
    r = await c.post(
        "/api/v1/tenants/current/transfer",
        json={"to_user_id": target_user_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 201

    # Target accepts
    r = await c.post(
        "/api/v1/tenants/current/transfer/accept",
        headers={"Authorization": f"Bearer {target_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 200

    # Verify role swap
    r = await c.get(
        "/api/v1/tenants/current/members",
        headers={"Authorization": f"Bearer {target_token}", "X-Tenant-ID": tenant_id},
    )
    members = r.json()
    new_owner = next(m for m in members if m["user_id"] == target_user_id)
    assert new_owner["role"] == "owner"

    # Old owner is now admin
    old_owner = next((m for m in members if m["user_id"] != target_user_id), None)
    if old_owner:
        assert old_owner["role"] == "admin"


async def test_transfer_already_pending(client):
    """SC5: Second transfer attempt returns 409 TRANSFER_ALREADY_PENDING."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_transfer3@test.com")
    workspace = await _create_workspace(c, owner_token, "Double Transfer Corp")
    tenant_id = workspace["tenant"]["id"]

    target1_token, target1_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "admin")
    target2_token, target2_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "developer")

    # First transfer
    r = await c.post(
        "/api/v1/tenants/current/transfer",
        json={"to_user_id": target1_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 201

    # Second transfer attempt — already pending
    r = await c.post(
        "/api/v1/tenants/current/transfer",
        json={"to_user_id": target2_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "TRANSFER_ALREADY_PENDING"


async def test_only_owner_can_initiate_transfer(client):
    """SC5: Admin trying to initiate transfer gets 403."""
    c, redis, app, db = client

    owner_token, _ = await _signup_verify_login(c, redis, "owner_transfer4@test.com")
    workspace = await _create_workspace(c, owner_token, "Admin Transfer Corp")
    tenant_id = workspace["tenant"]["id"]

    admin_token, admin_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "admin")
    dev_token, dev_id = await _setup_member_with_role(c, redis, owner_token, tenant_id, "developer")

    r = await c.post(
        "/api/v1/tenants/current/transfer",
        json={"to_user_id": dev_id},
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# SC6: Tenant context and isolation
# ---------------------------------------------------------------------------


async def test_tenant_context_by_uuid(client):
    """SC6: X-Tenant-ID with UUID resolves correctly."""
    c, redis, app, db = client

    token, _ = await _signup_verify_login(c, redis, "owner_uuid@test.com")
    workspace = await _create_workspace(c, token, "UUID Corp")
    tenant_id = workspace["tenant"]["id"]

    r = await c.get(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert r.status_code == 200
    assert r.json()["id"] == tenant_id


async def test_tenant_context_by_slug(client):
    """SC6: X-Tenant-ID with slug resolves correctly."""
    c, redis, app, db = client

    token, _ = await _signup_verify_login(c, redis, "owner_slug_ctx@test.com")
    workspace = await _create_workspace(c, token, "Slug Context Corp")
    tenant_id = workspace["tenant"]["id"]
    slug = workspace["tenant"]["slug"]

    r = await c.get(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": slug},
    )
    assert r.status_code == 200
    assert r.json()["id"] == tenant_id
    assert r.json()["slug"] == slug


async def test_missing_tenant_header_returns_403(client):
    """SC6: No X-Tenant-ID returns 403 TENANT_CONTEXT_REQUIRED."""
    c, redis, app, db = client

    token, _ = await _signup_verify_login(c, redis, "owner_noheader@test.com")
    await _create_workspace(c, token, "No Header Corp")

    # Call without X-Tenant-ID header
    r = await c.get(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert r.json()["error_code"] == "TENANT_CONTEXT_REQUIRED"


async def test_non_member_tenant_returns_404(client):
    """SC6: User accessing tenant they don't belong to gets 404."""
    c, redis, app, db = client

    # Create two users with separate workspaces
    token_a, _ = await _signup_verify_login(c, redis, "owner_isolation_a@test.com")
    token_b, _ = await _signup_verify_login(c, redis, "owner_isolation_b@test.com")

    ws_a = await _create_workspace(c, token_a, "Isolation Corp A")
    tenant_a_id = ws_a["tenant"]["id"]

    # User B tries to access Tenant A (not a member)
    r = await c.get(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {token_b}", "X-Tenant-ID": tenant_a_id},
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "TENANT_NOT_FOUND"


async def test_cross_tenant_isolation(client):
    """SC6: Users can only see their own tenant's data — zero cross-tenant leakage."""
    c, redis, app, db = client

    # User A creates workspace A
    token_a, _ = await _signup_verify_login(c, redis, "owner_cross_a@test.com")
    ws_a = await _create_workspace(c, token_a, "Cross Isolation A")
    tenant_a_id = ws_a["tenant"]["id"]

    # User B creates workspace B
    token_b, _ = await _signup_verify_login(c, redis, "owner_cross_b@test.com")
    ws_b = await _create_workspace(c, token_b, "Cross Isolation B")
    tenant_b_id = ws_b["tenant"]["id"]

    # User A with X-Tenant-ID=B gets 404 (not a member of B)
    r = await c.get(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {token_a}", "X-Tenant-ID": tenant_b_id},
    )
    assert r.status_code == 404

    # User B with X-Tenant-ID=A gets 404 (not a member of A)
    r = await c.get(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {token_b}", "X-Tenant-ID": tenant_a_id},
    )
    assert r.status_code == 404

    # Each user sees only their own members
    r = await c.get(
        "/api/v1/tenants/current/members",
        headers={"Authorization": f"Bearer {token_a}", "X-Tenant-ID": tenant_a_id},
    )
    assert r.status_code == 200
    members_a = r.json()
    assert len(members_a) == 1
    assert members_a[0]["email"] == "owner_cross_a@test.com"

    r = await c.get(
        "/api/v1/tenants/current/members",
        headers={"Authorization": f"Bearer {token_b}", "X-Tenant-ID": tenant_b_id},
    )
    assert r.status_code == 200
    members_b = r.json()
    assert len(members_b) == 1
    assert members_b[0]["email"] == "owner_cross_b@test.com"


# ---------------------------------------------------------------------------
# Multi-tenant membership
# ---------------------------------------------------------------------------


async def test_user_belongs_to_multiple_tenants(client):
    """TNNT-04: User creates workspace A, accepts invitation to workspace B, sees both via /tenants/me."""
    c, redis, app, db = client

    # User A creates workspace A
    user_a_token, _ = await _signup_verify_login(c, redis, "multi_owner@test.com")
    ws_a = await _create_workspace(c, user_a_token, "Multi Tenant A")
    tenant_a_id = ws_a["tenant"]["id"]

    # Owner B creates workspace B
    owner_b_token, _ = await _signup_verify_login(c, redis, "owner_multi_b@test.com")
    ws_b = await _create_workspace(c, owner_b_token, "Multi Tenant B")
    tenant_b_id = ws_b["tenant"]["id"]

    # Owner B invites user A
    r = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "multi_owner@test.com", "role": "developer", "billing_access": False},
        headers={"Authorization": f"Bearer {owner_b_token}", "X-Tenant-ID": tenant_b_id},
    )
    assert r.status_code == 201

    # User A accepts invitation to workspace B
    membership = await _accept_invitation_for_existing_user(
        c, user_a_token, "multi_owner@test.com", tenant_b_id
    )
    assert membership["role"] == "developer"

    # User A should see BOTH tenants via /tenants/me
    r = await c.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {user_a_token}"})
    assert r.status_code == 200
    tenants = r.json()["tenants"]
    assert len(tenants) == 2

    tenant_ids = [t["id"] for t in tenants]
    assert tenant_a_id in tenant_ids
    assert tenant_b_id in tenant_ids

    # Correct per-tenant roles
    tenant_a_mem = next(t for t in tenants if t["id"] == tenant_a_id)
    tenant_b_mem = next(t for t in tenants if t["id"] == tenant_b_id)
    assert tenant_a_mem["role"] == "owner"
    assert tenant_b_mem["role"] == "developer"
