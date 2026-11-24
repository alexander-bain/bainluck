"""Regression guards for ``redis 8.1.0`` + ``sentry-sdk 3.0.0`` upgrades (#13491)."""

from __future__ import annotations

import errno
import json
import pathlib
import socket
import ssl
import time
import warnings

import pytest
import sentry_sdk
from celery import Celery
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from redis.asyncio.retry import Retry as AsyncRetry
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sentry_sdk.transport import Transport

from app.tasks import build_celery_integration, redis_state
from app.utils.sentry_filter import SENTRY_NO_PII_DATA_COLLECTION, build_before_send

_PII_TOKENS = (
    "secret-cookie-9988",
    "secret-jwt-token-7766",
    "private-json-body-5544",
    "alice.pii",
    "203.0.113.42",
)


class _CapturingTransport(Transport):
    """In-memory Sentry transport capturing exact serialized envelopes & events."""

    def __init__(self) -> None:
        super().__init__()
        self.payloads: list[str] = []

    def capture_envelope(self, envelope) -> None:
        raw = envelope.serialize()
        self.payloads.append(raw.decode("utf-8", errors="replace"))

    def capture_event(self, event) -> None:
        self.payloads.append(json.dumps(event, default=str))

    def flush(self, timeout: float, callback=None) -> None:
        return None


def test_async_redis_client_uses_native_async_retry_without_warning():
    """Async client constructs a native AsyncRetry with zero conversion warnings."""
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


@pytest.mark.asyncio
async def test_async_retry_skips_econnrefused_but_still_retries_transient_errors(monkeypatch):
    """Pinned 8.1.0 wrapper fails fast on ECONNREFUSED and still retries transient TLS/reset errors."""
    sleeps: list[float] = []

    async def _fake_sleep(secs: float) -> None:
        sleeps.append(secs)

    monkeypatch.setattr("redis.asyncio.retry.sleep", _fake_sleep)
    retry = redis_state._async_redis_retry()

    refused_attempts = 0

    async def _do_refused() -> str:
        nonlocal refused_attempts
        refused_attempts += 1
        err = RedisConnectionError("refused")
        err.__cause__ = ConnectionRefusedError(errno.ECONNREFUSED, "refused")
        raise err

    async def _fail_noop(_exc: Exception) -> None:
        return None

    with pytest.raises(RedisConnectionError):
        await retry.call_with_retry(_do_refused, _fail_noop)
    assert refused_attempts == 1
    assert sleeps == []

    transient_attempts = 0

    async def _do_transient() -> str:
        nonlocal transient_attempts
        transient_attempts += 1
        if transient_attempts == 1:
            err = RedisConnectionError("EOF occurred")
            err.__cause__ = ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING")
            raise err
        return "ok"

    result = await retry.call_with_retry(_do_transient, _fail_noop)
    assert result == "ok"
    assert transient_attempts == 2
    assert len(sleeps) == 1


def test_both_sentry_init_configs_disable_pii_and_profiling(monkeypatch):
    """Both app/main.py and app/tasks/__init__.py init configs disable PII & profiling."""
    prev_client = sentry_sdk.get_client()
    monkeypatch.setattr("sentry_sdk.Client.flush", lambda *a, **kw: None)
    try:
        sentry_sdk.init(
            dsn="https://public@o0.ingest.sentry.io/0",
            environment="test",
            release="13491-test",
            traces_sample_rate=0.1,
            data_collection=SENTRY_NO_PII_DATA_COLLECTION,
            before_send=build_before_send(),
        )
        opts_web = sentry_sdk.get_client().options
        assert opts_web.get("profile_session_sample_rate") is None
        assert opts_web["data_collection"]["user_info"] is False
        assert opts_web["data_collection"]["cookies"] == {"mode": "off"}
        assert opts_web["data_collection"]["http_headers"] == {"request": {"mode": "off"}}
        assert opts_web["data_collection"]["http_bodies"] == []
        assert opts_web["data_collection"]["url_query_params"] == {"mode": "off"}
        assert opts_web["data_collection"]["queues"] is False
        assert opts_web["data_collection"]["stack_frame_variables"] is False
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
        assert opts_worker.get("profile_session_sample_rate") is None
        assert opts_worker["data_collection"]["user_info"] is False
        assert opts_worker["data_collection"]["queues"] is False
        assert "celery" in sentry_sdk.get_client().integrations
    finally:
        sentry_sdk.get_global_scope().set_client(prev_client)


def test_web_real_event_captures_zero_pii_through_stub_transport():
    """Real FastAPI request with cookie/auth/body/email-query/IP leaks nothing to Sentry transport."""
    transport = _CapturingTransport()
    prev_client = sentry_sdk.get_client()
    app = FastAPI()

    @app.post("/boom-13491")
    async def _boom(request: Request) -> dict[str, str]:
        _ = await request.json()
        _ = request.cookies.get("session_id")
        _ = request.headers.get("authorization")
        _ = request.query_params.get("email")
        raise RuntimeError("synthetic-web-boom-13491")

    try:
        sentry_sdk.init(
            dsn="https://public@o0.ingest.sentry.io/0",
            environment="test",
            release="13491-test",
            traces_sample_rate=1.0,
            data_collection=SENTRY_NO_PII_DATA_COLLECTION,
            before_send=build_before_send(),
            transport=transport,
            shutdown_timeout=0,
        )
        assert "fastapi" in sentry_sdk.get_client().integrations

        client = TestClient(
            app,
            client=("203.0.113.42", 54321),
            raise_server_exceptions=False,
        )
        resp = client.post(
            "/boom-13491?email=alice.pii%40example.com",
            headers={
                "Cookie": "session_id=secret-cookie-9988",
                "Authorization": "Bearer secret-jwt-token-7766",
                "X-Forwarded-For": "203.0.113.42",
                "X-Real-IP": "203.0.113.42",
            },
            json={"secret_field": "private-json-body-5544"},
        )
        assert resp.status_code == 500
        sentry_sdk.get_client().flush(timeout=2.0)

        assert any("synthetic-web-boom-13491" in p for p in transport.payloads), (
            f"Expected web boom event in transport payloads, got {len(transport.payloads)}"
        )
        combined = "\n".join(transport.payloads)
        for token in _PII_TOKENS:
            assert token not in combined, f"Web Sentry payload leaked PII token {token!r}"
    finally:
        sentry_sdk.init(dsn=None)
        sentry_sdk.get_global_scope().set_client(prev_client)


def test_celery_worker_real_event_captures_zero_pii_through_stub_transport():
    """Real Celery task exception with cookie/auth/body/email-query/IP kwargs/headers leaks no PII."""
    transport = _CapturingTransport()
    prev_client = sentry_sdk.get_client()
    celery_app = Celery("worker-pii-test-13491")
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=False)

    @celery_app.task(name="tests.worker_boom_13491")
    def _worker_boom(
        *,
        cookie: str,
        authorization: str,
        json_body: dict[str, str],
        query_string: str,
        client_ip: str,
    ) -> None:
        raise RuntimeError("synthetic-worker-boom-13491")

    try:
        sentry_sdk.init(
            dsn="https://public@o0.ingest.sentry.io/0",
            environment="test",
            release="13491-test",
            traces_sample_rate=1.0,
            data_collection=SENTRY_NO_PII_DATA_COLLECTION,
            before_send=build_before_send(),
            integrations=[build_celery_integration()],
            transport=transport,
            shutdown_timeout=0,
        )
        assert "celery" in sentry_sdk.get_client().integrations

        res = _worker_boom.apply_async(
            kwargs={
                "cookie": "session_id=secret-cookie-9988",
                "authorization": "Bearer secret-jwt-token-7766",
                "json_body": {"secret_field": "private-json-body-5544"},
                "query_string": "email=alice.pii@example.com",
                "client_ip": "203.0.113.42",
            },
            headers={
                "cookie": "session_id=secret-cookie-9988",
                "authorization": "Bearer secret-jwt-token-7766",
                "x-forwarded-for": "203.0.113.42",
                "query_string": "email=alice.pii@example.com",
                "body": "private-json-body-5544",
            },
        )
        assert res.failed()
        sentry_sdk.get_client().flush(timeout=2.0)

        assert any("synthetic-worker-boom-13491" in p for p in transport.payloads), (
            f"Expected worker boom event in transport payloads, got {len(transport.payloads)}"
        )
        combined = "\n".join(transport.payloads)
        for token in _PII_TOKENS:
            assert token not in combined, f"Worker Sentry payload leaked PII token {token!r}"
    finally:
        sentry_sdk.init(dsn=None)
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
        assert "profile_session_sample_rate" not in text, f"{rel} should keep continuous profiling OFF"
        assert "push_scope(" not in text, f"{rel} still calls removed sentry_sdk.push_scope"

    for rel in (
        "app/services/dnpl_activation_command.py",
        "app/services/dnpl_activation_operator.py",
    ):
        text = (backend / rel).read_text(encoding="utf-8")
        assert "from redis.retry import Retry" not in text
        assert "from redis.asyncio.retry import Retry" in text
