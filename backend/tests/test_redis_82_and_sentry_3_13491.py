"""Regression guards for the ``redis 8.2.0`` and ``sentry-sdk 3.0.0`` upgrades (#13491)."""

from __future__ import annotations

import errno
import pathlib
import socket
import ssl
import time
import warnings

import pytest
import sentry_sdk
from redis.asyncio.retry import Retry as AsyncRetry
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.tasks import build_celery_integration, redis_state
from app.utils.sentry_filter import SENTRY_NO_PII_DATA_COLLECTION, build_before_send


def test_async_redis_client_uses_native_async_retry_without_warning():
    """redis 8.2 warns and converts if passed synchronous redis.retry.Retry."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = redis_state.get_async_redis_client()
    retry = client.connection_pool.connection_kwargs["retry"]
    assert isinstance(retry, AsyncRetry)
    assert not any(
        "synchronous redis.retry.Retry" in str(w.message) for w in caught
    )


def test_is_connection_refused_matches_single_and_dual_stack_refusals_only():
    single = RedisConnectionError("connect failed")
    single.__cause__ = ConnectionRefusedError(errno.ECONNREFUSED, "refused")
    assert redis_state._is_connection_refused(single) is True

    dual = RedisConnectionError("connect failed")
    dual.__cause__ = OSError(
        f"Multiple exceptions: [Errno {errno.ECONNREFUSED}] Connect call failed ('::1', 6379, 0, 0), "
        f"[Errno {errno.ECONNREFUSED}] Connect call failed ('127.0.0.1', 6379)"
    )
    assert redis_state._is_connection_refused(dual) is True

    mixed = RedisConnectionError("connect failed")
    mixed.__cause__ = OSError(
        f"Multiple exceptions: [Errno {errno.ECONNREFUSED}] Connect call failed, "
        f"[Errno {errno.ETIMEDOUT}] Connect timed out"
    )
    assert redis_state._is_connection_refused(mixed) is False

    tls_eof = RedisConnectionError("EOF occurred")
    tls_eof.__cause__ = ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING")
    assert redis_state._is_connection_refused(tls_eof) is False

    reset = RedisConnectionError("reset by peer")
    reset.__cause__ = ConnectionResetError(errno.ECONNRESET, "reset")
    assert redis_state._is_connection_refused(reset) is False

    assert redis_state._is_connection_refused(RedisTimeoutError("timed out")) is False


@pytest.mark.asyncio
async def test_async_redis_client_fails_fast_on_closed_port_without_backoff_sleep(monkeypatch):
    """Refusing connections must not burn the EqualJitterBackoff retry budget (#13491)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    closed_port = sock.getsockname()[1]
    sock.close()

    monkeypatch.setattr(redis_state, "REDIS_URL", f"redis://127.0.0.1:{closed_port}/0")
    client = redis_state.get_async_redis_client()
    t0 = time.monotonic()
    try:
        with pytest.raises(RedisConnectionError):
            await client.ping()
        elapsed = time.monotonic() - t0
        assert elapsed < 0.2, f"closed port took {elapsed:.3f}s (unexpected backoff sleep)"
    finally:
        await client.aclose()


def test_both_sentry_init_configs_succeed_with_no_pii_data_collection(monkeypatch):
    """Both app/main.py and app/tasks/__init__.py init configs work on sentry-sdk 3.x."""
    prev_client = sentry_sdk.get_client()
    monkeypatch.setattr("sentry_sdk.Client.flush", lambda *a, **kw: None)
    try:
        sentry_sdk.init(
            dsn="https://public@o0.ingest.sentry.io/0",
            environment="test",
            release="13491-test",
            traces_sample_rate=0.1,
            profile_session_sample_rate=0.1,
            profile_lifecycle="trace",
            data_collection=SENTRY_NO_PII_DATA_COLLECTION,
            before_send=build_before_send(),
        )
        opts_web = sentry_sdk.get_client().options
        assert opts_web["data_collection"]["user_info"] is False
        assert opts_web["data_collection"]["cookies"] == {"mode": "off"}
        assert opts_web["data_collection"]["http_bodies"] == []
        assert opts_web["data_collection"]["gen_ai"] == {"inputs": False, "outputs": False}

        sentry_sdk.init(
            dsn="https://public@o0.ingest.sentry.io/0",
            environment="test",
            release="13491-test",
            traces_sample_rate=0.05,
            data_collection=SENTRY_NO_PII_DATA_COLLECTION,
            before_send=build_before_send(),
            integrations=[build_celery_integration()],
        )
        opts_worker = sentry_sdk.get_client().options
        assert opts_worker["data_collection"]["user_info"] is False
        assert "celery" in sentry_sdk.get_client().integrations
    finally:
        sentry_sdk.get_global_scope().set_client(prev_client)


def test_no_sync_retry_on_async_clients_and_no_removed_sentry_apis():
    backend = pathlib.Path(__file__).resolve().parent.parent
    for rel in (
        "app/main.py",
        "app/tasks/__init__.py",
        "app/tasks/sentry_snapshot.py",
    ):
        text = (backend / rel).read_text(encoding="utf-8")
        assert "send_default_pii" not in text, f"{rel} still passes removed send_default_pii"
        assert "profiles_sample_rate" not in text, f"{rel} still passes removed profiles_sample_rate"
        assert "push_scope(" not in text, f"{rel} still calls removed sentry_sdk.push_scope"

    for rel in (
        "app/services/dnpl_activation_command.py",
        "app/services/dnpl_activation_operator.py",
    ):
        text = (backend / rel).read_text(encoding="utf-8")
        assert "from redis.retry import Retry" not in text
        assert "from redis.asyncio.retry import Retry" in text
