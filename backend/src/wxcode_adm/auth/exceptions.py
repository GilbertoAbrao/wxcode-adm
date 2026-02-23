"""
Auth-domain exceptions for wxcode-adm.

All auth exceptions inherit from AppError (or AuthError which inherits from
AppError), so they are caught by the global AppError exception handler in
main.py and translated to structured JSON responses.

Security note: InvalidCredentialsError uses a SINGLE message for both wrong
email and wrong password cases — this prevents user enumeration attacks.
"""

from wxcode_adm.common.exceptions import AppError


class AuthError(AppError):
    """
    Base class for authentication and authorization errors.

    Defaults to HTTP 401 Unauthorized. Subclasses may override status_code.
    """

    def __init__(
        self,
        error_code: str = "AUTH_ERROR",
        message: str = "Authentication error",
        status_code: int = 401,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status_code,
        )


class InvalidCredentialsError(AuthError):
    """
    Raised when email or password is incorrect during login.

    Deliberately uses a single generic message for both wrong-email and
    wrong-password cases to prevent user enumeration.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="AUTH_INVALID_CREDENTIALS",
            message="Invalid email or password",
            status_code=401,
        )


class TokenExpiredError(AuthError):
    """Raised when a JWT has passed its expiry time."""

    def __init__(self) -> None:
        super().__init__(
            error_code="AUTH_TOKEN_EXPIRED",
            message="Token has expired",
            status_code=401,
        )


class InvalidTokenError(AuthError):
    """Raised when a JWT is malformed, has an invalid signature, or is otherwise invalid."""

    def __init__(self) -> None:
        super().__init__(
            error_code="AUTH_INVALID_TOKEN",
            message="Invalid token",
            status_code=401,
        )


class ReplayDetectedError(AuthError):
    """
    Raised when a consumed refresh token is replayed (replay attack detected).

    Triggers full logout — all sessions for the user are revoked.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="REPLAY_DETECTED",
            message="Session compromised \u2014 all sessions revoked. Please log in again.",
            status_code=401,
        )


class EmailNotVerifiedError(AppError):
    """
    Raised when a user attempts a privileged action before verifying their email.
    HTTP 403 — user is authenticated but not yet authorized.
    """

    def __init__(
        self,
        error_code: str = "EMAIL_NOT_VERIFIED",
        message: str = "Email address not verified",
        status_code: int = 403,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=status_code,
        )


class EmailAlreadyExistsError(AppError):
    """
    Raised when attempting to register with an email that already exists.
    HTTP 409 — resource conflict.
    """

    def __init__(self) -> None:
        super().__init__(
            error_code="EMAIL_ALREADY_EXISTS",
            message="An account with this email already exists",
            status_code=409,
        )
