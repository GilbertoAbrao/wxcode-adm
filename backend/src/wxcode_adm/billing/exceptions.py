"""
Billing domain exceptions for wxcode-adm.

All billing exceptions inherit from AppError and are caught by the global
AppError exception handler in main.py, translated to structured JSON responses
with appropriate HTTP status codes.

HTTP 402 Payment Required is used for all billing-related blocks.
"""

from wxcode_adm.common.exceptions import AppError


class PaymentRequiredError(AppError):
    """
    Raised when payment is required to continue (e.g., no active subscription).
    HTTP 402 Payment Required.
    """

    def __init__(
        self,
        error_code: str = "PAYMENT_REQUIRED",
        message: str = "Payment required",
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=402,
        )


class QuotaExceededError(AppError):
    """
    Raised when a tenant has exhausted their token quota for the period.
    HTTP 402 Payment Required (billing block, not server error).
    """

    def __init__(
        self,
        error_code: str = "TOKEN_QUOTA_EXCEEDED",
        message: str = "Token quota exceeded",
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=402,
        )


class MemberLimitError(AppError):
    """
    Raised when a tenant has reached the member cap for their plan.
    HTTP 402 Payment Required (upgrade required to add more members).
    """

    def __init__(
        self,
        error_code: str = "MEMBER_LIMIT_REACHED",
        message: str = "Member limit reached",
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=402,
        )
