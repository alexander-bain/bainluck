"""Guard tests for the `/typeahead` page warmer (#1866, LAT-P056).

The warmer's whole job is that the head of the query distribution is served
from RESIDENT index pages. Two properties matter more than the warming itself,
because both fail SILENTLY, and both are pinned here:

  * **It must actually write.** `/typeahead`'s debug flags default to
    `Query(False)`, a FastAPI marker object that is TRUTHY. A caller that omits
    them makes the route evaluate `not debug_evidence` as False and skip the
    cache write entirely — so the warmer would run every query, warm nothing,
    and report a clean success. That is not a hypothetical: it is the default
    behaviour of the obvious implementation, and nothing about the run's output
    would look wrong (gotcha #53).

  * **It cannot report success while the head is cold.** An empty head is a
    failure of this task's purpose, not a quiet no-op with nothing to do — the
    exact shape of the ten-week zero-yield SUCCESS that `task_verdict` exists to
    prevent.

And one property that keeps it safe to ship: it is **not load-bearing**. A cold
miss still builds inline in the route, so turning the task off makes
`/typeahead` slow again — never broken.
"""

import asyncio
import re
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from app.tasks import typeahead_warmer as warmer
from app.utils.task_verdict import classify_summary


class _FakeSession:
    """Enough session for the warmer: it only rolls back and (maybe) queries."""

    def __init__(self, log_rows=None, raise_on_execute=False):
        self._log_rows = log_rows or []
        self._raise = raise_on_execute
        self.rollbacks = 0

    async def execute(self, *a, **kw):
        if self._raise:
            raise RuntimeError("query log unavailable")

        rows = self._log_rows

        class _R:
            def all(self_inner):
                return [(q,) for q in rows]

        return _R()

    async def rollback(self):
        self.rollbacks += 1


@asynccontextmanager
async def _fake_session_ctx(session):
    yield session


def _patch_session(session):
    return patch(
        "app.tasks.base.get_task_session",
        lambda: _fake_session_ctx(session),
    )


def _patch_session_factory(made: list):
    """Hand out a DISTINCT session per `get_task_session()` call.

    `_patch_session` deliberately returns the same object every time, which is
    fine for every test that predates concurrency — but it makes "each worker
    got its own session" and "all four workers shared one" produce identical
    results. A mutation that passed `[sessions[0]] * width` to the worker pool
    survived the whole suite because of exactly that (LAT-P060 mutation M7).
    """

    def _make():
        session = _FakeSession()
        made.append(session)
        return _fake_session_ctx(session)

    return patch("app.tasks.base.get_task_session", _make)


class _FakeRedis:
    def __init__(self, members=(), lock_taken=False, ttls=None):
        self._members = list(members)
        self.store = {}
        if lock_taken:
            self.store[warmer._LOCK_KEY] = b"1"
        self.deleted = []
        self.ttls = dict(ttls or {})

    def zrevrange(self, key, start, stop):
        assert key == "search:trending:24h"
        return [m.encode() for m in self._members[start:stop + 1]]

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value.encode() if isinstance(value, str) else value
        return True

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)

    # LAT-P060: the refresh-ahead path reads TTLs. Redis `ttl` is three-valued
    # and the fake reproduces all three, because the code's whole point is that
    # -2 and -1 are not the same answer.
    def ttl(self, key):
        if key in self.ttls:
            return self.ttls[key]
        return -2 if key not in self.store else -1


def _patch_redis(redis):
    return patch("app.tasks.redis_state.get_redis_client", lambda *a, **kw: redis)


# --------------------------------------------------------------------------
# THE SILENT NO-OP. This is the test that earns the file.
# --------------------------------------------------------------------------


class TestTheWarmerActuallyWarms:
    async def test_debug_flags_are_passed_explicitly_as_false(self):
        """Omitting them makes the route skip its cache write and warm nothing.

        The assertion is on the VALUE, not merely on the key being present: a
        `Query(False)` sentinel is falsy-looking and truthy-behaving, so
        `"debug_evidence" in kwargs` would pass while the bug is fully intact.
        """
        seen = {}

        async def _fake_route(*, q, debug_evidence, debug_timing, db):
            seen["q"] = q
            seen["debug_evidence"] = debug_evidence
            seen["debug_timing"] = debug_timing
            return {"suggestions": [], "query": q}

        with patch("app.routes.events.typeahead_search", _fake_route):
            result = await warmer._warm_one(_FakeSession(), "red sox")

        assert result["ok"] is True
        assert seen["q"] == "red sox"
        assert seen["debug_evidence"] is False, (
            "must be the literal False — a Query(False) default is TRUTHY and "
            "makes the route skip the cache write"
        )
        assert seen["debug_timing"] is False

    def test_the_warmer_passes_every_marker_defaulted_route_parameter(self):
        """A NEW flag on `/typeahead` would silently re-break the warmer.

        The bug this file exists for is not "we forgot two arguments once" — it
        is that FastAPI marker defaults are truthy, so ANY parameter the warmer
        does not pass arrives as a truthy sentinel. Adding a third debug flag to
        the route would reintroduce the exact failure with no test noticing,
        because every existing test would keep passing.

        So the guard is structural: enumerate the route's marker-defaulted
        parameters and require the warmer to name each one.
        """
        import inspect

        from app.routes import events

        sig = inspect.signature(events.typeahead_search)
        marker_params = {
            name
            for name, p in sig.parameters.items()
            # A FastAPI marker (Query/Depends/Body/...) rather than a plain
            # Python default. `Depends(get_db)` is included deliberately: the
            # warmer must pass a real session for it too.
            if p.default is not inspect.Parameter.empty
            and type(p.default).__module__.startswith("fastapi")
        }

        warmer_src = inspect.getsource(warmer._warm_one)
        missing = {n for n in marker_params if f"{n}=" not in warmer_src}

        assert not missing, (
            f"/typeahead grew marker-defaulted parameter(s) {sorted(missing)} "
            f"that `_warm_one` does not pass. A FastAPI marker default is "
            f"TRUTHY, so the route will take a branch meant for a debug caller "
            f"and the warmer will silently stop warming."
        )

    async def test_route_write_guard_would_reject_the_defaults(self):
        """Pin the reason the test above exists, against the route's real guard.

        If `/typeahead`'s guard is ever restructured, this fails and points at
        the warmer — rather than the warmer quietly becoming a no-op again.
        """
        import inspect

        from app.routes import events

        src = inspect.getsource(events.typeahead_search)
        assert "not debug_evidence and not debug_timing" in src, (
            "the route's cache-READ guard changed shape; re-verify that the "
            "warmer's explicit False arguments still reach a cached write"
        )


# --------------------------------------------------------------------------
# A run that warmed nothing must not read as a healthy run.
# --------------------------------------------------------------------------


class TestZeroYieldIsNotSuccess:
    async def test_empty_head_reports_partial(self):
        session = _FakeSession(log_rows=[])
        with _patch_redis(_FakeRedis([])), _patch_session(session):
            summary = await warmer._warm_typeahead(queries=[])

        assert summary["total"] == 0
        assert summary["warmed"] == 0
        assert summary["terminal"] == "partial", (
            "a warmer that warmed nothing is a failed warmer, not an idle one"
        )
        assert classify_summary(summary) != "green"

    async def test_all_timeouts_reports_partial(self):
        async def _slow(**kw):
            await asyncio.sleep(5)

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _slow), \
                patch.object(warmer, "PER_QUERY_TIMEOUT_SECONDS", 0.01), \
                _patch_session(session):
            summary = await warmer._warm_typeahead(queries=["red sox", "yankees"])

        assert summary["terminal"] == "partial"
        assert summary["warmed"] == 0
        assert sorted(summary["timeouts"]) == ["red sox", "yankees"]


# --------------------------------------------------------------------------
# One bad query must never wipe the pass (gotcha #42).
# --------------------------------------------------------------------------


class TestOneBadQueryDoesNotWipeTheRun:
    async def test_healthy_siblings_survive_a_throwing_query(self):
        async def _route(*, q, debug_evidence, debug_timing, db):
            if q == "boom":
                raise RuntimeError("bad query")
            return {"suggestions": [], "query": q}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), _patch_session(session):
            summary = await warmer._warm_typeahead(
                queries=["red sox", "boom", "yankees"]
            )

        assert summary["warmed"] == 2, "the two healthy queries must still warm"
        assert summary["errors"] == ["boom"]
        assert summary["terminal"] == "partial"
        assert session.rollbacks >= 1, "a failed query must not poison the session"


# --------------------------------------------------------------------------
# The head is measured, and WHICH measurement produced it travels with the run.
# --------------------------------------------------------------------------


class TestHeadResolution:
    async def test_redis_trending_wins_when_present(self):
        session = _FakeSession(log_rows=["from the db"])
        with _patch_redis(_FakeRedis(["stanley cup", "world series"])):
            head, source = await warmer.resolve_head(session, 10)

        assert head == ["stanley cup", "world series"]
        assert source == "redis:search:trending:24h"

    async def test_falls_back_to_query_log_when_zset_empty(self):
        session = _FakeSession(log_rows=["world cup", "fed"])
        with _patch_redis(_FakeRedis([])):
            head, source = await warmer.resolve_head(session, 10)

        assert head == ["world cup", "fed"]
        assert source == "db:search_query_logs:30d"

    async def test_falls_back_to_static_floor_when_both_empty(self):
        session = _FakeSession(log_rows=[])
        with _patch_redis(_FakeRedis([])):
            head, source = await warmer.resolve_head(session, 10)

        assert head == list(warmer._STATIC_FLOOR)
        assert source == "static_floor"

    async def test_a_broken_query_log_falls_through_rather_than_raising(self):
        session = _FakeSession(raise_on_execute=True)
        with _patch_redis(_FakeRedis([])):
            head, source = await warmer.resolve_head(session, 10)

        assert source == "static_floor"
        assert session.rollbacks >= 1

    async def test_head_is_capped_at_the_requested_size(self):
        session = _FakeSession()
        with _patch_redis(_FakeRedis([f"q{i}" for i in range(50)])):
            head, _ = await warmer.resolve_head(session, 5)

        assert len(head) == 5

    async def test_head_source_travels_in_the_summary(self):
        async def _route(*, q, debug_evidence, debug_timing, db):
            return {"suggestions": [], "query": q}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), \
                _patch_redis(_FakeRedis(["stanley cup"])), _patch_session(session):
            summary = await warmer._warm_typeahead()

        assert summary["head_source"] == "redis:search:trending:24h", (
            "which source produced the head changes what the run means; it must "
            "not have to be inferred from the query list"
        )


# --------------------------------------------------------------------------
# The 30s cadence is faster than a cold run, so overlap must be refused.
# --------------------------------------------------------------------------


class TestSingleRunLock:
    async def test_a_second_run_skips_while_one_is_in_flight(self):
        calls = []

        async def _route(*, q, debug_evidence, debug_timing, db):
            calls.append(q)
            return {"suggestions": [], "query": q}

        redis = _FakeRedis(lock_taken=True)
        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), \
                _patch_redis(redis), _patch_session(session):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert calls == [], "a skipped run must not do the work anyway"
        assert summary["terminal"] == "skipped"
        assert classify_summary(summary) != "green", (
            "a run that banked no work cannot vouch for the task's health"
        )

    async def test_skipped_is_in_the_shared_no_work_vocabulary(self):
        """`skipped` must be a terminal `task_verdict` already recognises.

        A bespoke string would classify as `unknown/classifier_error` and the
        distinction between "another run has this" and "the contract broke"
        would be lost at exactly the moment an operator needs it.
        """
        from app.utils.task_verdict import _TERMINAL_NO_WORK

        assert "skipped" in _TERMINAL_NO_WORK

    async def test_the_lock_is_released_even_when_the_run_throws(self):
        async def _boom(*, q, debug_evidence, debug_timing, db):
            raise RuntimeError("nope")

        redis = _FakeRedis()
        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _boom), \
                _patch_redis(redis), _patch_session(session):
            await warmer._warm_typeahead(queries=["red sox"])

        assert warmer._LOCK_KEY in redis.deleted, (
            "a lock held past a failed run wedges the warmer off for its TTL"
        )

    async def test_lock_failure_warms_anyway_rather_than_going_quiet(self):
        """Fails OPEN: a Redis blip must not silently stop the warming."""
        calls = []

        async def _route(*, q, debug_evidence, debug_timing, db):
            calls.append(q)
            return {"suggestions": [], "query": q}

        def _broken(*a, **kw):
            raise RuntimeError("redis down")

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), \
                patch("app.tasks.redis_state.get_redis_client", _broken), \
                _patch_session(session):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert calls == ["red sox"]
        assert summary["warmed"] == 1

    def test_the_lock_ttl_cannot_wedge_the_warmer_permanently(self):
        assert warmer._LOCK_TTL_SECONDS > 0, "a lock with no TTL is a permanent outage"
        assert warmer._LOCK_TTL_SECONDS <= 300, (
            "must expire well inside the 300s hard SIGKILL, or a killed worker "
            "leaves the warmer locked off with nobody able to release it"
        )


# --------------------------------------------------------------------------
# Warming a query the route would reject burns a slot to raise a 422.
# --------------------------------------------------------------------------


class TestQueryBoundsMatchTheRoute:
    def test_bounds_agree_with_the_route_constants(self):
        from app.routes.events import _TYPEAHEAD_MAX_QUERY_CHARS

        assert warmer._MAX_QUERY_CHARS == _TYPEAHEAD_MAX_QUERY_CHARS, (
            "the warmer mirrors the route's max_length; a drift means every "
            "over-long head entry silently 422s on every run"
        )
        assert warmer._MIN_QUERY_CHARS == 2, "the route's min_length"

    async def test_too_short_and_too_long_queries_are_dropped(self):
        calls = []

        async def _route(*, q, debug_evidence, debug_timing, db):
            calls.append(q)
            return {"suggestions": [], "query": q}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), _patch_session(session):
            summary = await warmer._warm_typeahead(
                queries=["a", "ok", "x" * (warmer._MAX_QUERY_CHARS + 1)]
            )

        assert calls == ["ok"]
        assert summary["total"] == 1


# --------------------------------------------------------------------------
# Not load-bearing.
# --------------------------------------------------------------------------


class TestNotLoadBearing:
    def test_the_route_still_builds_inline_on_a_miss(self):
        """Turning the warmer off makes `/typeahead` slow, never broken."""
        import inspect

        from app.routes import events

        src = inspect.getsource(events.typeahead_search)
        # The route owns both halves: it reads the cache, and on a miss it runs
        # the queries itself and writes. Nothing about it is conditional on a
        # warmer having run.
        assert "_cache_key = f\"bainluck:typeahead:" in src
        assert "setex(_cache_key, 45" in src

    async def test_the_task_never_raises_out_of_a_failing_run(self):
        async def _route(**kw):
            raise RuntimeError("everything is on fire")

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), _patch_session(session):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert summary["terminal"] == "partial"
        assert summary["errors"] == ["red sox"]


# --------------------------------------------------------------------------
# LAT-P060 — the two holes that made `-51` deliver about half its benefit.
#
# HOLE 1: the pass (33-59s) outlasted its own 30s beat, so 25 of 50 beats were
#         lock skips and the real repaint period was 95.8s against a 45s TTL.
# HOLE 2: a pass that HIT the cache extended nothing — the route returns the
#         cached body before its own `setex` — so 12 of every 50 beats ran a
#         full 40-query "warm" in 0.65s and rebuilt exactly zero entries.
#
# Hole 2 is the one that makes cadence tuning futile on its own: with pass
# period T the rebuild period is T*ceil(45/T), so a 30s pass lands on a 75%
# duty cycle, not 100%, and a 20s pass is no better than a 30s one.
# --------------------------------------------------------------------------


class TestRefreshAheadActuallyRefreshes:
    async def test_a_near_expiry_entry_is_DROPPED_BEFORE_the_route_is_called(self):
        """The ordering IS the fix, and the wrong order is worse than no fix.

        Drop-then-call makes the route miss, recompute and write a fresh 45s
        TTL. Call-then-drop would evict the entry the route had just written,
        leaving the head permanently cold — a warmer that actively un-warms.
        Both orderings "call delete once and call the route once", so a test
        that only counted calls would pass on the catastrophic one.
        """
        order = []
        rc = _FakeRedis(ttls={"bainluck:typeahead:red sox": 12})

        def _delete(key):
            order.append(("delete", key))
            rc.store.pop(key, None)

        async def _route(*, q, debug_evidence, debug_timing, db):
            order.append(("route", q))
            return {"suggestions": [], "query": q}

        rc.delete = _delete
        with patch("app.routes.events.typeahead_search", _route), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "red sox")

        assert order == [
            ("delete", "bainluck:typeahead:red sox"),
            ("route", "red sox"),
        ], f"drop must precede the route call, got {order}"
        assert result["reason"] == "warmed"
        assert result["dropped"] is True

    async def test_a_genuinely_fresh_entry_is_skipped_and_SAYS_SO(self):
        """`fresh` is its own reason, never folded into `warmed`.

        Before LAT-P060 a pass that rebuilt 40 entries and a pass that read 40
        warm ones back both reported `warmed: 40/40`. That is the ten-week
        `task_verdict` failure in miniature: the summary could not distinguish
        work from the appearance of work.
        """
        called = []
        rc = _FakeRedis(
            ttls={"bainluck:typeahead:red sox": warmer.REFRESH_AHEAD_SECONDS + 1}
        )

        async def _route(**kw):
            called.append(kw["q"])
            return {"suggestions": []}

        with patch("app.routes.events.typeahead_search", _route), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "red sox")

        assert result["reason"] == "fresh"
        assert result["dropped"] is False
        assert called == [], "a fresh entry must not be recomputed"
        assert rc.deleted == [], "a fresh entry must not be dropped"

    async def test_the_boundary_rebuilds_rather_than_skipping(self):
        """At exactly the threshold, do the work. `>` not `>=`, deliberately.

        An entry with exactly one refresh-interval of life left does not
        survive to the next pass in the worst case, and the cost of being wrong
        in the skip direction is a cold user; in the rebuild direction it is
        one redundant hot query.
        """
        rc = _FakeRedis(ttls={"bainluck:typeahead:x y": warmer.REFRESH_AHEAD_SECONDS})

        async def _route(**kw):
            return {"suggestions": []}

        with patch("app.routes.events.typeahead_search", _route), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "x y")

        assert result["reason"] == "warmed"
        assert result["dropped"] is True

    async def test_no_key_means_rebuild_and_does_NOT_issue_a_pointless_delete(self):
        rc = _FakeRedis()  # ttl -> -2 for anything unknown

        async def _route(**kw):
            return {"suggestions": []}

        with patch("app.routes.events.typeahead_search", _route), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "red sox")

        assert result["reason"] == "warmed"
        assert result["ttl_before"] == warmer._TTL_NO_KEY
        assert rc.deleted == [], "nothing was cached; there is nothing to drop"

    async def test_a_key_with_no_expiry_is_rebuilt_not_treated_as_immortal(self):
        """-1 and -2 are opposite answers and must not collapse (gotcha #53)."""
        rc = _FakeRedis()
        rc.store["bainluck:typeahead:red sox"] = b"{}"  # present, ttl -> -1

        async def _route(**kw):
            return {"suggestions": []}

        with patch("app.routes.events.typeahead_search", _route), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "red sox")

        assert result["ttl_before"] == warmer._TTL_NO_EXPIRY
        assert result["reason"] == "warmed"
        assert rc.deleted == ["bainluck:typeahead:red sox"]

    async def test_an_unreadable_redis_rebuilds_rather_than_declaring_everything_fresh(self):
        """Fails toward doing the work, exactly as `_acquire_run_lock` does.

        The dangerous failure is the silent one: a TTL read that errors and is
        read as "plenty of life left" would stop the warmer dead while every
        run still reported `complete`.
        """
        called = []

        class _Broken(_FakeRedis):
            def ttl(self, key):
                raise RuntimeError("redis is down")

        rc = _Broken()

        async def _route(**kw):
            called.append(kw["q"])
            return {"suggestions": []}

        with patch("app.routes.events.typeahead_search", _route), _patch_redis(rc):
            result = await warmer._warm_one(_FakeSession(), "red sox")

        assert result["reason"] == "warmed", "must not skip on an unreadable TTL"
        assert result["ttl_before"] is None
        assert called == ["red sox"]

    def test_the_cache_key_matches_the_route_EXACTLY(self):
        """A drifted prefix would refresh a key nobody reads — silently.

        Every symptom would look like the bug was never fixed: the route would
        keep serving its own untouched entry, the warmer would keep reporting
        `rebuilt: 40`, and the duty cycle would sit back at 47%.
        """
        import inspect

        from app.routes import events

        src = inspect.getsource(events.typeahead_search)
        assert f'_cache_key = f"{warmer._CACHE_KEY_PREFIX}' in src, (
            f"warmer prefix {warmer._CACHE_KEY_PREFIX!r} no longer matches the "
            f"key /typeahead builds; the warmer is refreshing nothing"
        )

    def test_the_route_still_writes_its_cache_ONLY_on_the_miss_path(self):
        """The premise of the whole fix, pinned so it cannot silently invert.

        If `/typeahead` ever starts extending the TTL on a cache HIT, the drop
        becomes unnecessary work AND a needless cold window — this test is the
        prompt to delete `_drop_cached`, not to keep it out of habit.
        """
        import inspect

        from app.routes import events

        src = inspect.getsource(events.typeahead_search)
        read_at = src.index("_cached = _rc.get(_cache_key)")
        write_at = src.index("setex(_cache_key, 45")
        assert read_at < write_at
        assert "return _json.loads(_cached)" in src[read_at:write_at], (
            "the cache READ no longer returns early, so a hit may now reach the "
            "setex; re-derive the duty cycle before trusting REFRESH_AHEAD"
        )


class TestConcurrencyIsRealAndBounded:
    async def test_the_pass_overlaps_instead_of_summing(self):
        """Hole 1. Wall time must be ~total/width, not ~total.

        Graded on the ratio rather than an absolute so it does not become a
        clock-dependent flake (gotcha #44): 8 queries x 50ms serial is 400ms,
        at width 4 it must land nearer 100ms. The bar is deliberately loose.
        """
        rc = _FakeRedis()

        async def _route(**kw):
            await asyncio.sleep(0.05)
            return {"suggestions": []}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), \
                _patch_session(session), _patch_redis(rc):
            summary = await warmer._warm_typeahead(
                queries=[f"query {i}" for i in range(8)], concurrency=4
            )

        assert summary["completed"] == 8
        assert summary["concurrency"] == 4
        assert summary["seconds_total"] >= 0.35, "per-query times still sum"
        assert summary["seconds_wall"] < 0.25, (
            f"wall {summary['seconds_wall']}s is close to the serial sum "
            f"{summary['seconds_total']}s — the pass did not actually overlap"
        )

    async def test_width_one_is_still_correct(self):
        """The degenerate case stays valid; concurrency is not load-bearing."""
        rc = _FakeRedis()

        async def _route(**kw):
            return {"suggestions": []}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), \
                _patch_session(session), _patch_redis(rc):
            summary = await warmer._warm_typeahead(
                queries=["a b", "c d"], concurrency=1
            )

        assert summary["completed"] == 2
        assert summary["concurrency"] == 1

    async def test_results_stay_in_head_order_not_completion_order(self):
        """Otherwise two identical passes produce differently-ordered evidence."""
        rc = _FakeRedis()
        delays = {"slow one": 0.06, "mid one": 0.03, "fast one": 0.0}

        async def _route(*, q, **kw):
            await asyncio.sleep(delays[q])
            return {"suggestions": []}

        head = ["slow one", "mid one", "fast one"]
        with patch("app.routes.events.typeahead_search", _route), _patch_redis(rc):
            results = await warmer._warm_head_concurrently(
                [_FakeSession() for _ in range(3)], head
            )

        assert [r["q"] for r in results] == head

    async def test_the_pass_opens_one_session_PER_WORKER_not_one_shared(self):
        """The call site's half of the invariant, and it was uncovered.

        `_warm_head_concurrently` is given a list of sessions and honours it —
        that is asserted below. But nothing checked what `_warm_typeahead`
        actually PUTS in that list, and a mutation replacing it with
        `[sessions[0]] * width` passed all 39 tests: the shared fake session
        made "four sessions" and "one session four times" indistinguishable.
        An AsyncSession under concurrent coroutines is a corruption bug that no
        amount of load testing reliably surfaces, so it is pinned here.
        """
        made: list = []
        seen_ids = set()
        rc = _FakeRedis()

        async def _route(*, q, db, **kw):
            seen_ids.add(id(db))
            await asyncio.sleep(0.01)
            return {"suggestions": []}

        with patch("app.routes.events.typeahead_search", _route), \
                _patch_session_factory(made), _patch_redis(rc):
            summary = await warmer._warm_typeahead(
                queries=[f"query {i}" for i in range(8)], concurrency=4
            )

        assert summary["concurrency"] == 4
        assert len(made) == 4, (
            f"opened {len(made)} sessions for a width-4 pass; the pool's width "
            f"IS the session count"
        )
        assert len(seen_ids) == 4, (
            f"the 8 queries ran across {len(seen_ids)} distinct session(s), not "
            f"4 — workers are sharing an AsyncSession"
        )

    async def test_one_query_in_flight_per_session(self):
        """An AsyncSession under two coroutines is corruption, not slowness.

        The worker pool's width IS the session count for exactly this reason,
        so the invariant is asserted rather than left to the shape of the code.
        """
        rc = _FakeRedis()
        in_flight: dict[int, int] = {}
        peak = {"n": 0}

        async def _route(*, q, db, **kw):
            key = id(db)
            in_flight[key] = in_flight.get(key, 0) + 1
            peak["n"] = max(peak["n"], in_flight[key])
            await asyncio.sleep(0.02)
            in_flight[key] -= 1
            return {"suggestions": []}

        sessions = [_FakeSession() for _ in range(4)]
        with patch("app.routes.events.typeahead_search", _route), _patch_redis(rc):
            await warmer._warm_head_concurrently(
                sessions, [f"query {i}" for i in range(12)]
            )

        assert peak["n"] == 1, (
            f"{peak['n']} coroutines shared one session — an AsyncSession is "
            f"not concurrency-safe and this is a data-corruption bug"
        )


class TestTheSummaryCanTellWorkFromTheAppearanceOfWork:
    async def test_rebuilt_and_fresh_are_reported_separately(self):
        rc = _FakeRedis(ttls={
            "bainluck:typeahead:fresh one": warmer.REFRESH_AHEAD_SECONDS + 5,
            "bainluck:typeahead:stale one": 3,
        })

        async def _route(**kw):
            return {"suggestions": []}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), \
                _patch_session(session), _patch_redis(rc):
            summary = await warmer._warm_typeahead(
                queries=["fresh one", "stale one"], concurrency=2
            )

        assert summary["rebuilt"] == 1
        assert summary["fresh"] == 1
        assert summary["warmed"] == 2, "both are OK outcomes; only one did work"
        assert summary["refresh_ahead_s"] == warmer.REFRESH_AHEAD_SECONDS

    async def test_a_skipped_run_carries_the_same_keys_as_a_real_one(self):
        """A consumer must never branch on `terminal` to know a field exists."""
        rc = _FakeRedis(lock_taken=True)
        with _patch_redis(rc):
            skipped = await warmer._warm_typeahead(queries=["red sox"])

        rc2 = _FakeRedis()

        async def _route(**kw):
            return {"suggestions": []}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), \
                _patch_session(session), _patch_redis(rc2):
            real = await warmer._warm_typeahead(queries=["red sox"])

        assert skipped["terminal"] == "skipped"
        assert set(skipped) == set(real), (
            f"shape drift between skipped and real: "
            f"{set(real) ^ set(skipped)}"
        )

    async def test_seconds_wall_is_not_seconds_total(self):
        """Reporting only the sum would hide the entire benefit of the fix."""
        import inspect

        src = inspect.getsource(warmer._warm_typeahead)
        assert '"seconds_wall"' in src and '"seconds_total"' in src
        assert "sum(seconds)" in src, (
            "seconds_total must stay the SUM so it remains comparable to every "
            "pre-LAT-P060 measurement; the wall time is a new field, not a "
            "redefinition of an old one"
        )


class TestTheWidthIsBoundedByTheEngineItUses:
    def test_width_fits_inside_one_task_engines_connection_ceiling(self):
        """`WARM_CONCURRENCY` must remain implementable, not aspirational.

        `_get_task_engine()` is pool_size=3 + max_overflow=2, so five is the
        hard ceiling a single engine can hand out. A width above it would
        serialise on pool checkout and the concurrency would be a lie the
        summary could not detect — the pass would report `concurrency: 8` and
        run at 5.
        """
        import inspect

        from app.tasks import base

        src = inspect.getsource(base._get_task_engine)
        pool = int(re.search(r"pool_size=(\d+)", src).group(1))
        overflow = int(re.search(r"max_overflow=(\d+)", src).group(1))

        assert warmer.WARM_CONCURRENCY <= pool + overflow, (
            f"WARM_CONCURRENCY={warmer.WARM_CONCURRENCY} exceeds the "
            f"{pool + overflow} connections one task engine can supply"
        )

    def test_a_pass_at_this_width_fits_inside_the_beat(self):
        """The arithmetic the whole queue is about, pinned as a test.

        Worst measured serial pass 58.9s (2026-08-17, 50 invocations). The beat
        is 30s. If a pass cannot clear the beat the run-lock skips the next one
        and the repaint period doubles — which is hole 1, restated.
        """
        worst_serial_s = 58.9
        beat_s = 30
        projected = worst_serial_s / warmer.WARM_CONCURRENCY
        assert projected < beat_s * 0.75, (
            f"a worst-case pass projects to {projected:.1f}s at width "
            f"{warmer.WARM_CONCURRENCY}, which does not clear the {beat_s}s "
            f"beat with margin"
        )

    def test_refresh_ahead_covers_a_whole_beat(self):
        """Below one beat, entries expire between passes and the fix is void."""
        beat_s = 30
        assert warmer.REFRESH_AHEAD_SECONDS >= beat_s, (
            f"REFRESH_AHEAD_SECONDS={warmer.REFRESH_AHEAD_SECONDS} is under the "
            f"{beat_s}s beat, so an entry can expire before the next pass"
        )
        assert warmer.REFRESH_AHEAD_SECONDS < 45, (
            "at or above the 45s TTL every entry is rebuilt unconditionally and "
            "the `fresh` skip can never fire"
        )
