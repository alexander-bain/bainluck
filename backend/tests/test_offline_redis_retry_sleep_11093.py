"""The opt-in optimization preserves actual Redis retry-loop behavior."""

import pytest
from redis.asyncio.retry import Retry as AsyncRetry
from redis.backoff import EqualJitterBackoff
from redis.exceptions import ConnectionError, TimeoutError
from redis.retry import Retry

_PRODUCTION_COMPUTE = EqualJitterBackoff.compute


@pytest.mark.parametrize("error_type", [ConnectionError, TimeoutError])
@pytest.mark.parametrize("retries", [1, 3])
@pytest.mark.parametrize("recover", [False, True])
def test_sync_attempts_callbacks_and_original_error(
    offline_redis_no_retry_sleep, monkeypatch, error_type, retries, recover
):
    error = error_type("offline Redis")
    attempts = []
    failures = []

    def operation():
        attempts.append(1)
        if recover and len(attempts) == retries + 1:
            return "recovered"
        raise error

    def no_sleep(delay):
        pytest.fail(f"unexpected retry sleep: {delay}")

    monkeypatch.setattr("redis.retry.sleep", no_sleep)
    retry = Retry(EqualJitterBackoff(cap=1.0, base=0.05), retries)
    if recover:
        assert retry.call_with_retry(operation, failures.append) == "recovered"
    else:
        with pytest.raises(error_type) as caught:
            retry.call_with_retry(operation, failures.append)
        assert caught.value is error
    assert len(attempts) == retries + 1
    expected_failures = retries if recover else retries + 1
    assert len(failures) == expected_failures
    assert all(failure is error for failure in failures)


@pytest.mark.parametrize("error_type", [ConnectionError, TimeoutError])
@pytest.mark.parametrize("retries", [1, 3])
@pytest.mark.parametrize("recover", [False, True])
async def test_async_attempts_callbacks_and_original_error(
    offline_redis_no_retry_sleep, monkeypatch, error_type, retries, recover
):
    error = error_type("offline Redis")
    attempts = []
    failures = []

    async def operation():
        attempts.append(1)
        if recover and len(attempts) == retries + 1:
            return "recovered"
        raise error

    async def failed(failure):
        failures.append(failure)

    async def no_sleep(delay):
        pytest.fail(f"unexpected retry sleep: {delay}")

    monkeypatch.setattr("redis.asyncio.retry.sleep", no_sleep)
    retry = AsyncRetry(EqualJitterBackoff(cap=1.0, base=0.05), retries)
    if recover:
        assert await retry.call_with_retry(operation, failed) == "recovered"
    else:
        with pytest.raises(error_type) as caught:
            await retry.call_with_retry(operation, failed)
        assert caught.value is error
    assert len(attempts) == retries + 1
    expected_failures = retries if recover else retries + 1
    assert len(failures) == expected_failures
    assert all(failure is error for failure in failures)


def test_unrelated_error_is_not_retried(offline_redis_no_retry_sleep):
    attempts = []
    failures = []
    error = ValueError("not a Redis connection error")

    def operation():
        attempts.append(1)
        raise error

    retry = Retry(EqualJitterBackoff(), 3)
    with pytest.raises(ValueError) as caught:
        retry.call_with_retry(operation, failures.append)
    assert caught.value is error
    assert len(attempts) == 1
    assert failures == []


def test_failure_callback_error_propagates(offline_redis_no_retry_sleep):
    attempts = []
    callback_error = ValueError("failure callback")

    def operation():
        attempts.append(1)
        raise ConnectionError("offline")

    def failed(error):
        raise callback_error

    retry = Retry(EqualJitterBackoff(), 3)
    with pytest.raises(ValueError) as caught:
        retry.call_with_retry(operation, failed)
    assert caught.value is callback_error
    assert len(attempts) == 1


def test_unrequested_fixture_leaves_production_jitter_and_identity_intact():
    # Runs after requesting tests too: the same class method must be restored.
    assert EqualJitterBackoff.compute is _PRODUCTION_COMPUTE
    backoff = EqualJitterBackoff(cap=1.0, base=0.05)
    for failures in [1, 2, 3]:
        half = min(1.0, 0.05 * 2**failures) / 2
        assert half <= backoff.compute(failures) <= 2 * half
        assert backoff.compute(failures) > 0
