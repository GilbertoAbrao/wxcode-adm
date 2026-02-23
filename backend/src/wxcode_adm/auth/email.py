"""
arq email job functions for wxcode-adm.

These functions are registered as arq worker jobs and called by enqueueing
them from API code. The arq worker runs as a separate process:
    arq wxcode_adm.tasks.worker.WorkerSettings

Phase 2 behavior:
- Logs the verification code/reset link at INFO level for dev/test use.
- Attempts SMTP send via fastapi-mail if configured.
- Gracefully handles SMTP unavailability — job does NOT fail if SMTP is down.

This keeps the flow testable without an SMTP server in development.
"""

import logging

from wxcode_adm.config import settings

logger = logging.getLogger(__name__)


async def send_verification_email(
    ctx: dict, user_id: str, email: str, code: str
) -> None:
    """
    Send a verification email containing the 6-digit OTP code.

    Phase 2: Logs the code for dev/test access (intentional).
    Wraps actual SMTP send in try/except so the job never fails on
    SMTP misconfiguration.

    Args:
        ctx: arq job context (provided automatically by the worker).
        user_id: ID of the user requesting verification.
        email: Recipient email address.
        code: 6-digit OTP code to include in the email.
    """
    # DEV: Log the code so it's accessible without SMTP in development
    logger.info(f"[DEV] Verification code for {email}: {code}")

    try:
        from fastapi_mail import ConnectionConfig, FastMail, MessageSchema  # noqa: PLC0415

        conf = ConnectionConfig(
            MAIL_USERNAME=settings.SMTP_USER,
            MAIL_PASSWORD=settings.SMTP_PASSWORD,
            MAIL_FROM=settings.SMTP_FROM_EMAIL,
            MAIL_FROM_NAME=settings.SMTP_FROM_NAME,
            MAIL_PORT=settings.SMTP_PORT,
            MAIL_SERVER=settings.SMTP_HOST,
            MAIL_STARTTLS=settings.SMTP_TLS,
            MAIL_SSL_TLS=settings.SMTP_SSL,
            USE_CREDENTIALS=bool(settings.SMTP_USER),
        )
        message = MessageSchema(
            subject="WXCODE - Verify your email",
            recipients=[email],
            body=f"Your verification code is: {code}\n\nThis code expires in 10 minutes.",
            subtype="plain",
        )
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Verification email sent to {email}")
    except Exception:
        logger.warning(
            f"Failed to send verification email to {email} — SMTP may not be configured",
            exc_info=True,
        )


async def send_reset_email(
    ctx: dict, user_id: str, email: str, reset_link: str
) -> None:
    """
    Send a password reset email containing the reset link.

    Phase 2 stub: Logs the reset link for dev/test access.
    This function is registered now to avoid touching worker.py again in Plan 04.

    Args:
        ctx: arq job context (provided automatically by the worker).
        user_id: ID of the user requesting a password reset.
        email: Recipient email address.
        reset_link: Full URL for the password reset page.
    """
    # DEV: Log the link so it's accessible without SMTP in development
    logger.info(f"[DEV] Password reset link for {email}: {reset_link}")

    try:
        from fastapi_mail import ConnectionConfig, FastMail, MessageSchema  # noqa: PLC0415

        conf = ConnectionConfig(
            MAIL_USERNAME=settings.SMTP_USER,
            MAIL_PASSWORD=settings.SMTP_PASSWORD,
            MAIL_FROM=settings.SMTP_FROM_EMAIL,
            MAIL_FROM_NAME=settings.SMTP_FROM_NAME,
            MAIL_PORT=settings.SMTP_PORT,
            MAIL_SERVER=settings.SMTP_HOST,
            MAIL_STARTTLS=settings.SMTP_TLS,
            MAIL_SSL_TLS=settings.SMTP_SSL,
            USE_CREDENTIALS=bool(settings.SMTP_USER),
        )
        message = MessageSchema(
            subject="WXCODE - Reset your password",
            recipients=[email],
            body=f"Click the link below to reset your password:\n\n{reset_link}\n\nThis link expires in 24 hours and can only be used once.",
            subtype="plain",
        )
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Password reset email sent to {email}")
    except Exception:
        logger.warning(
            f"Failed to send reset email to {email} — SMTP may not be configured",
            exc_info=True,
        )
