"""#7109 — the playoff grid cache could not self-heal, and it held a fix off the reader.

`/api/playoffs/{league}` cached the grid for 3900 s with a 24 h `:stale` mirror
beside it. On a primary miss the route served the mirror **and stopped**: it
rebuilt nothing and rewrote neither key. Only the hourly warm in
`tasks/precompute_category_pages` could ever refresh a grid, so a league whose
warm failed stayed frozen at its last successful build for as long as the mirror
survived.

Measured on production 2026-09-19 04:13Z:

    /api/playoffs/mlb   last_updated 00:26:33Z   stale=true   3h47m old
    /api/playoffs/nba   last_updated 03:26:45Z   fresh
    /api/playoffs/nhl   last_updated 03:26:28Z   fresh
    /api/playoffs/nfl   last_updated 03:26:51Z   fresh

and the 01:25Z warm report recorded mlb as
``{"outcome": "timeout", "duration_s": 89.4, "timeout_s": 66.1}`` while
`ncaa-basketball`, which runs AFTER it, finished with 23.1 s of budget to spare —
so this was a build the warm could not complete, not a league starved of budget.
The same build on the web dyno took 7.62 s against a 25 s wall.

These tests pin both directions: the mirror serve must now schedule a rebuild,
and it must still be the mirror that gets served.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.playoffs import get_playoff_grid_cached
from app.utils import playoff_grid_cache as pgc


GOOD = {"teams": [{"name": "Yankees"}], "columns": [{"key": "championship"}]}


def _redis_mock(store: dict) -> MagicMock:
    """An async Redis double whose `get` answers from `store`."""
    rc = MagicMock()
    rc.get = AsyncMock(side_effect=lambda k: store.get(k))
    rc.set = AsyncMock()
    rc.aclose = AsyncMock()
    return rc


# ---------------------------------------------------------------------------
# 1. The defect itself: a mirror serve must schedule its own replacement.
# ---------------------------------------------------------------------------
class TestTheMirrorServeSchedulesARebuild:
    @pytest.mark.asyncio
    async def test_stale_serve_schedules_a_refresh_for_that_league(self):
        """THE regression guard. Before #7109 this call site did nothing at all,
        and MLB sat four hours stale behind a mirror nothing would replace."""
        rc = _redis_mock({"bainluck:category:playoffs:mlb:stale": json.dumps(GOOD)})

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch("app.routes.playoffs.schedule_grid_refresh") as sched:
            result = await get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        sched.assert_called_once_with("mlb")
        assert result["stale"] is True

    @pytest.mark.asyncio
    async def test_a_fresh_hit_schedules_nothing(self):
        """Adjacent direction. A live key is not a reason to rebuild anything —
        a refresh on every hit would be a rebuild per request, not per expiry."""
        rc = _redis_mock({"bainluck:category:playoffs:nba": json.dumps(GOOD)})

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch("app.routes.playoffs.schedule_grid_refresh") as sched:
            result = await get_playoff_grid_cached("nba", None, 10, False, MagicMock())

        sched.assert_not_called()
        assert result == GOOD

    @pytest.mark.asyncio
    async def test_an_unusable_mirror_schedules_nothing_and_builds_live(self):
        """An empty/error mirror is not served, so there is nothing to refresh
        behind — the reader gets a live build, which writes both keys itself."""
        junk = json.dumps({"teams": [], "columns": [], "error": "timeout"})
        rc = _redis_mock({"bainluck:category:playoffs:mlb:stale": junk})

        async def _build(*a, **kw):
            return GOOD

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch("app.routes.playoffs.schedule_grid_refresh") as sched, patch(
            "app.routes.playoffs.get_playoff_grid", side_effect=_build
        ):
            result = await get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        sched.assert_not_called()
        assert result == GOOD

    @pytest.mark.asyncio
    async def test_a_cache_ineligible_request_schedules_nothing(self):
        """`?hours=` / `?top=` / `?debug=` build a different shape and never
        touch these keys, so they must not publish one either."""
        rc = _redis_mock({})

        async def _build(*a, **kw):
            return GOOD

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch("app.routes.playoffs.schedule_grid_refresh") as sched, patch(
            "app.routes.playoffs.get_playoff_grid", side_effect=_build
        ):
            await get_playoff_grid_cached("mlb", 24, 10, False, MagicMock())

        sched.assert_not_called()
        rc.set.assert_not_awaited()


# ---------------------------------------------------------------------------
# 2. The refresh must not be able to change what the reader gets.
# ---------------------------------------------------------------------------
class TestTheRefreshIsAPassengerNotACondition:
    @pytest.mark.asyncio
    async def test_the_mirror_is_still_served_when_the_refresh_cannot_start(self):
        """`schedule_grid_refresh` False means the sync client is unreachable, so
        a synchronous rebuild could not publish its result either. Serving the
        mirror is strictly better than charging the reader for a discarded build."""
        rc = _redis_mock({"bainluck:category:playoffs:nhl:stale": json.dumps(GOOD)})

        built = []

        async def _build(*a, **kw):
            built.append(1)
            return GOOD

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch(
            "app.routes.playoffs.schedule_grid_refresh", return_value=False
        ), patch(
            "app.routes.playoffs.get_playoff_grid", side_effect=_build
        ):
            result = await get_playoff_grid_cached("nhl", None, 10, False, MagicMock())

        assert built == [], "a failed schedule must not cost the reader a rebuild"
        assert result["stale"] is True
        assert result["teams"] == GOOD["teams"]

    @pytest.mark.asyncio
    async def test_a_raising_scheduler_still_serves_the_mirror(self):
        """Nothing in the refresh path may turn a served page into a rebuild or
        an error. Without the guard inside `schedule_grid_refresh` this lands in
        the route's `except Exception` and silently becomes a live build."""
        rc = _redis_mock({"bainluck:category:playoffs:nhl:stale": json.dumps(GOOD)})

        built = []

        async def _build(*a, **kw):
            built.append(1)
            return GOOD

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch.object(
            pgc, "serve_stale_and_refresh", side_effect=RuntimeError("redis gone")
        ), patch("app.routes.playoffs.get_playoff_grid", side_effect=_build):
            result = await get_playoff_grid_cached("nhl", None, 10, False, MagicMock())

        assert built == []
        assert result["stale"] is True


# ---------------------------------------------------------------------------
# 3. Single-flight: one rebuild per expiry, not one per reader.
# ---------------------------------------------------------------------------
class TestSingleFlight:
    def test_a_burst_of_readers_produces_one_rebuild(self):
        """The lock is taken with `set(nx=True)`, so only the first of three
        concurrent readers gets a token. Without it, every reader arriving behind
        one TTL expiry starts its own 7.6 s build.

        All three still return True — "another process is already rebuilding" is
        just as good a reason to serve the mirror as "I started one".
        """
        rc = MagicMock()
        rc.set.side_effect = [True, None, None]  # only the first acquires
        rebuild = AsyncMock()

        async def _drive():
            with patch.object(pgc, "rebuild_grid", rebuild):
                verdicts = [pgc.schedule_grid_refresh("mlb", rc=rc) for _ in range(3)]
                await asyncio.sleep(0.05)  # let the scheduled task actually run
                return verdicts

        verdicts = asyncio.run(_drive())

        assert verdicts == [True, True, True]
        assert rebuild.await_count == 1, "three readers, one rebuild"
        assert rc.set.call_count == 3
        assert all(
            c.kwargs.get("nx") is True for c in rc.set.call_args_list
        ), "the lock must be acquired with NX or it is not a lock"

    def test_the_lock_key_is_scoped_to_one_league(self):
        """A shared lock would let one league's rebuild suppress every other
        league's — the exact starvation the warm beat already suffers."""
        assert pgc.grid_cache_keys("mlb").refresh_lock != (
            pgc.grid_cache_keys("nba").refresh_lock
        )

    def test_the_refresh_cannot_outlive_its_own_lease(self):
        """A build allowed to run past `REFRESH_LOCK_TTL` would release a lock a
        SECOND builder already holds, admitting the stampede this prevents."""
        from app.utils.event_concept_cache import REFRESH_LOCK_TTL

        assert pgc.REFRESH_TIMEOUT_S < REFRESH_LOCK_TTL


# ---------------------------------------------------------------------------
# 4. The published payload, and the keys it lands on.
# ---------------------------------------------------------------------------
class TestPublishGrid:
    def test_both_keys_are_written_with_their_ttls(self):
        rc = MagicMock()
        assert pgc.publish_grid(rc, "mlb", GOOD) is True

        written = {c.args[0]: c.args[1] for c in rc.setex.call_args_list}
        assert written == {
            "bainluck:category:playoffs:mlb": pgc.PRIMARY_TTL,
            "bainluck:category:playoffs:mlb:stale": pgc.MIRROR_TTL,
        }
        body = json.loads(rc.setex.call_args_list[0].args[2])
        assert body["teams"] == GOOD["teams"]

    @pytest.mark.parametrize(
        "bad",
        [
            {"teams": [], "columns": []},
            {"teams": [{"n": 1}], "error": "timeout"},
            {"teams": None},
            None,
        ],
    )
    def test_an_unusable_build_clobbers_neither_key(self, bad):
        """🔴 The refusal is the load-bearing half. This write owns the 24 h
        mirror, so publishing an empty build would REPLACE a working grid with
        one the reader then refuses as a fallback — turning a healthy page into
        a live rebuild. Several leagues build empty out of season."""
        rc = MagicMock()
        assert pgc.publish_grid(rc, "mlb", bad) is False
        rc.setex.assert_not_called()

    @pytest.mark.parametrize(
        "payload",
        [
            GOOD,
            {"teams": [{"n": 1}], "columns": []},
            {"teams": [], "columns": []},
            {"teams": [{"n": 1}], "error": "timeout"},
            {"teams": None},
            {},
            None,
            "grid",
            7,
        ],
    )
    def test_the_writer_publishes_exactly_what_the_reader_would_serve(self, payload):
        """Reuse, not a second opinion. A private "is this usable" copy in the
        writer drifts from the reader's, and the two disagreeing IS the bug: the
        writer stores something the reader then refuses. Checked as an
        equivalence over the whole shape space rather than by reading the source,
        so a re-implementation that agrees today but drifts tomorrow fails here.
        """
        from app.routes.playoffs import _grid_payload_usable

        rc = MagicMock()
        assert pgc.publish_grid(rc, "mlb", payload) is _grid_payload_usable(payload)


# ---------------------------------------------------------------------------
# 5. The rebuild must build what the cache serves.
# ---------------------------------------------------------------------------
class TestTheRebuildMatchesTheCacheEligibleRequest:
    def test_it_builds_the_cache_eligible_shape_on_its_own_session(self):
        """`cache_eligible = not debug and hours is None and top == 10`. A
        refresh that built a different shape would publish a payload the next
        reader is not asking for — `?hours=24` is a genuinely cheaper chart than
        the default's `config.trend_hours`, so this is not a formality.

        The session must also be the rebuild's OWN: the request's is closed by
        the time this runs.
        """
        seen = {}
        session = MagicMock()

        class _Ctx:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *a):
                return False

        async def _build(slug, hours, top, debug, db):
            seen.update(slug=slug, hours=hours, top=top, debug=debug, db=db)
            return GOOD

        rc = MagicMock()
        with patch("app.routes.playoffs.get_playoff_grid", side_effect=_build), patch(
            "app.tasks.base.get_task_session", return_value=_Ctx()
        ), patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            assert asyncio.run(pgc.rebuild_grid("mlb")) is True

        assert seen["slug"] == "mlb"
        assert seen["hours"] is None
        assert seen["top"] == 10
        assert seen["debug"] is False
        assert seen["db"] is session, "the rebuild must open its own session"
        assert rc.setex.call_count == 2

    def test_a_rebuild_that_builds_empty_publishes_nothing(self):
        class _Ctx:
            async def __aenter__(self):
                return MagicMock()

            async def __aexit__(self, *a):
                return False

        async def _build(*a, **kw):
            return {"teams": [], "columns": []}

        rc = MagicMock()
        with patch("app.routes.playoffs.get_playoff_grid", side_effect=_build), patch(
            "app.tasks.base.get_task_session", return_value=_Ctx()
        ), patch("app.tasks.redis_state.get_redis_client", return_value=rc):
            assert asyncio.run(pgc.rebuild_grid("mlb")) is False

        rc.setex.assert_not_called()


# ---------------------------------------------------------------------------
# 6. The slug is a path parameter, so it never reaches a log line raw.
# ---------------------------------------------------------------------------
class TestLogInjection:
    def test_a_known_league_logs_as_itself(self):
        assert pgc._log_league("mlb") == "mlb"
        assert pgc._log_league("nba") == "nba"

    @pytest.mark.parametrize(
        "hostile",
        [
            "mlb\nINFO forged log entry",
            "mlb\r\n2026-01-01 CRITICAL everything is fine",
            "../../etc/passwd",
            "",
        ],
    )
    def test_a_hostile_slug_never_reaches_the_log(self, hostile):
        """CodeQL grades a path parameter reaching a logger `py/log-injection`
        at MEDIUM — a notice-32 refuse. The value logged is re-sourced from our
        own config, so a newline cannot forge an entry."""
        assert pgc._log_league(hostile) == "<unknown-league>"

    def test_the_log_lines_pass_the_sanitised_value_not_the_argument(self):
        """The guard is only worth having if the call sites use it. Drives the
        real failure paths and asserts the raw slug is absent from the record."""
        hostile = "mlb\nINFO forged"

        with patch.object(pgc, "serve_stale_and_refresh", side_effect=RuntimeError):
            with patch.object(pgc.logger, "warning") as warn:
                pgc.schedule_grid_refresh(hostile)

        assert warn.call_count == 1
        assert hostile not in warn.call_args.args
        assert "<unknown-league>" in warn.call_args.args


# ---------------------------------------------------------------------------
# 7. The key layout is shared, not re-derived.
# ---------------------------------------------------------------------------
class TestKeyLayout:
    def test_the_keys_are_the_ones_already_live_in_production(self):
        """This is an adoption of the existing policy, NOT a migration: a prefix
        change here would orphan every warm key the beat has ever written."""
        keys = pgc.grid_cache_keys("mlb")
        assert keys.primary == "bainluck:category:playoffs:mlb"
        assert keys.stale == "bainluck:category:playoffs:mlb:stale"

    def test_the_warm_beat_writes_the_keys_this_module_reads(self):
        """The beat still writes its own literals. If either side moves, a warm
        lands somewhere the reader never looks — silently, because a missing key
        reads exactly like a cold one."""
        # `from app.tasks import precompute_category_pages` resolves to the
        # CELERY TASK PROXY of that name, which has no module attributes.
        import app.tasks.precompute_category_pages as pcp

        for slug in pcp.GRID_WARM_LEAGUES:
            assert (
                pgc.grid_cache_keys(slug).primary
                == f"bainluck:category:playoffs:{slug}"
            )
