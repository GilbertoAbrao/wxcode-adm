"""
Pydantic schemas for the audit log API.

AuditLogResponse: serializes a single AuditLog row.
AuditLogListResponse: wraps paginated results with a total count.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    """Serialized representation of a single audit log entry."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    created_at: datetime
    actor_id: Optional[uuid.UUID]
    tenant_id: Optional[uuid.UUID]
    action: str
    resource_type: str
    resource_id: Optional[str]
    ip_address: Optional[str]
    details: dict[str, Any]


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries with total count."""

    items: list[AuditLogResponse]
    total: int
