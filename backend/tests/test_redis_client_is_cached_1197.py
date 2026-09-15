"""#1197: the sync Redis client is cached per process, not minted per call.

Every ``get_redis_client()`` call used to build a new client AND a new
ConnectionPool — 290 call sites, so every Redis touch in the codebase was an
independent TLS handshake against Heroku Redis. The two stability settings
already on the client (``health_check_interval=25``, TCP keepalive) only ever
apply to a connection that gets REUSED, so a pool discarded after one op could
never benefit from either. That is the structural reason the keepalive-only
fixes (#233/#239) left the ``[SSL: UNEXPECTED_EOF_WHILE_READING]`` churn flat.

These are the properties that make the cache safe, each of which would be a
production defect if it broke:

* the same call signature gets the same warm client (the ship itself);
* different signatures do NOT share one (``fast_fail`` exists to give the
  request path a different retry budget — sharing would silently hand the hot
  path the 3-attempt background retry);
* a prefork child never inherits the parent's live sockets;
* patching ``redis.from_url`` still works, so a mocked test never gets served a
  real client built by an earlier one.
"""

import os
import pathlib
import threading
from unittest.mock import patch

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import get_redis_client, reset_redis_client_cache


@pytest.fixture(autouse=True)
def _clean_client_cache():
    reset_redis_client_cache()
    yield
    reset_redis_client_cache()


class TestOneClientPerProcessPerSignature:
    def test_repeat_bare_calls_return_the_same_client(self):
        """The ship. On the pre-fix code these are two different objects."""
        assert get_redis_client() is get_redis_client()

    def test_repeat_calls_share_one_connection_pool(self):
        """The pool is the thing that actually holds the warm connection."""
        first, second = get_redis_client(), get_redis_client()
        assert first.connection_pool is second.connection_pool

    def test_the_client_is_built_exactly_once_for_n_calls(self):
        with patch("redis.from_url", return_value=object()) as from_url:
            for _ in range(25):
                get_redis_client()
        assert from_url.call_count == 1

    def test_fast_fail_does_not_share_a_client_with_the_background_path(self):
        """A shared client would give the hot request path the 3-attempt retry."""
        assert get_redis_client() is not get_redis_client(fast_fail=True)

    def test_a_different_timeout_does_not_share_a_client(self):
        assert get_redis_client() is not get_redis_client(
            socket_timeout=2.0, socket_connect_timeout=2.0
        )

    def test_the_cached_client_still_carries_the_1197_stability_kwargs(self):
        """Caching must not quietly drop the settings it exists to make apply."""
        with patch("redis.from_url", return_value=object()) as from_url:
            get_redis_client()
        kwargs = from_url.call_args.kwargs
        assert kwargs["health_check_interval"] == 25
        assert kwargs["socket_keepalive"] is True
        assert kwargs["max_connections"] == redis_state._REDIS_MAX_CONNECTIONS
        assert kwargs["retry"] is not None
        assert kwargs["retry_on_error"]


class TestForkSafety:
    def test_the_pid_is_part_of_the_cache_key(self):
        """A prefork child must not be handed the parent's live sockets."""
        parent_client = get_redis_client()
        real_pid = os.getpid()
        with patch.object(os, "getpid", return_value=real_pid + 1):
            child_client = get_redis_client()
        assert child_client is not parent_client

    def test_the_fork_hook_clears_the_cache_without_taking_the_lock(self):
        """The parent can be mid-``with`` at fork time; a child that waits on
        that lock deadlocks forever, so the hook replaces it rather than
        acquiring it."""
        get_redis_client()
        assert redis_state._CLIENT_CACHE
        lock_before = redis_state._CLIENT_CACHE_LOCK
        lock_before.acquire()  # the parent holds it at the moment of the fork
        try:
            redis_state._reset_redis_client_cache_after_fork()
            assert redis_state._CLIENT_CACHE == {}
            assert redis_state._CLIENT_CACHE_LOCK is not lock_before
            # The replacement is usable: a child that cannot lock cannot cache.
            assert redis_state._CLIENT_CACHE_LOCK.acquire(blocking=False)
            redis_state._CLIENT_CACHE_LOCK.release()
        finally:
            lock_before.release()

    def test_the_fork_hook_is_registered(self):
        src = pathlib.Path(redis_state.__file__).read_text()
        assert "os.register_at_fork(after_in_child=" in src


class TestPatchingStillWorks:
    def test_a_mock_is_honoured_after_a_real_client_was_cached(self):
        """The trap this guards: a cache keyed only on parameters would serve a
        patched test whatever an earlier unpatched test happened to build — a
        real client, against real Redis, silently ignoring the mock."""
        real = get_redis_client()
        sentinel = object()
        with patch("redis.from_url", return_value=sentinel):
            assert get_redis_client() is sentinel
        # Leaving the patch does not resurrect the object built before it — the
        # entry was overwritten — but it must stop serving the mock, and the
        # rebuilt client must itself be cached.
        after = get_redis_client()
        assert after is not sentinel
        assert isinstance(after, type(real))
        assert get_redis_client() is after

    def test_two_successive_mocks_do_not_bleed_into_each_other(self):
        first_fake, second_fake = object(), object()
        with patch("redis.from_url", return_value=first_fake):
            assert get_redis_client() is first_fake
        with patch("redis.from_url", return_value=second_fake):
            assert get_redis_client() is second_fake

    def test_the_entry_keeps_the_factory_alive(self):
        """Identity is compared with ``is``; holding only an id would let a
        collected mock's id be recycled by a later one."""
        with patch("redis.from_url", return_value=object()):
            get_redis_client()
        entry = next(iter(redis_state._CLIENT_CACHE.values()))
        assert callable(entry[0])

    def test_reset_empties_the_cache(self):
        get_redis_client()
        assert redis_state._CLIENT_CACHE
        reset_redis_client_cache()
        assert redis_state._CLIENT_CACHE == {}


class TestThreadSafety:
    def test_concurrent_callers_converge_on_one_client(self):
        seen = []
        barrier = threading.Barrier(8)

        def _grab():
            barrier.wait()
            seen.append(get_redis_client())

        threads = [threading.Thread(target=_grab) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # A race may build a throwaway client, but every later caller must land
        # on the one that won, and the cache must hold exactly one entry.
        assert len(redis_state._CLIENT_CACHE) == 1
        assert get_redis_client() in seen or len(set(map(id, seen))) <= 2

    def test_the_shared_backoff_is_stateless(self):
        """One ``Retry`` is now shared across every thread in the process, so a
        backoff that accumulated state between calls would couple them."""
        from redis.backoff import AbstractBackoff

        backoff = redis_state._redis_retry()._backoff
        assert backoff.compute(0) >= 0
        # ``compute`` takes the failure count as an argument rather than reading
        # an instance counter, and ``reset`` is the no-op base implementation.
        assert type(backoff).reset is AbstractBackoff.reset


class TestAsyncClientIsExcludedForAReason:
    def test_async_client_is_not_cached_while_the_sse_path_closes_it(self):
        """``routes/event_stream.py`` ``aclose()``s its client when a stream
        ends. Caching the async client while that call exists would tear a
        shared client out from under every other user of it — so exactly one of
        the two may be true at a time."""
        app_dir = pathlib.Path(redis_state.__file__).parent.parent
        stream_src = (app_dir / "routes" / "event_stream.py").read_text()
        sse_closes_it = "aclose()" in stream_src

        state_src = pathlib.Path(redis_state.__file__).read_text()
        async_def = state_src.split("def get_async_redis_client(", 1)[1]
        async_body = async_def.split("\ndef ", 1)[0]
        async_is_cached = "_CLIENT_CACHE" in async_body

        assert not (sse_closes_it and async_is_cached), (
            "get_async_redis_client() is cached while event_stream.py still "
            "aclose()s it — a shared async client would be closed under its "
            "other users."
        )
