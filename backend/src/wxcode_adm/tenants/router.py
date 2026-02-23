"""
FastAPI routers for wxcode-adm tenant domain.

Two routers are defined:
- router: mounted at /api/v1/tenants — tenant info, members list, name updates,
  member management (change role, remove, leave) and ownership transfer
- onboarding_router: mounted at /api/v1/onboarding — workspace creation

Design decisions (from 03-CONTEXT.md):
- Workspace creation is a separate onboarding step, not part of sign-up.
- Tenant display name can be changed anytime; slug is permanent after creation.
- GET /tenants/me does NOT require X-Tenant-ID — it lists all tenants the user
  belongs to and is used before any tenant context is established.
- GET /tenants/current and PATCH /tenants/current require X-Tenant-ID header,
  resolved by the tenant context dependency chain.
- PATCH /tenants/current requires ADMIN role (not just any member).
- PATCH /members/{user_id}/role and DELETE /members/{user_id} require ADMIN role.
- POST /transfer requires OWNER role (only Owner initiates transfer).
- POST /leave and POST /transfer/accept are open to any tenant member.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wxcode_adm.auth.dependencies import require_verified
from wxcode_adm.auth.models import User
from wxcode_adm.common.exceptions import NotFoundError
from wxcode_adm.dependencies import get_session
from wxcode_adm.tenants import service
from wxcode_adm.tenants.dependencies import require_role, require_tenant_member
from wxcode_adm.tenants.models import MemberRole, Tenant, TenantMembership
from wxcode_adm.tenants.schemas import (
    ChangeRoleRequest,
    CreateWorkspaceRequest,
    InitiateTransferRequest,
    MembershipResponse,
    MessageResponse,
    MyTenantsResponse,
    TenantResponse,
    TransferResponse,
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


@router.patch(
    "/current/members/{user_id}/role",
    response_model=MembershipResponse,
    summary="Change a member's role",
    description=(
        "Changes the role (and optionally billing access) of a tenant member. "
        "Cannot assign OWNER via this endpoint — use ownership transfer. "
        "Owner cannot demote themselves without transferring ownership first. "
        "Requires ADMIN role or above."
    ),
)
async def change_member_role(
    user_id: uuid.UUID,
    body: ChangeRoleRequest,
    ctx=Depends(require_role(MemberRole.ADMIN)),
    db: AsyncSession = Depends(get_session),
) -> MembershipResponse:
    """
    PATCH /api/v1/tenants/current/members/{user_id}/role

    Requires X-Tenant-ID header and ADMIN role.
    """
    tenant, membership = ctx
    updated = await service.change_role(
        db,
        tenant,
        membership,
        user_id,
        MemberRole(body.role),
        body.billing_access,
    )
    # Look up user email for MembershipResponse (service returns membership only)
    user_result = await db.execute(
        select(User).where(User.id == updated.user_id)
    )
    user = user_result.scalar_one()
    return MembershipResponse(
        id=updated.id,
        user_id=updated.user_id,
        email=user.email,
        role=updated.role.value,
        billing_access=updated.billing_access,
        created_at=updated.created_at,
    )


@router.delete(
    "/current/members/{user_id}",
    response_model=MessageResponse,
    summary="Remove a member from the tenant",
    description=(
        "Removes a member from the tenant. The user's account is preserved — "
        "they just lose membership in this tenant and can still access other tenants. "
        "Cannot remove the Owner. Use POST /leave to remove yourself. "
        "Requires ADMIN role or above."
    ),
)
async def remove_member(
    user_id: uuid.UUID,
    ctx=Depends(require_role(MemberRole.ADMIN)),
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """
    DELETE /api/v1/tenants/current/members/{user_id}

    Requires X-Tenant-ID header and ADMIN role.
    """
    tenant, membership = ctx
    await service.remove_member(db, tenant, membership, user_id)
    return MessageResponse(message="Member removed from tenant")


@router.post(
    "/current/leave",
    response_model=MessageResponse,
    summary="Leave the current tenant",
    description=(
        "Allows the authenticated member to voluntarily leave the tenant. "
        "The Owner cannot leave without first transferring ownership. "
        "Any tenant member can use this endpoint."
    ),
)
async def leave_tenant(
    ctx=Depends(require_tenant_member),
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """
    POST /api/v1/tenants/current/leave

    Requires X-Tenant-ID header. Any member can call this to leave.
    """
    tenant, membership = ctx
    await service.leave_tenant(db, tenant.id, membership.user_id)
    return MessageResponse(message="You have left the tenant")


@router.post(
    "/current/transfer",
    response_model=TransferResponse,
    status_code=201,
    summary="Initiate ownership transfer",
    description=(
        "Initiates a two-step ownership transfer to another tenant member. "
        "The target member must accept the transfer within 7 days. "
        "Only one pending transfer per tenant is allowed at a time. "
        "Requires OWNER role."
    ),
)
async def initiate_transfer(
    body: InitiateTransferRequest,
    ctx=Depends(require_role(MemberRole.OWNER)),
    db: AsyncSession = Depends(get_session),
) -> TransferResponse:
    """
    POST /api/v1/tenants/current/transfer

    Requires X-Tenant-ID header and OWNER role. Creates a pending transfer.
    """
    tenant, membership = ctx
    transfer = await service.initiate_transfer(db, tenant, membership, body.to_user_id)
    return TransferResponse.model_validate(transfer)


@router.post(
    "/current/transfer/accept",
    response_model=MessageResponse,
    summary="Accept a pending ownership transfer",
    description=(
        "Accepts a pending ownership transfer directed at the authenticated user. "
        "Upon acceptance, the old Owner is downgraded to Admin and the accepting "
        "user becomes the new Owner. Any member who receives a transfer can accept. "
        "Requires X-Tenant-ID header."
    ),
)
async def accept_transfer(
    ctx=Depends(require_tenant_member),
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """
    POST /api/v1/tenants/current/transfer/accept

    Requires X-Tenant-ID header. User must be the transfer target.
    """
    tenant, membership = ctx
    await service.accept_transfer(db, tenant.id, membership.user_id)
    return MessageResponse(message="Ownership transferred successfully")


@router.get(
    "/current/transfer",
    response_model=TransferResponse,
    summary="Get pending ownership transfer",
    description=(
        "Returns the pending (non-expired) ownership transfer for this tenant. "
        "Returns 404 if no transfer is pending. "
        "Requires OWNER role."
    ),
)
async def get_pending_transfer(
    ctx=Depends(require_role(MemberRole.OWNER)),
    db: AsyncSession = Depends(get_session),
) -> TransferResponse:
    """
    GET /api/v1/tenants/current/transfer

    Requires X-Tenant-ID header and OWNER role.
    """
    tenant, _ = ctx
    transfer = await service.get_pending_transfer(db, tenant.id)
    if transfer is None:
        raise NotFoundError(
            error_code="TRANSFER_NOT_FOUND",
            message="No pending ownership transfer for this tenant",
        )
    return TransferResponse.model_validate(transfer)


# ---------------------------------------------------------------------------
# UpdateTenantRequest (defined locally to keep schemas.py clean for Plan 03-03)
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field  # noqa: E402


class UpdateTenantRequest(BaseModel):
    """Request body for PATCH /api/v1/tenants/current."""

    name: str = Field(min_length=2, max_length=255)
