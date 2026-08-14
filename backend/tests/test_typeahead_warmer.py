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


class _FakeRedis:
    def __init__(self, members=(), lock_taken=False):
        self._members = list(members)
        self.store = {}
        if lock_taken:
            self.store[warmer._LOCK_KEY] = b"1"
        self.deleted = []

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
