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
import math
import re
import time
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
    def __init__(self, members=(), lock_taken=False, ttls=None, last_pass_start=None):
        self._members = list(members)
        self.store = {}
        if lock_taken:
            self.store[warmer._LOCK_KEY] = b"1"
        # LAT-P062: the min-period floor reads the previous pass's start stamp.
        # Seeded as a REAL stored value rather than special-cased in `get`, so
        # the round-trip through `set`/`get` (including the bytes encoding) is
        # the thing under test — ruling 072: a fake that agrees with the code
        # instead of with Redis proves only that the code agrees with itself.
        if last_pass_start is not None:
            self.store[warmer._LAST_PASS_START_KEY] = repr(float(last_pass_start)).encode()
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

    def get(self, key):
        return self.store.get(key)

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


def _ok_route():
    """A `/typeahead` stand-in that succeeds and asserts nothing.

    The debug-flag contract has its own dedicated tests above; these cadence
    tests need a route that simply returns, so a failure here is unambiguously
    about the cadence and not about the route stub.
    """

    async def _route(*, q, debug_evidence, debug_timing, db):
        return {"suggestions": [], "query": q}

    return _route


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
    async def test_both_measured_sources_select_when_both_are_present(self):
        """LAT-P078/#1866. This REPLACES `test_redis_trending_wins_when_present`.

        That test pinned a strict first-non-empty cascade, and the cascade was
        the defect: `_head_from_redis` is never empty in production, so the
        query-log arm was unreachable and `search_query_logs` — the only source
        in this system that cannot be polluted by the warmer — had never
        selected a warmed term. The old assertion is preserved INVERTED below,
        so the regression is named rather than merely absent.
        """
        session = _FakeSession(log_rows=["masters winner", "nba champion"])
        with _patch_redis(_FakeRedis(["red sox", "yankees"])):
            head, source = await warmer.resolve_head(session, 10)

        assert "masters winner" in head, "the query-log head must reach the warmer"
        assert "red sox" in head, "the zset head must still reach the warmer"
        assert source.startswith("blend:"), source
        # The inverted old assertion: the zset no longer WINS, it shares.
        assert head != ["red sox", "yankees"], (
            "trending must not be the whole head when the query log has rows — "
            "that is the cascade this test replaced"
        )

    async def test_the_query_log_share_is_a_floor_the_zset_cannot_squeeze_out(self):
        """The guarantee that makes the real head reachable at all.

        Production shape: the zset is long (40 locked-in terms) and the query log
        is the thing being starved. If the reservation were a best-effort the
        long source would take the whole budget and nothing would change.
        """
        session = _FakeSession(log_rows=[f"log{i}" for i in range(20)])
        with _patch_redis(_FakeRedis([f"zset{i}" for i in range(40)])):
            head, _ = await warmer.resolve_head(session, 10)

        from_log = [q for q in head if q.startswith("log")]
        assert len(head) == 10
        assert len(from_log) == 5, f"expected half the budget reserved, got {from_log}"

    async def test_a_short_query_log_does_not_shrink_the_head(self):
        """A short query log must not shrink the head below the old behaviour.

        Warming fewer terms than the cascade did would make this change a
        regression on the very metric it exists to move.

        ⚠️ This test was originally named `..._an_unspent_reservation_is_
        backfilled_...` and it did NOT test that: with a 1-row log and a 40-term
        zset the budget is already full before the backfill runs, so deleting
        the backfill left it green (LAT-P078 mutation M6, SURVIVED). The
        backfill's real case is the mirror image and is the test below. Renamed
        to what it actually pins.
        """
        session = _FakeSession(log_rows=["only one"])
        with _patch_redis(_FakeRedis([f"zset{i}" for i in range(40)])):
            head, _ = await warmer.resolve_head(session, 10)

        assert len(head) == 10, "the budget must still be fully spent"
        assert "only one" in head

    async def test_a_short_zset_is_backfilled_from_the_query_log(self):
        """The backfill's actual case: the OTHER source is the short one.

        Reservation is 5 of 10 and the zset can only supply 2, so 3 slots can be
        filled only by going back to the query log for terms beyond its
        reservation. Without the backfill the head is 7 — the warmer would spend
        70% of its budget and report a clean pass, which is this module's
        signature failure mode (gotcha #53).
        """
        session = _FakeSession(log_rows=[f"log{i}" for i in range(20)])
        # Lower-case on purpose: `_head_from_redis` normalises, so a mixed-case
        # fixture asserts against a term the code never produces.
        with _patch_redis(_FakeRedis(["zseta", "zsetb"])):
            head, _ = await warmer.resolve_head(session, 10)

        assert len(head) == 10, f"budget under-spent: {head}"
        assert "zseta" in head and "zsetb" in head
        assert len([q for q in head if q.startswith("log")]) == 8

    async def test_a_term_in_both_sources_is_warmed_once(self):
        """The expected steady state once the real head starts trending too."""
        session = _FakeSession(log_rows=["stanley cup", "masters winner"])
        with _patch_redis(_FakeRedis(["stanley cup", "red sox"])):
            head, _ = await warmer.resolve_head(session, 10)

        assert head.count("stanley cup") == 1
        assert sorted(head) == ["masters winner", "red sox", "stanley cup"]

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
        assert "setex(_cache_key, 65" in src

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
        write_at = src.index("setex(_cache_key, 65")
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

    def test_the_pass_period_the_beat_can_produce_fits_under_the_ttl(self):
        """The arithmetic the whole queue is about, pinned against MEASUREMENT.

        ⚠️ This test replaces `test_a_pass_at_this_width_fits_inside_the_beat`,
        which asserted `58.9 / WARM_CONCURRENCY < 30 * 0.75` and PASSED — on a
        projection production then refuted. The projected 14.7s pass measured
        **27.4-38.1s** on v3829, because concurrency 4 bought 1.2x wall while
        inflating per-query time 3.3x. A test that grades a PROJECTION cannot
        notice that (ruling 074: a predicate over work performed, not a proxy).

        What actually has to hold is a property of the PERIOD, not the pass:
        an entry must be rebuilt before its 45s TTL runs out. With a run-lock
        serialising beats, the period quantises to `beat * ceil(wall / beat)`.
        """
        ttl_s = 45
        beat_s = _warm_typeahead_beat_seconds()
        # The measured envelope on v3829, not a projection.
        for wall_s in (27.4, 30.9, 36.2, 38.1):
            period = beat_s * math.ceil(wall_s / beat_s)
            assert period < ttl_s, (
                f"a {wall_s}s pass on a {beat_s}s beat quantises to a {period}s "
                f"period, which is not under the {ttl_s}s TTL — the head goes "
                f"cold between passes and the duty cycle cannot reach 100%"
            )

    def test_the_floor_bounds_how_hard_the_warmer_may_hit_the_database(self):
        """The other half of the beat change, and the reason it is safe.

        A short beat removes dead time AND removes the only bound on how often
        the warmer runs. The warmer already holds the database ~73% of
        wall-clock at concurrency 4; the floor is what stops a shorter beat
        turning that into ~100%.
        """
        assert warmer.MIN_PASS_PERIOD_SECONDS >= _warm_typeahead_beat_seconds(), (
            "a floor below the beat bounds nothing — the beat would already be "
            "the tighter constraint"
        )
        assert warmer.MIN_PASS_PERIOD_SECONDS < 45, (
            "a floor at or above the 45s TTL would itself guarantee the head "
            "goes cold, which is the bug, not the guard"
        )

    def test_refresh_ahead_is_inert_at_every_reachable_period_and_that_is_stated(self):
        """The constant is kept, its old justification is not.

        ⚠️ Replaces `test_refresh_ahead_covers_a_whole_beat`, which asserted
        `REFRESH_AHEAD_SECONDS >= beat` on the reasoning that the gap an entry
        must survive is "the pass PERIOD (the 30s beat)". Production measured
        the period at **42.5-51.7s**, not 30s.

        A threshold T can skip an entry only when `T < 45 - P`. At every period
        this scheduler can produce, that bound is far below 35 — so `fresh: 0`
        (observed on 5 of 5 production passes) is arithmetic, not a tuning miss.
        The test pins the SAFE direction: T must stay high enough that the skip
        never fires, because a skip would drop an entry with seconds of life
        left and let it expire before the next pass.
        """
        ttl_s = 45
        beat_s = _warm_typeahead_beat_seconds()
        largest_useful_t = ttl_s - max(beat_s, warmer.MIN_PASS_PERIOD_SECONDS)
        assert warmer.REFRESH_AHEAD_SECONDS > largest_useful_t, (
            f"REFRESH_AHEAD_SECONDS={warmer.REFRESH_AHEAD_SECONDS} has dropped "
            f"to where the `fresh` skip can fire (largest useful T is "
            f"{largest_useful_t}s). A skip at that margin drops an entry that "
            f"then expires before the next pass — it buys pass time by "
            f"re-opening the cold window refresh-ahead exists to close."
        )
        assert warmer.REFRESH_AHEAD_SECONDS < ttl_s, (
            "at or above the 45s TTL the threshold stops being a threshold; "
            "keep it a bound that COULD fire if the period ever collapsed"
        )


def _warm_typeahead_beat_seconds() -> float:
    """The live beat for `warm-typeahead`, read from the schedule, never quoted.

    Reading it makes the tests above fail when somebody retunes the cadence
    without re-deriving the period arithmetic — which is exactly how the old
    30s-beat assertions came to be asserting a refuted model.
    """
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule["warm-typeahead"]["schedule"]
    return float(getattr(schedule, "total_seconds", lambda: schedule)())


class TestThePassCanStateItsOwnCadence:
    """LAT-P062: `period_s`, `expired`, and the floor.

    Every duty-cycle grade on #1866 so far has been INFERRED — from a client
    probe, or reconstructed from a 50-entry duration histogram. Ruling 074 says
    an instrument reports the work it did; "how long since I last did it" and
    "was the entry already dead when I got there" are the two halves of that,
    and neither was answerable from the summary.
    """

    @pytest.mark.asyncio
    async def test_the_floor_suppresses_a_pass_that_is_too_soon(self):
        redis = _FakeRedis(last_pass_start=time.time() - 5)
        session = _FakeSession()

        with _patch_redis(redis), _patch_session(session):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert summary["terminal"] == "skipped"
        assert summary["skip_reason"] == "min_period"
        assert summary["period_s"] == pytest.approx(5, abs=1.5)
        assert classify_summary(summary) != "green"

    @pytest.mark.asyncio
    async def test_the_floor_releases_the_lock_it_took_to_check(self):
        """Checked UNDER the lock, so two beats cannot both pass the check.

        The cost of that is a lock this pass must hand back. If it does not,
        `_LOCK_TTL_SECONDS` (120s) wedges the warmer for four times the floor —
        a guard against too-frequent passes turning into no passes at all.
        """
        redis = _FakeRedis(last_pass_start=time.time() - 1)
        session = _FakeSession()

        with _patch_redis(redis), _patch_session(session):
            await warmer._warm_typeahead(queries=["red sox"])

        assert warmer._LOCK_KEY in redis.deleted, (
            "the floor took the run-lock to check itself and never released it"
        )
        assert warmer._LOCK_KEY not in redis.store

    @pytest.mark.asyncio
    async def test_a_pass_past_the_floor_runs_and_reports_its_period(self):
        redis = _FakeRedis(last_pass_start=time.time() - 120)
        session = _FakeSession()

        with _patch_redis(redis), _patch_session(session), \
                patch("app.routes.events.typeahead_search", _ok_route()):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert summary["terminal"] == "complete"
        assert summary["skip_reason"] is None
        assert summary["period_s"] == pytest.approx(120, abs=2)

    @pytest.mark.asyncio
    async def test_an_unknown_previous_start_does_not_suppress_the_pass(self):
        """Fails toward DOING the work, like every other Redis read here.

        A fresh Redis, a restarted dyno and an unreadable key all land here. If
        any of them suppressed the pass, a Redis blip would stop the warmer
        while it reported a tidy `skipped` — the shape this whole file exists
        to refuse.
        """
        redis = _FakeRedis()  # no last_pass_start at all
        session = _FakeSession()

        with _patch_redis(redis), _patch_session(session), \
                patch("app.routes.events.typeahead_search", _ok_route()):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert summary["terminal"] == "complete"
        assert summary["period_s"] is None, (
            "an unknown period must be None, never 0.0 — zero reads as two "
            "passes starting at the same instant (gotcha #53)"
        )

    @pytest.mark.asyncio
    async def test_a_future_previous_start_does_not_suppress_the_pass(self):
        """Clock skew between dynos must not be able to wedge the warmer.

        A future stamp makes `now - previous` negative, and a negative delta
        compares as `< MIN_PASS_PERIOD_SECONDS` — so the naive form suppresses
        every pass, forever, and reports `skipped` while doing it. This is the
        ahead-drift failure the lane-lock protocol already ruled on, relocated
        into a scheduler.
        """
        redis = _FakeRedis(last_pass_start=time.time() + 3600)
        session = _FakeSession()

        with _patch_redis(redis), _patch_session(session), \
                patch("app.routes.events.typeahead_search", _ok_route()):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert summary["terminal"] == "complete", (
            "a future last-pass stamp suppressed the pass — the floor treats a "
            "negative gap as 'a pass just ran'"
        )
        assert summary["period_s"] is None

    @pytest.mark.asyncio
    async def test_a_pass_records_its_start_so_the_next_one_can_measure_it(self):
        redis = _FakeRedis()
        session = _FakeSession()

        with _patch_redis(redis), _patch_session(session), \
                patch("app.routes.events.typeahead_search", _ok_route()):
            await warmer._warm_typeahead(queries=["red sox"])

        assert warmer._LAST_PASS_START_KEY in redis.store, (
            "a pass that does not record its start makes every subsequent "
            "`period_s` unknown, and the floor unenforceable"
        )

    @pytest.mark.asyncio
    async def test_expired_counts_only_a_missing_key_not_every_non_positive_ttl(self):
        """-2, -1 and None are three different answers (gotcha #53).

        Only -2 means "the entry was gone and a user typing this prefix paid a
        database read". -1 is a key with no expiry (a bug to fix, not a cold
        entry) and None is Redis declining to answer. A `<= 0` test would fold
        all three into the one number a duty-cycle grade rests on.
        """
        redis = _FakeRedis(
            ttls={
                warmer._CACHE_KEY_PREFIX + "gone": warmer._TTL_NO_KEY,
                warmer._CACHE_KEY_PREFIX + "immortal": warmer._TTL_NO_EXPIRY,
                warmer._CACHE_KEY_PREFIX + "stale": 4,
            }
        )
        session = _FakeSession()

        with _patch_redis(redis), _patch_session(session), \
                patch("app.routes.events.typeahead_search", _ok_route()):
            summary = await warmer._warm_typeahead(
                queries=["gone", "immortal", "stale"]
            )

        assert summary["rebuilt"] == 3, "all three are under the threshold"
        assert summary["fresh"] == 0
        assert summary["expired"] == 1, (
            f"expected exactly the -2 entry to count as expired, got "
            f"{summary['expired']} — -1 and a live-but-stale TTL are not "
            f"'the head was cold'"
        )

    @pytest.mark.asyncio
    async def test_the_two_skips_are_distinguishable(self):
        """A wedged lock and a too-tight floor are opposite diagnoses.

        Both produce `terminal: skipped` with every count at zero. Without
        `skip_reason` the summaries are byte-identical, and the operator reading
        "the warmer skipped 40 of 50 beats" cannot tell whether a pass is stuck
        or whether the floor is doing its job.
        """
        lock_held = _FakeRedis(lock_taken=True)
        too_soon = _FakeRedis(last_pass_start=time.time() - 1)
        session = _FakeSession()

        with _patch_redis(lock_held), _patch_session(session):
            a = await warmer._warm_typeahead(queries=["red sox"])
        with _patch_redis(too_soon), _patch_session(session):
            b = await warmer._warm_typeahead(queries=["red sox"])

        assert a["terminal"] == b["terminal"] == "skipped"
        assert a["skip_reason"] == "lock"
        assert b["skip_reason"] == "min_period"
        assert a["skip_reason"] != b["skip_reason"]
        assert set(a) == set(b), "the two skip shapes must not drift apart"


# --------------------------------------------------------------------------
# LAT-P078 / #1866 — the warmer must not vote for its own head.
#
# `resolve_head` reads `search:trending:24h`; `_warm_one` warms by calling the
# route; the route's last act was to `zincrby` the query into that same zset. So
# every pass incremented all 40 of its own head terms, ~1,700 times a day each,
# against ~3/day for a real user query. The head was self-sustaining and CLOSED.
#
# Production evidence, 2026-08-21: the top five scored 5414, 5411, 5403, 5400,
# 5399 — a spread of 15 across five terms, which is a round-robin machine, not a
# human distribution. Real traffic over the same window runs 102, 101, 95, 90, 82.
# --------------------------------------------------------------------------


class TestTheWarmerDoesNotVoteForItsOwnHead:
    @pytest.mark.asyncio
    async def test_the_route_call_runs_with_trending_writes_suppressed(self):
        """The loop-break, observed at the seam where it has to hold.

        Asserted INSIDE the route stand-in rather than after the call, because
        the flag only has to be true for the duration of the route body — that
        is the only window in which the `zincrby` could fire.
        """
        from app.routes.events import _suppress_trending_write

        seen = []

        async def _route(*, q, debug_evidence, debug_timing, db):
            seen.append(_suppress_trending_write.get())
            return {"suggestions": [], "query": q}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), _patch_session(session):
            await warmer._warm_typeahead(queries=["red sox", "yankees"])

        assert seen == [True, True], (
            "every warmed query must run with the trending write suppressed; "
            f"got {seen}"
        )

    def test_a_real_user_request_still_counts(self):
        """The suppression must not leak out of the warmer.

        The ContextVar defaults to False and nothing outside `_warm_one` sets it,
        so an ordinary request counts. If this ever failed, the trending zset
        would stop being written at all and the head would freeze permanently —
        the same outcome as the bug, reached from the opposite direction.
        """
        from app.routes.events import _suppress_trending_write

        assert _suppress_trending_write.get() is False

    def test_the_zincrby_is_actually_inside_the_guard(self):
        """Source-shape guard, because the behavioural test cannot see a revert.

        `_warm_one` sets the flag; the route reads it. A revert that deleted only
        the route-side `if` would leave the warmer setting a flag nobody honours,
        every behavioural test above would still pass, and the loop would be back
        with its instrument reporting success. Reading the source is the only
        thing that catches that, and this program has been bitten by the same
        shape before (`test_heavy_beat_literals_match_their_effective_queue`).
        """
        import inspect

        from app.routes import events as events_route

        src = inspect.getsource(events_route.typeahead_search)
        assert 'zincrby("search:trending:24h"' in src, (
            "the trending write moved; re-point this guard at its new home"
        )

        guard = "if not _suppress_trending_write.get():"
        assert guard in src, "the trending write is no longer guarded (#1866)"
        assert src.index(guard) < src.index('zincrby("search:trending:24h"'), (
            "the guard must precede the write it guards"
        )

    @pytest.mark.asyncio
    async def test_warming_is_not_load_bearing_on_the_flag(self):
        """A ContextVar failure must never break warming.

        The flag is an instrument-integrity concern; the warm is the product.
        If setting it ever raised, the head would go unwarmed — a far worse
        outcome than a polluted count.
        """
        async def _route(*, q, debug_evidence, debug_timing, db):
            return {"suggestions": [], "query": q}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), _patch_session(session):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert summary["warmed"] == 1
        assert summary["terminal"] == "complete"


# --------------------------------------------------------------------------
# LAT-P078 / #1866 — the ring records the SET, not just its provenance.
#
# "Was the term I probed actually in the warmed set" was unanswerable from
# production for four cycles. LAT-P076 published 80% -> 0% and LAT-P077
# withdrew it, because both were measuring five `_STATIC_FLOOR` strings that the
# warmer only uses when BOTH measured sources are empty.
# --------------------------------------------------------------------------


class TestTheRingCarriesTheHeadItself:
    def test_a_real_pass_record_carries_the_head_and_its_true_length(self):
        summary = {
            "terminal": "complete",
            "head_source": "blend:query_log+trending:5/10_from_log",
            "head": [f"q{i}" for i in range(40)],
        }
        record = warmer._pass_ring_record(summary, at=1.0)

        assert record["head"] == [f"q{i}" for i in range(warmer._RING_HEAD_SAMPLE)]
        assert record["head_n"] == 40, (
            "the TRUE head length must survive truncation, or a sampled list "
            "reads as a short head"
        )

    def test_the_truncation_is_visible_rather_than_silent(self):
        """`head_n` > `len(head)` is the reader's signal that it holds a sample."""
        summary = {"head": [f"q{i}" for i in range(40)]}
        record = warmer._pass_ring_record(summary, at=1.0)

        assert len(record["head"]) < record["head_n"]

    @pytest.mark.asyncio
    async def test_a_skip_carries_an_empty_head_not_a_missing_one(self):
        """Gotcha #53 at the field level: absent and empty are different facts."""
        lock_held = _FakeRedis(lock_taken=True)
        session = _FakeSession()

        with _patch_redis(lock_held), _patch_session(session):
            summary = await warmer._warm_typeahead(queries=["red sox"])

        assert "head" in summary, "the same-keys contract covers `head` too"
        assert summary["head"] == []

    @pytest.mark.asyncio
    async def test_the_head_travels_from_the_pass_into_the_summary(self):
        async def _route(*, q, debug_evidence, debug_timing, db):
            return {"suggestions": [], "query": q}

        session = _FakeSession()
        with patch("app.routes.events.typeahead_search", _route), _patch_session(session):
            summary = await warmer._warm_typeahead(queries=["red sox", "yankees"])

        assert summary["head"] == ["red sox", "yankees"]
