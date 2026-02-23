"""
FastAPI routers for wxcode-adm tenant domain.

Two routers are defined:
- router: mounted at /api/v1/tenants — tenant info, members list, name updates
- onboarding_router: mounted at /api/v1/onboarding — workspace creation

Design decisions (from 03-CONTEXT.md):
- Workspace creation is a separate onboarding step, not part of sign-up.
- Tenant display name can be changed anytime; slug is permanent after creation.
- GET /tenants/me does NOT require X-Tenant-ID — it lists all tenants the user
  belongs to and is used before any tenant context is established.
- GET /tenants/current and PATCH /tenants/current require X-Tenant-ID header,
  resolved by the tenant context dependency chain.
- PATCH /tenants/current requires ADMIN role (not just any member).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.auth.models import User
from wxcode_adm.dependencies import get_session
from wxcode_adm.tenants import service
from wxcode_adm.tenants.dependencies import require_role, require_tenant_member
from wxcode_adm.tenants.models import MemberRole, Tenant, TenantMembership
from wxcode_adm.tenants.schemas import (
    CreateWorkspaceRequest,
    MyTenantsResponse,
    TenantResponse,
    WorkspaceCreatedResponse,
)

# ---------------------------------------------------------------------------
# Onboarding router — mounted at /api/v1/onboarding (no /tenants prefix)
# ---------------------------------------------------------------------------

onboarding_router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@onboarding_router.post(
    "/workspace",
    response_model=WorkspaceCreatedResponse,
    status_code=201,
    summary="Create a new workspace",
    description=(
        "Creates a workspace (tenant) for the authenticated user. "
        "The user is automatically assigned as Owner with billing access. "
        "A permanent URL-safe slug is generated from the workspace name."
    ),
)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_session),
) -> WorkspaceCreatedResponse:
    """
    POST /api/v1/onboarding/workspace

    Creates a new tenant and assigns the creator as Owner.

    Returns:
        WorkspaceCreatedResponse with tenant details and membership_id.
    """
    tenant, membership = await service.create_workspace(db, user, body.name)
    return WorkspaceCreatedResponse(
        tenant=TenantResponse.model_validate(tenant),
        membership_id=membership.id,
    )


# ---------------------------------------------------------------------------
# Tenant router — mounted at /api/v1/tenants
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get(
    "/me",
    response_model=MyTenantsResponse,
    summary="List user's tenant memberships",
    description=(
        "Returns all tenants the authenticated user belongs to. "
        "Does NOT require X-Tenant-ID header — used before tenant context is established."
    ),
)
async def list_my_tenants(
    user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_session),
) -> MyTenantsResponse:
    """
    GET /api/v1/tenants/me

    Returns the user's list of tenant memberships without requiring
    a tenant context header.
    """
    tenants = await service.get_user_tenants(db, user.id)
    return MyTenantsResponse(tenants=tenants)


@router.get(
    "/current",
    response_model=TenantResponse,
    summary="Get current tenant info",
    description=(
        "Returns the tenant resolved from the X-Tenant-ID header. "
        "Requires the user to be a member of the specified tenant."
    ),
)
async def get_current_tenant(
    ctx=Depends(require_tenant_member),
) -> TenantResponse:
    """
    GET /api/v1/tenants/current

    Requires X-Tenant-ID header. Returns info for the current tenant.
    """
    tenant, membership = ctx
    return TenantResponse.model_validate(tenant)


@router.patch(
    "/current",
    response_model=TenantResponse,
    summary="Update current tenant display name",
    description=(
        "Updates the tenant's display name. Slug is permanent and cannot be changed. "
        "Requires ADMIN role or above."
    ),
)
async def update_current_tenant(
    body: "UpdateTenantRequest",
    ctx=Depends(require_role(MemberRole.ADMIN)),
    db: AsyncSession = Depends(get_session),
) -> TenantResponse:
    """
    PATCH /api/v1/tenants/current

    Requires X-Tenant-ID header and ADMIN role. Updates tenant display name.
    Per user decision: display name can be changed anytime; slug is permanent.
    """
    tenant, membership = ctx
    tenant.name = body.name
    db.add(tenant)
    await db.flush()
    return TenantResponse.model_validate(tenant)


@router.get(
    "/current/members",
    summary="List current tenant members",
    description=(
        "Returns all members of the current tenant with their roles and billing access. "
        "Any tenant member can view the member list."
    ),
)
async def list_members(
    ctx=Depends(require_tenant_member),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """
    GET /api/v1/tenants/current/members

    Requires X-Tenant-ID header. Returns list of member dicts with user email.
    """
    tenant, _ = ctx

    result = await db.execute(
        select(TenantMembership)
        .where(TenantMembership.tenant_id == tenant.id)
        .options(selectinload(TenantMembership.user))
    )
    memberships = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "user_id": str(m.user_id),
            "email": m.user.email,
            "role": m.role.value,
            "billing_access": m.billing_access,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in memberships
    ]


# ---------------------------------------------------------------------------
# UpdateTenantRequest (defined locally to keep schemas.py clean for Plan 03-03)
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field  # noqa: E402


class UpdateTenantRequest(BaseModel):
    """Request body for PATCH /api/v1/tenants/current."""

    name: str = Field(min_length=2, max_length=255)
