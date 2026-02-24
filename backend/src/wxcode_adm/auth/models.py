"""
SQLAlchemy models for wxcode-adm auth domain.

The User and RefreshToken models are platform-level (not tenant-scoped).
They intentionally inherit from Base + TimestampMixin rather than TenantModel,
because authentication is a cross-cutting concern that must work before a
tenant context is established (e.g., at login time).

Phase 6 additions:
- User.password_hash is now nullable (supports OAuth-only accounts)
- User.mfa_enabled / User.mfa_secret — TOTP MFA enrollment state
- OAuthAccount — links a User to a Google or GitHub OAuth identity
- MfaBackupCode — hashed one-time backup codes for TOTP recovery
- TrustedDevice — long-lived device trust tokens that skip MFA prompts
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wxcode_adm.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """
    Platform-level user account.

    NOT tenant-scoped — a user may belong to multiple tenants via the
    TenantMembership join table (added in Phase 3). Auth operations require
    looking up a user by email before any tenant context is known.

    password_hash is nullable to support OAuth-only users who have no password.
    mfa_enabled/mfa_secret track TOTP enrollment state (Phase 6).
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )
    # Nullable: OAuth-only users have no password (Phase 6)
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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
    # Phase 6: MFA enrollment state
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    mfa_secret: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        default=None,
    )

    # Phase 3: TenantMembership join table links users to tenants.
    # String reference avoids circular import — SQLAlchemy resolves at mapper
    # configuration time. foreign_keys disambiguates TenantMembership.user_id
    # from TenantMembership.invited_by_id (both reference users.id).
    memberships: Mapped[list["TenantMembership"]] = relationship(  # type: ignore[name-defined]
        back_populates="user",
        foreign_keys="TenantMembership.user_id",
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


class OAuthAccount(TimestampMixin, Base):
    """
    Links a User to an external OAuth identity (Google or GitHub).

    A user may have at most one OAuth account per provider (uq_oauth_accounts_user_provider).
    A given provider user ID may only belong to one local user
    (uq_oauth_accounts_provider_provider_user_id).

    Locked decision: one OAuth provider per account. Users must unlink the
    existing provider before linking a different one.
    """

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_oauth_accounts_provider_provider_user_id",
        ),
        UniqueConstraint(
            "user_id",
            "provider",
            name="uq_oauth_accounts_user_provider",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # 'google' | 'github'
    provider_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"OAuthAccount(id={self.id!r}, user_id={self.user_id!r}, "
            f"provider={self.provider!r})"
        )


class MfaBackupCode(TimestampMixin, Base):
    """
    Hashed one-time backup codes for TOTP MFA recovery.

    Generated at enrollment time; each code may only be used once
    (used_at is set when redeemed). Codes are stored as bcrypt/argon2 hashes —
    never in plain text.
    """

    __tablename__ = "mfa_backup_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    def __repr__(self) -> str:
        return f"MfaBackupCode(id={self.id!r}, user_id={self.user_id!r})"


class TrustedDevice(TimestampMixin, Base):
    """
    Long-lived device trust token that allows skipping MFA prompts.

    When a user completes MFA and opts in to device trust, a random token is
    generated and stored as a SHA-256 hash here with an expiry. On subsequent
    logins, the plain token is hashed and compared — if found and not expired,
    MFA is skipped.
    """

    __tablename__ = "trusted_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"TrustedDevice(id={self.id!r}, user_id={self.user_id!r})"
