"""Custom exceptions used across the application."""


class DevLinkerError(Exception):
    """Base exception for application-level failures."""


class AuthorizationError(DevLinkerError):
    """Raised when a user is not allowed to execute a request."""


class RateLimitExceededError(DevLinkerError):
    """Raised when a user exceeds the configured request budget."""


class SafetyViolationError(DevLinkerError):
    """Raised when a dangerous command pattern is detected."""


class AgentExecutionError(DevLinkerError):
    """Raised when the backing agent fails to complete a run."""


class PendingApprovalNotFoundError(DevLinkerError):
    """Raised when an approval token does not exist."""
