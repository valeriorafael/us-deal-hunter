import pytest
import requests
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from app.services.resilience import (
    Deadline,
    RateLimiter,
    RetryPolicy,
    compute_backoff,
    is_transient,
    retry_call,
)


class StatusError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


class StatusCodeError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status_code = status


class ResponseError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.response = type(
            "Response", (), {"status_code": status}
        )()


def make_counter(exc_factory=None, result=None):
    state = {"calls": 0, "failures": 10**9}

    def fn():
        state["calls"] += 1

        if (
            exc_factory is not None
            and state["calls"] <= state["failures"]
        ):
            raise exc_factory()

        return result if result is not None else state["calls"]

    return state, fn


# --- retry_call -------------------------------------------------


def test_retry_raises_original_exception_after_three_attempts():
    error = StatusError(503)
    state, fn = make_counter(lambda: error)
    sleeps = []

    with pytest.raises(StatusError) as raised:
        retry_call(
            fn,
            sleep=sleeps.append,
            rng=lambda: 0.5,
        )

    assert raised.value is error
    assert state["calls"] == 3
    assert len(sleeps) == 2


def test_retry_third_attempt_is_the_last_one():
    state, fn = make_counter(lambda: TimeoutError("t"))

    with pytest.raises(TimeoutError):
        retry_call(fn, sleep=lambda _: None)

    assert state["calls"] == 3


def test_retry_succeeds_on_second_attempt():
    state, fn = make_counter(
        lambda: TimeoutError("t"), result="done"
    )
    state["failures"] = 1
    sleeps = []

    outcome = retry_call(
        fn, sleep=sleeps.append, rng=lambda: 0.0
    )

    assert outcome == "done"
    assert state["calls"] == 2
    assert sleeps == [0.0]


def test_retry_does_not_sleep_after_immediate_success():
    sleeps = []

    outcome = retry_call(
        lambda: "ok", sleep=sleeps.append
    )

    assert outcome == "ok"
    assert sleeps == []


def test_retry_backoff_grows_per_attempt():
    state, fn = make_counter(lambda: TimeoutError("t"))
    sleeps = []

    with pytest.raises(TimeoutError):
        retry_call(
            fn,
            sleep=sleeps.append,
            rng=lambda: 1.0,
        )

    assert len(sleeps) == 2
    assert 0.0 <= sleeps[0] <= 1.0
    assert 0.0 <= sleeps[1] <= 2.0


def test_retry_backoff_respects_max_delay():
    policy = RetryPolicy(
        attempts=3,
        base_delay=10.0,
        multiplier=10.0,
        max_delay=5.0,
        full_jitter=False,
    )
    state, fn = make_counter(lambda: TimeoutError("t"))
    sleeps = []

    with pytest.raises(TimeoutError):
        retry_call(
            fn, policy=policy, sleep=sleeps.append
        )

    assert sleeps == [5.0, 5.0]


def test_retry_full_jitter_scales_backoff():
    policy = RetryPolicy(full_jitter=True)
    rng = lambda: 0.25

    assert compute_backoff(policy, 1, rng) == 0.25
    assert compute_backoff(policy, 2, rng) == 0.5


def test_retry_without_jitter_returns_raw_backoff():
    policy = RetryPolicy(full_jitter=False)

    assert compute_backoff(policy, 1) == 1.0
    assert compute_backoff(policy, 2) == 2.0


def test_retry_calls_on_retry_callback():
    state, fn = make_counter(lambda: TimeoutError("t"))
    seen = []

    def on_retry(attempt, exc, delay):
        seen.append((attempt, type(exc), delay))

    with pytest.raises(TimeoutError):
        retry_call(
            fn,
            sleep=lambda _: None,
            on_retry=on_retry,
        )

    assert [item[0] for item in seen] == [1, 2]
    assert all(
        item[1] is TimeoutError for item in seen
    )
    assert all(
        0.0 <= item[2] <= 2.0 for item in seen
    )


def test_retry_non_transient_runs_exactly_once():
    calls = {"count": 0}
    sleeps = []

    def fn():
        calls["count"] += 1

        raise ValueError("bad input")

    with pytest.raises(ValueError):
        retry_call(fn, sleep=sleeps.append)

    assert calls["count"] == 1
    assert sleeps == []


def test_retry_never_captures_keyboard_interrupt():
    calls = {"count": 0}

    def fn():
        calls["count"] += 1

        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        retry_call(fn, sleep=lambda _: None)

    assert calls["count"] == 1


def test_retry_rejects_attempts_below_one():
    with pytest.raises(ValueError):
        RetryPolicy(attempts=0)

    # defense in depth: retry_call validates the policy too
    policy = RetryPolicy.__new__(RetryPolicy)
    object.__setattr__(policy, "attempts", 0)

    with pytest.raises(ValueError):
        retry_call(lambda: None, policy=policy)


# --- is_transient -----------------------------------------------


def test_429_and_5xx_are_transient():
    assert is_transient(StatusError(429)) is True
    assert is_transient(StatusError(503)) is True
    assert is_transient(StatusCodeError(500)) is True
    assert is_transient(ResponseError(502)) is True


def test_4xx_client_errors_are_not_transient():
    assert is_transient(StatusError(401)) is False
    assert is_transient(StatusError(404)) is False
    assert is_transient(ResponseError(403)) is False


def test_common_network_errors_are_transient():
    assert is_transient(TimeoutError("t")) is True
    assert is_transient(ConnectionError("c")) is True
    assert is_transient(
        requests.exceptions.Timeout("t")
    ) is True
    assert is_transient(
        requests.exceptions.ConnectTimeout("t")
    ) is True
    assert is_transient(
        requests.exceptions.ReadTimeout("t")
    ) is True
    assert is_transient(
        requests.exceptions.ConnectionError("c")
    ) is True
    assert is_transient(Urllib3HTTPError("u")) is True


def test_non_network_errors_are_not_transient():
    assert is_transient(ValueError("v")) is False
    assert is_transient(AssertionError("a")) is False
    assert is_transient(NotImplementedError("n")) is False
    assert is_transient(KeyError("k")) is False
    assert is_transient(RuntimeError("r")) is False


# --- RateLimiter ------------------------------------------------


class FakeClock:
    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_first_wait_does_not_sleep():
    clock = FakeClock()
    sleeps = []
    limiter = RateLimiter(
        1.0, clock=clock, sleep=sleeps.append
    )

    limiter.wait()

    assert sleeps == []


def test_rate_limiter_second_wait_respects_interval():
    clock = FakeClock()
    sleeps = []
    limiter = RateLimiter(
        1.0, clock=clock, sleep=sleeps.append
    )

    limiter.wait()

    clock.now = 0.4
    limiter.wait()

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.6)

    clock.now = 2.0
    limiter.wait()

    assert len(sleeps) == 1


def test_rate_limiter_uses_injected_sleep_duration():
    clock = FakeClock()
    recorded = []

    def sleep(seconds):
        recorded.append(seconds)
        clock.now += seconds

    limiter = RateLimiter(
        2.5, clock=clock, sleep=sleep
    )

    limiter.wait()
    clock.now = 1.0
    limiter.wait()

    assert recorded == [1.5]


# --- Deadline ---------------------------------------------------


def test_deadline_expires_with_fake_clock():
    clock = FakeClock()
    deadline = Deadline(10.0, clock=clock)

    assert deadline.expired is False

    clock.now = 9.9
    assert deadline.expired is False

    clock.now = 10.0
    assert deadline.expired is True


def test_deadline_remaining_counts_down_and_clamps():
    clock = FakeClock()
    deadline = Deadline(10.0, clock=clock)

    assert deadline.remaining == 10.0

    clock.now = 4.0
    assert deadline.remaining == 6.0

    clock.now = 99.0
    assert deadline.remaining == 0.0


def test_deadline_default_uses_constant():
    deadline = Deadline()

    assert deadline.seconds == 110.0
    assert deadline.expired is False


def test_channel_verification_constants_match_spec():
    from app.services.resilience import (
        CHANNEL_VERIFY_MAX_AGE_SECONDS,
        CHANNEL_VERIFY_MAX_PER_RUN,
    )

    assert CHANNEL_VERIFY_MAX_AGE_SECONDS == 48 * 3600
    assert CHANNEL_VERIFY_MAX_PER_RUN == 10
