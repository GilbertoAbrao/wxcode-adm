"""
Audit log router for wxcode-adm.

Provides super-admin-only access to the immutable audit trail.

audit_router: mounted at /api/v1/admin/audit-logs
  GET / — paginated, filterable list of audit log entries (super-admin only)
"""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.audit.models import AuditLog
from wxcode_adm.audit.schemas import AuditLogListResponse, AuditLogResponse
from wxcode_adm.admin.dependencies import require_admin
from wxcode_adm.auth.models import User
from wxcode_adm.dependencies import get_session

audit_router = APIRouter(prefix="/admin/audit-logs", tags=["audit"])


@audit_router.get("/", response_model=AuditLogListResponse)
async def list_audit_logs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_admin)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: Optional[str] = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    actor_id: Optional[str] = Query(default=None),
) -> AuditLogListResponse:
    """
    List audit log entries — super-admin only.

    Returns paginated, filterable audit log entries ordered by most recent first.
    Supports filtering by action, tenant_id, and actor_id.

    - Returns 403 if the authenticated user is not a super-admin.
    - Returns 200 with items list and total count.
    """
    # Build base query with optional filters
    base_query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if action is not None:
        base_query = base_query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    if tenant_id is not None:
        try:
            tenant_uuid = uuid.UUID(tenant_id)
        except ValueError:
            return AuditLogListResponse(items=[], total=0)
        base_query = base_query.where(AuditLog.tenant_id == tenant_uuid)
        count_query = count_query.where(AuditLog.tenant_id == tenant_uuid)

    if actor_id is not None:
        try:
            actor_uuid = uuid.UUID(actor_id)
        except ValueError:
            return AuditLogListResponse(items=[], total=0)
        base_query = base_query.where(AuditLog.actor_id == actor_uuid)
        count_query = count_query.where(AuditLog.actor_id == actor_uuid)

    # Execute count query for total
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Execute paginated data query
    data_query = (
        base_query
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(data_query)
    entries = result.scalars().all()

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(e) for e in entries],
        total=total,
    )
