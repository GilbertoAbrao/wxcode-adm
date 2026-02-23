"""
arq email job functions for wxcode-adm tenant domain.

These functions are registered as arq worker jobs and called by enqueueing
them from tenant service code (invite_user). The arq worker runs as a
separate process:
    arq wxcode_adm.tasks.worker.WorkerSettings

Phase 3 behavior:
- Logs the invite link at INFO level for dev/test use.
- Attempts SMTP send via fastapi-mail if configured.
- Gracefully handles SMTP unavailability — job does NOT fail if SMTP is down.

This follows the exact same pattern as auth/email.py's send_verification_email
and send_reset_email.
"""

import logging

from wxcode_adm.config import settings

logger = logging.getLogger(__name__)


async def send_invitation_email(
    ctx: dict,
    email: str,
    tenant_name: str,
    invite_link: str,
    role: str,
) -> None:
    """
    Send a tenant invitation email with the acceptance link.

    Phase 3: Logs the invite link for dev/test access (intentional).
    Wraps actual SMTP send in try/except so the job never fails on
    SMTP misconfiguration.

    Args:
        ctx: arq job context (provided automatically by the worker).
        email: Recipient email address (the invitee).
        tenant_name: Display name of the tenant the user is being invited to.
        invite_link: Full URL for the invitation acceptance page.
        role: The role the invitee will receive upon acceptance.
    """
    # DEV: Log the invite link so it's accessible without SMTP in development
    logger.info(f"[DEV] Invitation link for {email} to join {tenant_name}: {invite_link}")

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
            subject=f"You've been invited to {tenant_name}",
            recipients=[email],
            body=(
                f"You've been invited to join {tenant_name} as {role}. "
                f"Click the link to accept: {invite_link}. "
                "This invitation expires in 7 days."
            ),
            subtype="plain",
        )
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Invitation email sent to {email} for tenant {tenant_name}")
    except Exception:
        logger.warning(
            f"Failed to send invitation email to {email} — SMTP may not be configured",
            exc_info=True,
        )
