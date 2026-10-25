"""#10225 — a transient outcome-arm shed never replaces a live COMPLETE answer.

THE DEFECT (LAT-P241's own stated residual). An outcome-arm shed is cacheable
(#3399), because a term that sheds on every request has no fuller answer to wait
for. But the write was an unconditional `setex`, so a term that normally
completes and sheds ONCE wrote its thinner body over its own complete entry, and
every reader of that term got the thinner answer for the 65 s TTL. Sentry
BAINLUCK-14R put 99.1% of those sheds in the warmer — the one caller that
rebuilds OVER a live entry.

THE FIX. A shed body goes through `_typeahead_publish_thinner`: it leaves a live
complete entry exactly as it is (bytes and TTL), and writes only into an empty,
expired or already-thin slot, through the compare-and-set #2311 introduced. A
complete body still writes unconditionally.

EVERY CONTROL BELOW DRIVES THE REAL ROUTE. The warmer controls run
`typeahead_warmer._warm_one` → `typeahead_search` end to end on a mocked session;
only the outcome arm's answer (shed or not) and Redis are doubled. The fake
Redis's `eval` is dispatched on script IDENTITY and models Redis's documented
semantics; `TestTheRealLua` runs the same decisions against a real redis-server
when `redislite` is installed.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_mod
from app.tasks import typeahead_warmer as warmer
from app.utils import event_concept_cache as cache_mod
from app.utils.typeahead_beat_budget import RESPONSE_CACHE_TTL_S

Q = "us open"
KEY = f"bainluck:typeahead:{Q}"
T0 = 1_790_000_000.0


def _b(v):
    return v.encode() if isinstance(v, str) else v


class FakeRedis:
    """String get/setex/ttl with a clock, the #2311 compare-and-set, and a
    swallowing pipeline for the trending write."""

    def __init__(self):
        self.now = T0
        self.store: dict[str, bytes] = {}
        self.expires_at: dict[str, float] = {}
        self.writes: list[str] = []
        self.trending: list[str] = []

    def _live(self, k):
        if k in self.expires_at and self.expires_at[k] <= self.now:
            self.store.pop(k, None)
            self.expires_at.pop(k, None)
        return self.store.get(k)

    def get(self, k):
        return self._live(k)

    def setex(self, k, ttl, v):
        self.writes.append(k)
        self.store[k] = _b(v)
        self.expires_at[k] = self.now + int(ttl)
        return True

    def ttl(self, k):
        if self._live(k) is None:
            return -2
        return int(round(self.expires_at[k] - self.now))

    def eval(self, script, numkeys, *args):
        assert script is cache_mod._SETEX_IF_UNCHANGED_LUA, "unexpected script"
        key, absent_only, expected, ttl, value = args
        current = self._live(key)
        if absent_only == "1":
            if current is not None:
                return 0
        elif current != _b(expected):
            return 0
        self.setex(key, ttl, value)
        return 1

    def pipeline(self, transaction=True):
        rc = self

        class _P:
            def zincrby(self, key, amount, member):
                rc.trending.append(member)
                return self

            def expire(self, *a):
                return self

            def execute(self):
                return []

        return _P()


def _empty_result():
    r = MagicMock()
    r.scalars.return_value.all.return_value = []
    r.scalars.return_value.unique.return_value.all.return_value = []
    r.scalars.return_value.first.return_value = None
    r.scalar_one_or_none.return_value = None
    r.scalar.return_value = None
    r.fetchall.return_value = []
    r.all.return_value = []
    r.first.return_value = None
    return r


class _FuturesTimeout(Exception):
    pass


def _session(futures_times_out: bool = False):
    session = AsyncMock()

    async def _execute(stmt, *a, **k):
        if futures_times_out:
            sql = str(stmt)
            if "futures_markets" in sql and "ORDER BY" in sql.upper():
                raise _FuturesTimeout()
        return _empty_result()

    session.execute = AsyncMock(side_effect=_execute)
    return session


@pytest.fixture
def rc(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: client)
    monkeypatch.setattr(events_mod, "get_redis_client", lambda *a, **k: client, raising=False)
    monkeypatch.setattr(warmer, "get_redis_client", lambda *a, **k: client, raising=False)
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    return client


@pytest.fixture
def arm(monkeypatch):
    """`arm.shed = True` makes the outcome arm shed, exactly as its bound does."""

    class _Arm:
        shed = False

    state = _Arm()

    async def _resolve(*a, **k):
        return None if state.shed else []

    monkeypatch.setattr(events_mod, "_resolve_typeahead_outcome_arm", _resolve)
    return state


async def _warm(rc, arm, *, shed: bool, session=None):
    """One warm, in its OWN task as `_warm_head_concurrently` runs it — `_warm_one`
    sets `_suppress_trending_write` without resetting it, which is only safe
    because each warm owns a context copy."""
    arm.shed = shed
    return await asyncio.create_task(
        warmer._warm_one(session or _session(), Q, refresh_ahead=10_000)
    )


async def _reader(arm, *, shed: bool, **kw):
    arm.shed = shed
    kw.setdefault("debug_evidence", False)
    kw.setdefault("debug_timing", False)
    return await events_mod.typeahead_search(q=Q, db=kw.pop("db", _session()), **kw)


def _stored(rc):
    raw = rc.get(KEY)
    return None if raw is None else json.loads(raw)


def _is_thin(body):
    return body is not None and body.get("degraded") == ["outcome_names"]


def _is_complete(body):
    return body is not None and "suggestions" in body and not body.get("degraded")


# ---------------------------------------------------------------------------


class TestTheHarnessIsReal:
    """Non-vacuity: both builds really reach the route's cache write, and they
    really differ in the one way this file is about."""

    async def test_a_complete_build_writes_a_complete_body(self, rc, arm):
        out = await _warm(rc, arm, shed=False)
        assert out["reason"] == "warmed"
        assert _is_complete(_stored(rc))

    async def test_a_shed_build_into_an_empty_slot_writes_a_thin_body(self, rc, arm):
        out = await _warm(rc, arm, shed=True)
        assert out["reason"] == "warmed"
        assert _is_thin(_stored(rc))


class TestCompleteThenTransientShed:
    """THE REPRODUCTION. RED on `2f18107550`: the shed body replaced the complete
    one and the warmer called it `warmed`."""

    async def test_a_shed_rebuild_keeps_the_live_complete_entry(self, rc, arm):
        await _warm(rc, arm, shed=False)
        complete_bytes = rc.get(KEY)
        rc.now += 20

        out = await _warm(rc, arm, shed=True)

        assert rc.get(KEY) == complete_bytes, (
            "a transient shed replaced the live complete answer — #10225"
        )
        assert out["reason"] == "retained" and out["rebuilt"] is False

    async def test_the_retained_entry_is_not_refreshed(self, rc, arm):
        """Not rewritten, so not made to look newly computed: its TTL keeps
        running down from the complete build's own write."""
        await _warm(rc, arm, shed=False)
        rc.now += 20
        writes_before = len(rc.writes)

        out = await _warm(rc, arm, shed=True)

        assert len(rc.writes) == writes_before
        assert rc.ttl(KEY) == RESPONSE_CACHE_TTL_S - 20
        assert out["ttl_after"] == RESPONSE_CACHE_TTL_S - 20

    async def test_the_retained_entry_still_expires_on_its_own_clock(self, rc, arm):
        await _warm(rc, arm, shed=False)
        rc.now += 20
        await _warm(rc, arm, shed=True)
        rc.now += RESPONSE_CACHE_TTL_S - 20
        assert rc.get(KEY) is None


class TestPartialThenComplete:
    async def test_a_complete_build_replaces_a_thin_entry(self, rc, arm):
        await _warm(rc, arm, shed=True)
        rc.now += 30

        out = await _warm(rc, arm, shed=False)

        assert _is_complete(_stored(rc))
        assert rc.ttl(KEY) == RESPONSE_CACHE_TTL_S
        assert out["reason"] == "warmed"


class TestPermanentShedStaysCacheable:
    """#3399, unchanged: a term that sheds every time is cached, refreshed by the
    warmer, and never reported as a `no_write` defect."""

    async def test_a_thin_entry_is_refreshed_by_the_next_thin_build(self, rc, arm):
        await _warm(rc, arm, shed=True)
        first = rc.get(KEY)
        rc.now += 30

        out = await _warm(rc, arm, shed=True)

        assert _is_thin(_stored(rc))
        assert rc.ttl(KEY) == RESPONSE_CACHE_TTL_S
        assert out["reason"] == "warmed" and out["rebuilt"] is True
        assert rc.get(KEY) == first  # same content, rewritten

    async def test_a_reader_miss_that_sheds_is_cached(self, rc, arm):
        """The organic path: the slot is empty, so the shed answer is the best
        one there is and the next keystroke must not pay the build again."""
        body = await _reader(arm, shed=True)
        assert body["degraded"] == ["outcome_names"]
        assert _is_thin(_stored(rc))


class TestExpiredIsNotRevived:
    async def test_after_the_complete_entry_expires_a_shed_build_fills_the_slot(
        self, rc, arm
    ):
        await _warm(rc, arm, shed=False)
        rc.now += RESPONSE_CACHE_TTL_S + 1
        assert rc.get(KEY) is None

        out = await _warm(rc, arm, shed=True)

        assert _is_thin(_stored(rc)), "the expired complete answer came back"
        assert rc.ttl(KEY) == RESPONSE_CACHE_TTL_S
        assert out["reason"] == "warmed"


class TestWholeFuturesLossIsStillNeverCached:
    """LAT-P007, unchanged: losing the futures stage is never written — not into
    an empty slot, not over a thin one, not over a complete one."""

    @pytest.fixture(autouse=True)
    def _timeout_is_a_timeout(self, monkeypatch):
        real = events_mod._is_query_timeout
        monkeypatch.setattr(
            events_mod, "_is_query_timeout",
            lambda exc: isinstance(exc, _FuturesTimeout) or real(exc),
        )

    async def test_the_harness_reaches_the_futures_timeout(self, rc, arm):
        body = await _reader(arm, shed=False, db=_session(futures_times_out=True))
        assert "futures" in body.get("degraded", []), "the futures stage did not time out"

    @pytest.mark.parametrize("prior", [None, "thin", "complete"])
    @pytest.mark.parametrize("shed", [False, True])
    async def test_a_degraded_build_writes_nothing(self, rc, arm, prior, shed):
        if prior is not None:
            await _warm(rc, arm, shed=(prior == "thin"))
            # Off the full-TTL ceiling, so the TTL test can tell no-write from
            # a write (LAT-P270's same-second case).
            rc.now += 20
        before = rc.get(KEY)
        writes = len(rc.writes)

        out = await _warm(rc, arm, shed=shed, session=_session(futures_times_out=True))

        assert len(rc.writes) == writes and rc.get(KEY) == before
        assert out["reason"] == "no_write"


class TestDebugAnswersAreNeverWritten:
    @pytest.mark.parametrize("flag", ["debug_timing", "debug_evidence"])
    @pytest.mark.parametrize("shed", [False, True])
    async def test_a_debug_build_writes_nothing_into_an_empty_slot(self, rc, arm, flag, shed):
        await _reader(arm, shed=shed, **{flag: True})
        assert rc.writes == []

    @pytest.mark.parametrize("flag", ["debug_timing", "debug_evidence"])
    async def test_a_debug_shed_build_leaves_a_thin_entry_alone(self, rc, arm, flag):
        await _warm(rc, arm, shed=True)
        before, writes = rc.get(KEY), len(rc.writes)
        await _reader(arm, shed=True, **{flag: True})
        assert rc.get(KEY) == before and len(rc.writes) == writes


class _RacingRedis(FakeRedis):
    """Runs `between()` once, right after the shed build's read of the entry and
    before its conditional write — the worst interleaving."""

    def __init__(self):
        super().__init__()
        self.between = None

    def eval(self, script, numkeys, *args):
        if self.between is not None:
            hook, self.between = self.between, None
            hook()
        return super().eval(script, numkeys, *args)


@pytest.fixture
def racing(monkeypatch):
    client = _RacingRedis()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: client)
    monkeypatch.setattr(events_mod, "get_redis_client", lambda *a, **k: client, raising=False)
    monkeypatch.setattr(warmer, "get_redis_client", lambda *a, **k: client, raising=False)
    return client


COMPLETE_BYTES = json.dumps({"suggestions": [{"name": "complete"}], "query": Q})
OTHER_THIN = json.dumps(
    {"suggestions": [{"name": "newer thin"}], "query": Q, "degraded": ["outcome_names"]}
)


class TestOverlappingWriters:
    async def test_a_complete_answer_landing_mid_write_survives(self, racing, arm):
        racing.between = lambda: racing.setex(KEY, RESPONSE_CACHE_TTL_S, COMPLETE_BYTES)

        out = await _warm(racing, arm, shed=True)

        assert racing.get(KEY) == COMPLETE_BYTES.encode()
        assert out["reason"] == "superseded" and out["rebuilt"] is False

    async def test_a_newer_thin_answer_landing_mid_write_is_not_clobbered(
        self, racing, arm
    ):
        await _warm(racing, arm, shed=True)
        racing.now += 30
        racing.between = lambda: racing.setex(KEY, RESPONSE_CACHE_TTL_S, OTHER_THIN)

        out = await _warm(racing, arm, shed=True)

        assert racing.get(KEY) == OTHER_THIN.encode()
        assert out["reason"] == "superseded"

    async def test_an_entry_expiring_mid_write_is_not_refilled_from_a_stale_read(
        self, racing, arm
    ):
        await _warm(racing, arm, shed=True)
        racing.now += 30

        def _expire():
            racing.now += RESPONSE_CACHE_TTL_S

        racing.between = _expire

        out = await _warm(racing, arm, shed=True)

        assert racing.get(KEY) is None
        # F1: nothing usable is stored, so this is the master grading — not an
        # ok `superseded` over an empty slot.
        assert out["reason"] == "no_write" and out["ok"] is False

    async def test_a_complete_answer_landing_over_a_full_ttl_is_still_superseded(
        self, racing, arm
    ):
        """The ceiling case (LAT-P270): the slot was at a full TTL when read and
        the other writer's entry lands at a full TTL too — `65 > 65` is false."""
        racing.setex(KEY, RESPONSE_CACHE_TTL_S, OTHER_THIN)
        racing.between = lambda: racing.setex(KEY, RESPONSE_CACHE_TTL_S, COMPLETE_BYTES)

        out = await _warm(racing, arm, shed=True)

        assert out["ttl_before"] == RESPONSE_CACHE_TTL_S
        assert out["reason"] == "superseded" and out["ok"] is True


class _RefusingRedis(FakeRedis):
    """A Redis that REFUSES writes, as an OOM'd or read-only one does. The
    compare-and-set swallows the error and reports False — the same answer it
    gives when another writer landed. #10225 F1."""

    def __init__(self, *, refuse_setex: bool = False):
        super().__init__()
        self.refuse_setex = refuse_setex
        self.refusing = False

    def eval(self, script, numkeys, *args):
        if self.refusing:
            raise RuntimeError("OOM command not allowed when used memory > 'maxmemory'")
        return super().eval(script, numkeys, *args)

    def setex(self, k, ttl, v):
        if self.refusing and self.refuse_setex:
            raise RuntimeError("OOM command not allowed when used memory > 'maxmemory'")
        return super().setex(k, ttl, v)


def _install(monkeypatch, client):
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: client)
    monkeypatch.setattr(events_mod, "get_redis_client", lambda *a, **k: client, raising=False)
    monkeypatch.setattr(warmer, "get_redis_client", lambda *a, **k: client, raising=False)
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    return client


def _pass_harness(monkeypatch):
    """Run `_warm_typeahead` for real with its locks and ring bookkeeping stubbed."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _sess():
        yield _session()

    monkeypatch.setattr("app.tasks.base.get_task_session", _sess)
    monkeypatch.setattr(warmer, "_acquire_run_lock", lambda: "tok")
    monkeypatch.setattr(warmer, "_release_run_lock", lambda *a: None)
    monkeypatch.setattr(warmer, "_renew_run_lock", lambda *a: True)
    monkeypatch.setattr(warmer, "_seconds_since_last_pass", lambda now: None)
    monkeypatch.setattr(warmer, "_record_pass_start", lambda now: None)
    monkeypatch.setattr(warmer, "_record_outcome", lambda *a, **k: None)
    monkeypatch.setattr(warmer, "REFRESH_AHEAD_SECONDS", 10_000)


class TestARefusedWriteIsNotSuperseded:
    """#10225 F1 (lane1's review of ae8115331a). RED on that head: a shed term
    over an empty slot with Redis refusing writes read `superseded`, ok,
    `terminal=complete`, with nothing stored. Master graded it `no_write`."""

    @pytest.mark.parametrize("refuse_setex", [False, True], ids=["eval", "eval+setex"])
    async def test_a_shed_term_over_an_empty_slot_is_a_no_write(
        self, monkeypatch, arm, refuse_setex
    ):
        client = _install(monkeypatch, _RefusingRedis(refuse_setex=refuse_setex))
        client.refusing = True

        out = await _warm(client, arm, shed=True)

        assert client.get(KEY) is None
        assert out["reason"] == "no_write" and out["ok"] is False

    @pytest.mark.parametrize("refuse_setex", [False, True], ids=["eval", "eval+setex"])
    async def test_the_pass_reports_the_defect_as_master_does(
        self, monkeypatch, arm, refuse_setex
    ):
        client = _install(monkeypatch, _RefusingRedis(refuse_setex=refuse_setex))
        client.refusing = True
        arm.shed = True
        _pass_harness(monkeypatch)

        summary = await warmer._warm_typeahead(queries=[Q], concurrency=1)

        assert summary["no_writes"] == [Q]
        assert summary["superseded"] == []
        assert summary["warmed"] == 0
        assert summary["terminal"] == "partial"

    async def test_a_live_thin_entry_plus_a_refused_write_is_a_no_write(
        self, monkeypatch, arm
    ):
        """Its TTL has decayed and nobody rewrote it, so the re-read cannot
        mistake it for another writer's entry."""
        client = _install(monkeypatch, _RefusingRedis())
        await _warm(client, arm, shed=True)
        client.now += 30
        client.refusing = True

        out = await _warm(client, arm, shed=True)

        assert _is_thin(_stored(client))
        assert out["ttl_after"] == RESPONSE_CACHE_TTL_S - 30
        assert out["reason"] == "no_write" and out["ok"] is False

    async def test_an_unreadable_re_read_is_unverified_not_graded(
        self, racing, arm, monkeypatch
    ):
        """Redis silent on the TTL re-read: the instrument is out, so neither an
        ok `superseded` nor a `no_write` defect — the `warmed_unverified` rule."""
        reads = {"n": 0}
        real_ttl = racing.ttl

        def _ttl(k):
            reads["n"] += 1
            if reads["n"] > 1:
                raise ConnectionError("redis went away")
            return real_ttl(k)

        racing.ttl = _ttl
        racing.between = lambda: racing.setex(KEY, RESPONSE_CACHE_TTL_S, COMPLETE_BYTES)

        out = await _warm(racing, arm, shed=True)

        assert out["reason"] == "superseded_unverified"
        assert out["ok"] is True and out["ttl_after"] is None


class TestReaderSemanticsAreUnchanged:
    async def test_the_shed_requester_gets_its_own_answer(self, rc, arm):
        """The retained entry is for the NEXT reader; this response is still the
        build it ran, declared as shed (#1740)."""
        rc.setex(KEY, RESPONSE_CACHE_TTL_S, COMPLETE_BYTES)
        token = events_mod._force_cache_rebuild.set(True)
        try:
            body = await _reader(arm, shed=True)
        finally:
            events_mod._force_cache_rebuild.reset(token)
        assert body["degraded"] == ["outcome_names"]
        assert rc.get(KEY) == COMPLETE_BYTES.encode()

    async def test_a_reader_hit_serves_the_retained_complete_answer(self, rc, arm):
        await _warm(rc, arm, shed=False)
        await _warm(rc, arm, shed=True)
        body = await _reader(arm, shed=True)
        assert _is_complete(body)

    async def test_a_reader_is_counted_and_the_warmer_is_not(self, rc, arm):
        await _warm(rc, arm, shed=True)
        assert rc.trending == []
        await _reader(arm, shed=True)
        assert rc.trending == [Q]

    async def test_a_reader_request_has_no_receipt(self):
        assert events_mod._typeahead_cache_receipt.get() is None


class TestThePassSummary:
    async def test_a_retained_term_is_neither_rebuilt_nor_a_defect(
        self, rc, arm, monkeypatch
    ):
        await _warm(rc, arm, shed=False)
        rc.now += 40
        arm.shed = True
        _pass_harness(monkeypatch)

        summary = await warmer._warm_typeahead(queries=[Q], concurrency=1)

        assert summary["retained"] == [Q]
        assert summary["no_writes"] == []
        assert summary["rebuilt"] == 0
        assert summary["terminal"] == "complete"

    async def test_a_verified_superseded_term_is_ok_and_listed(
        self, racing, arm, monkeypatch
    ):
        racing.between = lambda: racing.setex(KEY, RESPONSE_CACHE_TTL_S, COMPLETE_BYTES)
        arm.shed = True
        _pass_harness(monkeypatch)

        summary = await warmer._warm_typeahead(queries=[Q], concurrency=1)

        assert summary["superseded"] == [Q]
        assert summary["no_writes"] == [] and summary["unverified"] == 0
        assert summary["terminal"] == "complete"


class TestTheRealLua:
    """The helper's three decisions on a real redis-server."""

    @pytest.fixture
    def server(self, tmp_path):
        redislite = pytest.importorskip("redislite")
        srv = redislite.Redis(str(tmp_path / "ta.rdb"))
        try:
            yield srv
        finally:
            srv.shutdown()

    THIN = json.dumps({"suggestions": [], "query": Q, "degraded": ["outcome_names"]})

    def test_a_live_complete_entry_is_retained_untouched(self, server):
        server.setex(KEY, 65, COMPLETE_BYTES)
        server.expire(KEY, 40)
        assert events_mod._typeahead_publish_thinner(server, KEY, 65, self.THIN) == "retained"
        assert server.get(KEY) == COMPLETE_BYTES.encode()
        assert 38 <= server.ttl(KEY) <= 40

    def test_an_empty_slot_is_filled(self, server):
        assert events_mod._typeahead_publish_thinner(server, KEY, 65, self.THIN) == "written"
        assert server.get(KEY) == self.THIN.encode() and server.ttl(KEY) > 60

    def test_a_thin_entry_is_refreshed(self, server):
        server.setex(KEY, 20, OTHER_THIN)
        assert events_mod._typeahead_publish_thinner(server, KEY, 65, self.THIN) == "written"
        assert server.get(KEY) == self.THIN.encode() and server.ttl(KEY) > 60


class TestCompletenessReadsTheExistingContract:
    @pytest.mark.parametrize(
        "raw,complete",
        [
            (None, False),
            (b"", False),
            (b"not json", False),
            (b"[]", False),
            (json.dumps({"query": Q}), False),
            (COMPLETE_BYTES, True),
            (json.dumps({"suggestions": [], "query": Q, "degraded": []}), True),
            (OTHER_THIN, False),
        ],
    )
    def test_degraded_absent_or_empty_is_complete(self, raw, complete):
        assert events_mod._typeahead_cached_body_is_complete(raw) is complete
