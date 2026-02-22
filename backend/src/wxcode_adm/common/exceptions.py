"""
Domain exceptions for wxcode-adm.

These are NOT HTTPException subclasses. They represent domain-level errors
and will be caught by a FastAPI exception handler (registered in Plan 02)
that translates them to appropriate HTTP responses.

Usage:
    raise NotFoundError(error_code="USER_NOT_FOUND", message="User not found")
    raise TenantIsolationError(message="Cross-tenant access detected")
"""


class AppError(Exception):
    """Base class for all wxcode-adm domain errors."""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"status_code={self.status_code})"
        )


class NotFoundError(AppError):
    """Resource was not found."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(error_code=error_code, message=message, status_code=404)


class ForbiddenError(AppError):
    """Access to the resource is forbidden."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(error_code=error_code, message=message, status_code=403)


class ConflictError(AppError):
    """Resource conflict (e.g., duplicate email, already exists)."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(error_code=error_code, message=message, status_code=409)


class TenantIsolationError(AppError):
    """
    Raised when a cross-tenant access violation is detected.
    Always status 500 — this is a programming error, not a user error.
    """

    def __init__(self, message: str = "Tenant isolation violation detected") -> None:
        super().__init__(
            error_code="TENANT_ISOLATION_VIOLATION",
            message=message,
            status_code=500,
        )
