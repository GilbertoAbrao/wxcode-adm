"""
Pydantic v2 request and response schemas for wxcode-adm tenant domain.

Requests carry minimal required fields plus validation. Responses always use
model_config = ConfigDict(from_attributes=True) to enable ORM-to-schema
conversion.

Role validation note: InviteRequest and ChangeRoleRequest reject OWNER as a
role because Owner status is only granted at workspace creation time. Owners
transfer ownership via the dedicated transfer endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from wxcode_adm.tenants.models import MemberRole

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

_VALID_NON_OWNER_ROLES = {r.value for r in MemberRole if r != MemberRole.OWNER}
_VALID_ALL_ROLES = {r.value for r in MemberRole}


class CreateWorkspaceRequest(BaseModel):
    """Request body for POST /api/v1/onboarding/workspace."""

    name: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Workspace name must be at least 2 characters")
        if len(v) > 255:
            raise ValueError("Workspace name must be at most 255 characters")
        return v


class InviteRequest(BaseModel):
    """Request body for POST /api/v1/tenants/{tenant_id}/invitations."""

    email: EmailStr
    role: str
    billing_access: bool = False

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in _VALID_NON_OWNER_ROLES:
            raise ValueError(
                f"role must be one of {sorted(_VALID_NON_OWNER_ROLES)}. "
                "Owner role is assigned only at workspace creation."
            )
        return v


class AcceptInvitationRequest(BaseModel):
    """Request body for POST /api/v1/invitations/accept."""

    token: str


class ChangeRoleRequest(BaseModel):
    """Request body for PATCH /api/v1/tenants/{tenant_id}/members/{user_id}."""

    role: str
    billing_access: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in _VALID_NON_OWNER_ROLES:
            raise ValueError(
                f"role must be one of {sorted(_VALID_NON_OWNER_ROLES)}. "
                "Use the ownership transfer endpoint to change the Owner role."
            )
        return v


class InitiateTransferRequest(BaseModel):
    """Request body for POST /api/v1/tenants/{tenant_id}/transfer."""

    to_user_id: uuid.UUID


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TenantResponse(BaseModel):
    """Response schema for a Tenant object."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


class MembershipResponse(BaseModel):
    """Response schema for a TenantMembership with user email included."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    role: str
    billing_access: bool
    created_at: datetime


class InvitationResponse(BaseModel):
    """Response schema for a pending Invitation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


class TransferResponse(BaseModel):
    """Response schema for a pending OwnershipTransfer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    expires_at: datetime
    created_at: datetime


class WorkspaceCreatedResponse(BaseModel):
    """Response for POST /api/v1/onboarding/workspace on success."""

    tenant: TenantResponse
    membership_id: uuid.UUID
    message: str = "Workspace created successfully"


class MessageResponse(BaseModel):
    """Generic success response carrying only a human-readable message."""

    message: str


class MyTenantItem(BaseModel):
    """Single item in MyTenantsResponse.tenants list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    role: str
    billing_access: bool


class MyTenantsResponse(BaseModel):
    """Response for GET /api/v1/tenants/me — user's tenant memberships."""

    tenants: list[MyTenantItem]
