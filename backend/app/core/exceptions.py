class ExternalServiceError(Exception):
    """A safe, provider-independent external service failure."""


class AuthenticationError(ExternalServiceError):
    """The provider rejected the configured credentials."""


class RateLimitError(ExternalServiceError):
    """The provider temporarily rejected the request due to a rate limit."""


class RequestBudgetExceeded(ExternalServiceError):
    """No more external API requests are allowed for this operation."""


class InvalidProviderResponse(ExternalServiceError):
    """The provider returned an unexpected or malformed response."""
