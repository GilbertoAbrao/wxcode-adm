"""
Integration tests for the billing domain — Phase 4 success criteria.

Covers all 5 Phase 4 success criteria:
SC1: Super-admin CRUD billing plans + Stripe sync (BILL-01)
SC2: Stripe Checkout flow — session creation, free plan rejection, free subscription bootstrap (BILL-02)
SC3: Webhook processing — checkout completed, payment failed, invoice paid, subscription deleted, idempotency (BILL-03)
SC4: Customer Portal — returns portal URL (BILL-04)
SC5: Plan enforcement — quota block, past_due block, member cap block (BILL-05)

Note: The `client` fixture yields a 4-tuple: (http_client, fake_redis, app, test_db).
Each test destructures it as needed.

Stripe calls are mocked via monkeypatch in conftest.py (_FakeStripeClient).
get_arq_pool is mocked in webhook_router_module and tasks.worker.
"""

import uuid

import pytest


# ---------------------------------------------------------------------------
# Helpers: signup + verify + login sequence
# ---------------------------------------------------------------------------


async def _signup_verify_login(
    client, redis, email: str = "billing@test.com", password: str = "Test1234!"
) -> tuple[str, str]:
    """
    Sign up, verify email, and log in.

    Tracks which OTP keys existed BEFORE signup to identify the new one.
    Returns (access_token, user_id) tuple.
    """
    # Record OTP keys that exist BEFORE signup
    keys_before = set()
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k:
            keys_before.add(k)

    # Signup
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, f"Signup failed: {r.text}"

    # Find the NEW OTP key
    new_key = None
    async for k in redis.scan_iter("auth:otp:*"):
        if "attempts" not in k and "cooldown" not in k and k not in keys_before:
            new_key = k
            break

    assert new_key is not None, f"Expected new OTP key after signup for {email}"
    code = await redis.get(new_key)
    assert code is not None

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


async def _create_workspace(client, token: str, name: str = "Test Billing Workspace") -> str:
    """Create workspace. Returns tenant_id string."""
    resp = await client.post(
        "/api/v1/onboarding/workspace",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Create workspace failed: {resp.text}"
    return resp.json()["tenant"]["id"]


async def _seed_paid_plan(test_db) -> uuid.UUID:
    """Insert a paid plan directly into DB for tests. Returns plan.id."""
    from wxcode_adm.billing.models import Plan

    async with test_db() as session:
        plan = Plan(
            name="Starter",
            slug="starter",
            monthly_fee_cents=2900,
            token_quota=100000,
            overage_rate_cents_per_token=4,
            member_cap=10,
            is_active=True,
            stripe_product_id="prod_test",
            stripe_price_id="price_test_flat",
            stripe_meter_id="mtr_test",
            stripe_overage_price_id="price_test_overage",
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan.id


async def _make_superuser(test_db, email: str) -> None:
    """Elevate a user to superuser in the DB."""
    from sqlalchemy import select

    from wxcode_adm.auth.models import User

    async with test_db() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.is_superuser = True
        await session.commit()


async def _seed_super_admin(test_db, email: str, password: str) -> None:
    """Insert a super-admin user directly into test DB."""
    from sqlalchemy import select

    from wxcode_adm.auth.models import User
    from wxcode_adm.auth.password import hash_password

    async with test_db() as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return
        admin = User(
            email=email,
            password_hash=hash_password(password),
            email_verified=True,
            is_active=True,
            is_superuser=True,
        )
        session.add(admin)
        await session.commit()


async def _admin_login(client, email: str, password: str) -> str:
    """Log in via /api/v1/admin/login and return admin-audience access token."""
    r = await client.post(
        "/api/v1/admin/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# SC1: Super-admin CRUD billing plans + Stripe sync (BILL-01)
# ---------------------------------------------------------------------------


async def test_superadmin_create_plan(client):
    """SC1: Super-admin can create a billing plan synced to Stripe (admin-audience JWT)."""
    c, redis, app, test_db = client
    await _seed_super_admin(test_db, "admin_create@test.com", "Test1234!")
    token = await _admin_login(c, "admin_create@test.com", "Test1234!")

    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={
            "name": "Pro",
            "slug": "pro",
            "monthly_fee_cents": 9900,
            "token_quota": 500000,
            "overage_rate_cents_per_token": 2,
            "member_cap": 50,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Create plan failed: {resp.text}"
    data = resp.json()
    assert data["name"] == "Pro"
    assert data["slug"] == "pro"
    assert data["monthly_fee_cents"] == 9900
    assert data["token_quota"] == 500000
    assert data["is_active"] is True


async def test_regular_jwt_rejected_on_billing_admin(client):
    """SC1: Regular-audience JWT gets 401 on admin billing endpoints (audience isolation)."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "nonadmin_create@test.com")

    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={
            "name": "Pro",
            "slug": "pro-noadmin",
            "monthly_fee_cents": 9900,
            "token_quota": 500000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


async def test_superadmin_update_plan(client):
    """SC1: Super-admin can update plan details (admin-audience JWT)."""
    c, redis, app, test_db = client
    await _seed_super_admin(test_db, "admin_update@test.com", "Test1234!")
    token = await _admin_login(c, "admin_update@test.com", "Test1234!")

    # Create plan first
    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={
            "name": "UpdateMe",
            "slug": "update-me",
            "monthly_fee_cents": 1000,
            "token_quota": 50000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    plan_id = resp.json()["id"]

    # Update it
    resp = await c.patch(
        f"/api/v1/admin/billing/plans/{plan_id}",
        json={"name": "Updated Plan", "monthly_fee_cents": 1500},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"Update plan failed: {resp.text}"
    data = resp.json()
    assert data["name"] == "Updated Plan"
    assert data["monthly_fee_cents"] == 1500


async def test_superadmin_delete_plan(client):
    """SC1: Super-admin can soft-delete a plan (is_active=False) via admin-audience JWT."""
    c, redis, app, test_db = client
    await _seed_super_admin(test_db, "admin_delete@test.com", "Test1234!")
    token = await _admin_login(c, "admin_delete@test.com", "Test1234!")

    # Create plan
    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={
            "name": "DeleteMe",
            "slug": "delete-me",
            "monthly_fee_cents": 500,
            "token_quota": 5000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    plan_id = resp.json()["id"]

    # Soft-delete
    resp = await c.delete(
        f"/api/v1/admin/billing/plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"Delete plan failed: {resp.text}"
    assert resp.json()["is_active"] is False


async def test_list_active_plans(client):
    """SC1: Admin CRUD + public list only returns active plans.

    Admin operations use admin-audience JWT (require_admin).
    Public GET /billing/plans uses regular-audience JWT (require_verified).
    """
    c, redis, app, test_db = client
    # Admin token for plan CRUD
    await _seed_super_admin(test_db, "listplans@test.com", "Test1234!")
    admin_token = await _admin_login(c, "listplans@test.com", "Test1234!")

    # Regular user token for public listing endpoint (require_verified)
    regular_token, _ = await _signup_verify_login(c, redis, "listplans_regular@test.com")

    # Create an active plan and an inactive one (admin-audience)
    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={"name": "Active Plan", "slug": "active-plan", "monthly_fee_cents": 3000, "token_quota": 200000},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    active_id = resp.json()["id"]

    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={"name": "Inactive Plan", "slug": "inactive-plan", "monthly_fee_cents": 5000, "token_quota": 300000},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    inactive_id = resp.json()["id"]

    # Soft-delete the inactive plan (admin-audience)
    await c.delete(
        f"/api/v1/admin/billing/plans/{inactive_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Public plan listing returns only active plans (regular-audience token)
    resp = await c.get("/api/v1/billing/plans", headers={"Authorization": f"Bearer {regular_token}"})
    assert resp.status_code == 200
    plan_ids = [p["id"] for p in resp.json()]
    assert active_id in plan_ids
    assert inactive_id not in plan_ids


async def test_create_plan_with_limits(client):
    """SC1: Admin can create a plan with explicit wxcode limit values."""
    c, redis, app, test_db = client
    await _seed_super_admin(test_db, "admin_limits@test.com", "Test1234!")
    token = await _admin_login(c, "admin_limits@test.com", "Test1234!")

    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={
            "name": "Limits Plan",
            "slug": "limits-plan",
            "monthly_fee_cents": 4900,
            "token_quota": 200000,
            "max_projects": 10,
            "max_output_projects": 50,
            "max_storage_gb": 25,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Create plan with limits failed: {resp.text}"
    data = resp.json()
    assert data["max_projects"] == 10
    assert data["max_output_projects"] == 50
    assert data["max_storage_gb"] == 25


async def test_create_plan_limits_defaults(client):
    """SC1: Admin creates a plan without limit fields — response has correct defaults."""
    c, redis, app, test_db = client
    await _seed_super_admin(test_db, "admin_limits_defaults@test.com", "Test1234!")
    token = await _admin_login(c, "admin_limits_defaults@test.com", "Test1234!")

    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={
            "name": "Defaults Plan",
            "slug": "defaults-plan",
            "monthly_fee_cents": 1900,
            "token_quota": 100000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Create plan with defaults failed: {resp.text}"
    data = resp.json()
    assert data["max_projects"] == 5
    assert data["max_output_projects"] == 20
    assert data["max_storage_gb"] == 10


async def test_update_plan_limits(client):
    """SC1: Admin can patch individual limit fields; unpatched fields remain unchanged."""
    c, redis, app, test_db = client
    await _seed_super_admin(test_db, "admin_limits_update@test.com", "Test1234!")
    token = await _admin_login(c, "admin_limits_update@test.com", "Test1234!")

    # Create plan with default limits
    resp = await c.post(
        "/api/v1/admin/billing/plans/",
        json={
            "name": "Update Limits Plan",
            "slug": "update-limits-plan",
            "monthly_fee_cents": 7900,
            "token_quota": 300000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Create plan failed: {resp.text}"
    plan_id = resp.json()["id"]

    # Patch only max_projects and max_storage_gb; max_output_projects should remain 20
    resp = await c.patch(
        f"/api/v1/admin/billing/plans/{plan_id}",
        json={"max_projects": 15, "max_storage_gb": 50},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"Update plan limits failed: {resp.text}"
    data = resp.json()
    assert data["max_projects"] == 15
    assert data["max_storage_gb"] == 50
    assert data["max_output_projects"] == 20  # unchanged


# ---------------------------------------------------------------------------
# SC2: Stripe Checkout flow (BILL-02)
# ---------------------------------------------------------------------------


async def test_checkout_creates_session(client):
    """SC2: User can create a Stripe Checkout session for a paid plan."""
    c, redis, app, test_db = client
    paid_plan_id = await _seed_paid_plan(test_db)
    token, _ = await _signup_verify_login(c, redis, "checkout@test.com")
    tenant_id = await _create_workspace(c, token, "Checkout Test")

    resp = await c.post(
        "/api/v1/billing/checkout",
        json={"plan_id": str(paid_plan_id)},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert resp.status_code == 200, f"Checkout failed: {resp.text}"
    data = resp.json()
    assert "checkout_url" in data
    assert "session_id" in data
    assert data["checkout_url"] == "https://checkout.stripe.com/test"


async def test_checkout_rejects_free_plan(client):
    """SC2: Cannot checkout for the free plan (returns 409)."""
    c, redis, app, test_db = client

    # Get the free plan id from DB
    from sqlalchemy import select

    from wxcode_adm.billing.models import Plan

    async with test_db() as session:
        free_plan = (
            await session.execute(
                select(Plan).where(Plan.monthly_fee_cents == 0, Plan.is_active.is_(True))
            )
        ).scalar_one()
        free_plan_id = str(free_plan.id)

    token, _ = await _signup_verify_login(c, redis, "free_checkout@test.com")
    tenant_id = await _create_workspace(c, token, "Free Checkout Test")

    resp = await c.post(
        "/api/v1/billing/checkout",
        json={"plan_id": free_plan_id},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"


async def test_workspace_creates_free_subscription(client):
    """SC2: Workspace creation bootstraps TenantSubscription with status=free."""
    c, redis, app, test_db = client

    from sqlalchemy import select

    from wxcode_adm.billing.models import Plan, TenantSubscription

    # Get the seeded free plan id
    async with test_db() as session:
        free_plan = (
            await session.execute(
                select(Plan).where(Plan.monthly_fee_cents == 0, Plan.is_active.is_(True))
            )
        ).scalar_one()
        free_plan_id = free_plan.id

    token, _ = await _signup_verify_login(c, redis, "bootstrap@test.com")
    tenant_id = await _create_workspace(c, token, "Bootstrap Test")

    # Verify subscription exists with status=free
    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        assert sub.status.value == "free"
        assert sub.plan_id == free_plan_id


# ---------------------------------------------------------------------------
# SC3: Webhook processing (BILL-03)
# ---------------------------------------------------------------------------


async def test_webhook_checkout_completed(client):
    """SC3: checkout.session.completed activates subscription."""
    c, redis, app, test_db = client
    paid_plan_id = await _seed_paid_plan(test_db)
    token, _ = await _signup_verify_login(c, redis, "webhook_checkout@test.com")
    tenant_id = await _create_workspace(c, token, "Webhook Checkout Test")

    from wxcode_adm.billing.service import process_stripe_event

    ctx = {"session_maker": test_db}
    data_object = {
        "customer": "cus_test_123",
        "subscription": "sub_test_checkout_1",
        "metadata": {"tenant_id": tenant_id, "plan_id": str(paid_plan_id)},
    }
    await process_stripe_event(ctx, "evt_checkout_completed_1", "checkout.session.completed", data_object)

    from sqlalchemy import select

    from wxcode_adm.billing.models import SubscriptionStatus, TenantSubscription

    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.stripe_subscription_id == "sub_test_checkout_1"
        assert sub.plan_id == paid_plan_id


async def test_webhook_payment_failed(client):
    """SC3: invoice.payment_failed sets past_due and revokes tokens."""
    c, redis, app, test_db = client
    paid_plan_id = await _seed_paid_plan(test_db)
    token, _ = await _signup_verify_login(c, redis, "webhook_payment_failed@test.com")
    tenant_id = await _create_workspace(c, token, "Payment Failed Test")

    from sqlalchemy import select

    from wxcode_adm.billing.models import SubscriptionStatus, TenantSubscription

    # First activate the subscription via checkout completed
    from wxcode_adm.billing.service import process_stripe_event

    ctx = {"session_maker": test_db}
    await process_stripe_event(
        ctx,
        "evt_checkout_for_pf",
        "checkout.session.completed",
        {
            "customer": "cus_pf_test",
            "subscription": "sub_payment_failed_1",
            "metadata": {"tenant_id": tenant_id, "plan_id": str(paid_plan_id)},
        },
    )

    # Now trigger payment_failed
    await process_stripe_event(
        ctx,
        "evt_payment_failed_1",
        "invoice.payment_failed",
        {"subscription": "sub_payment_failed_1"},
    )

    # Verify status=PAST_DUE
    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        assert sub.status == SubscriptionStatus.PAST_DUE


async def test_payment_failed_blacklists_access_token(client):
    """E2E flow #8: payment failure webhook -> subscription PAST_DUE -> access tokens
    blacklisted -> member blocked on platform-level endpoints.

    Proves: _handle_payment_failed uses UserSession.access_token_jti + blacklist_jti
    to revoke active sessions, not the broken token.token pattern.
    """
    c, redis, app, test_db = client
    paid_plan_id = await _seed_paid_plan(test_db)

    # 1. Login as regular user and create workspace
    token, _ = await _signup_verify_login(c, redis, "flow8_e2e@test.com")
    tenant_id = await _create_workspace(c, token, "Flow 8 E2E")

    # 2. Verify pre-condition: user can access platform endpoints
    resp = await c.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert resp.status_code == 200, f"Expected 200 pre-payment-failure, got {resp.status_code}: {resp.text}"

    # 3. Activate subscription via checkout webhook
    from wxcode_adm.billing.service import process_stripe_event

    ctx = {"session_maker": test_db}
    await process_stripe_event(
        ctx,
        "evt_flow8_checkout",
        "checkout.session.completed",
        {
            "customer": "cus_flow8",
            "subscription": "sub_flow8",
            "metadata": {"tenant_id": tenant_id, "plan_id": str(paid_plan_id)},
        },
    )

    # 4. Fire payment_failed webhook
    await process_stripe_event(
        ctx,
        "evt_flow8_failed",
        "invoice.payment_failed",
        {"subscription": "sub_flow8"},
    )

    # 5. Verify subscription is PAST_DUE
    from sqlalchemy import select

    from wxcode_adm.billing.models import SubscriptionStatus, TenantSubscription

    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        assert sub.status == SubscriptionStatus.PAST_DUE, (
            f"Expected PAST_DUE, got {sub.status}"
        )

    # 6. Verify JTI is blacklisted in Redis
    from wxcode_adm.auth.models import UserSession

    async with test_db() as session:
        result = await session.execute(
            select(UserSession).where(
                UserSession.user_id.in_(
                    [row[0] async for row in await session.stream(
                        select(UserSession.user_id).limit(100)
                    )]
                )
            )
        )

    # Simpler: scan Redis for any blacklist key created by the webhook
    blacklist_keys = []
    async for key in redis.scan_iter("auth:blacklist:jti:*"):
        blacklist_keys.append(key)
    assert len(blacklist_keys) > 0, (
        "Expected at least one JTI blacklist key in Redis after payment failure"
    )

    # 7. Verify original token is rejected (blacklisted JTI causes 401)
    resp = await c.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert resp.status_code == 401, (
        f"Expected 401 (blacklisted token), got {resp.status_code}: {resp.text}"
    )


async def test_webhook_invoice_paid_restores(client):
    """SC3: invoice.paid restores past_due subscription to active."""
    c, redis, app, test_db = client
    paid_plan_id = await _seed_paid_plan(test_db)
    token, _ = await _signup_verify_login(c, redis, "webhook_invoice_paid@test.com")
    tenant_id = await _create_workspace(c, token, "Invoice Paid Test")

    from wxcode_adm.billing.service import process_stripe_event

    ctx = {"session_maker": test_db}
    sub_id = "sub_invoice_paid_1"

    # Activate
    await process_stripe_event(
        ctx,
        "evt_checkout_for_ip",
        "checkout.session.completed",
        {
            "customer": "cus_ip_test",
            "subscription": sub_id,
            "metadata": {"tenant_id": tenant_id, "plan_id": str(paid_plan_id)},
        },
    )

    # Set to past_due
    await process_stripe_event(
        ctx,
        "evt_payment_failed_for_ip",
        "invoice.payment_failed",
        {"subscription": sub_id},
    )

    # Restore via invoice.paid
    await process_stripe_event(
        ctx,
        "evt_invoice_paid_1",
        "invoice.paid",
        {"subscription": sub_id},
    )

    from sqlalchemy import select

    from wxcode_adm.billing.models import SubscriptionStatus, TenantSubscription

    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        assert sub.status == SubscriptionStatus.ACTIVE


async def test_webhook_subscription_deleted(client):
    """SC3: customer.subscription.deleted sets subscription to canceled."""
    c, redis, app, test_db = client
    paid_plan_id = await _seed_paid_plan(test_db)
    token, _ = await _signup_verify_login(c, redis, "webhook_sub_deleted@test.com")
    tenant_id = await _create_workspace(c, token, "Sub Deleted Test")

    from wxcode_adm.billing.service import process_stripe_event

    ctx = {"session_maker": test_db}
    sub_id = "sub_deleted_1"

    # Activate first
    await process_stripe_event(
        ctx,
        "evt_checkout_for_delete",
        "checkout.session.completed",
        {
            "customer": "cus_deleted_test",
            "subscription": sub_id,
            "metadata": {"tenant_id": tenant_id, "plan_id": str(paid_plan_id)},
        },
    )

    # Delete subscription
    await process_stripe_event(
        ctx,
        "evt_sub_deleted_1",
        "customer.subscription.deleted",
        {"id": sub_id},
    )

    from sqlalchemy import select

    from wxcode_adm.billing.models import SubscriptionStatus, TenantSubscription

    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        assert sub.status == SubscriptionStatus.CANCELED


async def test_webhook_idempotency(client):
    """SC3: Duplicate webhook events are processed at most once (idempotency)."""
    c, redis, app, test_db = client
    paid_plan_id = await _seed_paid_plan(test_db)
    token, _ = await _signup_verify_login(c, redis, "webhook_idempotency@test.com")
    tenant_id = await _create_workspace(c, token, "Idempotency Test")

    from wxcode_adm.billing.service import process_stripe_event

    ctx = {"session_maker": test_db}
    event_id = "evt_idempotency_same_event"

    # Process same event twice
    data_object = {
        "customer": "cus_idempotency_test",
        "subscription": "sub_idempotency_1",
        "metadata": {"tenant_id": tenant_id, "plan_id": str(paid_plan_id)},
    }
    await process_stripe_event(ctx, event_id, "checkout.session.completed", data_object)
    await process_stripe_event(ctx, event_id, "checkout.session.completed", data_object)

    # Verify only one WebhookEvent row was created
    from sqlalchemy import func, select

    from wxcode_adm.billing.models import WebhookEvent

    async with test_db() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(WebhookEvent).where(
                    WebhookEvent.stripe_event_id == event_id
                )
            )
        ).scalar_one()
        assert count == 1, f"Expected 1 WebhookEvent, got {count}"


# ---------------------------------------------------------------------------
# SC4: Customer Portal (BILL-04)
# ---------------------------------------------------------------------------


async def test_portal_returns_url(client):
    """SC4: User with billing_access can open Stripe Customer Portal."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "portal@test.com")
    tenant_id = await _create_workspace(c, token, "Portal Test")

    # Set stripe_customer_id on subscription (required for portal access)
    from sqlalchemy import select

    from wxcode_adm.billing.models import TenantSubscription

    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        sub.stripe_customer_id = "cus_test_portal"
        await session.commit()

    resp = await c.post(
        "/api/v1/billing/portal",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert resp.status_code == 200, f"Portal failed: {resp.text}"
    assert "portal_url" in resp.json()
    assert resp.json()["portal_url"] == "https://billing.stripe.com/test"


# ---------------------------------------------------------------------------
# SC5: Plan enforcement (BILL-05)
# ---------------------------------------------------------------------------


async def test_free_tier_blocked_at_quota(client):
    """SC5: Free tier tenant gets QuotaExceededError when _enforce_token_quota is called at quota."""
    c, redis, app, test_db = client

    from sqlalchemy import select

    from wxcode_adm.billing.models import Plan, TenantSubscription

    # Get the seeded free plan
    async with test_db() as session:
        free_plan = (
            await session.execute(
                select(Plan).where(Plan.monthly_fee_cents == 0, Plan.is_active.is_(True))
            )
        ).scalar_one()
        free_plan_quota = free_plan.token_quota

    token, _ = await _signup_verify_login(c, redis, "quota_test@test.com")
    tenant_id = await _create_workspace(c, token, "Quota Test")

    # Set tokens_used_this_period to quota limit
    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        sub.tokens_used_this_period = free_plan_quota  # at quota
        await session.commit()

    # Reload and verify enforcement raises QuotaExceededError
    from wxcode_adm.billing.dependencies import _enforce_token_quota
    from wxcode_adm.billing.exceptions import QuotaExceededError

    async with test_db() as session:
        plan = (
            await session.execute(
                select(Plan).where(Plan.monthly_fee_cents == 0, Plan.is_active.is_(True))
            )
        ).scalar_one()
        sub = (
            await session.execute(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == uuid.UUID(tenant_id)
                )
            )
        ).scalar_one()

        # Confirm preconditions
        assert plan.monthly_fee_cents == 0, "must be free tier"
        assert sub.tokens_used_this_period >= plan.token_quota, "must be at quota"

        # The enforcement path MUST raise QuotaExceededError for free tier at quota
        with pytest.raises(QuotaExceededError):
            _enforce_token_quota(plan, sub)


async def test_past_due_tenant_blocked_by_require_active_subscription(client):
    """SC5: past_due subscription raises PaymentRequiredError when _enforce_active_subscription fires."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "past_due_test@test.com")
    tenant_id = await _create_workspace(c, token, "Past Due Test")

    # Set subscription to past_due
    from sqlalchemy import select

    from wxcode_adm.billing.models import SubscriptionStatus, TenantSubscription

    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        sub.status = SubscriptionStatus.PAST_DUE
        await session.commit()

    # The enforcement path MUST raise PaymentRequiredError for past_due status
    from wxcode_adm.billing.dependencies import _enforce_active_subscription
    from wxcode_adm.billing.exceptions import PaymentRequiredError

    async with test_db() as session:
        sub = (
            await session.execute(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == uuid.UUID(tenant_id)
                )
            )
        ).scalar_one()

        with pytest.raises(PaymentRequiredError):
            _enforce_active_subscription(sub)


async def test_canceled_tenant_blocked_by_require_active_subscription(client):
    """SC5: canceled subscription also raises PaymentRequiredError."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "canceled_test@test.com")
    tenant_id = await _create_workspace(c, token, "Canceled Test")

    from sqlalchemy import select

    from wxcode_adm.billing.models import SubscriptionStatus, TenantSubscription

    async with test_db() as session:
        result = await session.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == uuid.UUID(tenant_id)
            )
        )
        sub = result.scalar_one()
        sub.status = SubscriptionStatus.CANCELED
        await session.commit()

    from wxcode_adm.billing.dependencies import _enforce_active_subscription
    from wxcode_adm.billing.exceptions import PaymentRequiredError

    async with test_db() as session:
        sub = (
            await session.execute(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == uuid.UUID(tenant_id)
                )
            )
        ).scalar_one()

        with pytest.raises(PaymentRequiredError):
            _enforce_active_subscription(sub)


async def test_member_cap_blocks_invitation(client):
    """SC5: Invitation blocked when at member cap.

    Sets the plan member_cap=1 (owner only) directly in DB, then verifies
    that the next invitation attempt returns 402.
    """
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "membercap_owner@test.com")
    tenant_id = await _create_workspace(c, token, "Cap Test")

    # Reduce the plan member_cap to 1 so any invitation hits the cap immediately.
    # The workspace owner is already the sole member (count=1), matching the cap.
    from sqlalchemy import select

    from wxcode_adm.billing.models import Plan, TenantSubscription

    async with test_db() as session:
        sub = (
            await session.execute(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == uuid.UUID(tenant_id)
                )
            )
        ).scalar_one()
        plan = await session.get(Plan, sub.plan_id)
        plan.member_cap = 1  # owner-only cap: next invite should fail
        await session.commit()

    # Try to invite — should get 402 (at member cap)
    resp = await c.post(
        "/api/v1/tenants/current/invitations",
        json={"email": "extra_member@test.com", "role": "developer", "billing_access": False},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert resp.status_code == 402, f"Expected 402 (member cap reached), got {resp.status_code}: {resp.text}"


async def test_subscription_status_endpoint(client):
    """SC5/SC4: GET /billing/subscription returns subscription details."""
    c, redis, app, test_db = client
    token, _ = await _signup_verify_login(c, redis, "sub_status@test.com")
    tenant_id = await _create_workspace(c, token, "Subscription Status Test")

    resp = await c.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
    )
    assert resp.status_code == 200, f"Get subscription failed: {resp.text}"
    data = resp.json()
    assert "status" in data
    assert data["status"] == "free"
    assert "plan" in data
    assert data["plan"]["monthly_fee_cents"] == 0
