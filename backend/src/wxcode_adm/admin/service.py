"""
Admin service module for wxcode-adm.

Contains business logic for super-admin authentication, tenant management,
and user management:

Authentication (Plan 01):
- admin_login: authenticate a super-admin user and issue admin-audience tokens
- admin_refresh: rotate an admin refresh token
- admin_logout: invalidate an admin session

Tenant management (Plan 02):
- list_tenants: paginated tenant list with plan info and member count
- get_tenant_detail: full tenant detail with subscription and member count
- suspend_tenant: set is_suspended=True and invalidate all member sessions
- reactivate_tenant: clear is_suspended flag
- soft_delete_tenant: set is_deleted=True (data retained indefinitely)

User management (Plan 03):
- search_users: paginated user search by email/name, filterable by tenant
- get_user_detail: full user profile with memberships and active sessions
- block_user: set is_blocked=True on TenantMembership (per-tenant scope)
- unblock_user: clear is_blocked on TenantMembership (per-tenant scope)
- force_password_reset: invalidate sessions, set flag, send reset email

Admin tokens carry aud="wxcode-adm-admin" and are issued ONLY to users with
is_superuser=True. The refresh token lifecycle reuses the same RefreshToken
model as regular auth (no separate table needed for Phase 8).

Audit actions:
  admin_login         — successful admin authentication
  admin_logout        — admin session termination
  suspend_tenant      — tenant suspended (with reason)
  reactivate_tenant   — tenant reactivated (with reason)
  soft_delete_tenant  — tenant soft-deleted (with reason)
  block_user          — user blocked in a specific tenant (with reason)
  unblock_user        — user unblocked in a specific tenant (with reason)
  force_password_reset — admin-initiated password reset (with reason)
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.admin.jwt import create_admin_access_token
from wxcode_adm.audit.service import write_audit
from wxcode_adm.auth.exceptions import InvalidCredentialsError, InvalidTokenError, TokenExpiredError
from wxcode_adm.auth.models import RefreshToken, User, UserSession
from wxcode_adm.auth.password import verify_password
from wxcode_adm.auth.service import blacklist_jti
from wxcode_adm.billing.models import Plan, TenantSubscription
from wxcode_adm.common.exceptions import ConflictError, NotFoundError
from wxcode_adm.config import settings
from wxcode_adm.tenants.models import Tenant, TenantMembership

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Admin authentication (Plan 01)
# ---------------------------------------------------------------------------


async def admin_login(
    db: AsyncSession,
    redis: Redis,
    email: str,
    password: str,
    client_ip: str | None,
) -> dict:
    """
    Authenticate a super-admin user and issue an admin-audience token pair.

    Steps:
    1. Look up user by email — raise InvalidCredentialsError if not found.
    2. Verify is_superuser=True — raise InvalidCredentialsError if not.
    3. Verify password — raise InvalidCredentialsError if wrong.
    4. Issue admin access token via create_admin_access_token.
    5. Create a RefreshToken row (same pattern as regular auth).
    6. Write audit log entry (admin_login action).

    Returns:
        dict with access_token and refresh_token keys.

    Raises:
        InvalidCredentialsError: user not found, not superuser, or wrong password.
    """
    # 1. Load user by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentialsError()

    # 2. Must be a super-admin — same error as wrong password to prevent enumeration
    if not user.is_superuser:
        raise InvalidCredentialsError()

    # 3. Verify password — also guards against OAuth-only accounts (no password_hash)
    if not user.password_hash or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    # 4. Issue admin-audience access token
    access_token = create_admin_access_token(str(user.id))

    # 5. Create refresh token (reuse regular RefreshToken model — no separate table)
    refresh_token_str = secrets.token_urlsafe(32)
    rt = RefreshToken(
        token=refresh_token_str,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(rt)

    # 6. Write audit log (does NOT commit — session commit is caller's responsibility)
    await write_audit(
        db,
        action="admin_login",
        resource_type="user",
        actor_id=user.id,
        ip_address=client_ip,
    )

    logger.info("Admin login: user=%s (id=%s) ip=%s", user.email, user.id, client_ip)
    return {"access_token": access_token, "refresh_token": refresh_token_str}


async def admin_refresh(
    db: AsyncSession,
    redis: Redis,
    refresh_token_str: str,
) -> dict:
    """
    Rotate an admin refresh token: consume the old one and issue a new pair.

    Steps:
    1. Find RefreshToken row by token value — raise InvalidTokenError if not found.
    2. Check expiry — raise TokenExpiredError if expired, delete the row.
    3. Delete old row, create new RefreshToken + new admin access token.
    4. Return new access_token + refresh_token.

    Note: Admin refresh does NOT do replay detection (shadow keys) to keep the
    implementation simple — admin sessions are short-lived and the IP allowlist
    provides additional protection at the login gate.

    Returns:
        dict with access_token and refresh_token keys.

    Raises:
        InvalidTokenError: token not found in DB.
        TokenExpiredError: token has passed its expiry time.
    """
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token_str)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise InvalidTokenError()

    # Check expiry — handle both timezone-aware (PostgreSQL) and naive (SQLite test) datetimes
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.delete(row)
        raise TokenExpiredError()

    # Capture user_id before deleting
    user_id = row.user_id

    # Rotation: delete old refresh token
    await db.delete(row)
    await db.flush()

    # Issue new admin access token + new refresh token
    access_token = create_admin_access_token(str(user_id))
    new_refresh_str = secrets.token_urlsafe(32)
    new_rt = RefreshToken(
        token=new_refresh_str,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(new_rt)

    logger.info("Admin token refreshed for user_id=%s", user_id)
    return {"access_token": access_token, "refresh_token": new_refresh_str}


async def admin_logout(
    db: AsyncSession,
    redis: Redis,
    refresh_token_str: str,
    access_token_jti: str,
) -> None:
    """
    Invalidate an admin session.

    Steps:
    1. Delete the RefreshToken row (idempotent — ignore if not found).
    2. Blacklist the access token JTI in Redis.
    3. Write audit log entry (admin_logout action).

    Args:
        db: async database session
        redis: Redis client
        refresh_token_str: the refresh token string to revoke
        access_token_jti: the JTI of the access token to blacklist
    """
    # 1. Delete refresh token (idempotent)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == refresh_token_str)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        actor_id = row.user_id
        await db.delete(row)
    else:
        actor_id = None

    # 2. Blacklist access token JTI
    await blacklist_jti(redis, access_token_jti)

    # 3. Write audit log
    await write_audit(
        db,
        action="admin_logout",
        resource_type="user",
        actor_id=actor_id,
    )

    logger.info("Admin logout: jti=%s", access_token_jti)


# ---------------------------------------------------------------------------
# Tenant management (Plan 02)
# ---------------------------------------------------------------------------


async def list_tenants(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
    plan_slug: str | None = None,
    status: str | None = None,
) -> tuple[list[dict], int]:
    """
    Return a paginated list of tenants with plan info and member count.

    Args:
        db: async database session
        limit: max results per page (1-100)
        offset: number of results to skip
        plan_slug: filter by Plan.slug (optional)
        status: filter by status — "active", "suspended", "deleted", or None for all

    Returns:
        Tuple of (list of tenant dicts, total count).
    """
    # Member count correlated subquery
    member_count_subq = (
        select(func.count(TenantMembership.id))
        .where(TenantMembership.tenant_id == Tenant.id)
        .correlate(Tenant)
        .scalar_subquery()
    )

    # Base filter conditions
    filters = []
    if status == "suspended":
        filters.append(Tenant.is_suspended == True)  # noqa: E712
    elif status == "deleted":
        filters.append(Tenant.is_deleted == True)  # noqa: E712
    elif status == "active":
        filters.append(Tenant.is_suspended == False)  # noqa: E712
        filters.append(Tenant.is_deleted == False)  # noqa: E712

    # Count query — must use a clean subquery base
    count_q = select(func.count()).select_from(Tenant)
    if plan_slug:
        count_q = count_q.join(
            TenantSubscription, TenantSubscription.tenant_id == Tenant.id, isouter=True
        ).join(Plan, Plan.id == TenantSubscription.plan_id, isouter=True)
        filters.append(Plan.slug == plan_slug)
    if filters:
        count_q = count_q.where(*filters)

    count_result = await db.execute(count_q)
    total = count_result.scalar_one()

    # Main query: select Tenant + member_count + plan info via outer joins
    main_q = (
        select(
            Tenant,
            member_count_subq.label("member_count"),
            Plan.name.label("plan_name"),
            Plan.slug.label("plan_slug"),
        )
        .outerjoin(TenantSubscription, TenantSubscription.tenant_id == Tenant.id)
        .outerjoin(Plan, Plan.id == TenantSubscription.plan_id)
    )
    if filters:
        main_q = main_q.where(*filters)
    main_q = main_q.order_by(Tenant.created_at.desc()).limit(limit).offset(offset)

    rows = await db.execute(main_q)
    items = []
    for row in rows:
        tenant = row[0]
        member_count = row[1]
        plan_name = row[2]
        plan_slug_val = row[3]
        items.append(
            {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "is_suspended": getattr(tenant, "is_suspended", False),
                "is_deleted": getattr(tenant, "is_deleted", False),
                "plan_name": plan_name,
                "plan_slug": plan_slug_val,
                "member_count": member_count,
                "created_at": tenant.created_at,
            }
        )

    return items, total


async def get_tenant_detail(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> dict:
    """
    Return full tenant detail including subscription info and member count.

    Args:
        db: async database session
        tenant_id: the tenant UUID to look up

    Returns:
        Dict matching TenantDetailResponse shape.

    Raises:
        NotFoundError: tenant not found.
    """
    # Load tenant
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise NotFoundError(error_code="TENANT_NOT_FOUND", message="Tenant not found")

    # Load subscription + plan (outerjoin: tenant may not have a subscription)
    sub_result = await db.execute(
        select(TenantSubscription, Plan)
        .outerjoin(Plan, Plan.id == TenantSubscription.plan_id)
        .where(TenantSubscription.tenant_id == tenant_id)
    )
    sub_row = sub_result.first()
    subscription = sub_row[0] if sub_row else None
    plan = sub_row[1] if sub_row else None

    # Count members
    count_result = await db.execute(
        select(func.count(TenantMembership.id)).where(
            TenantMembership.tenant_id == tenant_id
        )
    )
    member_count = count_result.scalar_one()

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "is_suspended": getattr(tenant, "is_suspended", False),
        "is_deleted": getattr(tenant, "is_deleted", False),
        "mfa_enforced": tenant.mfa_enforced,
        "wxcode_url": getattr(tenant, "wxcode_url", None),
        "plan_name": plan.name if plan else None,
        "plan_slug": plan.slug if plan else None,
        "subscription_status": subscription.status.value if subscription else None,
        "member_count": member_count,
        "created_at": tenant.created_at,
        "updated_at": tenant.updated_at,
    }


async def suspend_tenant(
    db: AsyncSession,
    redis: Redis,
    tenant_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
) -> Tenant:
    """
    Suspend a tenant: set is_suspended=True and invalidate all member sessions.

    Session invalidation:
    - Blacklist all UserSession.access_token_jti for members of this tenant.
    - Delete all RefreshToken rows for those users.

    Audit log entry written with action="suspend_tenant" and reason.

    Args:
        db: async database session
        redis: Redis client (for JTI blacklisting)
        tenant_id: the tenant to suspend
        reason: required reason string for audit log
        actor_id: the admin user performing the action

    Returns:
        The updated Tenant instance.

    Raises:
        NotFoundError: tenant not found.
        ConflictError: tenant is already suspended.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise NotFoundError(error_code="TENANT_NOT_FOUND", message="Tenant not found")

    if getattr(tenant, "is_suspended", False):
        raise ConflictError(
            error_code="ALREADY_SUSPENDED",
            message="Tenant is already suspended",
        )

    # Set is_suspended flag (column added by migration 007 in Plan 08-04)
    tenant.is_suspended = True

    # Get all member user IDs
    member_result = await db.execute(
        select(TenantMembership.user_id).where(TenantMembership.tenant_id == tenant_id)
    )
    user_ids = [row[0] for row in member_result.fetchall()]

    if user_ids:
        # Blacklist all active access tokens for these users
        session_result = await db.execute(
            select(UserSession.access_token_jti).where(
                UserSession.user_id.in_(user_ids)
            )
        )
        jtis = [row[0] for row in session_result.fetchall()]
        for jti in jtis:
            await blacklist_jti(redis, jti)

        # Delete all refresh tokens for these users
        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id.in_(user_ids))
        )

    # Write audit log
    await write_audit(
        db,
        action="suspend_tenant",
        resource_type="tenant",
        actor_id=actor_id,
        resource_id=str(tenant_id),
        details={"reason": reason},
    )

    logger.info(
        "Admin suspend_tenant: tenant_id=%s actor_id=%s reason=%r",
        tenant_id,
        actor_id,
        reason,
    )
    return tenant


async def reactivate_tenant(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
) -> Tenant:
    """
    Reactivate a previously suspended tenant by clearing is_suspended.

    Audit log entry written with action="reactivate_tenant" and reason.

    Args:
        db: async database session
        tenant_id: the tenant to reactivate
        reason: required reason string for audit log
        actor_id: the admin user performing the action

    Returns:
        The updated Tenant instance.

    Raises:
        NotFoundError: tenant not found.
        ConflictError: tenant is not suspended.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise NotFoundError(error_code="TENANT_NOT_FOUND", message="Tenant not found")

    if not getattr(tenant, "is_suspended", False):
        raise ConflictError(
            error_code="NOT_SUSPENDED",
            message="Tenant is not currently suspended",
        )

    # Clear is_suspended flag
    tenant.is_suspended = False

    # Write audit log
    await write_audit(
        db,
        action="reactivate_tenant",
        resource_type="tenant",
        actor_id=actor_id,
        resource_id=str(tenant_id),
        details={"reason": reason},
    )

    logger.info(
        "Admin reactivate_tenant: tenant_id=%s actor_id=%s reason=%r",
        tenant_id,
        actor_id,
        reason,
    )
    return tenant


async def soft_delete_tenant(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
) -> Tenant:
    """
    Soft-delete a tenant by setting is_deleted=True. Data is retained indefinitely.

    No session invalidation is performed — the get_tenant_context enforcement hook
    (from Plan 01) handles blocking deleted tenants on their next request.

    Audit log entry written with action="soft_delete_tenant" and reason.

    Args:
        db: async database session
        tenant_id: the tenant to soft-delete
        reason: required reason string for audit log
        actor_id: the admin user performing the action

    Returns:
        The updated Tenant instance.

    Raises:
        NotFoundError: tenant not found.
        ConflictError: tenant is already soft-deleted.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise NotFoundError(error_code="TENANT_NOT_FOUND", message="Tenant not found")

    if getattr(tenant, "is_deleted", False):
        raise ConflictError(
            error_code="ALREADY_DELETED",
            message="Tenant is already soft-deleted",
        )

    # Set is_deleted flag
    tenant.is_deleted = True

    # Write audit log
    await write_audit(
        db,
        action="soft_delete_tenant",
        resource_type="tenant",
        actor_id=actor_id,
        resource_id=str(tenant_id),
        details={"reason": reason},
    )

    logger.info(
        "Admin soft_delete_tenant: tenant_id=%s actor_id=%s reason=%r",
        tenant_id,
        actor_id,
        reason,
    )
    return tenant


# ---------------------------------------------------------------------------
# User management (Plan 03)
# ---------------------------------------------------------------------------


async def search_users(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
    q: str | None = None,
    tenant_id: uuid.UUID | None = None,
) -> tuple[list[dict], int]:
    """
    Return a paginated list of users, optionally filtered by search string and/or
    tenant membership.

    Args:
        db: async database session
        limit: max results per page (1-100)
        offset: number of results to skip
        q: case-insensitive search against email and display_name (optional)
        tenant_id: filter to users who are members of this tenant (optional)

    Returns:
        Tuple of (list of user dicts matching UserListItem, total count).
    """
    base_q = select(User)
    count_q = select(func.count()).select_from(User)

    if q:
        search_filter = or_(
            User.email.ilike(f"%{q}%"),
            User.display_name.ilike(f"%{q}%"),
        )
        base_q = base_q.where(search_filter)
        count_q = count_q.where(search_filter)

    if tenant_id is not None:
        base_q = base_q.join(
            TenantMembership, TenantMembership.user_id == User.id
        ).where(TenantMembership.tenant_id == tenant_id)
        count_q = count_q.join(
            TenantMembership, TenantMembership.user_id == User.id
        ).where(TenantMembership.tenant_id == tenant_id)

    # Total count (same filters, no limit/offset)
    count_result = await db.execute(count_q)
    total = count_result.scalar_one()

    # Paginated results
    main_q = base_q.order_by(User.created_at.desc()).limit(limit).offset(offset)
    rows = await db.execute(main_q)
    users = rows.scalars().all()

    items = [
        {
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "email_verified": u.email_verified,
            "is_active": u.is_active,
            "mfa_enabled": u.mfa_enabled,
            "created_at": u.created_at,
        }
        for u in users
    ]

    return items, total


async def get_user_detail(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """
    Return the full profile of a user, including all tenant memberships and
    active sessions.

    Args:
        db: async database session
        user_id: the user UUID to look up

    Returns:
        Dict matching UserDetailResponse shape.

    Raises:
        NotFoundError: user not found.
    """
    # Load user
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError(error_code="USER_NOT_FOUND", message="User not found")

    # Load memberships with tenant info via join
    membership_result = await db.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(TenantMembership.user_id == user_id)
    )
    memberships = []
    for m, tenant in membership_result:
        memberships.append(
            {
                "tenant_id": m.tenant_id,
                "tenant_name": tenant.name,
                "tenant_slug": tenant.slug,
                "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                "billing_access": m.billing_access,
                "is_blocked": getattr(m, "is_blocked", False),
            }
        )

    # Load active sessions
    session_result = await db.execute(
        select(UserSession).where(UserSession.user_id == user_id)
    )
    sessions = []
    for s in session_result.scalars().all():
        sessions.append(
            {
                "id": s.id,
                "device_type": s.device_type,
                "browser_name": s.browser_name,
                "ip_address": s.ip_address,
                "city": s.city,
                "last_active_at": s.last_active_at,
            }
        )

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "email_verified": user.email_verified,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "mfa_enabled": user.mfa_enabled,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "memberships": memberships,
        "sessions": sessions,
    }


async def block_user(
    db: AsyncSession,
    redis: Redis,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
) -> None:
    """
    Block a user's access to a specific tenant by setting is_blocked=True on
    their TenantMembership.

    Per-tenant scope: only this tenant is affected. The user's memberships in
    other tenants are not changed. The enforcement hook in get_tenant_context
    (Plan 01) checks is_blocked on every request, so the block takes effect
    immediately on the next request.

    No JTI blacklisting is needed for per-tenant block — the membership check
    happens every request so enforcement is immediate once is_blocked=True is set.

    Args:
        db: async database session
        redis: Redis client (reserved for future per-tenant session invalidation)
        user_id: the user to block
        tenant_id: the specific tenant to block them from
        reason: required reason string for audit log
        actor_id: the admin user performing the action

    Raises:
        NotFoundError: user is not a member of the specified tenant.
    """
    result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError(
            error_code="MEMBERSHIP_NOT_FOUND",
            message="User is not a member of the specified tenant",
        )

    # Set block flag (column added by migration 007 in Plan 08-04)
    membership.is_blocked = True

    await write_audit(
        db,
        action="block_user",
        resource_type="user",
        actor_id=actor_id,
        resource_id=str(user_id),
        tenant_id=tenant_id,
        details={"reason": reason, "tenant_id": str(tenant_id)},
    )

    logger.info(
        "Admin block_user: user_id=%s tenant_id=%s actor_id=%s reason=%r",
        user_id,
        tenant_id,
        actor_id,
        reason,
    )


async def unblock_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
) -> None:
    """
    Restore a user's access to a specific tenant by clearing is_blocked on their
    TenantMembership.

    Args:
        db: async database session
        user_id: the user to unblock
        tenant_id: the specific tenant to restore access for
        reason: required reason string for audit log
        actor_id: the admin user performing the action

    Raises:
        NotFoundError: user is not a member of the specified tenant.
    """
    result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError(
            error_code="MEMBERSHIP_NOT_FOUND",
            message="User is not a member of the specified tenant",
        )

    # Clear block flag
    membership.is_blocked = False

    await write_audit(
        db,
        action="unblock_user",
        resource_type="user",
        actor_id=actor_id,
        resource_id=str(user_id),
        tenant_id=tenant_id,
        details={"reason": reason, "tenant_id": str(tenant_id)},
    )

    logger.info(
        "Admin unblock_user: user_id=%s tenant_id=%s actor_id=%s reason=%r",
        user_id,
        tenant_id,
        actor_id,
        reason,
    )


async def force_password_reset(
    db: AsyncSession,
    redis: Redis,
    user_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID,
) -> None:
    """
    Force a password reset for a user.

    Steps:
    1. Load user — raise NotFoundError if not found.
    2. Set password_reset_required=True (enforcement hook in get_current_user from
       Plan 01 blocks API access until the user completes the reset).
    3. Invalidate all sessions: blacklist each UserSession.access_token_jti in Redis
       and delete all RefreshToken rows for this user.
    4. Send password reset email via arq job (same path as forgot_password).
    5. Write audit log entry.

    Args:
        db: async database session
        redis: Redis client (for JTI blacklisting)
        user_id: the user to force-reset
        reason: required reason string for audit log
        actor_id: the admin user performing the action

    Raises:
        NotFoundError: user not found.
    """
    # 1. Load user
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError(error_code="USER_NOT_FOUND", message="User not found")

    # 2. Set forced-reset flag (column added by migration 007 in Plan 08-04)
    user.password_reset_required = True

    # 3. Invalidate all sessions
    session_result = await db.execute(
        select(UserSession.access_token_jti).where(UserSession.user_id == user_id)
    )
    jtis = [row[0] for row in session_result.fetchall()]
    for jti in jtis:
        await blacklist_jti(redis, jti)

    # Delete all refresh tokens
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))

    # 4. Enqueue password reset email
    # Lazy import to avoid circular dependency at module load time
    from wxcode_adm.auth.service import generate_reset_token, _reset_salt  # noqa: PLC0415
    from wxcode_adm.tasks.worker import get_arq_pool  # noqa: PLC0415

    # Flush to make password_reset_required visible within the transaction
    # (generate_reset_token uses the current password_hash as salt)
    await db.flush()

    # Re-load user after flush to get current state (including any hash changes)
    await db.refresh(user)

    token = generate_reset_token(user.email, _reset_salt(user))
    reset_link = f"{settings.ALLOWED_ORIGINS[0]}/reset-password?token={token}"

    try:
        pool = await get_arq_pool()
        try:
            await pool.enqueue_job("send_reset_email", str(user.id), user.email, reset_link)
        finally:
            await pool.aclose()
    except Exception as exc:
        # Non-blocking: log the failure but do not roll back the forced-reset flag
        logger.warning(
            "force_password_reset: failed to enqueue reset email for user_id=%s: %s",
            user_id,
            exc,
        )

    # 5. Write audit log
    await write_audit(
        db,
        action="force_password_reset",
        resource_type="user",
        actor_id=actor_id,
        resource_id=str(user_id),
        details={"reason": reason},
    )

    logger.info(
        "Admin force_password_reset: user_id=%s actor_id=%s reason=%r",
        user_id,
        actor_id,
        reason,
    )
