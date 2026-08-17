import asyncio
import random
import time
from enum import Enum
from functools import wraps
from typing import Callable, Any, TypeVar, ParamSpec

T = TypeVar("T")
P = ParamSpec("P")

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreakerOpenException(Exception):
    """Raised when the circuit breaker is OPEN and fails fast."""
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()

    def __call__(self, func: Callable[P, Any]) -> Callable[P, Any]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_state_change > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerOpenException("Circuit is OPEN. Failing fast.")
            try:
                res = await func(*args, **kwargs)
                if self.state == CircuitState.HALF_OPEN:
                    self.record_success()
                return res
            except Exception as e:
                self.record_failure()
                raise e
        return wrapper


def retry_with_backoff(
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    jitter: bool = True,
) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """Decorator/helper to retry an async function with exponential backoff and optional jitter."""
    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            delay = initial_delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        raise e
                    sleep_time = delay
                    if jitter:
                        sleep_time = delay * random.uniform(0.5, 1.5)
                    await asyncio.sleep(sleep_time)
                    delay *= backoff_factor
        return wrapper
    return decorator
