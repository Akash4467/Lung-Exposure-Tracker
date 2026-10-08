"""Errors services raise. Each has a stable machine-readable `code` the app can switch on;
only the API layer turns them into HTTP status codes."""


class Retryable(Exception):
    """A temporary failure (timeout, rate limit, 5xx). The job should run again later."""


class AppError(Exception):
    code = "error"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class InvalidInput(AppError):
    code = "validation_failed"


class Unauthorized(AppError):
    code = "unauthorized"


class Forbidden(AppError):
    code = "forbidden"


class NotFound(AppError):
    code = "not_found"


class Conflict(AppError):
    code = "conflict"


class TooManyRequests(AppError):
    code = "rate_limited"

    def __init__(self, message: str, retry_after_s: int) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class TryLater(AppError):
    """The request is fine but the data isn't ready yet (e.g. first air fetch running)."""

    code = "not_ready"

    def __init__(self, message: str, retry_after_s: int = 60) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s
