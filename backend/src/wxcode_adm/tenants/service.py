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
- generate_invitation_token / verify_invitation_token: itsdangerous token helpers
- invite_user: creates an Invitation record and enqueues the email arq job
- accept_invitation: existing-user flow — verifies token and creates membership
- auto_join_pending_invitations: new-user flow — called by verify_email after
  email verification; joins user to all pending invitations automatically
- list_invitations: returns pending (non-accepted) invitations for a tenant
- cancel_invitation: deletes a pending invitation

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

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from itsdangerous import URLSafeTimedSerializer
from itsdangerous.exc import BadSignature, SignatureExpired
from redis.asyncio import Redis
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wxcode_adm.auth.exceptions import InvalidTokenError, TokenExpiredError
from wxcode_adm.auth.models import User
from wxcode_adm.common.exceptions import ConflictError, ForbiddenError, NotFoundError
from wxcode_adm.config import settings
from wxcode_adm.tenants.exceptions import (
    AlreadyMemberError,
    InsufficientRoleError,
    InvitationAlreadyExistsError,
    NotMemberError,
    OwnerCannotLeaveError,
    OwnerCannotSelfDemoteError,
    TransferAlreadyPendingError,
)
from wxcode_adm.tenants.models import Invitation, MemberRole, OwnershipTransfer, Tenant, TenantMembership
from wxcode_adm.tasks.worker import get_arq_pool

logger = logging.getLogger(__name__)

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

    # Bootstrap billing: Stripe Customer (best-effort) + free plan subscription.
    # Lazy import avoids circular import at module load time (same pattern as
    # auto_join_pending_invitations which lazily imports auth.service).
    from wxcode_adm.billing.service import (  # noqa: PLC0415
        bootstrap_free_subscription,
        create_stripe_customer,
    )

    stripe_customer_id = await create_stripe_customer(
        tenant_name=name,
        owner_email=user.email,
        tenant_id=tenant.id,
    )
    await bootstrap_free_subscription(db, tenant.id, stripe_customer_id)

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


# ---------------------------------------------------------------------------
# Invitation token helpers
# ---------------------------------------------------------------------------


def generate_invitation_token(email: str, tenant_id: str) -> str:
    """
    Generate a signed itsdangerous invitation token embedding email and tenant_id.

    Args:
        email: The invitee's email address.
        tenant_id: The tenant UUID as a string.

    Returns:
        A signed URL-safe token string.
    """
    return invitation_serializer.dumps({"email": email, "tenant_id": tenant_id})


def verify_invitation_token(token: str) -> dict:
    """
    Verify an itsdangerous invitation token and return its payload.

    Args:
        token: The signed token to verify.

    Returns:
        The payload dict with keys: email, tenant_id.

    Raises:
        TokenExpiredError: Token has passed the 7-day expiry.
        InvalidTokenError: Token is malformed, tampered, or has bad signature.
    """
    try:
        return invitation_serializer.loads(token, max_age=7 * 24 * 3600)
    except SignatureExpired:
        raise TokenExpiredError()
    except BadSignature:
        raise InvalidTokenError()


# ---------------------------------------------------------------------------
# Invitation service functions
# ---------------------------------------------------------------------------


async def invite_user(
    db: AsyncSession,
    redis: Redis,
    tenant: Tenant,
    membership: TenantMembership,
    body,
) -> Invitation:
    """
    Create an invitation record and enqueue the invitation email arq job.

    Requires the calling user (identified by membership) to be Admin or above.
    Raises 409 if the target email is already a member or has a pending
    non-expired invitation.

    Steps:
    1. Guard: caller must be Admin+ (defense in depth alongside require_role).
    2. Check if email is already a member of this tenant.
    3. Check for existing active (non-accepted, non-expired) invitation.
    4. Generate invitation token (itsdangerous) and compute SHA-256 hash.
    5. Create Invitation record, flush to get ID.
    6. Build invite link and enqueue send_invitation_email arq job.

    Args:
        db: Async database session.
        redis: Redis connection (for get_arq_pool — passed for future direct use).
        tenant: The resolved Tenant for the current request.
        membership: The caller's TenantMembership (provides user_id + role).
        body: InviteRequest with fields: email, role, billing_access.

    Returns:
        The created Invitation ORM instance.

    Raises:
        InsufficientRoleError: Caller's role is below ADMIN.
        AlreadyMemberError: Target email is already a tenant member.
        InvitationAlreadyExistsError: Active invitation already exists.
    """
    # 1. Guard: caller must be Admin+ (defense in depth)
    if membership.role.level < MemberRole.ADMIN.level:
        raise InsufficientRoleError(
            message="Only Admins and Owners can invite users"
        )

    # 2. Check if email is already a member
    member_result = await db.execute(
        select(TenantMembership)
        .join(User, TenantMembership.user_id == User.id)
        .where(
            User.email == body.email,
            TenantMembership.tenant_id == tenant.id,
        )
    )
    if member_result.scalar_one_or_none() is not None:
        raise AlreadyMemberError()

    # 3. Check for existing active (non-expired, non-accepted) invitation
    now = datetime.now(tz=timezone.utc)
    existing_result = await db.execute(
        select(Invitation).where(
            Invitation.email == body.email,
            Invitation.tenant_id == tenant.id,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > now,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise InvitationAlreadyExistsError()

    # 4. Generate token and hash
    token = generate_invitation_token(body.email, str(tenant.id))
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # 5. Create Invitation record
    invitation = Invitation(
        email=body.email,
        tenant_id=tenant.id,
        role=MemberRole(body.role),
        token_hash=token_hash,
        invited_by_id=membership.user_id,
        expires_at=now + timedelta(days=7),
        billing_access=body.billing_access,
    )
    db.add(invitation)
    await db.flush()

    # 6. Build invite link and enqueue email job
    invite_link = f"{settings.ALLOWED_ORIGINS[0]}/invitations/accept?token={token}"
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job(
            "send_invitation_email",
            body.email,
            tenant.name,
            invite_link,
            body.role,
        )
    finally:
        await pool.aclose()

    logger.info(
        f"Invitation created for {body.email} to tenant {tenant.name} "
        f"(id={tenant.id}) with role={body.role}"
    )
    return invitation


async def accept_invitation(
    db: AsyncSession,
    user: User,
    token: str,
) -> TenantMembership:
    """
    Accept an invitation as an existing, verified user.

    This is the EXISTING USER flow only. New users who sign up via an invitation
    link are auto-joined by auto_join_pending_invitations (called from
    auth/service.py verify_email) — they do NOT call this endpoint.

    Steps:
    1. Verify token — get payload (email, tenant_id).
    2. Confirm token email matches authenticated user's email.
    3. Look up Invitation by token_hash.
    4. Validate: not yet accepted, not expired.
    5. Check user is not already a member.
    6. Create TenantMembership with role + billing_access from invitation.
    7. Mark invitation.accepted_at.

    Args:
        db: Async database session.
        user: The authenticated, verified user accepting the invitation.
        token: The raw invitation token from the accept URL.

    Returns:
        The created TenantMembership.

    Raises:
        TokenExpiredError: Token has expired (> 7 days).
        InvalidTokenError: Token is malformed, tampered, or not found in DB.
        ForbiddenError: Token email does not match authenticated user's email.
        ConflictError: Invitation already accepted.
        AlreadyMemberError: User is already a member of this tenant.
    """
    # 1. Verify token — get payload
    payload = verify_invitation_token(token)

    # 2. Confirm token email matches authenticated user's email
    if payload.get("email") != user.email:
        raise ForbiddenError(
            error_code="INVITATION_EMAIL_MISMATCH",
            message="This invitation was sent to a different email address",
        )

    # 3. Look up Invitation by token_hash
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    inv_result = await db.execute(
        select(Invitation).where(Invitation.token_hash == token_hash)
    )
    invitation = inv_result.scalar_one_or_none()
    if invitation is None:
        raise InvalidTokenError()

    # 4. Validate: not yet accepted
    if invitation.accepted_at is not None:
        raise ConflictError(
            error_code="INVITATION_ALREADY_ACCEPTED",
            message="This invitation has already been accepted",
        )

    # 4b. Check expiry (handle timezone-naive datetimes from SQLite in tests)
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(tz=timezone.utc):
        raise TokenExpiredError()

    # 5. Check user is not already a member
    member_result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == invitation.tenant_id,
        )
    )
    if member_result.scalar_one_or_none() is not None:
        raise AlreadyMemberError()

    # 6. Create TenantMembership
    new_membership = TenantMembership(
        user_id=user.id,
        tenant_id=invitation.tenant_id,
        role=invitation.role,
        billing_access=invitation.billing_access,
        invited_by_id=invitation.invited_by_id,
    )
    db.add(new_membership)

    # 7. Mark accepted
    invitation.accepted_at = datetime.now(tz=timezone.utc)
    await db.flush()

    logger.info(
        f"Invitation accepted by {user.email} for tenant_id={invitation.tenant_id}"
    )
    return new_membership


async def auto_join_pending_invitations(
    db: AsyncSession,
    user: User,
) -> list[TenantMembership]:
    """
    Automatically join a newly-verified user to all pending invitations.

    This implements the NEW USER invitation flow per CONTEXT.md locked decision:
    "New user invitation flow: invite link -> sign-up -> email verification ->
    auto-join tenant (no separate accept step)"

    Called by auth/service.py's verify_email function AFTER setting
    email_verified=True. Runs inside the same DB transaction as verify_email.

    CRITICAL: This function MUST NOT raise exceptions. It is fault-tolerant:
    failures in individual invitation processing are caught, logged as warnings,
    and skipped. The overall verify_email always succeeds.

    Args:
        db: Async database session (shared transaction with verify_email).
        user: The newly-verified user.

    Returns:
        List of TenantMembership records created (may be empty if no pending
        invitations exist for this email — that is normal and expected).
    """
    now = datetime.now(tz=timezone.utc)

    # Query all pending (non-accepted) invitations for this email
    result = await db.execute(
        select(Invitation).where(
            Invitation.email == user.email,
            Invitation.accepted_at.is_(None),
        )
    )
    pending = result.scalars().all()

    memberships: list[TenantMembership] = []

    for inv in pending:
        try:
            # Handle timezone-naive (SQLite in tests) vs timezone-aware (PostgreSQL)
            expires_at = inv.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            # Skip expired invitations
            if expires_at <= now:
                continue

            # Check if user is already a member (idempotent)
            member_result = await db.execute(
                select(TenantMembership).where(
                    TenantMembership.user_id == user.id,
                    TenantMembership.tenant_id == inv.tenant_id,
                )
            )
            if member_result.scalar_one_or_none() is not None:
                # Already a member — skip
                continue

            # Create membership
            new_membership = TenantMembership(
                user_id=user.id,
                tenant_id=inv.tenant_id,
                role=inv.role,
                billing_access=inv.billing_access,
                invited_by_id=inv.invited_by_id,
            )
            db.add(new_membership)

            # Mark invitation as accepted
            inv.accepted_at = datetime.now(tz=timezone.utc)

            memberships.append(new_membership)

        except Exception:
            logger.warning(
                f"Failed to auto-join {user.email} to tenant_id={inv.tenant_id} "
                f"from invitation id={inv.id} — skipping",
                exc_info=True,
            )
            continue

    if memberships:
        await db.flush()

    logger.info(
        f"Auto-joined user {user.email} to {len(memberships)} tenant(s) "
        "from pending invitations"
    )
    return memberships


async def list_invitations(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[Invitation]:
    """
    Return all pending (non-accepted) invitations for a tenant.

    Includes both active and expired invitations — frontend can filter by
    expires_at. Ordered by created_at descending (newest first).

    Args:
        db: Async database session.
        tenant_id: The tenant UUID to list invitations for.

    Returns:
        List of Invitation ORM instances (may be empty).
    """
    result = await db.execute(
        select(Invitation)
        .where(
            Invitation.tenant_id == tenant_id,
            Invitation.accepted_at.is_(None),
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


async def cancel_invitation(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    invitation_id: uuid.UUID,
) -> None:
    """
    Cancel (delete) a pending invitation for a tenant.

    Args:
        db: Async database session.
        tenant_id: The tenant UUID (used to scope the lookup).
        invitation_id: The invitation UUID to cancel.

    Raises:
        NotFoundError: Invitation not found for this tenant.
        ConflictError: Invitation has already been accepted.
    """
    result = await db.execute(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.tenant_id == tenant_id,
        )
    )
    invitation = result.scalar_one_or_none()

    if invitation is None:
        raise NotFoundError(
            error_code="INVITATION_NOT_FOUND",
            message="Invitation not found",
        )

    if invitation.accepted_at is not None:
        raise ConflictError(
            error_code="INVITATION_ALREADY_ACCEPTED",
            message="Cannot cancel an accepted invitation",
        )

    await db.delete(invitation)
    logger.info(f"Invitation {invitation_id} cancelled for tenant_id={tenant_id}")
