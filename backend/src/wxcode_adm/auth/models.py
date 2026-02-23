"""
User SQLAlchemy model for wxcode-adm.

The User model is platform-level (not tenant-scoped). It intentionally
inherits from Base + TimestampMixin rather than TenantModel, because
authentication is a cross-cutting concern that must work before a tenant
context is established (e.g., at login time).
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from wxcode_adm.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """
    Platform-level user account.

    NOT tenant-scoped — a user may belong to multiple tenants via the
    TenantMembership join table (added in Phase 3). Auth operations require
    looking up a user by email before any tenant context is known.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r})"
