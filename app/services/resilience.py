"""Generic resilience primitives for Phase 3 (robustness).

Contains the retry policy with exponential backoff and jitter,
the transient-exception classifier, a rate limiter and a run
deadline. All time sources are injectable so tests never sleep
for real.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import requests
from urllib3.exceptions import HTTPError as Urllib3HTTPError

# Single place for the Phase 3 timing defaults. No CLI flag is
# introduced for any of them (spec invariant I3).
AMAZON_RETRY_ATTEMPTS = 3
AMAZON_RETRY_BASE_DELAY = 1.0
AMAZON_RETRY_MULTIPLIER = 2.0
AMAZON_RETRY_MAX_DELAY = 5.0

AMAZON_MIN_INTERVAL_SECONDS = 1.0
DEFAULT_RUN_DEADLINE_SECONDS = 110.0
STALE_ATTEMPT_SECONDS = 600

# Channel verification window (phase 4): only attempts older than
# the stale threshold are probed, and never rows older than 48h.
CHANNEL_VERIFY_MAX_AGE_SECONDS = 48 * 3600
CHANNEL_VERIFY_MAX_PER_RUN = 10

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """attempts is the TOTAL number of calls (attempts >= 3 per
    MASTER_SPEC 9.5)."""

    attempts: int = AMAZON_RETRY_ATTEMPTS
    base_delay: float = AMAZON_RETRY_BASE_DELAY
    multiplier: float = AMAZON_RETRY_MULTIPLIER
    max_delay: float = AMAZON_RETRY_MAX_DELAY
    full_jitter: bool = True

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError(
                "attempts must be at least 1."
            )


AMAZON_RETRY_POLICY = RetryPolicy()


def _status_code(exc: BaseException) -> int | None:
    for attribute in ("status", "status_code"):
        value = getattr(exc, attribute, None)

        if isinstance(value, int) and not isinstance(value, bool):
            return value

    # requests.HTTPError keeps the code on the response. 429 and
    # 5xx are transient regardless of how the error was wrapped
    # (MASTER_SPEC 9.5).
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    return None


def is_transient(exc: BaseException) -> bool:
    """True only for failures that are safe to retry.

    Everything else (4xx except 429, auth errors,
    NotImplementedError, ValueError, parsing bugs, AssertionError,
    SQLite errors, ...) is raised immediately.
    """
    if isinstance(
        exc,
        (
            TimeoutError,
            ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            Urllib3HTTPError,
        ),
    ):
        return True

    status = _status_code(exc)

    if status is None:
        return False

    return status == 429 or 500 <= status <= 599


def compute_backoff(
    policy: RetryPolicy,
    failed_attempt: int,
    rng: Callable[[], float] = random.random,
) -> float:
    """Delay before retrying after ``failed_attempt`` (1-based).

    attempt 1 -> U(0, base), attempt 2 -> U(0, 2 * base), always
    capped by max_delay. With full_jitter disabled the raw
    exponential backoff is returned.
    """
    backoff = min(
        policy.base_delay
        * (policy.multiplier ** (failed_attempt - 1)),
        policy.max_delay,
    )

    if policy.full_jitter:
        return rng() * backoff

    return backoff


def retry_call(
    fn: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    should_retry: Callable[
        [BaseException], bool
    ] = is_transient,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
    on_retry: Callable[
        [int, BaseException, float], None
    ] | None = None,
) -> T:
    """Run ``fn`` retrying transient failures.

    Re-raises the last exception when attempts are exhausted and
    re-raises non-transient exceptions immediately. Only
    ``Exception`` is ever caught (never KeyboardInterrupt or
    SystemExit).
    """
    policy = policy or RetryPolicy()

    if policy.attempts < 1:
        raise ValueError("attempts must be at least 1.")

    attempt = 1

    while True:
        try:
            return fn()
        except Exception as exc:
            if (
                attempt >= policy.attempts
                or not should_retry(exc)
            ):
                raise

            delay = compute_backoff(policy, attempt, rng)

            if on_retry is not None:
                on_retry(attempt, exc, delay)

            sleep(delay)

            attempt += 1


class RateLimiter:
    """Enforces a minimum interval between two operations."""

    def __init__(
        self,
        min_interval: float = AMAZON_MIN_INTERVAL_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()

        if self._last is None:
            self._last = now

            return

        remaining = self.min_interval - (now - self._last)

        if remaining <= 0:
            self._last = now

            return

        self._sleep(remaining)

        self._last = self._clock()


class Deadline:
    """Cooperative time budget for one run."""

    def __init__(
        self,
        seconds: float = DEFAULT_RUN_DEADLINE_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.seconds = seconds
        self._clock = clock
        self._started_at = clock()

    @property
    def elapsed(self) -> float:
        return self._clock() - self._started_at

    @property
    def expired(self) -> bool:
        return self.elapsed >= self.seconds

    @property
    def remaining(self) -> float:
        return max(0.0, self.seconds - self.elapsed)
