"""Exponential backoff retry with full-jitter."""

import functools
import logging
import random
import time
from typing import Any, Callable, Tuple, Type

logger = logging.getLogger(__name__)


def retry_with_backoff(
    fn: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    operation_name: str = "",
    **kwargs,
) -> Any:
    last_exc = None
    op = operation_name or getattr(fn, "__name__", "op")
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            if jitter:
                delay = random.uniform(0, delay)
            logger.warning(
                "Retry %d/%d for '%s' after %.2fs — %s",
                attempt + 1,
                max_attempts - 1,
                op,
                delay,
                exc,
            )
            time.sleep(delay)
    raise last_exc


def retryable(
    max_attempts=3,
    base_delay=0.1,
    max_delay=30.0,
    jitter=True,
    retryable_exceptions=(Exception,),
):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return retry_with_backoff(
                fn,
                *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                retryable_exceptions=retryable_exceptions,
                operation_name=fn.__qualname__,
                **kwargs,
            )

        return wrapper

    return decorator
