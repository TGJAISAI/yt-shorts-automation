"""Retry utilities with exponential backoff."""

import time
import random
import functools
from typing import Callable, Type, Tuple, Any
import logging

from app.core.exceptions import RateLimitError

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    jitter: bool = True
):
    """Decorator for retrying a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        exponential_base: Base for exponential backoff calculation.
        exceptions: Tuple of exception types to catch and retry.
        jitter: Whether to add random jitter to delay.

    Returns:
        Decorated function with retry logic.

    Example:
        @retry_with_backoff(max_attempts=3, base_delay=1)
        def unstable_api_call():
            # Make API call
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 0
            last_exception = None

            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    attempt += 1

                    if attempt >= max_attempts:
                        logger.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts",
                            exc_info=True
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)

                    # Add jitter to prevent thundering herd
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    # Handle rate limit errors specially
                    if isinstance(e, RateLimitError) and e.retry_after:
                        delay = max(delay, e.retry_after)

                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {str(e)}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    time.sleep(delay)

            return None

        return wrapper
    return decorator


def retry_on_condition(
    condition: Callable[[Any], bool],
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: bool = True
):
    """Decorator for retrying based on a condition.

    Args:
        condition: Function that takes the result and returns True if should retry.
        max_attempts: Maximum number of retry attempts.
        delay: Initial delay in seconds between retries.
        backoff: Whether to use exponential backoff.

    Returns:
        Decorated function with conditional retry logic.

    Example:
        @retry_on_condition(lambda result: result is None, max_attempts=3)
        def may_return_none():
            # Function that might return None
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_attempts):
                result = func(*args, **kwargs)

                if not condition(result):
                    return result

                if attempt < max_attempts - 1:
                    current_delay = delay * (2 ** attempt) if backoff else delay
                    logger.warning(
                        f"Condition not met for {func.__name__} (attempt {attempt + 1}/{max_attempts}). "
                        f"Retrying in {current_delay}s..."
                    )
                    time.sleep(current_delay)

            logger.error(f"Function {func.__name__} failed to meet condition after {max_attempts} attempts")
            return result

        return wrapper
    return decorator


class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit.
            recovery_timeout: Seconds to wait before attempting recovery.
            expected_exception: Exception type to catch.
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Call function with circuit breaker protection.

        Args:
            func: Function to call.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Function result.

        Raises:
            Exception: If circuit is open or function fails.
        """
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half_open"
                logger.info(f"Circuit breaker entering half-open state for {func.__name__}")
            else:
                raise Exception(f"Circuit breaker is open for {func.__name__}")

        try:
            result = func(*args, **kwargs)

            # Success - reset if in half-open state
            if self.state == "half_open":
                self.state = "closed"
                self.failure_count = 0
                logger.info(f"Circuit breaker closed for {func.__name__}")

            return result

        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error(
                    f"Circuit breaker opened for {func.__name__} after "
                    f"{self.failure_count} failures"
                )

            raise


def with_timeout(seconds: float):
    """Decorator to add timeout to a function (Unix only).

    Args:
        seconds: Timeout in seconds.

    Returns:
        Decorated function with timeout.

    Note:
        This uses signal.alarm() which only works on Unix systems.
    """
    import signal

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds}s")

            # Set the signal handler and alarm
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(seconds))

            try:
                result = func(*args, **kwargs)
            finally:
                # Reset the alarm and handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

            return result

        return wrapper
    return decorator
