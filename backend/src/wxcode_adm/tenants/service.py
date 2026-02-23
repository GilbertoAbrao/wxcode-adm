"""
Business logic for wxcode-adm tenant domain.

Provides:
- generate_unique_slug: generates a URL-safe slug from a workspace name,
  ensuring uniqueness against existing tenant slugs
- create_workspace: creates a Tenant and assigns the creator as Owner
- get_user_tenants: returns a user's tenant memberships with tenant details
- change_role: Owner or Admin changes a member's role (blocks Owner self-demotion)
- remove_member: Owner or Admin removes a member (preserves user account)
- leave_tenant: Member voluntarily leaves a tenant (Owner must transfer first)
- initiate_transfer: Owner initiates a two-step ownership transfer
- accept_transfer: Target member accepts the ownership transfer
- get_pending_transfer: Returns the pending transfer for a tenant, or None

Design notes:
- generate_unique_slug uses python-slugify with a 10-iteration uniqueness loop.
  The DB UNIQUE constraint on tenants.slug is the authoritative guard; this
  pre-check handles the common case efficiently without race-condition issues.
- create_workspace uses db.flush() (not db.commit()) to get the tenant.id for
  membership creation without prematurely committing — the caller's session
  lifecycle controls the final commit.
- invitation_serializer is module-level (captured at import time) and follows
  the same itsdangerous pattern as auth/service.py reset_serializer. Tests
  monkeypatch this attribute to use a test-keyed serializer.
- change_role guard ORDER: owner self-demotion check FIRST (per research
  pitfall #5), then actor privilege check, then OWNER role assignment block.
- Datetime comparisons handle timezone-naive (SQLite in tests) vs
  timezone-aware (PostgreSQL in production) by attaching utc tzinfo to naive
  datetimes — same pattern as auth/service.py refresh token expiry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from itsdangerous import URLSafeTimedSerializer
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wxcode_adm.auth.exceptions import TokenExpiredError
from wxcode_adm.auth.models import User
from wxcode_adm.common.exceptions import ConflictError
from wxcode_adm.config import settings
from wxcode_adm.tenants.exceptions import (
    InsufficientRoleError,
    NotMemberError,
    OwnerCannotLeaveError,
    OwnerCannotSelfDemoteError,
    TransferAlreadyPendingError,
)
from wxcode_adm.common.exceptions import ForbiddenError, NotFoundError
from wxcode_adm.tenants.models import MemberRole, OwnershipTransfer, Tenant, TenantMembership

# ---------------------------------------------------------------------------
# Module-level serializer (tests monkeypatch this attribute)
# ---------------------------------------------------------------------------

invitation_serializer = URLSafeTimedSerializer(
    settings.JWT_PRIVATE_KEY.get_secret_value(),
    salt="tenant-invitation",
)


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


async def generate_unique_slug(db: AsyncSession, name: str) -> str:
    """
    Generate a URL-safe slug from a workspace name, ensuring uniqueness.

    Uses python-slugify with max_length=80 to leave room for a counter suffix
    (the full slug must fit within 100 chars as defined on Tenant.slug).

    Falls back to "workspace" if the name contains only special characters.
    Tries up to 10 counter variants ({base_slug}-2, -3, ... -10). Raises
    ConflictError if all variants are taken.

    Args:
        db: Async database session.
        name: Raw workspace name from the request.

    Returns:
        A unique slug string.

    Raises:
        ConflictError: SLUG_UNAVAILABLE if all 10 variants are taken.
    """
    base_slug = slugify(name, max_length=80)
    if not base_slug:
        base_slug = "workspace"

    # First, try the base slug without a counter
    slug = base_slug
    for counter in range(1, 11):
        if counter > 1:
            slug = f"{base_slug}-{counter}"

        result = await db.execute(select(Tenant).where(Tenant.slug == slug))
        existing = result.scalar_one_or_none()
        if existing is None:
            return slug

    raise ConflictError(
        error_code="SLUG_UNAVAILABLE",
        message="Workspace name is too common, try a different one",
    )


# ---------------------------------------------------------------------------
# Workspace creation
# ---------------------------------------------------------------------------


async def create_workspace(
    db: AsyncSession,
    user: User,
    name: str,
) -> tuple[Tenant, TenantMembership]:
    """
    Create a new tenant workspace and assign the creator as Owner.

    Steps:
    1. Generate a unique slug from the workspace name.
    2. Create and flush the Tenant to obtain its primary key.
    3. Create a TenantMembership with OWNER role and billing_access=True.
    4. Flush the membership (caller's session controls final commit).

    Per user decision: tenant creation is a separate onboarding step, not
    part of sign-up. Creators receive Owner role with billing_access=True.

    Args:
        db: Async database session (caller manages commit/rollback).
        user: The authenticated, verified user creating the workspace.
        name: Workspace display name (2-255 chars, validated by schema).

    Returns:
        (Tenant, TenantMembership) — the created tenant and owner membership.
    """
    slug = await generate_unique_slug(db, name)

    tenant = Tenant(name=name, slug=slug)
    db.add(tenant)
    await db.flush()  # Obtain tenant.id without committing

    membership = TenantMembership(
        user_id=user.id,
        tenant_id=tenant.id,
        role=MemberRole.OWNER,
        billing_access=True,
    )
    db.add(membership)
    await db.flush()

    return tenant, membership


# ---------------------------------------------------------------------------
# User tenant list
# ---------------------------------------------------------------------------


async def get_user_tenants(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[dict]:
    """
    Return all tenants the user is a member of, with membership details.

    Uses selectinload to eagerly load the Tenant associated with each
    membership in a single additional query (avoids N+1).

    Args:
        db: Async database session.
        user_id: UUID of the user whose memberships to retrieve.

    Returns:
        List of dicts with keys: id, name, slug, role, billing_access.
        The 'id' is the Tenant UUID and 'role' is the MemberRole value string.
    """
    result = await db.execute(
        select(TenantMembership)
        .where(TenantMembership.user_id == user_id)
        .options(selectinload(TenantMembership.tenant))
    )
    memberships = result.scalars().all()

    return [
        {
            "id": membership.tenant.id,
            "name": membership.tenant.name,
            "slug": membership.tenant.slug,
            "role": membership.role.value,
            "billing_access": membership.billing_access,
        }
        for membership in memberships
    ]


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


async def change_role(
    db: AsyncSession,
    tenant: Tenant,
    actor: TenantMembership,
    target_user_id: uuid.UUID,
    new_role: MemberRole,
    billing_access: bool | None,
) -> TenantMembership:
    """
    Change a member's role within a tenant.

    Guard order (per research pitfall #5 — owner self-demotion checked FIRST):
    1. Fetch target membership — 404 if not found.
    2. If target IS the Owner AND target IS the actor: block self-demotion.
    3. If target IS the Owner AND actor is NOT the Owner: only Owner can touch Owner.
    4. Reject OWNER as new_role — use ownership transfer instead.
    5. Apply the role (and optional billing_access) change.

    Args:
        db: Async database session.
        tenant: The resolved Tenant object.
        actor: The TenantMembership of the user making the request.
        target_user_id: UUID of the user whose role is being changed.
        new_role: The desired new role (must not be OWNER).
        billing_access: If provided, also update billing_access toggle.

    Returns:
        The updated TenantMembership.

    Raises:
        NotFoundError: MEMBER_NOT_FOUND — target is not a member.
        OwnerCannotSelfDemoteError: Owner tried to demote themselves.
        InsufficientRoleError: Admin tried to change Owner's role.
        ForbiddenError: USE_TRANSFER — caller tried to assign OWNER via this endpoint.
    """
    # 1. Find target membership
    result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == target_user_id,
            TenantMembership.tenant_id == tenant.id,
        )
    )
    target_membership = result.scalar_one_or_none()
    if target_membership is None:
        raise NotFoundError(
            error_code="MEMBER_NOT_FOUND",
            message="Member not found in this tenant",
        )

    # 2. Owner cannot demote themselves — must transfer ownership first
    if (
        target_membership.role == MemberRole.OWNER
        and target_membership.user_id == actor.user_id
    ):
        raise OwnerCannotSelfDemoteError()

    # 3. Only the Owner can modify the Owner's membership
    if (
        target_membership.role == MemberRole.OWNER
        and actor.role != MemberRole.OWNER
    ):
        raise InsufficientRoleError(
            message="Only the Owner can change the Owner's role"
        )

    # 4. Cannot assign OWNER via change_role — use ownership transfer
    if new_role == MemberRole.OWNER:
        raise ForbiddenError(
            error_code="USE_TRANSFER",
            message="Use ownership transfer to assign Owner role",
        )

    # 5. Apply the changes
    target_membership.role = new_role
    if billing_access is not None:
        target_membership.billing_access = billing_access

    return target_membership


async def remove_member(
    db: AsyncSession,
    tenant: Tenant,
    actor: TenantMembership,
    target_user_id: uuid.UUID,
) -> None:
    """
    Remove a member from a tenant (Admin/Owner action).

    The user's account is preserved — they just lose membership in this tenant.
    Use leave_tenant for self-removal; this endpoint is for admin actions only.

    Args:
        db: Async database session.
        tenant: The resolved Tenant object.
        actor: The TenantMembership of the user making the request.
        target_user_id: UUID of the user to remove.

    Raises:
        ForbiddenError: USE_LEAVE — actor tried to remove themselves.
        NotFoundError: MEMBER_NOT_FOUND — target is not a member.
        ForbiddenError: CANNOT_REMOVE_OWNER — cannot remove the tenant Owner.
    """
    # Cannot remove yourself via this endpoint — use leave_tenant
    if target_user_id == actor.user_id:
        raise ForbiddenError(
            error_code="USE_LEAVE",
            message="Use the leave endpoint to remove yourself",
        )

    # Find target membership
    result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == target_user_id,
            TenantMembership.tenant_id == tenant.id,
        )
    )
    target_membership = result.scalar_one_or_none()
    if target_membership is None:
        raise NotFoundError(
            error_code="MEMBER_NOT_FOUND",
            message="Member not found",
        )

    # Cannot remove the Owner
    if target_membership.role == MemberRole.OWNER:
        raise ForbiddenError(
            error_code="CANNOT_REMOVE_OWNER",
            message="Cannot remove the tenant Owner",
        )

    await db.delete(target_membership)


async def leave_tenant(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Allow a member to voluntarily leave a tenant.

    The Owner cannot leave without first transferring ownership.

    Args:
        db: Async database session.
        tenant_id: UUID of the tenant to leave.
        user_id: UUID of the user leaving.

    Raises:
        NotMemberError: User is not a member of this tenant.
        OwnerCannotLeaveError: Owner must transfer ownership before leaving.
    """
    result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotMemberError()

    if membership.role == MemberRole.OWNER:
        raise OwnerCannotLeaveError()

    await db.delete(membership)


# ---------------------------------------------------------------------------
# Ownership transfer
# ---------------------------------------------------------------------------


def _normalize_expires_at(expires_at: datetime) -> datetime:
    """
    Attach UTC tzinfo to a naive datetime for safe comparison.

    SQLite stores datetimes as naive; PostgreSQL as timezone-aware.
    This follows the same pattern as auth/service.py refresh token expiry.
    """
    if expires_at.tzinfo is None:
        return expires_at.replace(tzinfo=timezone.utc)
    return expires_at


async def initiate_transfer(
    db: AsyncSession,
    tenant: Tenant,
    owner_membership: TenantMembership,
    to_user_id: uuid.UUID,
) -> OwnershipTransfer:
    """
    Initiate a two-step ownership transfer to another tenant member.

    Only the current Owner can call this. The target must already be a member.
    Only one pending (non-expired) transfer is allowed per tenant at a time.
    Expired stale transfers are cleaned up automatically.

    Args:
        db: Async database session.
        tenant: The resolved Tenant object.
        owner_membership: The TenantMembership of the requesting user (must be OWNER).
        to_user_id: UUID of the member who will receive ownership.

    Returns:
        The created OwnershipTransfer record.

    Raises:
        InsufficientRoleError: Caller is not the Owner.
        ForbiddenError: CANNOT_TRANSFER_TO_SELF — transferring to yourself.
        NotFoundError: MEMBER_NOT_FOUND — target is not a member.
        TransferAlreadyPendingError: A non-expired transfer already exists.
    """
    # Verify actor IS the Owner
    if owner_membership.role != MemberRole.OWNER:
        raise InsufficientRoleError(
            message="Only the Owner can initiate ownership transfer"
        )

    # Cannot transfer to yourself
    if to_user_id == owner_membership.user_id:
        raise ForbiddenError(
            error_code="CANNOT_TRANSFER_TO_SELF",
            message="Cannot transfer ownership to yourself",
        )

    # Verify target is a member
    result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == to_user_id,
            TenantMembership.tenant_id == tenant.id,
        )
    )
    target_membership = result.scalar_one_or_none()
    if target_membership is None:
        raise NotFoundError(
            error_code="MEMBER_NOT_FOUND",
            message="Target user is not a member of this tenant",
        )

    # Check for existing pending transfer
    now = datetime.now(tz=timezone.utc)
    existing_result = await db.execute(
        select(OwnershipTransfer).where(OwnershipTransfer.tenant_id == tenant.id)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        expires_at = _normalize_expires_at(existing.expires_at)
        if expires_at > now:
            raise TransferAlreadyPendingError()
        # Expired — delete stale record and proceed
        await db.delete(existing)
        await db.flush()

    # Create the transfer
    transfer = OwnershipTransfer(
        tenant_id=tenant.id,
        from_user_id=owner_membership.user_id,
        to_user_id=to_user_id,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=7),
    )
    db.add(transfer)
    await db.flush()

    return transfer


async def accept_transfer(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Accept a pending ownership transfer (called by the target member).

    Upon acceptance:
    - The old Owner is downgraded to Admin.
    - The accepting user is upgraded to Owner.
    - The transfer record is deleted.

    Args:
        db: Async database session.
        tenant_id: UUID of the tenant.
        user_id: UUID of the user accepting (must match transfer.to_user_id).

    Raises:
        NotFoundError: TRANSFER_NOT_FOUND — no pending transfer for this user.
        TokenExpiredError: The transfer has expired.
    """
    # Find the pending transfer for this user
    result = await db.execute(
        select(OwnershipTransfer).where(
            OwnershipTransfer.tenant_id == tenant_id,
            OwnershipTransfer.to_user_id == user_id,
        )
    )
    transfer = result.scalar_one_or_none()
    if transfer is None:
        raise NotFoundError(
            error_code="TRANSFER_NOT_FOUND",
            message="No pending ownership transfer found for you",
        )

    # Check expiry
    now = datetime.now(tz=timezone.utc)
    expires_at = _normalize_expires_at(transfer.expires_at)
    if expires_at < now:
        await db.delete(transfer)
        raise TokenExpiredError()

    # Find from_user membership (current Owner)
    from_result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == transfer.from_user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    from_membership = from_result.scalar_one_or_none()

    # Find to_user membership (new Owner)
    to_result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    to_membership = to_result.scalar_one_or_none()

    # Swap roles
    if from_membership is not None:
        from_membership.role = MemberRole.ADMIN
    if to_membership is not None:
        to_membership.role = MemberRole.OWNER

    # Delete the transfer record
    await db.delete(transfer)


async def get_pending_transfer(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> OwnershipTransfer | None:
    """
    Return the pending (non-expired) ownership transfer for a tenant.

    If a transfer exists but has expired, it is deleted and None is returned.
    If no transfer exists, None is returned.

    Args:
        db: Async database session.
        tenant_id: UUID of the tenant.

    Returns:
        OwnershipTransfer if a valid pending transfer exists, else None.
    """
    result = await db.execute(
        select(OwnershipTransfer).where(OwnershipTransfer.tenant_id == tenant_id)
    )
    transfer = result.scalar_one_or_none()
    if transfer is None:
        return None

    now = datetime.now(tz=timezone.utc)
    expires_at = _normalize_expires_at(transfer.expires_at)
    if expires_at <= now:
        await db.delete(transfer)
        return None

    return transfer
