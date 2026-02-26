"""
FastAPI tenant context dependencies for wxcode-adm.

Provides:
- get_tenant_context: resolves tenant + membership from X-Tenant-ID header
- require_role: dependency factory enforcing minimum MemberRole level
- require_tenant_member: semantic alias for get_tenant_context (any member passes)

Security design:
- Missing X-Tenant-ID raises NoTenantContextError (403 TENANT_CONTEXT_REQUIRED)
- Non-existent tenant AND non-member both raise TenantNotFoundError (404) to
  prevent tenant enumeration — callers cannot distinguish "no tenant" from
  "not a member".
- Role enforcement uses integer level comparison: membership.role.level >= required.level

Usage:
    from wxcode_adm.tenants.dependencies import get_tenant_context, require_role

    @router.get("/tenant-scoped")
    async def endpoint(ctx = Depends(require_role(MemberRole.ADMIN))):
        tenant, membership = ctx
        ...
"""

import uuid
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.auth.models import User
from wxcode_adm.common.exceptions import ForbiddenError
from wxcode_adm.dependencies import get_session
from wxcode_adm.tenants.exceptions import InsufficientRoleError, NoTenantContextError, TenantNotFoundError
from wxcode_adm.tenants.models import MemberRole, Tenant, TenantMembership


async def get_tenant_context(
    x_tenant_id: Annotated[str | None, Header()] = None,
    user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_session),
) -> tuple[Tenant, TenantMembership]:
    """
    Resolve the tenant context from the X-Tenant-ID request header.

    X-Tenant-ID may be either a UUID (tenant primary key) or a slug string.
    FastAPI automatically converts the underscore parameter name to hyphens
    for the HTTP header (X-Tenant-Id is case-insensitive in HTTP).

    Steps:
    1. Require X-Tenant-ID header — raise NoTenantContextError if absent.
    2. Try parsing as UUID; fall back to slug lookup if not a valid UUID.
    3. Query Tenant by id or slug — raise TenantNotFoundError if not found.
    4. Query TenantMembership for this user+tenant — raise TenantNotFoundError
       if not a member (same error, prevents tenant enumeration).
    5. Return (tenant, membership) tuple.

    Note: Tenant and TenantMembership are NOT TenantModel subclasses, so
    no execution_options (tenant_id context) are needed for these queries.

    Returns:
        (Tenant, TenantMembership) — the resolved tenant and membership.

    Raises:
        NoTenantContextError: X-Tenant-ID header is missing.
        TenantNotFoundError: Tenant does not exist or user is not a member.
    """
    if x_tenant_id is None:
        raise NoTenantContextError()

    # Try parsing x_tenant_id as UUID; fall back to slug if not a valid UUID
    tenant: Tenant | None = None
    try:
        tenant_uuid = uuid.UUID(x_tenant_id)
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        tenant = result.scalar_one_or_none()
    except ValueError:
        # Not a UUID — treat as slug
        result = await db.execute(select(Tenant).where(Tenant.slug == x_tenant_id))
        tenant = result.scalar_one_or_none()

    if tenant is None:
        raise TenantNotFoundError()

    # Enforcement hook: deleted tenants appear as nonexistent (Plan 08-02 sets is_deleted)
    # Direct access: column exists on model as of migration 007 (Plan 08-04)
    if tenant.is_deleted:
        raise TenantNotFoundError()

    # Enforcement hook: suspended tenants are blocked (Plan 08-02 sets is_suspended)
    # Direct access: column exists on model as of migration 007 (Plan 08-04)
    if tenant.is_suspended:
        raise ForbiddenError(
            error_code="TENANT_SUSPENDED",
            message="This tenant account has been suspended",
        )

    # Check membership — same error as missing tenant to prevent enumeration
    membership_result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == user.id,
        )
    )
    membership = membership_result.scalar_one_or_none()

    if membership is None:
        raise TenantNotFoundError()

    # Enforcement hook: blocked users within a tenant (Plan 08-03 sets is_blocked)
    # Direct access: column exists on model as of migration 007 (Plan 08-04)
    if membership.is_blocked:
        raise ForbiddenError(
            error_code="USER_BLOCKED",
            message="Your access to this tenant has been blocked",
        )

    return tenant, membership


def require_role(minimum_role: MemberRole):
    """
    Dependency factory that enforces a minimum MemberRole level.

    Returns a FastAPI dependency function (closure) that checks
    membership.role.level >= minimum_role.level.

    Usage:
        @router.patch("/admin-action")
        async def endpoint(ctx = Depends(require_role(MemberRole.ADMIN))):
            tenant, membership = ctx
            ...

    Args:
        minimum_role: The minimum MemberRole required to access the endpoint.

    Returns:
        A FastAPI dependency callable that returns (Tenant, TenantMembership).

    Raises:
        InsufficientRoleError: If the user's role level is below the minimum.
    """

    async def _inner(
        ctx: tuple[Tenant, TenantMembership] = Depends(get_tenant_context),
    ) -> tuple[Tenant, TenantMembership]:
        tenant, membership = ctx
        if membership.role.level < minimum_role.level:
            raise InsufficientRoleError(
                message=f"Requires {minimum_role.value} role or above"
            )
        return tenant, membership

    return _inner


async def require_tenant_member(
    ctx: tuple[Tenant, TenantMembership] = Depends(get_tenant_context),
) -> tuple[Tenant, TenantMembership]:
    """
    Pass-through dependency for endpoints that require any authenticated member.

    Semantically equivalent to get_tenant_context but expresses intent clearly:
    "any member is allowed" vs. "get the context". Use this instead of
    get_tenant_context directly in router depends for readability.

    Returns:
        (Tenant, TenantMembership) — the resolved tenant and membership.
    """
    return ctx
