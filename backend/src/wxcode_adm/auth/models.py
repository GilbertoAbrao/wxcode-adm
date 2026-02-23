"""
SQLAlchemy models for wxcode-adm auth domain.

The User and RefreshToken models are platform-level (not tenant-scoped).
They intentionally inherit from Base + TimestampMixin rather than TenantModel,
because authentication is a cross-cutting concern that must work before a
tenant context is established (e.g., at login time).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
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


class RefreshToken(TimestampMixin, Base):
    """
    Platform-level refresh token for JWT token rotation.

    NOT tenant-scoped — refresh tokens belong to users, which are
    platform-level entities. Each row represents an active refresh token
    that can be exchanged for a new access+refresh token pair.

    Single-session policy: all existing rows for a user are deleted on new
    login. Replay detection: consumed tokens' SHA-256 hashes are stored in
    Redis shadow keys; replaying a consumed token triggers full logout.
    """

    __tablename__ = "refresh_tokens"

    token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"RefreshToken(id={self.id!r}, user_id={self.user_id!r})"
