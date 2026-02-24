"""
arq email job functions for wxcode-adm tenant domain.

These functions are registered as arq worker jobs and called by enqueueing
them from tenant service code (invite_user). The arq worker runs as a
separate process:
    arq wxcode_adm.tasks.worker.WorkerSettings

Phase 5 behavior:
- Logs the invite link at INFO level for dev/test use.
- Sends multipart HTML+plain-text email using shared FastMail singleton and
  branded Jinja2 template from templates/email/invitation.html.
- Gracefully handles SMTP unavailability — job does NOT fail if SMTP is down.

This follows the exact same pattern as auth/email.py's send_verification_email
and send_reset_email.
"""

import logging

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

    Logs the invite link for dev/test access (intentional).
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
        from fastapi_mail import MessageSchema, MessageType  # noqa: PLC0415

        from wxcode_adm.common.mail import fast_mail  # noqa: PLC0415

        message = MessageSchema(
            subject=f"You've been invited to {tenant_name} \u2014 WXCODE",
            recipients=[email],
            template_body={
                "tenant_name": tenant_name,
                "invite_link": invite_link,
                "role": role,
                "email": email,
            },
            subtype=MessageType.html,
        )
        await fast_mail.send_message(
            message,
            html_template="invitation.html",
            plain_template="invitation.txt",
        )
        logger.info(f"Invitation email sent to {email} for tenant {tenant_name}")
    except Exception:
        logger.warning(
            f"Failed to send invitation email to {email} \u2014 SMTP may not be configured",
            exc_info=True,
        )
