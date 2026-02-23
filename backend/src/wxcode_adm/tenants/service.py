"""
Business logic for wxcode-adm tenant domain.

Provides:
- generate_unique_slug: generates a URL-safe slug from a workspace name,
  ensuring uniqueness against existing tenant slugs
- create_workspace: creates a Tenant and assigns the creator as Owner
- get_user_tenants: returns a user's tenant memberships with tenant details

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
"""

import uuid

from itsdangerous import URLSafeTimedSerializer
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wxcode_adm.auth.models import User
from wxcode_adm.common.exceptions import ConflictError
from wxcode_adm.config import settings
from wxcode_adm.tenants.models import MemberRole, Tenant, TenantMembership

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
