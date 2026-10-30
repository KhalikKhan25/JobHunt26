"""Small bounded retry helper for transient HTTP responses."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Any, Callable

import requests

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
MAX_BACKOFF = 8.0
MAX_RETRY_AFTER = 30.0


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, min(float(value), MAX_RETRY_AFTER))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, min(delay, MAX_RETRY_AFTER))


def _backoff(attempt: int, response: requests.Response | None = None) -> float:
    if response is not None:
        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        if retry_after is not None:
            return retry_after
    return min(2.0 ** attempt, MAX_BACKOFF)


def request_with_retries(
    request: Callable[..., requests.Response], *args: Any, **kwargs: Any
) -> requests.Response:
    """Retry transient statuses and connection/time-out failures at most twice."""
    for attempt in range(MAX_ATTEMPTS):
        response = None
        try:
            response = request(*args, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            if attempt + 1 == MAX_ATTEMPTS:
                raise
        else:
            if (response.status_code not in RETRYABLE_STATUSES
                    or attempt + 1 == MAX_ATTEMPTS):
                return response
        time.sleep(_backoff(attempt, response))
    raise AssertionError("unreachable")
