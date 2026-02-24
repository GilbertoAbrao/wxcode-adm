"""
AuditLog model for wxcode-adm.

This table is APPEND-ONLY — no updated_at column, no TimestampMixin.
Rows are never modified after creation; only purge_old_audit_logs deletes old rows.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wxcode_adm.db.base import Base


class AuditLog(Base):
    """
    Immutable audit log entry.

    Each row records a single write operation performed by an actor.
    No updated_at column — this table is strictly append-only.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Actor who performed the action (NULL for unauthenticated operations)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Tenant context (NULL for platform-level operations like signup/login)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # What happened (e.g., "login", "invite_user", "update_plan")
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # What kind of resource was affected (e.g., "user", "tenant", "invitation", "plan")
    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Stringified UUID of the affected resource (NULL when not applicable)
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Client IP address (IPv4 or IPv6, up to 45 chars for full IPv6 with brackets)
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )

    # Additional structured context about the operation
    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
