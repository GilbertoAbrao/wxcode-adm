"""
Domain exceptions for wxcode-adm tenant domain.

All tenant exceptions inherit from common base classes (ForbiddenError,
NotFoundError, ConflictError) so they are caught by the global AppError
exception handler in main.py and translated to structured JSON responses.

Security note: TenantNotFoundError uses a single message for both "tenant
does not exist" and "user is not a member" to prevent tenant enumeration.
"""

from wxcode_adm.common.exceptions import ConflictError, ForbiddenError, NotFoundError


class NoTenantContextError(ForbiddenError):
    """
    Raised when a tenant-scoped endpoint is called without X-Tenant-ID header
    and the user has not completed workspace setup.

    HTTP 403 — user is authenticated but has no tenant context.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="TENANT_CONTEXT_REQUIRED",
            message=(
                "This endpoint requires a tenant context. Include X-Tenant-ID header "
                "or complete workspace setup at POST /api/v1/onboarding/workspace."
            ),
        )


class TenantNotFoundError(NotFoundError):
    """
    Raised when a tenant does not exist OR the user is not a member.

    Uses a single generic message for both cases to prevent tenant enumeration.
    HTTP 404.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="TENANT_NOT_FOUND",
            message="Tenant not found or you are not a member",
        )


class InsufficientRoleError(ForbiddenError):
    """
    Raised when a user's role level is below the required minimum for an action.
    HTTP 403.
    """

    def __init__(
        self,
        message: str = "You do not have the required role for this action",
    ) -> None:
        super().__init__(
            error_code="INSUFFICIENT_ROLE",
            message=message,
        )


class NotMemberError(ForbiddenError):
    """
    Raised when an operation explicitly requires confirmed membership and the
    user is not a member (distinct from TenantNotFoundError which is for
    initial tenant lookup). HTTP 403.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="NOT_MEMBER",
            message="You are not a member of this tenant",
        )


class OwnerCannotSelfDemoteError(ForbiddenError):
    """
    Raised when the owner attempts to change their own role without first
    transferring ownership. HTTP 403.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="OWNER_CANNOT_SELF_DEMOTE",
            message="Transfer ownership first before changing your own role",
        )


class OwnerCannotLeaveError(ForbiddenError):
    """
    Raised when the tenant owner attempts to leave the tenant without first
    transferring ownership. HTTP 403.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="OWNER_CANNOT_LEAVE",
            message="Transfer ownership before leaving the tenant",
        )


class InvitationAlreadyExistsError(ConflictError):
    """
    Raised when an active (not yet accepted or expired) invitation already
    exists for the same email+tenant combination. HTTP 409.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="INVITATION_ALREADY_EXISTS",
            message="An active invitation already exists for this email in this tenant",
        )


class AlreadyMemberError(ConflictError):
    """
    Raised when attempting to invite a user who is already a member of the
    tenant. HTTP 409.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="ALREADY_MEMBER",
            message="User is already a member of this tenant",
        )


class TransferAlreadyPendingError(ConflictError):
    """
    Raised when attempting to initiate an ownership transfer when one is already
    pending for the tenant. Only one transfer may be pending at a time. HTTP 409.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="TRANSFER_ALREADY_PENDING",
            message="An ownership transfer is already pending for this tenant",
        )
