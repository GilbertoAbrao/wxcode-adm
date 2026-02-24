"""
Audit log service for wxcode-adm.

Provides:
- write_audit: helper to append an audit entry within the caller's DB session/transaction
- purge_old_audit_logs: arq cron job that deletes entries older than AUDIT_LOG_RETENTION_DAYS
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from wxcode_adm.audit.models import AuditLog
from wxcode_adm.config import settings

logger = logging.getLogger(__name__)


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    actor_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Append an audit log entry within the caller's DB session/transaction.

    Does NOT commit — the caller's session commit includes this entry atomically
    with the business operation being audited.

    Args:
        db: The active async session (same session as the business operation).
        action: Short verb string describing the operation (e.g., "login", "invite_user").
        resource_type: Category of the affected resource (e.g., "user", "tenant", "plan").
        actor_id: UUID of the authenticated user performing the action. None for
                  unauthenticated operations (signup, forgot_password).
        tenant_id: UUID of the tenant context. None for platform-level operations.
        resource_id: Stringified UUID of the specific resource affected. None if not applicable.
        ip_address: Client IP address from request.client.host. None if unavailable.
        details: Additional structured context (e.g., {"email": "x@y.com", "role": "admin"}).
    """
    entry = AuditLog(
        actor_id=actor_id,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        details=details or {},
    )
    db.add(entry)


async def purge_old_audit_logs(ctx: dict) -> int:
    """
    arq cron job: delete audit log entries older than AUDIT_LOG_RETENTION_DAYS.

    Runs daily at 2:00 AM UTC (configured in WorkerSettings.cron_jobs).

    Args:
        ctx: arq worker context dict containing 'session_maker' (set in startup hook).

    Returns:
        Number of rows deleted.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
    session_maker = ctx["session_maker"]

    async with session_maker() as db:
        result = await db.execute(
            delete(AuditLog).where(AuditLog.created_at < cutoff)
        )
        await db.commit()
        deleted = result.rowcount
        logger.info(
            "purge_old_audit_logs: deleted %d rows older than %s (cutoff=%s, retention_days=%d)",
            deleted,
            cutoff.date(),
            cutoff.isoformat(),
            settings.AUDIT_LOG_RETENTION_DAYS,
        )
        return deleted
