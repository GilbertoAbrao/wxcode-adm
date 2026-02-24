"""
arq email job functions for wxcode-adm.

These functions are registered as arq worker jobs and called by enqueueing
them from API code. The arq worker runs as a separate process:
    arq wxcode_adm.tasks.worker.WorkerSettings

Phase 5 behavior:
- Logs the verification code/reset link at INFO level for dev/test use.
- Sends multipart HTML+plain-text emails using shared FastMail singleton and
  branded Jinja2 templates from templates/email/.
- Gracefully handles SMTP unavailability — job does NOT fail if SMTP is down.

This keeps the flow testable without an SMTP server in development.
"""

import logging

logger = logging.getLogger(__name__)


async def send_verification_email(
    ctx: dict, user_id: str, email: str, code: str
) -> None:
    """
    Send a verification email containing the 6-digit OTP code.

    Logs the code for dev/test access (intentional).
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
        from fastapi_mail import MessageSchema, MessageType  # noqa: PLC0415

        from wxcode_adm.common.mail import fast_mail  # noqa: PLC0415

        message = MessageSchema(
            subject="WXCODE \u2014 Verify your email",
            recipients=[email],
            template_body={"code": code, "email": email},
            subtype=MessageType.html,
        )
        await fast_mail.send_message(
            message,
            html_template="verify_email.html",
            plain_template="verify_email.txt",
        )
        logger.info(f"Verification email sent to {email}")
    except Exception:
        logger.warning(
            f"Failed to send verification email to {email} \u2014 SMTP may not be configured",
            exc_info=True,
        )


async def send_reset_email(
    ctx: dict, user_id: str, email: str, reset_link: str
) -> None:
    """
    Send a password reset email containing the reset link.

    Logs the reset link for dev/test access (intentional).
    Wraps actual SMTP send in try/except so the job never fails on
    SMTP misconfiguration.

    Args:
        ctx: arq job context (provided automatically by the worker).
        user_id: ID of the user requesting a password reset.
        email: Recipient email address.
        reset_link: Full URL for the password reset page.
    """
    # DEV: Log the link so it's accessible without SMTP in development
    logger.info(f"[DEV] Password reset link for {email}: {reset_link}")

    try:
        from fastapi_mail import MessageSchema, MessageType  # noqa: PLC0415

        from wxcode_adm.common.mail import fast_mail  # noqa: PLC0415

        message = MessageSchema(
            subject="WXCODE \u2014 Reset your password",
            recipients=[email],
            template_body={"reset_link": reset_link, "email": email},
            subtype=MessageType.html,
        )
        await fast_mail.send_message(
            message,
            html_template="reset_password.html",
            plain_template="reset_password.txt",
        )
        logger.info(f"Password reset email sent to {email}")
    except Exception:
        logger.warning(
            f"Failed to send reset email to {email} \u2014 SMTP may not be configured",
            exc_info=True,
        )
