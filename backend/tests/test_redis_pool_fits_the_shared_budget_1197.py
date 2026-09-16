"""#1197 follow-through: the connection pool fits the SHARED budget, and a full
pool queues instead of failing.

Caching the sync client (``test_redis_client_is_cached_1197.py``) turned
``_REDIS_MAX_CONNECTIONS`` from a dead number into a real per-process ceiling —
redis-py's pool has no idle reaper, so a cached pool's connection count is a
high-water mark that only ratchets up. At the old value of 40 the Procfile's
process envelope had a ceiling of 560 connections against a server limit of 80.

Lowering the number on its own would have been the wrong fix. ``ConnectionPool``
answers a full pool by raising ``MaxConnectionsError``, and
``Redis._execute_command`` acquires the connection BEFORE
``conn.retry.call_with_retry(...)`` — so pool exhaustion is invisible to every
retry policy on the client and lands raw on the caller. A smaller cap on a plain
pool would have bought a smaller connection count by paying in hard client
failures at exactly the busy moments the budget exists for. So the cap came down
AND the pool became blocking, and these are the properties that pairing has to
keep:

* the declared envelope times the cap fits the plan limit (the ship);
* healthy concurrent callers all get served;
* a caller that arrives at a full pool WAITS for a connection and gets one when
  another caller releases;
* a wait that cannot be satisfied is still BOUNDED (#969) and raises a
  ``ConnectionError``, which is what the fail-open callers already catch.
"""

import os
import pathlib
import re
import socket
import threading
import time

import pytest
import redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.tasks import redis_state


# ---------------------------------------------------------------------------
# The ship: the ceiling fits the budget.
# ---------------------------------------------------------------------------


def _procfile_path() -> pathlib.Path:
    # tests/ -> backend/
    return pathlib.Path(__file__).resolve().parent.parent / "Procfile"


def _pool_holding_processes(procfile_text: str) -> int:
    """OS processes that can hold a client cache, derived from the Procfile.

    The cache key carries the pid, so a Celery prefork parent and each of its
    ``--concurrency`` children counts separately. ``release`` is not a
    long-running process and holds nothing.
    """
    total = 0
    for line in procfile_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, command = line.split(":", 1)
        if name.strip() == "release":
            continue
        concurrency = re.search(r"--concurrency[= ](\d+)", command)
        # A prefork worker is a parent plus N children; anything else is one
        # process (uvicorn is started without --workers).
        total += 1 + int(concurrency.group(1)) if concurrency else 1
    return total


class TestTheCeilingFitsThePlanLimit:
    def test_the_procfile_is_readable_and_declares_processes(self):
        """If this ever reads 0 the budget assertion below is vacuous."""
        assert _pool_holding_processes(_procfile_path().read_text()) >= 10

    def test_envelope_times_the_cap_fits_the_shared_connection_limit(self):
        """The ship, mechanized. At the old cap of 40 this asserts 560 <= 80.

        Re-derived from the Procfile on every run, so raising a worker's
        ``--concurrency`` (or adding a dyno type) fails here instead of quietly
        eating a budget that is shared with the other app and with Celery's own
        broker connections.
        """
        processes = _pool_holding_processes(_procfile_path().read_text())
        ceiling = processes * redis_state._REDIS_MAX_CONNECTIONS
        assert ceiling <= redis_state._REDIS_PLAN_CONNECTION_LIMIT, (
            f"{processes} pool-holding processes x "
            f"{redis_state._REDIS_MAX_CONNECTIONS} connections = {ceiling}, "
            f"over the {redis_state._REDIS_PLAN_CONNECTION_LIMIT}-connection "
            "plan limit shared by both apps"
        )

    def test_the_cap_leaves_room_for_more_than_one_concurrent_caller(self):
        """The other side of the same bound: a cap of 1 would serialize every
        process onto one connection and make the blocking wait load-bearing for
        ordinary traffic rather than for bursts."""
        assert redis_state._REDIS_MAX_CONNECTIONS >= 2

    def test_the_request_path_waits_less_than_its_socket_timeout(self):
        """A sampled request may not spend the background wait queueing: the
        fast-fail clients pass socket_timeout=0.5 precisely to stay sub-second."""
        assert (
            0 < redis_state._REDIS_POOL_WAIT_FAST_FAIL < redis_state._REDIS_POOL_WAIT
        )
        assert redis_state._REDIS_POOL_WAIT_FAST_FAIL < 0.5


# ---------------------------------------------------------------------------
# The pool the production path actually builds.
# ---------------------------------------------------------------------------


class TestTheProductionClientGetsABlockingPool:
    def test_the_sync_client_pool_is_blocking_and_carries_the_cap(self):
        client = redis_state._build_bounded_client(
            "redis://localhost:6379/0",
            redis_state._REDIS_POOL_WAIT,
            socket_timeout=5.0,
            max_connections=redis_state._REDIS_MAX_CONNECTIONS,
        )
        pool = client.connection_pool
        assert isinstance(pool, redis.BlockingConnectionPool)
        assert pool.max_connections == redis_state._REDIS_MAX_CONNECTIONS
        assert pool.timeout == redis_state._REDIS_POOL_WAIT

    def test_a_tls_url_still_gets_the_tls_connection_class(self):
        """The pool is built by us now, not by ``redis.from_url`` — the scheme,
        credentials and db must still be honoured or production talks plaintext
        to a TLS port."""
        client = redis_state._build_bounded_client(
            "rediss://:secret@redis.example.com:6380/3",
            redis_state._REDIS_POOL_WAIT,
            max_connections=redis_state._REDIS_MAX_CONNECTIONS,
        )
        pool = client.connection_pool
        assert pool.connection_class is redis.connection.SSLConnection
        assert pool.connection_kwargs["host"] == "redis.example.com"
        assert pool.connection_kwargs["port"] == 6380
        assert pool.connection_kwargs["db"] == 3
        assert pool.connection_kwargs["password"] == "secret"

    def test_get_redis_client_installs_the_blocking_pool(self):
        redis_state.reset_redis_client_cache()
        try:
            pool = redis_state.get_redis_client().connection_pool
            assert isinstance(pool, redis.BlockingConnectionPool)
            assert pool.max_connections == redis_state._REDIS_MAX_CONNECTIONS
            assert pool.timeout == redis_state._REDIS_POOL_WAIT
        finally:
            redis_state.reset_redis_client_cache()

    def test_the_fast_fail_client_gets_the_short_wait(self):
        """Sharing one wait would put the background budget on the hot path."""
        redis_state.reset_redis_client_cache()
        try:
            fast = redis_state.get_redis_client(fast_fail=True)
            assert fast.connection_pool.timeout == (
                redis_state._REDIS_POOL_WAIT_FAST_FAIL
            )
        finally:
            redis_state.reset_redis_client_cache()

    def test_the_async_client_pool_is_blocking_and_capped(self):
        """``utils/request_cache.py`` keeps ONE async client for the whole
        request path, so a plain pool would surface MaxConnectionsError to a
        reader the moment concurrency touched the cap."""
        import redis.asyncio as aioredis

        pool = redis_state.get_async_redis_client().connection_pool
        assert isinstance(pool, aioredis.BlockingConnectionPool)
        assert pool.max_connections == redis_state._REDIS_MAX_CONNECTIONS
        assert pool.timeout == redis_state._REDIS_POOL_WAIT


# ---------------------------------------------------------------------------
# Behaviour under concurrency, against a fake connection so the test needs no
# Redis and no network.
# ---------------------------------------------------------------------------


class _FakeConnection:
    """The slice of redis-py's Connection contract a pool actually touches."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        # ``ConnectionPool.owns_connection`` compares this against the pool's
        # pid; a connection the pool does not own is discarded on release
        # instead of being reused, which would make "the cap binds" untestable.
        self.pid = os.getpid()
        self.retry = None
        self.credential_provider = None

    def connect(self):
        return None

    def disconnect(self, *args):
        return None

    def can_read(self, timeout=0):
        return False

    def should_reconnect(self):
        return False

    def register_connect_callback(self, _cb):
        return None

    def deregister_connect_callback(self, _cb):
        return None


def _fake_pool(max_connections, timeout):
    return redis.BlockingConnectionPool(
        max_connections=max_connections,
        timeout=timeout,
        connection_class=_FakeConnection,
    )


class TestHealthyConcurrentCallersAreAllServed:
    def test_callers_up_to_the_cap_hold_connections_at_the_same_time(self):
        """The cap is a real ceiling, not a serializer: four concurrent callers
        on a cap of four are all holding a connection simultaneously."""
        pool = _fake_pool(max_connections=4, timeout=1.0)
        held = []
        barrier = threading.Barrier(4, timeout=5)

        def _take():
            conn = pool.get_connection()
            held.append(conn)
            barrier.wait()  # nobody releases until everyone has one
            pool.release(conn)

        threads = [threading.Thread(target=_take) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(held) == 4
        assert len({id(c) for c in held}) == 4, "four callers shared a connection"

    def test_more_callers_than_the_cap_are_all_served_by_reuse(self):
        """Twelve callers on a cap of three: the pool queues them and every one
        completes. On a plain ConnectionPool nine of these raise."""
        pool = _fake_pool(max_connections=3, timeout=2.0)
        served = []
        errors = []

        def _use():
            try:
                conn = pool.get_connection()
                try:
                    served.append(id(conn))
                finally:
                    pool.release(conn)
            except Exception as exc:  # pragma: no cover - the failure we guard
                errors.append(exc)

        threads = [threading.Thread(target=_use) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"a healthy caller failed: {errors}"
        assert len(served) == 12
        assert len(set(served)) <= 3, "the cap did not bind"


class TestExhaustionWaitsAndStaysBounded:
    def test_a_caller_at_a_full_pool_waits_and_is_served_on_release(self):
        """The whole point of the pairing: 'too busy' is a short wait, not an
        exception. A plain pool raises MaxConnectionsError here instead."""
        pool = _fake_pool(max_connections=1, timeout=5.0)
        first = pool.get_connection()
        outcome = {}

        def _second():
            started = time.monotonic()
            try:
                conn = pool.get_connection()
                outcome["waited"] = time.monotonic() - started
                outcome["conn"] = conn
                pool.release(conn)
            except Exception as exc:  # pragma: no cover - the failure we guard
                outcome["error"] = exc

        waiter = threading.Thread(target=_second)
        waiter.start()
        time.sleep(0.2)
        assert "conn" not in outcome and "error" not in outcome, (
            "the second caller did not wait — the pool is not blocking"
        )
        pool.release(first)
        waiter.join(timeout=5)

        assert "error" not in outcome, outcome.get("error")
        assert outcome["conn"] is first, "the released connection was not reused"

    def test_a_wait_that_cannot_be_satisfied_is_bounded_and_raises(self):
        """A blocking pool must not trade a hard failure for a hang (#969). The
        error is a ConnectionError, which is what the fail-open callers catch."""
        pool = _fake_pool(max_connections=1, timeout=0.25)
        pool.get_connection()  # never released

        started = time.monotonic()
        with pytest.raises(RedisConnectionError):
            pool.get_connection()
        waited = time.monotonic() - started

        assert 0.2 <= waited < 3.0, f"waited {waited:.2f}s for a 0.25s timeout"


class TestExhaustionIsNotRetriedByTheClientRetryPolicy:
    def test_the_connection_is_acquired_outside_the_retry_wrapper(self):
        """The fact that makes a plain, smaller pool the wrong fix — and the one
        that would silently stop being true if redis-py moved the acquisition
        inside ``call_with_retry``, which would make this whole pairing
        unnecessary. Either way we want to know.
        """
        import inspect

        src = inspect.getsource(redis.Redis._execute_command)
        acquire = src.index("pool.get_connection()")
        retry = src.index("retry.call_with_retry")
        assert acquire < retry, (
            "redis-py now acquires the connection inside the retry wrapper; "
            "re-read whether the blocking pool is still the right mechanism"
        )

    def test_max_connections_error_is_a_connection_error(self):
        """So the callers that already fail open on ConnectionError also cover
        the residual case where a wait expires."""
        from redis.exceptions import MaxConnectionsError

        assert issubclass(MaxConnectionsError, RedisConnectionError)


# ---------------------------------------------------------------------------
# End to end, against a real socket.
#
# The tests above drive the pool directly. These drive the production path —
# ``get_redis_client()`` -> ``Redis.execute_command`` -> pool -> a real
# ``Connection`` on a real TCP socket — because the claim the ship makes is
# about SOCKETS AT THE SERVER, and only the server can count those. A fake
# connection can prove the pool's bookkeeping and nothing about the budget.
# ---------------------------------------------------------------------------


class _TinyRespServer:
    """Answers every command and counts the connections it accepted.

    It has to answer ``HELLO`` as well as ``+PONG``, and that is not a detail:
    redis-py only sends ``HELLO`` when the connection speaks RESP3, so a server
    that ignores it passes locally on a RESP2 default and fails wherever the
    library's default is RESP3 — the client reads ``+PONG`` where it expects a
    handshake map and dies on ``'bytes' object has no attribute 'get'``. Our
    requirement is an unpinned ``redis>=5.0.1``, so the protocol the tests run
    under is not ours to assume; both are exercised below.
    """

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]
        self.accepted = 0
        self.concurrent = 0
        self.peak_concurrent = 0
        self.hold = 0.0  # seconds to stall each command, to force contention
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads = []
        self._acceptor = threading.Thread(target=self._accept_loop, daemon=True)
        self._acceptor.start()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with self._lock:
                self.accepted += 1
                self.concurrent += 1
                self.peak_concurrent = max(self.peak_concurrent, self.concurrent)
            t = threading.Thread(target=self._serve, args=(conn,), daemon=True)
            t.start()
            self._threads.append(t)

    def _serve(self, conn):
        buf = b""
        try:
            while not self._stop.is_set():
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
                # One reply per complete RESP command, so the client never
                # desynchronizes; a reply per recv() would.
                while True:
                    parsed = _parse_resp_command(buf)
                    if parsed is None:
                        break
                    consumed, args = parsed
                    buf = buf[consumed:]
                    if self.hold:
                        time.sleep(self.hold)
                    conn.sendall(_reply_to(args))
        except OSError:
            return
        finally:
            with self._lock:
                self.concurrent -= 1
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


def _parse_resp_command(buf: bytes):
    """``(bytes consumed, [args])`` for the first complete command, or None."""
    if not buf.startswith(b"*"):
        return None
    end = buf.find(b"\r\n")
    if end == -1:
        return None
    try:
        argc = int(buf[1:end])
    except ValueError:
        return None
    pos = end + 2
    args = []
    for _ in range(argc):
        if not buf[pos:].startswith(b"$"):
            return None
        end = buf.find(b"\r\n", pos)
        if end == -1:
            return None
        try:
            size = int(buf[pos + 1 : end])
        except ValueError:
            return None
        start = end + 2
        pos = start + size + 2
        if len(buf) < pos:
            return None
        args.append(buf[start : start + size])
    return pos, args


def _reply_to(args):
    """``HELLO`` gets a handshake map; everything else gets ``+PONG``.

    redis-py checks ``handshake_metadata.get(b"proto") == self.protocol``, so the
    version we echo has to be the one it asked for, as an integer — which is
    what ``Connection(protocol=...)`` holds.
    """
    if args and args[0].upper() == b"HELLO":
        proto = int(args[1]) if len(args) > 1 else 3
        return (
            b"%3\r\n"
            b"$6\r\nserver\r\n$5\r\nredis\r\n"
            b"$7\r\nversion\r\n$5\r\n7.4.0\r\n"
            b"$5\r\nproto\r\n:" + str(proto).encode() + b"\r\n"
        )
    return b"+PONG\r\n"


@pytest.fixture
def resp_server():
    server = _TinyRespServer()
    try:
        yield server
    finally:
        server.close()


#: Both RESP versions, because ``redis>=5.0.1`` is unpinned and the library's
#: default has moved before: RESP3 adds a HELLO handshake to every connection
#: this pool opens. Leaving it to the default meant CI exercised a path the
#: laptop never did.
_PROTOCOLS = ["2", "3"]


@pytest.fixture(params=_PROTOCOLS, ids=lambda p: f"resp{p}")
def real_client(request, resp_server, monkeypatch):
    """A production-path client pointed at the toy server."""
    monkeypatch.setattr(
        redis_state,
        "REDIS_URL",
        f"redis://127.0.0.1:{resp_server.port}/0?protocol={request.param}",
    )
    redis_state.reset_redis_client_cache()
    try:
        yield redis_state.get_redis_client(socket_timeout=5.0, socket_connect_timeout=5.0)
    finally:
        redis_state.reset_redis_client_cache()


class TestTheBudgetHoldsOnRealSockets:
    def test_many_concurrent_callers_never_open_more_sockets_than_the_cap(
        self, resp_server, real_client
    ):
        """The ship, measured where it is spent. Before the cap was re-sized this
        pool was allowed 40 sockets; the process envelope made that 560 against a
        server that accepts 80.
        """
        resp_server.hold = 0.02  # make the callers genuinely overlap
        errors = []
        done = []
        barrier = threading.Barrier(16, timeout=10)

        def _ping():
            try:
                barrier.wait()
                for _ in range(3):
                    real_client.execute_command("PING")
                done.append(1)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_ping) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"a healthy concurrent caller failed: {errors[:3]}"
        assert len(done) == 16, "not every caller completed"
        # Without real overlap the cap is never approached and the two
        # assertions below would hold for any cap at all.
        assert resp_server.peak_concurrent >= 2, (
            "the callers never overlapped, so this proves nothing about the cap"
        )
        assert resp_server.peak_concurrent <= redis_state._REDIS_MAX_CONNECTIONS, (
            f"{resp_server.peak_concurrent} sockets open at once against a cap "
            f"of {redis_state._REDIS_MAX_CONNECTIONS}"
        )
        assert resp_server.accepted <= redis_state._REDIS_MAX_CONNECTIONS, (
            f"{resp_server.accepted} sockets opened in total — the pool is "
            "minting connections rather than reusing them"
        )

    @pytest.mark.parametrize("protocol", _PROTOCOLS, ids=lambda p: f"resp{p}")
    def test_a_saturated_pool_queues_the_caller_instead_of_raising(
        self, resp_server, monkeypatch, protocol
    ):
        """On a plain pool the 3rd of 3 callers gets MaxConnectionsError the
        instant the cap is reached. Here it waits and is served."""
        monkeypatch.setattr(
            redis_state,
            "REDIS_URL",
            f"redis://127.0.0.1:{resp_server.port}/0?protocol={protocol}",
        )
        monkeypatch.setattr(redis_state, "_REDIS_MAX_CONNECTIONS", 2)
        redis_state.reset_redis_client_cache()
        try:
            client = redis_state.get_redis_client()
            assert client.connection_pool.max_connections == 2
            resp_server.hold = 0.15
            errors = []
            served = []
            barrier = threading.Barrier(6, timeout=10)

            def _ping():
                try:
                    barrier.wait()
                    client.execute_command("PING")
                    served.append(1)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=_ping) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            assert not errors, f"a queued caller failed instead of waiting: {errors[:3]}"
            assert len(served) == 6
            assert resp_server.accepted <= 2
        finally:
            redis_state.reset_redis_client_cache()


class TestClosingAClientStillReleasesItsSockets:
    """Building the pool ourselves lost a default that ``from_url`` had set.

    ``Redis.aclose()`` only disconnects the pool when
    ``auto_close_connection_pool`` is true, and ``Redis(connection_pool=...)``
    leaves it false. ``routes/event_stream.py`` closes its client at the end of
    every SSE stream and ``utils/request_cache.py`` closes the shared one at
    shutdown — if those stopped disconnecting their pools, the cap above would
    be enforcing a budget while the sockets leaked out the other side.
    """

    def test_the_sync_client_still_owns_its_pool(self):
        client = redis_state._build_bounded_client(
            "redis://localhost:6379/0",
            redis_state._REDIS_POOL_WAIT,
            max_connections=redis_state._REDIS_MAX_CONNECTIONS,
        )
        assert client.auto_close_connection_pool is True

    def test_the_async_client_still_owns_its_pool(self):
        assert redis_state.get_async_redis_client().auto_close_connection_pool is True

    @pytest.mark.asyncio
    async def test_aclose_actually_disconnects_the_async_pool(self):
        """The property that matters, not just the flag that implies it."""
        client = redis_state.get_async_redis_client()
        disconnected = []
        original = client.connection_pool.disconnect

        async def _spy(*args, **kwargs):
            disconnected.append(True)
            return await original(*args, **kwargs)

        client.connection_pool.disconnect = _spy
        await client.aclose()
        assert disconnected, "aclose() left the pool's connections open"
