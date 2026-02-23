"""
Super-admin seed function for wxcode-adm.

Called during application lifespan startup to ensure the platform operator
has admin access from day one. The seed is idempotent — running it multiple
times has no effect if the super-admin already exists.

The super-admin account is:
- email: settings.SUPER_ADMIN_EMAIL
- password: settings.SUPER_ADMIN_PASSWORD (stored as Argon2id hash)
- email_verified: True (pre-verified — no OTP flow needed)
- is_active: True
- is_superuser: True
"""

import logging

from sqlalchemy import select

from wxcode_adm.auth.models import User
from wxcode_adm.auth.password import hash_password

logger = logging.getLogger(__name__)


async def seed_super_admin(session_maker, settings) -> None:
    """
    Create the super-admin user if it does not already exist.

    Args:
        session_maker: An async SQLAlchemy session maker (async_session_maker).
        settings: The application Settings instance.

    This function is safe to call on every startup — it is a no-op if the
    super-admin account already exists.
    """
    async with session_maker() as session:
        result = await session.execute(
            select(User).where(User.email == settings.SUPER_ADMIN_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            logger.info(f"Super-admin already exists: {settings.SUPER_ADMIN_EMAIL}")
            return

        admin = User(
            email=settings.SUPER_ADMIN_EMAIL,
            password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD.get_secret_value()),
            email_verified=True,
            is_active=True,
            is_superuser=True,
        )
        session.add(admin)
        await session.commit()
        logger.info(f"Super-admin seeded: {settings.SUPER_ADMIN_EMAIL}")
