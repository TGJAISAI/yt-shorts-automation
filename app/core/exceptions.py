"""Custom exceptions for the application."""


class VideoAutomationError(Exception):
    """Base exception for video automation errors."""

    def __init__(self, message: str, details: dict = None):
        """Initialize exception.

        Args:
            message: Error message.
            details: Additional error details.
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ConfigurationError(VideoAutomationError):
    """Raised when there's a configuration error."""
    pass


class APIError(VideoAutomationError):
    """Raised when API calls fail."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        """Initialize API error.

        Args:
            message: Error message.
            status_code: HTTP status code.
            response: API response data.
        """
        super().__init__(message, {"status_code": status_code, "response": response})
        self.status_code = status_code
        self.response = response


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int = None):
        """Initialize rate limit error.

        Args:
            message: Error message.
            retry_after: Seconds to wait before retrying.
        """
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ScriptGenerationError(VideoAutomationError):
    """Raised when script generation fails."""
    pass


class AudioGenerationError(VideoAutomationError):
    """Raised when audio generation fails."""
    pass


class VideoGenerationError(VideoAutomationError):
    """Raised when video generation fails."""
    pass


class VideoAPIError(APIError):
    """Raised when video generation API calls fail."""
    pass


class VideoClipError(VideoGenerationError):
    """Raised when video clip processing fails."""
    pass


class YouTubeUploadError(VideoAutomationError):
    """Raised when YouTube upload fails."""
    pass


class ValidationError(VideoAutomationError):
    """Raised when validation fails."""
    pass


class DurationExceededError(ValidationError):
    """Raised when video duration exceeds maximum allowed."""
    pass


class FileOperationError(VideoAutomationError):
    """Raised when file operations fail."""
    pass


class QuotaExceededError(APIError):
    """Raised when API quota is exceeded."""
    pass


class AuthenticationError(APIError):
    """Raised when authentication fails."""
    pass


class ResourceNotFoundError(VideoAutomationError):
    """Raised when a required resource is not found."""
    pass


class MemoryError(VideoAutomationError):
    """Raised when there's insufficient memory."""
    pass


class PipelineError(VideoAutomationError):
    """Raised when the pipeline execution fails."""

    def __init__(self, message: str, step: str = None, job_id: str = None):
        """Initialize pipeline error.

        Args:
            message: Error message.
            step: Pipeline step where error occurred.
            job_id: Job ID of the failed pipeline.
        """
        super().__init__(message, {"step": step, "job_id": job_id})
        self.step = step
        self.job_id = job_id
