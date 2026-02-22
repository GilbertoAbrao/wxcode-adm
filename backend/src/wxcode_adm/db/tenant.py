import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, event
from sqlalchemy.orm import Mapped, mapped_column

from wxcode_adm.common.exceptions import TenantIsolationError
from wxcode_adm.db.base import Base, TimestampMixin

logger = logging.getLogger(__name__)


class TenantModel(TimestampMixin, Base):
    """
    Abstract base for all tenant-scoped tables.

    Any ORM SELECT on a TenantModel subclass that does NOT set the
    `_tenant_enforced` execution option raises `TenantIsolationError`.

    Platform-wide data (plans, settings) uses tenant_id = NULL (None).
    """

    __abstract__ = True

    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        index=True,
        nullable=True,  # NULL = platform-owned data (plans, settings)
    )


class SoftDeleteMixin:
    """Add to models that need soft delete (tenants, users)."""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


# ---- Tenant isolation guard via do_orm_execute ----


def _requires_tenant_id(mapper) -> bool:
    """Return True if this mapper is a TenantModel subclass."""
    try:
        return issubclass(mapper.class_, TenantModel)
    except AttributeError:
        return False


def install_tenant_guard(session_factory) -> None:
    """
    Register the do_orm_execute event on the session class.
    Call once during app startup after async_session_maker is created.

    Raises TenantIsolationError on unguarded queries against TenantModel subclasses.

    Usage:
        install_tenant_guard(async_session_maker)
    """

    @event.listens_for(session_factory.class_.sync_session_class, "do_orm_execute")
    def _enforce_tenant_id(orm_execute_state) -> None:
        if not orm_execute_state.is_select:
            return
        # Skip relationship and column loads — they inherit context from the parent query
        if orm_execute_state.is_column_load or orm_execute_state.is_relationship_load:
            return

        for mapper in orm_execute_state.all_mappers:
            if _requires_tenant_id(mapper):
                # Check that a tenant_id filter was signalled via execution option
                # Set via: stmt.execution_options(_tenant_enforced=True)
                if not orm_execute_state.execution_options.get("_tenant_enforced"):
                    raise TenantIsolationError(
                        f"Unguarded query on TenantModel subclass '{mapper.class_.__name__}'. "
                        "All queries on tenant-scoped models must include tenant_id context. "
                        "Pass execution_options(_tenant_enforced=True) or use the TenantSession helper."
                    )
                break
