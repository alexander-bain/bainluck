"""#10090 — a slow removal notification never stalls another game or a healthy
price, an older retry never replaces the latest state, and a replacement
consumer adopts every owed removal at startup and recycle, on real PostgreSQL
and real Redis.

## the ship

Peer source-removal sends and healthy prices keep progressing without an older
retry replacing the latest state, and a recycled worker keeps adopting the
removals its predecessor still owed.

## where these cases come from

The peer-publication groups are the accepted lab cases of attempts 128 and 134
(the frozen packets under
``artifacts/live-iteration-goal-20261011/local-blended-web-20261016/``),
ported with their assertions so they travel with the application source they
judge. Nothing here reads an artifact directory; the lab's result files became
assertion messages.

* attempt128 ``test_peer_publication.py`` / ``test_peer_redis.py`` — event 2's
  removal reaches its subscriber while event 1's removal acknowledgement is
  held (recording sink, then a real Redis socket).
* attempt128 ``test_peer_controls.py`` — two send slots, same-event exclusion,
  full drain; fresh custody bypasses an older backoff without resetting it;
  the final drain attempts each custody once; a cancelled joiner leaves both
  sends running and teardown joins both.
* attempt128 ``test_publication_failure.py`` — a SELECT/DELETE failure in the
  publication owner never ends the price flush; backoff then recovery; an
  explicit teardown cancels and joins the owner, retaining custody.
* attempt134 ``test_publication_debt_backoff.py`` (the CORRECTED file Lane1
  accepted) — a committed removal reaches a quiet reader after cancel,
  connection loss and restart; a late notification never overrides a newer
  revision or a final; a publish error retains the owed notification; the
  actual cadence recovers after connection loss; a real-Redis ambiguous
  acknowledgement replays the identical revision.
* attempt134 ``test_release_controls.py`` — P1's same-event split (newer
  custody first, older retry later, retained latest frame stays the newer)
  and P2's real four-connection BlockingConnectionPool with two removal
  acknowledgements held while a healthy stamped price still reaches its
  subscriber.

The startup/recycle group is NEW in this port (not a lab file). Root retired
attempt132's startup flag (ruling on Lane1's 132 review, option A): normal
startup recovery stays, so a replacement consumer's FIRST load adopts both the
``polymarket_withdrawal`` rows and the ``_publish`` notification custody its
predecessor left, both transaction guards stay active on normal and final
flushes, and an own uncertain commit recovers before or after that first load.
The retired flag's OFF/ON mode cases stay historical in the 132 packet; the
recycle case's ``"0"`` arm only proves the retired name cannot turn startup
adoption off.

## the rig

#10090's withdrawal-debt rig (``test_pm_withdrawal_debt_10090_pg``) over the
release-wake rig: the shipped flush closures on the consumer's own pool, real
stamps, and a recording Redis that acknowledges a frame only after an
independent connection reads the committed row. The socket cases use a REAL
Redis: a private ``redis-server`` (``EVENT_FRAME_REDIS_SERVER`` or ``PATH``),
else the loopback server ``PM_WITHDRAWAL_REDIS_URL`` names (CI's job-local
``redis:7`` service, its own logical db, flushed around each case). Neither
present is a FAILURE, never a skip.

Synthetic rows on one machine: order and coherence, not production timing.
The 1 s bounds are the lab's own bounds.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from sqlalchemy import text

from app.tasks import polymarket_ws as pm
from app.utils.blend_preview import is_preview_frame
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
    seed,
)
from tests.integration.test_pm_stamp_release_wake_10090_pg import (
    _Pool,
    start_cadence,
    stop_cadence,
)
from tests.integration.test_pm_withdrawal_debt_10090_pg import (  # noqa: F401
    WIDE,
    consumer,
    flush,
    prime,
    setup,
    state,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

OWNER = pm.PM_WITHDRAWAL_DEBT_SOURCE + "_owner"
PUBLISH = pm.PM_WITHDRAWAL_DEBT_SOURCE + "_publish"
#: attempt132's retired startup flag. Only the recycle case names it, to prove
#: the retired name cannot switch startup adoption off.
RETIRED_FLAG = "PM_WS_STARTUP_WITHDRAWAL_RECOVERY"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


# ------------------------------------------------------------------ real Redis


class RedisEndpoint(SimpleNamespace):
    """How to reach the case's real Redis: ``client()`` for an ordinary
    client, ``blocking_pool()`` for a real redis-py BlockingConnectionPool."""

    def client(self):
        from redis.asyncio import Redis

        return Redis(**self.client_kwargs)

    def blocking_pool(self, *, max_connections, timeout):
        from redis.asyncio import BlockingConnectionPool

        return BlockingConnectionPool(
            connection_class=self.connection_class,
            max_connections=max_connections,
            timeout=timeout,
            **self.connection_kwargs,
        )


@pytest.fixture
def real_redis():
    binary = os.environ.get("EVENT_FRAME_REDIS_SERVER") or shutil.which("redis-server")
    url = os.environ.get("PM_WITHDRAWAL_REDIS_URL")
    if binary:
        from redis.asyncio.connection import UnixDomainSocketConnection

        with tempfile.TemporaryDirectory(prefix="pm-withdrawal-10090-") as tmp:
            sock = Path(tmp) / "redis.sock"
            with (Path(tmp) / "redis.log").open("w") as log:
                process = subprocess.Popen(
                    [
                        binary,
                        "--port",
                        "0",
                        "--unixsocket",
                        str(sock),
                        "--save",
                        "",
                        "--appendonly",
                        "no",
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 3
                    while not sock.exists():
                        if process.poll() is not None:
                            pytest.fail((Path(tmp) / "redis.log").read_text())
                        if time.monotonic() > deadline:
                            pytest.fail("private Redis startup timed out")
                        time.sleep(0.01)
                    yield RedisEndpoint(
                        client_kwargs={"unix_socket_path": str(sock)},
                        connection_class=UnixDomainSocketConnection,
                        connection_kwargs={"path": str(sock)},
                    )
                finally:
                    process.terminate()
                    process.wait(timeout=5)
        return
    if url:
        import redis
        from redis.asyncio.connection import Connection

        parsed = urlparse(url)
        db = int((parsed.path or "/0").lstrip("/") or 0)
        if parsed.scheme != "redis" or parsed.hostname not in LOOPBACK or db == 0:
            pytest.fail(
                f"PM_WITHDRAWAL_REDIS_URL must be a loopback redis:// URL with a "
                f"dedicated non-zero db (it is FLUSHED), got {url!r}"
            )
        kwargs = {"host": parsed.hostname, "port": parsed.port or 6379, "db": db}
        sync = redis.Redis(socket_timeout=5, **kwargs)
        sync.flushdb()
        try:
            yield RedisEndpoint(
                client_kwargs=kwargs,
                connection_class=Connection,
                connection_kwargs=kwargs,
            )
        finally:
            sync.flushdb()
            sync.close()
        return
    pytest.fail(
        "no real Redis: set EVENT_FRAME_REDIS_SERVER (a redis-server binary) or "
        "PM_WITHDRAWAL_REDIS_URL (a loopback server, dedicated db)"
    )


@pytest.fixture
async def default_preview_redis(monkeypatch, real_redis, consumer, rig):
    """Run default DNPL Lua alongside the independently checked commit sink.

    The recording connection implements committed packed publications only.
    Give preview commands a real transport instead of treating its missing
    send_command method as a simulated Redis outage on every healthy flush.
    Explicit _client failures in the cases still fail before this transport.
    """
    from app.tasks.live_blend_refresh import LiveBlendRefresher
    from tests.integration.test_pm_stamp_release_wake_10090_pg import _Connection
    from tests.integration.test_pm_nongame_first_wait_10090_pg import warm_price_statement
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from pathlib import Path
    from uuid import uuid4
    import runpy
    from app.services.dnpl_authority import AuthorityStore, preparing_candidate
    from app.services.dnpl_activation import ActivationController
    from app.utils import blend_preview

    # These cases inject publication faults into a running price consumer.
    # Prepare asyncpg's array types on its five connections before arming the
    # unchanged 250 ms price deadline; no rows are changed by the warmup.
    await warm_price_statement(consumer)
    client = real_redis.client()
    blend_preview.reset_registry_for_tests()

    def upgrade(conn):
        with Operations.context(MigrationContext.configure(conn)):
            for name in ('dnpl_authority_10090.py', 'dnpl_retirement_10090.py'):
                runpy.run_path(str(Path(__file__).parents[2] / 'alembic/versions' / name))['upgrade']()

    async with rig.engine.begin() as conn:
        await conn.run_sync(upgrade)
    store = AuthorityStore(rig.maker)
    server, repl = await client.info('server'), await client.info('replication')
    old = await store.read()
    current = await store.prepare(old, preparing_candidate(
        old, namespace=uuid4(), operation_id=uuid4(), redis_run_id=server['run_id'],
        redis_master_replid=repl['master_replid'],
        policy_fingerprint=blend_preview.registry().policy.fingerprint,
    ))
    controller = ActivationController(store, client)
    await controller.arm(current)
    await controller.initialize(current)
    await controller.ready(current)
    await blend_preview.registry().bind_primary(store)
    shipped = LiveBlendRefresher._preview_call
    monkeypatch.setattr(
        LiveBlendRefresher, "_preview_call",
        staticmethod(lambda connection: client.execute_command
                     if isinstance(connection, _Connection) else shipped(connection)),
    )
    try:
        yield
    finally:
        await client.aclose()
        blend_preview.reset_registry_for_tests()


async def next_message(pubsub, timeout=1):
    async with asyncio.timeout(timeout):
        while True:
            item = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.02
            )
            if item:
                return json.loads(item["data"])


# --------------------------------------------------------------------- helpers


@contextlib.asynccontextmanager
async def committing(rig):
    async with rig.maker() as db:
        yield db
        await db.commit()


async def custody_counts(rig):
    """attempt134's corrected `counts`: the ownership fence row is exactly one
    and is not custody; every other withdrawal row is unpaid custody."""
    async with rig.engine.connect() as conn:
        rows = dict(
            (
                await conn.execute(
                    text(
                        "SELECT source, count(*) FROM owed_chart_points GROUP BY source"
                    )
                )
            ).all()
        )
    owner_rows = rows.pop(OWNER, 0)
    assert owner_rows == 1, rows
    # Withdrawal rows only: a stamp's price publication intent
    # (`polymarket_price_publish`, #10090 attempt151) is a different duty,
    # settled by the refresher's next recovery opportunity.
    return {
        source: count for source, count in rows.items()
        if source.startswith(pm.PM_WITHDRAWAL_DEBT_SOURCE)
    }


async def make(rig):
    """attempt128 ``test_peer_controls.make``: a debt over three seeded events
    whose custody is recorded through the real ``record_publications``."""
    await seed(rig, count=3)
    sessions = lambda: committing(rig)  # noqa: E731
    debt = pm.PMWithdrawalDebt()
    await debt.load(sessions)

    async def add(eid):
        async with sessions() as db:
            rev = await db.scalar(
                text("SELECT win_probability_sources_rev FROM events WHERE id=:id"),
                {"id": eid},
            )
            rows = await debt.record_publications(
                db, [{"event_id": eid, "rev": {str(eid): rev}, "invalidation": True}]
            )
        debt.publications.update(rows)
        return next(iter(rows))

    ref = SimpleNamespace(
        _last_written_value={}, _last_refresh_at={}, _last_snapshot_at={}
    )
    return debt, sessions, add, ref


def ack(frames):
    return {(f["event_id"], f["rev"][str(f["event_id"])]) for f in frames}


# ------------------------------------------- attempt128: peer publication


async def test_new_peer_removal_publishes_while_first_ack_is_held(
    rig, consumer, monkeypatch
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    t.accept(2, 0.62)
    await flush(t)
    assert any(e == 2 and v == 0.62 for _, e, v, _ in t.pubs)
    entered = asyncio.Event()
    release = asyncio.Event()
    sent = {}
    active = 0
    max_active = 0
    original = t.r._publish

    async def publish(frames):
        nonlocal active, max_active
        if not any(f.get("invalidation") for f in frames):
            return await original(frames)
        active += 1
        max_active = max(max_active, active)
        try:
            if any(f["event_id"] == 1 for f in frames):
                entered.set()
                await release.wait()
            result = await original(frames)
            for f in frames:
                if f.get("invalidation"):
                    sent[f["event_id"]] = time.monotonic()
            return result
        finally:
            active -= 1

    t.r._publish = publish
    t.p.ns["withdraw_buffer"][1] = WIDE
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    result = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        accepted = time.monotonic()
        t.p.ns["withdraw_buffer"][2] = WIDE
        deadline = accepted + 1.15
        while 2 not in sent and time.monotonic() < deadline:
            await asyncio.sleep(0.003)
        elapsed = None if 2 not in sent else sent[2] - accepted
        result = {
            "peer_input_to_publication_seconds": elapsed,
            "peer_delivered_while_first_held": 2 in sent,
            "peer_oldest_outstanding_seconds": (
                0 if 2 in sent else time.monotonic() - accepted
            ),
            "controlled_first_still_held": not release.is_set() and 1 not in sent,
            "max_concurrent_removal_sends": max_active,
            "eligible_peer_count": 1,
            "delivered_peer_count": int(2 in sent),
        }
        release.set()
        async with asyncio.timeout(2):
            while len(t.invalidations) < 2:
                await asyncio.sleep(0.003)
        await t.r.withdrawal_debt.join_publications()
        result.update(
            final_invalidations=list(t.invalidations),
            remaining_publications=len(t.r.withdrawal_debt.publications),
            all_send_tasks_finished=active == 0,
        )
        assert elapsed is not None and elapsed < 1, result
        assert result["controlled_first_still_held"] and max_active <= 2, result
        assert (
            len(t.invalidations) == 2
            and not t.r.withdrawal_debt.publications
            and active == 0
        ), result
        async with rig.engine.connect() as db:
            assert (
                await db.scalar(
                    text(
                        "SELECT count(*) FROM events WHERE id IN (1,2) "
                        "AND win_probability_sources ? 'polymarket'"
                    )
                )
            ) == 0
    finally:
        release.set()
        await stop_cadence(t, stop, cadence)
        await t.r.withdrawal_debt.join_publications(cancel=True)


async def test_real_redis_peer_flows_while_first_socket_ack_is_held(
    rig, consumer, monkeypatch, real_redis
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    t.accept(2, 0.62)
    await flush(t)
    assert any(e == 2 and v == 0.62 for _, e, v, _ in t.pubs)
    from app.utils.live_push import event_channel, latest_frame_key

    client = real_redis.client()
    subscriber = real_redis.client()
    pubsub = subscriber.pubsub()
    held = asyncio.Event()
    release = asyncio.Event()
    active = set()
    max_event_sockets = 0

    class Connection:
        def __init__(self, raw):
            self.raw = raw
            self.removals = set()

        def pack_commands(self, commands):
            nonlocal max_event_sockets
            for cmd in commands:
                if cmd[0] == "EVAL":
                    frame = json.loads(cmd[5])
                    if frame.get("invalidation"):
                        self.removals.add(frame["event_id"])
            if self.removals:
                active.add(self)
                max_event_sockets = max(max_event_sockets, len(active))
            return self.raw.pack_commands(commands)

        async def send_packed_command(self, *a, **kw):
            return await self.raw.send_packed_command(*a, **kw)

        async def read_response(self):
            if 1 in self.removals:
                held.set()
                await release.wait()
            return await self.raw.read_response()

        async def disconnect(self):
            await self.raw.disconnect()

    class Pool:
        async def get_connection(self, *a, **kw):
            return Connection(await client.connection_pool.get_connection(*a, **kw))

        async def release(self, conn):
            active.discard(conn)
            await client.connection_pool.release(conn.raw)

    await client.ping()
    await pubsub.subscribe(event_channel(2))
    await pubsub.get_message(timeout=1)
    t.r._client = lambda: SimpleNamespace(connection_pool=Pool())
    stop = asyncio.Event()
    cadence = None
    try:
        t.p.ns["withdraw_buffer"][1] = WIDE
        cadence = start_cadence(t, stop)
        await asyncio.wait_for(held.wait(), 2)
        accepted = time.monotonic()
        t.p.ns["withdraw_buffer"][2] = WIDE
        peer = None
        elapsed = None
        deadline = accepted + 1.15
        while time.monotonic() < deadline:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.02
            )
            if message:
                peer = json.loads(message["data"])
                elapsed = time.monotonic() - accepted
                break
        result = {
            "peer_input_to_redis_subscriber_seconds": elapsed,
            "peer_delivered_before_ack_release": peer is not None,
            "peer_oldest_outstanding_seconds": (
                0 if peer else time.monotonic() - accepted
            ),
            "max_removal_sockets": max_event_sockets,
            "first_ack_still_held": not release.is_set(),
            "peer": peer,
        }
        release.set()
        async with asyncio.timeout(2):
            while t.r.withdrawal_debt.publications:
                await asyncio.sleep(0.003)
        await t.r.withdrawal_debt.join_publications()
        result["remaining_publications"] = len(t.r.withdrawal_debt.publications)
        result["active_removal_sockets_after_join"] = len(active)
        result["first_retained_frame"] = json.loads(
            await client.get(latest_frame_key(1))
        )
        assert elapsed is not None and elapsed < 1, result
        assert (
            peer["event_id"] == 2
            and peer["invalidation"]
            and peer["reconcile"]["event_id"] == 2
        )
        assert result["first_ack_still_held"] and max_event_sockets <= 2
        assert not active and not t.r.withdrawal_debt.publications
        async with rig.engine.connect() as db:
            assert (
                await db.scalar(
                    text(
                        "SELECT count(*) FROM events WHERE id IN (1,2) "
                        "AND win_probability_sources ? 'polymarket'"
                    )
                )
            ) == 0
    finally:
        release.set()
        if cadence is not None:
            await stop_cadence(t, stop, cadence)
        await t.r.withdrawal_debt.join_publications(cancel=True)
        await pubsub.aclose()
        await subscriber.aclose()
        await client.aclose()


# ---------------------------------------------- attempt128: peer controls


async def test_two_slots_same_event_exclusion_and_full_drain(rig):
    debt, sessions, add, ref = await make(rig)
    releases = {i: asyncio.Event() for i in [1, 2, 3]}
    entered = {i: asyncio.Event() for i in [1, 2, 3]}
    active = set()
    max_active = 0
    calls = []

    async def publish(frames):
        nonlocal max_active
        events = {f["event_id"] for f in frames}
        assert active.isdisjoint(events), "same-event sends overlap"
        active.update(events)
        max_active = max(max_active, len(active))
        calls.extend(f["reconcile"]["custody_id"] for f in frames)
        try:
            for eid in events:
                entered[eid].set()
            await asyncio.gather(*(releases[eid].wait() for eid in events))
            return ack(frames)
        finally:
            active.difference_update(events)

    ref._publish = publish
    try:
        c1 = await add(1)
        await debt.publish_pending(ref, sessions, background=True)
        await asyncio.wait_for(entered[1].wait(), 1)
        c1b = await add(1)
        c2 = await add(2)
        await debt.publish_pending(ref, sessions, background=True)
        await asyncio.wait_for(entered[2].wait(), 1)
        c3 = await add(3)
        for _ in range(20):
            await debt.publish_pending(ref, sessions, background=True)
        await asyncio.sleep(0.02)
        assert len(debt._publication_claims) == 2 and not entered[3].is_set()
        assert calls.count(f"pm-withdrawal:{c1b}") == 0
        second = next(t for t, batch in debt._publication_claims.items() if c2 in batch)
        releases[2].set()
        await asyncio.wait_for(asyncio.shield(second), 1)
        releases[3].set()
        await debt.publish_pending(ref, sessions, background=True)
        await asyncio.wait_for(entered[3].wait(), 1)
        assert not releases[1].is_set()
        releases[1].set()
        await debt.join_publications()
        await debt.publish_pending(ref, sessions)
        assert not debt.publications and not debt._publication_claims
        assert max_active == 2
        assert Counter(calls) == Counter(
            f"pm-withdrawal:{cid}" for cid in [c1, c1b, c2, c3]
        )
    finally:
        for event in releases.values():
            event.set()
        await debt.join_publications(cancel=True)


async def test_fresh_peer_bypasses_old_backoff_without_resetting_it(rig):
    debt, sessions, add, ref = await make(rig)
    calls = []
    fail = True

    async def publish(frames):
        calls.extend(f["event_id"] for f in frames)
        return {item for item in ack(frames) if item[0] != 1 or not fail}

    ref._publish = publish
    await add(1)
    await debt.publish_pending(ref, sessions)
    retry = debt._publication_retry_at
    assert retry > time.monotonic()
    await add(2)
    await debt.publish_pending(ref, sessions)
    assert calls == [1, 2] and len(debt.publications) == 1
    assert debt._publication_retry_at == retry
    for _ in range(20):
        await debt.publish_pending(ref, sessions, background=True)
    assert calls == [1, 2]
    fail = False
    await asyncio.sleep(max(0, retry - time.monotonic()) + 0.01)
    await debt.publish_pending(ref, sessions)
    assert calls == [1, 2, 1] and not debt.publications


async def test_final_attempts_each_custody_once_even_after_failure(rig):
    debt, sessions, add, ref = await make(rig)
    calls = []

    async def publish(frames):
        calls.extend(f["reconcile"]["custody_id"] for f in frames)
        return set()

    ref._publish = publish
    c1 = await add(1)
    c2 = await add(2)
    for _ in range(4):
        await debt.publish_pending(ref, sessions, final=True)
    assert Counter(calls) == Counter([f"pm-withdrawal:{c1}", f"pm-withdrawal:{c2}"])
    c3 = await add(3)
    for _ in range(4):
        await debt.publish_pending(ref, sessions, final=True)
    assert Counter(calls) == Counter(f"pm-withdrawal:{cid}" for cid in [c1, c2, c3])
    assert len(debt.publications) == 3 and not debt._publication_claims


async def test_joiner_cancel_keeps_both_sends_and_teardown_joins_both(rig):
    debt, sessions, add, ref = await make(rig)
    entered = {1: asyncio.Event(), 2: asyncio.Event()}
    release = asyncio.Event()

    async def publish(frames):
        for frame in frames:
            entered[frame["event_id"]].set()
        await release.wait()
        return ack(frames)

    ref._publish = publish
    try:
        for eid in [1, 2]:
            await add(eid)
            await debt.publish_pending(ref, sessions, background=True)
            await asyncio.wait_for(entered[eid].wait(), 1)
        owners = list(debt._publication_claims)
        assert len(owners) == 2
        joiner = asyncio.create_task(debt.join_publications())
        await asyncio.sleep(0)
        joiner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await joiner
        assert all(not task.done() and not task.cancelling() for task in owners)
        cleanup = asyncio.create_task(debt.join_publications(cancel=True))
        await asyncio.sleep(0.02)
        assert not cleanup.done()
        release.set()
        await asyncio.wait_for(cleanup, 1)
        assert all(task.done() and task.cancelled() for task in owners)
        assert (
            not debt._publication_claims
            and debt._publication_task is None
            and debt._peer_publication_task is None
        )
        assert len(debt.publications) == 2
        async with sessions() as db:
            n = await db.scalar(
                text("SELECT count(*) FROM owed_chart_points WHERE source=:source"),
                {"source": PUBLISH},
            )
            assert n == 2
    finally:
        release.set()
        await debt.join_publications(cancel=True)


# ---------------------------------------- attempt128: publication failure


async def refused_once(t):
    """attempt128 ``test_publication_failure.pending``: the first removal
    notification is refused, so its custody stays owed."""
    original = t.r._client

    def broken():
        raise ConnectionError("initial Redis refusal")

    t.r._client = broken
    t.p.ns["withdraw_buffer"][1] = WIDE
    await flush(t)
    t.r._client = original
    assert t.r.withdrawal_debt.publications
    return t.r.withdrawal_debt


@pytest.mark.parametrize("stage", ["select", "delete"])
async def test_owner_database_error_does_not_end_next_price_flush(
    rig, consumer, monkeypatch, stage
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    debt = await refused_once(t)
    factory = t.p.ns["get_task_session"]
    failures = []
    peer = []
    original = t.r._publish

    async def recorded(frames):
        result = await original(frames)
        if any(f.get("event_id") == 2 and not f.get("invalidation") for f in frames):
            peer.append(time.monotonic())
        return result

    t.r._publish = recorded

    @contextlib.asynccontextmanager
    async def faulty():
        async with factory() as session:
            execute = session.execute

            async def injected(statement, *args, **kw):
                query = str(statement).upper()
                if asyncio.current_task().get_name() == (
                    "polymarket-withdrawal-publication"
                ) and (
                    (stage == "select" and "SELECT EVENTS.ID" in query)
                    or (stage == "delete" and "DELETE FROM OWED_CHART_POINTS" in query)
                ):
                    failures.append(time.monotonic())
                    raise ConnectionError(
                        "controlled publication " + stage + " failure"
                    )
                return await execute(statement, *args, **kw)

            session.execute = injected
            yield session

    t.p.ns["get_task_session"] = faulty
    # Force one owner attempt after priming; backoff policy is tested separately.
    if hasattr(debt, "_publication_retry_at"):
        debt._publication_retry_at = 0
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    failure = None
    try:
        async with asyncio.timeout(2):
            while not failures:
                await asyncio.sleep(0.002)
        accepted = time.monotonic()
        t.accept(2, 0.73)
        deadline = time.monotonic() + 1.1
        while not peer and not cadence.done() and time.monotonic() < deadline:
            await asyncio.sleep(0.002)
        if cadence.done():
            try:
                cadence.result()
            except BaseException as exc:
                failure = repr(exc)
        result = {
            "stage": stage,
            "loop_stopped": cadence.done(),
            "escaped_error": failure,
            "failures": len(failures),
            "eligible_count": 1,
            "delivered_count": len(peer),
            "max_completed_seconds": peer[0] - accepted if peer else None,
            "oldest_outstanding_seconds": 0 if peer else time.monotonic() - accepted,
            "pending": len(debt.publications),
        }
        assert peer and peer[0] - accepted < 1 and not cadence.done(), result
        # A second fresh quote proves the same loop remains useful after reaping.
        t.accept(2, 0.77)
        async with asyncio.timeout(1):
            while len(peer) < 2:
                await asyncio.sleep(0.002)
        assert debt.publications
    finally:
        t.p.ns["get_task_session"] = factory
        if not cadence.done():
            await stop_cadence(t, stop, cadence)
        if debt._publication_task is not None:
            try:
                await debt._publication_task
            except BaseException:
                pass
        await t.boundary.join_stamps()
        await t.r.drain_history()


async def test_failed_publication_backs_off_then_recovers_original_custody(
    rig, consumer, monkeypatch
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    debt = await refused_once(t)
    assert debt._publication_retry_at > time.monotonic()
    calls = []
    original = debt._publish_pending_once

    async def recorded(*args):
        calls.append(time.monotonic())
        return await original(*args)

    debt._publish_pending_once = recorded
    for _ in range(20):
        await debt.publish_pending(t.r, t.p.ns["get_task_session"], background=True)
    assert not calls and debt.publications
    # Real elapsed retry interval, not weakened correctness or discarded rows.
    await asyncio.sleep(max(0, debt._publication_retry_at - time.monotonic()) + 0.01)
    await debt.publish_pending(t.r, t.p.ns["get_task_session"])
    assert len(calls) == 1 and not debt.publications and len(t.invalidations) == 1


async def test_explicit_teardown_cancels_and_joins_owner_retaining_custody(
    rig, consumer, monkeypatch
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    debt = await refused_once(t)
    entered = asyncio.Event()
    release = asyncio.Event()
    original = t.r._publish

    async def delayed(frames):
        entered.set()
        await release.wait()
        return await original(frames)

    t.r._publish = delayed
    debt._publication_retry_at = 0
    await debt.publish_pending(t.r, t.p.ns["get_task_session"], background=True)
    await asyncio.wait_for(entered.wait(), 1)
    owner = debt._publication_task
    cleanup = asyncio.create_task(debt.join_publications(cancel=True))
    await asyncio.sleep(0.01)
    assert not cleanup.done()
    release.set()
    await asyncio.wait_for(cleanup, 1)
    assert (
        owner.done()
        and owner.cancelled()
        and debt._publication_task is None
        and debt.publications
    )


# ------------------------- attempt134: publication debt backoff (corrected)


async def arm_commit_cut(t, monkeypatch, mode):
    armed = {"ready": False, "fired": False}
    original = pm.withdraw_attributed_event_sources

    async def removed(*args, **kw):
        result = await original(*args, **kw)
        if result:
            armed["ready"] = True
        return result

    monkeypatch.setattr(pm, "withdraw_attributed_event_sources", removed)
    factory = t.p.ns["get_task_session"]
    original_publish = t.r._publish
    t.recovery_publications = []

    async def observed_publish(frames):
        result = await original_publish(frames)
        for f in frames:
            if f.get("invalidation"):
                t.recovery_publications.append(time.monotonic())
        return result

    t.r._publish = observed_publish

    @contextlib.asynccontextmanager
    async def sessions(*args, **kw):
        async with factory(*args, **kw) as session:
            yield session
        if armed["ready"] and not armed["fired"]:
            armed["fired"] = True
            armed["cut_at"] = time.monotonic()
            if mode == "connection":
                raise ConnectionError(
                    "injected connection loss after committed removal / context close"
                )
            raise asyncio.CancelledError(
                "injected cancellation after committed removal"
            )

    t.p.ns["get_task_session"] = sessions
    return factory, armed


async def cut_at_removal_commit(t, monkeypatch, mode):
    factory, armed = await arm_commit_cut(t, monkeypatch, mode)
    t.p.ns["withdraw_buffer"][1] = WIDE
    try:
        await flush(t)
    except asyncio.CancelledError:
        pass
    assert armed["fired"]
    t.cut_mono = armed["cut_at"]
    return factory


@pytest.mark.parametrize("mode", ["cancel", "connection", "restart"])
async def test_committed_removal_reaches_quiet_reader(rig, consumer, monkeypatch, mode):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    factory = await cut_at_removal_commit(t, monkeypatch, mode)
    cut = await state(rig)
    assert cut.source is None and cut.vertices == 1
    custody = await custody_counts(rig)
    t.p.ns["get_task_session"] = factory
    t.p.ns["withdraw_buffer"].clear()
    if mode == "restart":
        t.r.withdrawal_debt = pm.PMWithdrawalDebt()
    started = time.monotonic()
    await asyncio.sleep(0.25)
    await flush(t)
    result = {
        "mode": mode,
        "cut": vars(cut),
        "custody_after_cut": custody,
        "invalidations": list(t.invalidations),
        "recovery_ms": (
            None
            if not t.invalidations
            else (t.recovery_publications[0] - t.cut_mono) * 1000
        ),
        "oldest_outstanding_seconds": (
            0 if t.invalidations else time.monotonic() - started
        ),
        "remaining_custody": await custody_counts(rig),
        "final": vars(await state(rig)),
    }
    await flush(t)
    result["after_repeat_count"] = len(t.invalidations)
    assert len(t.invalidations) == 1 and result["remaining_custody"] == {}, result
    assert result["final"]["vertices"] == 1 and result["recovery_ms"] < 1000, result


@pytest.mark.parametrize("mode", ["newer", "terminal", "terminal_status_only"])
async def test_late_notification_does_not_override_newer_revision(
    rig, consumer, monkeypatch, mode
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    factory = await cut_at_removal_commit(t, monkeypatch, "cancel")
    t.p.ns["get_task_session"] = factory
    t.p.ns["withdraw_buffer"].clear()
    async with rig.engine.begin() as conn:
        if mode == "newer":
            await conn.execute(
                text(
                    "UPDATE futures_outcomes SET current_probability=.7,"
                    "last_updated=clock_timestamp() WHERE id=1"
                )
            )
        elif mode == "terminal_status_only":
            await conn.execute(
                text(
                    "UPDATE events SET status='completed',"
                    "completed_at=clock_timestamp() WHERE id=1"
                )
            )
        else:
            await conn.execute(
                text(
                    "UPDATE events SET status='completed',completed_at=clock_timestamp(),"
                    "win_probability_sources=win_probability_sources||"
                    "jsonb_build_object('settlement',jsonb_build_object('value',1)) "
                    "WHERE id=1"
                )
            )
    if mode == "newer":
        await asyncio.sleep(0.25)
        await t.r.refresh([1])
        await t.r.drain_history()
        # The late removal is a reconcile-only control carrying its ORIGINAL
        # revision; it must not replace current truth. Lane1 134 N1: this sink
        # refuses any other frame BY NAME (a price, or a frame without
        # `reconcile_only`), and a refused send keeps custody, so it cannot
        # pass vacuously.
        t.reconciliations = []

        async def reconcile_sink(frame):
            if frame.get("reconcile_only") is not True:
                raise AssertionError(
                    f"newer-revision sink received a non-reconcile frame: {frame}"
                )
            assert frame["invalidation"] is True
            assert frame["reconcile"]["removal_rev"] == frame["rev"]
            async with rig.engine.connect() as db:
                current = await db.scalar(
                    text("SELECT win_probability_sources_rev FROM events WHERE id=1")
                )
            assert current > frame["rev"]["1"]
            assert (await state(rig)).source["value"] == 0.7
            t.reconciliations.append(frame)

        t.r._client = lambda: SimpleNamespace(connection_pool=_Pool(reconcile_sink))
    await flush(t)
    final = await state(rig)
    result = {
        "mode": mode,
        "state": vars(final),
        "invalidations": t.invalidations,
        "remaining_custody": await custody_counts(rig),
    }
    assert not result["remaining_custody"], result
    if mode == "newer":
        # Lane1 134 N1: the original recorder is off this path, so the
        # guarantee is the sink's per-frame assertions plus these two.
        assert final.source["value"] == 0.7
        assert len(t.reconciliations) == 1
    else:
        assert not t.invalidations, result


async def test_publish_error_retains_owed_notification(
    rig, consumer, monkeypatch, default_preview_redis,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    old = t.r._client

    def broken():
        raise ConnectionError("injected Redis unavailable before write")

    t.r._client = broken
    t.p.ns["withdraw_buffer"][1] = WIDE
    await flush(t)
    held = await custody_counts(rig)
    assert (await state(rig)).source is None and not t.invalidations
    t.r._client = old
    t.p.ns["withdraw_buffer"].clear()
    await asyncio.sleep(
        max(0, t.r.withdrawal_debt._publication_retry_at - time.monotonic()) + 0.01
    )
    await flush(t)
    result = {
        "custody_after_publish_failure": held,
        "invalidations": t.invalidations,
        "remaining_custody": await custody_counts(rig),
        "vertices": (await state(rig)).vertices,
    }
    assert (
        len(t.invalidations) == 1
        and result["vertices"] == 1
        and not result["remaining_custody"]
    ), result


async def test_actual_cadence_after_connection_loss(rig, consumer, monkeypatch):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    factory, armed = await arm_commit_cut(t, monkeypatch, "connection")
    t.p.ns["withdraw_buffer"][1] = WIDE
    stop = asyncio.Event()
    cadence = start_cadence(t, stop)
    try:
        started = time.monotonic()
        deadline = started + 3.0
        while not t.recovery_publications and time.monotonic() < deadline:
            await asyncio.sleep(0.002)
        elapsed = (
            None
            if not t.invalidations
            else t.recovery_publications[0] - armed["cut_at"]
        )
        result = {
            "mode": "actual-cadence-connection-loss",
            "recovery_ms": None if elapsed is None else elapsed * 1000,
            "oldest_outstanding_seconds": (
                0 if elapsed is not None else time.monotonic() - armed["cut_at"]
            ),
            "invalidations": t.invalidations,
            "flush_starts": t.flush_starts,
            "remaining_custody": await custody_counts(rig),
            "final": vars(await state(rig)),
        }
        assert len(t.invalidations) == 1 and elapsed is not None and elapsed < 1, result
    finally:
        await stop_cadence(t, stop, cadence)


async def test_real_redis_ambiguous_ack_retains_then_replays_identical_revision(
    rig, consumer, monkeypatch, real_redis
):
    from app.utils.live_push import event_channel, latest_frame_key

    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    # The lab's `skip` for a source without publication custody is dropped: the
    # source this file judges has it, and a skip here would hide its absence.
    assert hasattr(t.r.withdrawal_debt, "publications")
    factory = await cut_at_removal_commit(t, monkeypatch, "cancel")
    t.p.ns["get_task_session"] = factory
    t.p.ns["withdraw_buffer"].clear()
    client = real_redis.client()
    subscriber = real_redis.client()
    pubsub = subscriber.pubsub()

    class Connection:
        def __init__(self, c):
            self.c = c

        def pack_commands(self, commands):
            return self.c.pack_commands(commands)

        async def send_packed_command(self, *a, **kw):
            return await self.c.send_packed_command(*a, **kw)

        async def read_response(self):
            raise ConnectionError(
                "injected lost acknowledgement after actual Redis send"
            )

        async def disconnect(self):
            await self.c.disconnect()

    class Pool:
        async def get_connection(self, *a, **kw):
            return Connection(await client.connection_pool.get_connection(*a, **kw))

        async def release(self, c):
            await client.connection_pool.release(c.c)

    previews = []

    async def message():
        # Default DNPL shares the channel with committed publications. Only
        # its recognized preview frames lack committed revision identity.
        async with asyncio.timeout(2):
            while True:
                value = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.1
                )
                if value:
                    frame = json.loads(value["data"])
                    if is_preview_frame(frame):
                        previews.append(frame)
                        continue
                    return frame

    try:
        await client.ping()
        await pubsub.subscribe(event_channel(1))
        await pubsub.get_message(timeout=1)
        t.r._client = lambda: SimpleNamespace(connection_pool=Pool())
        await flush(t)
        first = await message()
        pending = await custody_counts(rig)
        assert pending.get(PUBLISH) == 1, pending
        assert json.loads(await client.get(latest_frame_key(1))) == first
        t.r._client = lambda: client
        await asyncio.sleep(
            max(0, t.r.withdrawal_debt._publication_retry_at - time.monotonic()) + 0.01
        )
        await flush(t)
        second = await message()
        remaining = await custody_counts(rig)
        assert second == first and not remaining and (await state(rig)).vertices == 1
        # A subsequent real stamped source outranks a late duplicate removal.
        async with rig.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE futures_outcomes SET current_probability=.7,"
                    "last_updated=clock_timestamp() WHERE id=1"
                )
            )
        await asyncio.sleep(0.25)
        await t.r.refresh([1])
        await t.r.drain_history()
        newer = await message()
        assert newer["rev"]["1"] > first["rev"]["1"]
        await t.r._publish([first])
        replayed = await message()
        retained = json.loads(await client.get(latest_frame_key(1)))
        result = {
            "first": first,
            "retry": second,
            "pending_after_ambiguous_send": pending,
            "remaining_after_ack": remaining,
            "newer": newer,
            "previews": previews,
            "late_duplicate": replayed,
            "retained": retained,
            "vertices": (await state(rig)).vertices,
        }
        assert retained == newer and replayed == first, result
    finally:
        await pubsub.aclose()
        await subscriber.aclose()
        await client.aclose()


# --------------------------------------- attempt134: release controls P1/P2


async def test_newer_same_event_custody_precedes_old_retry_without_latest_regression(
    rig, real_redis
):
    from app.tasks.live_blend_refresh import LiveBlendRefresher
    from app.utils.live_push import event_channel, latest_frame_key

    debt, sessions, add, _ = await make(rig)
    ref = LiveBlendRefresher("polymarket", session_factory=sessions)
    client = real_redis.client()
    subscriber = real_redis.client()
    pubsub = subscriber.pubsub()
    attempts = []
    original = ref._publish

    async def unavailable(frames):
        attempts.extend(frames)
        return set()

    ref._publish = unavailable
    try:
        old = await add(1)
        old_rev = dict(debt.publications[old]["rev"])
        # Reach the real two-second retry backoff, without changing its clock.
        for _ in range(4):
            await asyncio.sleep(max(0, debt._publication_retry_at - time.monotonic()))
            await debt.publish_pending(ref, sessions)
        retry_at = debt._publication_retry_at
        async with sessions() as db:
            await db.execute(
                text(
                    "UPDATE events SET win_probability_sources=jsonb_build_object("
                    "'polymarket',jsonb_build_object('value',.7)) WHERE id=1"
                )
            )
            await db.execute(
                text("UPDATE events SET win_probability_sources='{}'::jsonb WHERE id=1")
            )
        new = await add(1)
        new_rev = dict(debt.publications[new]["rev"])
        assert new_rev["1"] > old_rev["1"]
        ref._publish = original
        ref._client = lambda: client
        await pubsub.subscribe(event_channel(1))
        await pubsub.get_message(timeout=1)
        assert time.monotonic() < retry_at
        await debt.publish_pending(ref, sessions)
        newer = await next_message(pubsub)
        assert newer["reconcile"]["custody_id"] == f"pm-withdrawal:{new}"
        assert newer["rev"] == new_rev and not newer["reconcile_only"]
        assert set(debt.publications) == {old}
        assert debt._publication_retry_at == retry_at
        await asyncio.sleep(max(0, retry_at - time.monotonic()) + 0.01)
        await debt.publish_pending(ref, sessions)
        older = await next_message(pubsub)
        assert older["rev"] == old_rev and older["reconcile_only"] is True
        assert older["reconcile"]["removal_rev"] == old_rev
        assert older["reconcile"]["custody_id"] == f"pm-withdrawal:{old}"
        retained = json.loads(await client.get(latest_frame_key(1)))
        assert retained == newer and not debt.publications
        async with sessions() as db:
            remaining = await db.scalar(
                text("SELECT count(*) FROM owed_chart_points WHERE source=:s"),
                {"s": PUBLISH},
            )
        assert remaining == 0, dict(
            newer=newer,
            older=older,
            retained=retained,
            remaining=remaining,
            failed_attempts=len(attempts),
        )
    finally:
        await debt.join_publications(cancel=True)
        await pubsub.aclose()
        await subscriber.aclose()
        await client.aclose()


async def test_four_connection_pool_keeps_healthy_price_flow_with_two_removal_acks_held(
    rig, consumer, monkeypatch, real_redis
):
    from app.tasks import redis_state
    from app.utils.live_push import event_channel

    # The demonstrated scope (Lane1 134 P2): the consumer's ONE pool at the
    # source defaults, cap 4 / wait 2 s. A moved default needs a re-derivation.
    assert (redis_state._REDIS_MAX_CONNECTIONS, redis_state._REDIS_POOL_WAIT) == (
        4,
        2.0,
    )
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    t.accept(2, 0.62)
    await flush(t)
    pool = real_redis.blocking_pool(max_connections=4, timeout=2)
    client = real_redis.client()
    subscriber = real_redis.client()
    pubsub = subscriber.pubsub()
    entered = {1: asyncio.Event(), 2: asyncio.Event()}
    release = asyncio.Event()
    active = set()
    removal_sockets = set()
    checkout_waits = []
    peak = 0

    class Connection:
        def __init__(self, raw, wait):
            self.raw = raw
            self.wait = wait
            self.removals = set()
            self.price = False

        def pack_commands(self, commands):
            for cmd in commands:
                if cmd[0] == "EVAL":
                    frame = json.loads(cmd[5])
                    if frame.get("invalidation"):
                        self.removals.add(frame["event_id"])
                    elif frame.get("event_id") == 3:
                        self.price = True
                        checkout_waits.append(self.wait)
            if self.removals:
                removal_sockets.add(self)
            return self.raw.pack_commands(commands)

        async def send_packed_command(self, *a, **kw):
            return await self.raw.send_packed_command(*a, **kw)

        async def read_response(self):
            if self.removals:
                for eid in self.removals:
                    entered[eid].set()
                await release.wait()
            return await self.raw.read_response()

        async def disconnect(self):
            await self.raw.disconnect()

    class Pool:
        async def get_connection(self, *a, **kw):
            nonlocal peak
            started = time.monotonic()
            raw = await pool.get_connection(*a, **kw)
            conn = Connection(raw, time.monotonic() - started)
            active.add(conn)
            peak = max(peak, len(active))
            return conn

        async def release(self, conn):
            active.discard(conn)
            removal_sockets.discard(conn)
            await pool.release(conn.raw)

    t.r._client = lambda: SimpleNamespace(connection_pool=Pool())
    stop = asyncio.Event()
    cadence = None
    try:
        await pubsub.subscribe(event_channel(3))
        await pubsub.get_message(timeout=1)
        t.p.ns["withdraw_buffer"][1] = WIDE
        cadence = start_cadence(t, stop)
        await asyncio.wait_for(entered[1].wait(), 2)
        t.p.ns["withdraw_buffer"][2] = WIDE
        await asyncio.wait_for(entered[2].wait(), 2)
        assert (
            len(removal_sockets) == 2
            and len(t.r.withdrawal_debt._publication_claims) == 2
        )
        accepted = time.monotonic()
        t.accept(3, 0.64)
        frame = await next_message(pubsub)
        elapsed = time.monotonic() - accepted
        result = dict(
            input_to_subscriber_seconds=elapsed,
            price_checkout_seconds=checkout_waits,
            peak_borrowers=peak,
            held_removal_sockets=len(removal_sockets),
            frame=frame,
            release_set=release.is_set(),
            pool_cap=pool.max_connections,
            pool_wait=pool.timeout,
        )
        assert (
            frame["event_id"] == 3
            and frame["source_value"] == 0.64
            and not frame.get("invalidation")
        ), result
        assert elapsed < 1 and checkout_waits and max(checkout_waits) < 1, result
        assert len(removal_sockets) == 2 and not release.is_set() and peak <= 4, result
        release.set()
        await t.r.withdrawal_debt.join_publications()
        assert not t.r.withdrawal_debt.publications and not removal_sockets
    finally:
        release.set()
        if cadence is not None:
            await stop_cadence(t, stop, cadence)
        await t.r.withdrawal_debt.join_publications(cancel=True)
        await pubsub.aclose()
        await subscriber.aclose()
        await client.aclose()
        await pool.aclose()


# ------------------------------------------ startup and recycle (new here)


async def event_state(rig, eid):
    async with rig.engine.connect() as conn:
        sources = await conn.scalar(
            text("SELECT win_probability_sources FROM events WHERE id = :id"),
            {"id": eid},
        )
        vertices = await conn.scalar(
            text(
                "SELECT count(*) FROM win_prob_snapshots WHERE event_id = :id "
                "AND source = 'polymarket' AND home_win_probability IS NULL "
                "AND (game_state->>'live_source_withdrawal')::boolean IS TRUE"
            ),
            {"id": eid},
        )
    return SimpleNamespace(speaks="polymarket" in sources, vertices=vertices)


@pytest.mark.parametrize("setting", [None, "0"])
async def test_recycle_adopts_both_custody_kinds_at_startup_and_settles_them(
    rig, consumer, monkeypatch, setting, default_preview_redis,
):
    """The outgoing consumer leaves BOTH kinds of custody: event 1's removal
    committed but its notification was refused (a ``_publish`` row), and event
    2's price withdrawal committed but its removal died with the process (a
    ``polymarket_withdrawal`` row). The replacement's startup load — empty
    memory, no book, no catalog entry for either leg — must adopt both and
    fence the outgoing writer; its first flush settles both exactly once while
    a healthy quote on event 3 still publishes."""
    if setting is None:
        monkeypatch.delenv(RETIRED_FLAG, raising=False)
    else:
        monkeypatch.setenv(RETIRED_FLAG, setting)
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    t.accept(2, 0.62)
    await flush(t)
    assert any(e == 2 and v == 0.62 for _, e, v, _ in t.pubs)
    outgoing = t.r.withdrawal_debt
    working = t.r._client

    def refused():
        raise ConnectionError("Redis refused the outgoing consumer's notification")

    # Redis keeps refusing until the outgoing consumer is gone, so no retry of
    # event 1's notification can settle it before the recycle.
    t.r._client = refused
    t.p.ns["withdraw_buffer"][1] = WIDE
    await flush(t)
    shipped = pm.withdraw_attributed_event_sources

    async def died(*_a, **_kw):
        raise RuntimeError("process gone before the removal committed")

    monkeypatch.setattr(pm, "withdraw_attributed_event_sources", died)
    t.p.ns["withdraw_buffer"][2] = WIDE
    assert await flush(t) is False
    monkeypatch.setattr(pm, "withdraw_attributed_event_sources", shipped)
    await outgoing.join_publications(cancel=True)  # the recycle's teardown
    t.r._client = working
    left = await custody_counts(rig)
    assert left == {pm.PM_WITHDRAWAL_DEBT_SOURCE: 1, PUBLISH: 1}, left
    one, two = await event_state(rig, 1), await event_state(rig, 2)
    assert not one.speaks and one.vertices == 1 and two.speaks, (vars(one), vars(two))
    assert not t.invalidations

    t.p.ns["withdraw_buffer"].clear()
    t.p.ns["event_id_by_outcome"].pop(1)
    t.p.ns["event_id_by_outcome"].pop(2)
    replacement = pm.PMWithdrawalDebt()
    t.r.withdrawal_debt = replacement
    loaded = await replacement.load(t.p.ns["get_task_session"])  # startup
    adopted = {
        "loaded_rows": loaded,
        "owed_legs": replacement.legs(),
        "publication_events": [
            f["event_id"] for f in replacement.publications.values()
        ],
        "owner_claimed": replacement._owner_id is not None,
    }
    assert adopted == {
        "loaded_rows": 2,
        "owed_legs": {2: 2},
        "publication_events": [1],
        "owner_claimed": True,
    }, adopted
    with pytest.raises(pm.PMWithdrawalOwnershipDeferred, match="superseded"):
        async with rig.maker() as db:
            await outgoing.guard_owner(db)

    t.accept(3, 0.64)
    assert await flush(t) is True
    assert any(e == 3 and v == 0.64 for _, e, v, _ in t.pubs)
    await flush(t)  # a repeat settles nothing twice
    one, two = await event_state(rig, 1), await event_state(rig, 2)
    result = {
        "invalidations": list(t.invalidations),
        "remaining_custody": await custody_counts(rig),
        "event_1": vars(one),
        "event_2": vars(two),
        "owed": replacement.owed,
        "publications": replacement.publications,
    }
    assert sorted(eid for eid, _ in t.invalidations) == [1, 2], result
    assert result["remaining_custody"] == {}, result
    assert not one.speaks and not two.speaks, result
    assert one.vertices == 1 and two.vertices == 1, result
    assert not replacement.owed and not replacement.publications, result
    async with rig.maker() as db:
        await replacement.guard_owner(db)


async def record_publication(rig, debt):
    async with committing(rig) as db:
        xid = (await db.execute(text("SELECT pg_current_xact_id()::text"))).scalar_one()
        rows = await debt.record_publications(
            db, [{"event_id": 1, "rev": {"1": 0}, "invalidation": True}]
        )
    return xid, rows


@pytest.mark.parametrize("before_initial_load", [False, True])
async def test_own_uncertain_commit_recovers_before_or_after_the_startup_load(
    rig, before_initial_load
):
    """attempt132 ``test_off_keeps_own_uncertain_commit_recovery`` without its
    flag: an own commit whose outcome was uncertain is adopted, and its
    identity retired, whether it predates the consumer's first load or not."""
    await seed(rig, count=1)
    debt = pm.PMWithdrawalDebt()
    if not before_initial_load:
        await debt.load(lambda: committing(rig))
    xid, expected = await record_publication(rig, debt)
    debt.require_reload(xid=xid)
    await debt.load(lambda: committing(rig))
    assert debt.publications == expected and not debt._uncertain_xids


@pytest.mark.parametrize("final", [False, True])
async def test_normal_and_final_flush_take_both_transaction_guards(
    rig, consumer, monkeypatch, final
):
    """attempt132 ``test_off_keeps_both_transaction_guards_chart_and_final_drain``
    without its flag: the price withdrawal and the source removal each take
    the ownership guard in their own transaction, on the normal flush and the
    final drain; the chart keeps one withdrawal vertex and no owed point."""
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    debt = t.r.withdrawal_debt
    guards = []
    original = debt.guard_owner

    async def guarded(db):
        await original(db)
        guards.append(id(db))

    debt.guard_owner = guarded
    t.p.ns["withdraw_buffer"][1] = WIDE
    t.flush_starts.append(None)
    assert await t.p.ns["flush_prices"](flush_started=None, final=final)
    await t.boundary.join_stamps()
    await t.r.drain_history()
    s = await state(rig)
    assert len(guards) == 2 and len(set(guards)) == 2
    assert s.source is None and s.price is None and s.vertices == 1 and s.owed == 0
    assert len(t.invalidations) == 1 and not debt.publications
