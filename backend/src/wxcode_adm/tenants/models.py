"""
SQLAlchemy models for wxcode-adm tenant domain.

Tenant model is the workspace entity. TenantMembership is the association
object linking users to tenants with roles. Invitation stores pending
email invitations. OwnershipTransfer tracks pending ownership changes.

IMPORTANT: Tenant, TenantMembership, Invitation, and OwnershipTransfer all
inherit from Base+TimestampMixin (NOT TenantModel). The Tenant model IS the
tenant — it is not scoped to itself. TenantMembership, Invitation, and
OwnershipTransfer are scoped by foreign key to tenants.id, not by the
TenantModel base class (which is for domain data that lives inside a tenant).

Design decisions (from 03-CONTEXT.md):
- MemberRole uses native_enum=False to avoid PostgreSQL CREATE TYPE and the
  Alembic migration issues documented in RESEARCH.md pitfall #1.
- billing_access is a Boolean toggle on membership (not a role) — Owner
  decisions always include billing, others toggle explicitly.
- Invitation stores a SHA-256 hash of the itsdangerous delivery token;
  the DB record is authoritative state, the token is the delivery mechanism.
- OwnershipTransfer requires the to_user to authenticate via JWT and accept
  — no separate accept token is needed.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wxcode_adm.db.base import Base, TimestampMixin


class MemberRole(enum.Enum):
    """
    Tenant membership roles in descending privilege order.

    The `level` property enables numeric comparisons in require_role:
        membership.role.level >= required_role.level
    """

    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"

    @property
    def level(self) -> int:
        """Integer privilege level — higher = more privileged."""
        _levels = {
            MemberRole.OWNER: 4,
            MemberRole.ADMIN: 3,
            MemberRole.DEVELOPER: 2,
            MemberRole.VIEWER: 1,
        }
        return _levels[self]


class Tenant(TimestampMixin, Base):
    """
    A workspace/organization tenant.

    NOT a TenantModel subclass — this model IS the tenant. It is platform-level
    and inherits Base+TimestampMixin directly. The memberships relationship
    gives access to all members of this tenant.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    # Phase 6: whether MFA is required for all members of this tenant
    mfa_enforced: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    # Phase 7: per-tenant wxcode application URL (custom domains / whitelabel)
    wxcode_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        default=None,
    )
    # Phase 8: super-admin suspension and soft-delete flags (added by migration 007)
    is_suspended: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Phase 20: Claude and wxcode integration fields (added by migration 008)
    claude_oauth_token: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        default=None,
    )
    claude_default_model: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="sonnet",
    )
    claude_max_concurrent_sessions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )
    claude_monthly_token_budget: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    database_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    default_target_stack: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="fastapi-jinja2",
    )
    neo4j_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending_setup",
    )

    memberships: Mapped[list["TenantMembership"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Tenant(id={self.id!r}, slug={self.slug!r})"


class TenantMembership(TimestampMixin, Base):
    """
    Association object linking a User to a Tenant with a role.

    billing_access is a separate Boolean toggle — it is not embedded in the
    role. An Admin or Developer may or may not have billing access.

    native_enum=False on MemberRole columns avoids PostgreSQL enum type
    creation and the Alembic migration issues from RESEARCH.md pitfall #1.
    """

    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "tenant_id",
            name="uq_tenant_memberships_user_tenant",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MemberRole] = mapped_column(
        sqlalchemy.Enum(MemberRole, native_enum=False, length=20),
        nullable=False,
    )
    billing_access: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    # Phase 8: per-tenant user block flag (added by migration 007)
    is_blocked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    invited_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[user_id],
        back_populates="memberships",
    )
    tenant: Mapped["Tenant"] = relationship(
        back_populates="memberships",
    )

    def __repr__(self) -> str:
        return (
            f"TenantMembership(user_id={self.user_id!r}, "
            f"tenant_id={self.tenant_id!r}, role={self.role!r})"
        )


class Invitation(TimestampMixin, Base):
    """
    Pending email invitation to join a tenant.

    token_hash stores the SHA-256 hex digest of the itsdangerous delivery token.
    The DB record is the authoritative state; the token in the email is just
    the delivery mechanism.

    billing_access propagates to TenantMembership.billing_access when the
    invitation is accepted — either via POST /invitations/accept (existing users)
    or via auto_join_pending_invitations after email verification (new users).
    """

    __tablename__ = "invitations"
    __table_args__ = (
        UniqueConstraint(
            "email",
            "tenant_id",
            name="uq_invitations_email_tenant",
        ),
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MemberRole] = mapped_column(
        sqlalchemy.Enum(MemberRole, native_enum=False, length=20),
        nullable=False,
    )
    billing_access: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    tenant: Mapped["Tenant"] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"Invitation(id={self.id!r}, email={self.email!r}, tenant_id={self.tenant_id!r})"


class OwnershipTransfer(TimestampMixin, Base):
    """
    Pending ownership transfer request.

    Only one transfer may be pending per tenant at a time (unique=True on
    tenant_id). The to_user authenticates via JWT and accepts via the
    accept endpoint — no separate token needed.
    """

    __tablename__ = "ownership_transfers"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"OwnershipTransfer(id={self.id!r}, tenant_id={self.tenant_id!r}, "
            f"from={self.from_user_id!r}, to={self.to_user_id!r})"
        )
