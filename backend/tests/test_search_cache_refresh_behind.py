"""LAT-P116/#2272 — the two process-global caches stop charging their rebuild
to whichever user's request happened to arrive after the TTL.

`_load_ei_percentiles` and `_build_team_lookup` are process-global caches with a
300 s TTL and nothing that rebuilds them. Measured on production slug
`606bd84b` via `?debug_timing=1`, on the two `WEB_CONCURRENCY=2` workers:

    event_gei    216 ms / 276 ms   (warm: 0 ms)
    event_teams  424 ms / 342 ms   (warm: 0 ms)

against a 157 ms p50 total build for the same request. Every five minutes, in
every worker, one user paid ~560-700 ms for a rebuild — and never the same user
twice, which is why it never looked like a slow endpoint.

WHAT THESE TESTS PIN, AND WHY EACH ONE EXISTS.

Every test here drives the REAL functions against a fake session and asserts on
BEHAVIOUR — how many builds ran, what was returned, whether the caller blocked.
None of them assert on source text. A guard that reads the source stays green
when the function stops doing the thing (the `_plant_must_hit_the_render` class
of failure), and the whole value of this change is in *when* the build runs.

The three properties that must not regress, in the order they were reasoned out:

1. **Past the TTL the caller does not wait.** This is the ship.
2. **The stale value served is the same shape the blocking path builds.** A
   warmed payload differing from the served one by one key is a wrong answer
   served fast (LAT-P115's `build_and_cache_movers` lesson) — so both paths go
   through one extractor and this asserts they agree on real data.
3. **It fails CLOSED.** An empty cache blocks; a rebuild that keeps failing
   stops being papered over past `_STALE_SERVE_CEILING` and degrades to the old
   slow behaviour rather than serving indefinitely-old data with no signal.
"""

import asyncio

import pytest

from app.routes import events as ev


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def unique(self):
        return self


class FakeSession:
    """Counts executes so 'did the caller build?' is a number, not a guess."""

    def __init__(self, rows):
        self.rows = rows
        self.executes = 0

    async def execute(self, _stmt):
        self.executes += 1
        return FakeResult(self.rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class FakeTeam:
    """Every column `_snapshot_team` reads. Deliberately not an ORM object —
    the point of `TeamSnapshot` (#2107) is that nothing downstream needs one."""

    def __init__(self, tid, name, alternate_names=None, sport_id=1):
        self.id = tid
        self.name = name
        self.slug = name.lower().replace(" ", "-")
        self.alternate_names = alternate_names or []
        self.sport_id = sport_id
        self.abbreviation = None
        self.primary_color = "#123456"
        self.secondary_color = None
        self.logo_url_small = "https://example.test/logo-small.png"
        self.logo_url_large = "https://example.test/logo-large.png"
        self.current_record = None
        self.standings_data = None
        self.season_stats = None


EI_ROWS = [("nfl", 50, 1.5), ("nfl", 90, 4.0), ("nba", 50, 2.0)]


@pytest.fixture(autouse=True)
def _reset_caches():
    """Every test starts from a cold process. These are module globals, so a
    leaked value from one test is a silently-passing assertion in the next."""
    ev._ei_cache = {}
    ev._ei_cache_time = 0
    ev._team_cache = {}
    ev._team_cache_time = 0
    ev._STALE_REFRESH_INFLIGHT.clear()
    ev._STALE_REFRESH_TASKS.clear()
    yield
    ev._ei_cache = {}
    ev._ei_cache_time = 0
    ev._team_cache = {}
    ev._team_cache_time = 0
    ev._STALE_REFRESH_INFLIGHT.clear()
    ev._STALE_REFRESH_TASKS.clear()


async def _settle():
    """Let the refresh task that was kicked onto the loop actually run.

    The whole point of the change is that the rebuild happens AFTER the caller
    returns, so a test that asserts immediately is asserting on the wrong
    instant. One `sleep(0)` is not enough — the task has its own awaits.
    """
    for _ in range(20):
        await asyncio.sleep(0)
        if not ev._STALE_REFRESH_INFLIGHT:
            # The in-flight flag clears in the task's `finally`; the task's
            # done-callback (which releases the strong ref) is scheduled with
            # `call_soon` and has not run yet. Give the loop that turn, or
            # `_STALE_REFRESH_TASKS` reads as leaked when it is merely pending.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            return
    raise AssertionError("refresh never completed")


# ---------------------------------------------------------------------------
# 1. THE SHIP — past the TTL the caller does not wait.
# ---------------------------------------------------------------------------


class TestTheUserStopsPayingForTheRebuild:
    @pytest.mark.asyncio
    async def test_expired_ei_cache_is_served_without_a_query_on_the_request(self, monkeypatch):
        db = FakeSession(EI_ROWS)
        first = await ev._load_ei_percentiles(db)
        assert db.executes == 1, "a cold cache must build — that is not the bug"
        assert first == {"nfl": {50: 1.5, 90: 4.0}, "nba": {50: 2.0}}

        rebuilt = FakeSession(EI_ROWS)
        monkeypatch.setattr(
            "app.services.database.async_session_maker", lambda: rebuilt
        )
        ev._ei_cache_time -= ev._EI_CACHE_TTL + 1  # expire it

        served = await ev._load_ei_percentiles(db)
        assert db.executes == 1, (
            "the REQUEST's session must not be used to rebuild — that is the "
            "216-276 ms this change exists to stop charging a user"
        )
        assert served == first, "the stale value is served, not an empty dict"

        await _settle()
        assert rebuilt.executes == 1, "the rebuild must actually run, behind the response"

    @pytest.mark.asyncio
    async def test_expired_team_cache_is_served_without_a_query_on_the_request(self, monkeypatch):
        teams = [FakeTeam(1, "Celtics"), FakeTeam(2, "Lakers")]
        db = FakeSession(teams)
        first = await ev._build_team_lookup(db, ["Celtics"])
        assert db.executes == 1
        assert set(first) == {"Celtics"}

        rebuilt = FakeSession(teams)
        monkeypatch.setattr(
            "app.services.database.async_session_maker", lambda: rebuilt
        )
        ev._team_cache_time -= ev._TEAM_CACHE_TTL + 1

        served = await ev._build_team_lookup(db, ["Celtics"])
        assert db.executes == 1, (
            "the REQUEST's session must not load 1,592 teams — that is the "
            "342-424 ms this change exists to stop charging a user"
        )
        assert set(served) == {"Celtics"}

        await _settle()
        assert rebuilt.executes == 1

    @pytest.mark.asyncio
    async def test_a_burst_of_expired_requests_launches_ONE_rebuild(self, monkeypatch):
        """Without the in-flight guard, every request arriving in the same
        expired millisecond starts its own rebuild and the stampede is worse
        than the thing being fixed."""
        db = FakeSession(EI_ROWS)
        await ev._load_ei_percentiles(db)

        rebuilt = FakeSession(EI_ROWS)
        monkeypatch.setattr(
            "app.services.database.async_session_maker", lambda: rebuilt
        )
        ev._ei_cache_time -= ev._EI_CACHE_TTL + 1

        await asyncio.gather(*[ev._load_ei_percentiles(db) for _ in range(10)])
        await _settle()

        assert rebuilt.executes == 1, "ten expired callers, one rebuild"
        assert db.executes == 1, "and none of them blocked"


# ---------------------------------------------------------------------------
# 2. THE STALE VALUE MATCHES WHAT A BLOCKING BUILD WOULD HAVE PRODUCED.
# ---------------------------------------------------------------------------


class TestBothPathsShapeTheDataIdentically:
    @pytest.mark.asyncio
    async def test_refreshed_ei_value_equals_a_cold_blocking_build(self, monkeypatch):
        cold = await ev._load_ei_percentiles(FakeSession(EI_ROWS))

        ev._ei_cache = {"stale": {}}
        ev._ei_cache_time = 0  # ancient, but inside the ceiling after the nudge
        import time as _t

        ev._ei_cache_time = _t.monotonic() - (ev._EI_CACHE_TTL + 1)
        monkeypatch.setattr(
            "app.services.database.async_session_maker", lambda: FakeSession(EI_ROWS)
        )
        await ev._load_ei_percentiles(FakeSession(EI_ROWS))
        await _settle()

        assert ev._ei_cache == cold, (
            "the refresh-behind path and the blocking path must agree key for "
            "key — a warmed payload that differs by one key is a wrong answer "
            "served fast"
        )

    @pytest.mark.asyncio
    async def test_refreshed_team_value_equals_a_cold_blocking_build(self, monkeypatch):
        teams = [FakeTeam(1, "Celtics", ["Boston Celtics"]), FakeTeam(2, "Lakers")]
        await ev._build_team_lookup(FakeSession(teams), ["Celtics"])
        cold = dict(ev._team_cache)

        import time as _t

        ev._team_cache = {"stale": object()}
        ev._team_cache_time = _t.monotonic() - (ev._TEAM_CACHE_TTL + 1)
        monkeypatch.setattr(
            "app.services.database.async_session_maker", lambda: FakeSession(teams)
        )
        await ev._build_team_lookup(FakeSession(teams), ["Celtics"])
        await _settle()

        assert set(ev._team_cache) == set(cold)
        assert ev._team_cache.keys() >= {"Celtics", "Boston Celtics", "Lakers"}, (
            "the alternate-names dedup must survive the extraction — it is the "
            "reason this build is expensive and the reason it cannot be skipped"
        )


# ---------------------------------------------------------------------------
# 3. IT FAILS CLOSED.
# ---------------------------------------------------------------------------


class TestFailClosed:
    @pytest.mark.asyncio
    async def test_an_empty_cache_still_blocks_and_builds(self):
        """A first request in a fresh process has no stale value to serve.
        Returning `{}` there ships a search with no logos rather than a slow
        one — a wrong answer, not a fast one.

        🔴 The timestamp is set to NOW on purpose, and the first version of this
        test did not do that. With `_ei_cache_time = 0` the computed age is
        `time.monotonic()`, i.e. the MACHINE's uptime — so on any host up longer
        than 25 minutes an "empty cache is served stale" mutant fell through the
        ceiling into the blocking build and the test passed for a reason that
        had nothing to do with the code (gotcha #44: an anchor that depends on
        the clock is not an anchor). Pinning the timestamp makes the emptiness
        of the cache the ONLY thing that can send this down the blocking path.
        """
        import time as _t

        db = FakeSession(EI_ROWS)
        ev._ei_cache = {}
        ev._ei_cache_time = _t.monotonic()  # fresh, so only emptiness can block
        out = await ev._load_ei_percentiles(db)
        assert db.executes == 1, "an empty cache must BUILD, not serve {} fast"
        assert out, "an empty cache must not be 'served stale' as {}"

        tdb = FakeSession([FakeTeam(1, "Celtics")])
        ev._team_cache = {}
        ev._team_cache_time = _t.monotonic()
        tout = await ev._build_team_lookup(tdb, ["Celtics"])
        assert tdb.executes == 1
        assert tout

    @pytest.mark.asyncio
    async def test_past_the_ceiling_the_caller_blocks_again(self, monkeypatch):
        """A refresher that fails forever must degrade into the OLD slow
        behaviour, never into silently serving hour-old data with no signal.
        This is what makes the ceiling different from `TTL * 10`.

        🔴 The age below is a LITERAL, and the first version of this test used
        `ev._EI_CACHE_TTL * ev._STALE_SERVE_CEILING + 1`. That reads the very
        constant it exists to pin: raise the ceiling to a billion and the test
        raises its own age to match, so a mutant that deletes the ceiling
        entirely survived. A pin that is computed from the thing it pins is not
        a pin. The companion assertion states the expected constants outright,
        so a deliberate change to either fails HERE, visibly, instead of
        quietly widening what this test permits.
        """
        assert (ev._EI_CACHE_TTL, ev._STALE_SERVE_CEILING) == (300, 5), (
            "the literal age below is derived from these; changing a constant "
            "must be a visible edit to this test, not a silent re-base"
        )
        db = FakeSession(EI_ROWS)
        await ev._load_ei_percentiles(db)
        assert db.executes == 1

        monkeypatch.setattr(
            "app.services.database.async_session_maker", lambda: FakeSession(EI_ROWS)
        )
        ev._ei_cache_time -= 1501  # 300 s TTL * 5 ceiling, plus one second

        await ev._load_ei_percentiles(db)
        assert db.executes == 2, (
            "past the ceiling the request rebuilds synchronously — slow, but "
            "never silently stale"
        )

    @pytest.mark.asyncio
    async def test_a_failing_rebuild_leaves_the_previous_value_intact(self, monkeypatch):
        """A failed refresh must not poison the cache. The ceiling above is what
        stops the failure being invisible if it persists."""
        db = FakeSession(EI_ROWS)
        good = await ev._load_ei_percentiles(db)

        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr("app.services.database.async_session_maker", _boom)
        ev._ei_cache_time -= ev._EI_CACHE_TTL + 1

        served = await ev._load_ei_percentiles(db)
        assert served == good
        await _settle()
        assert ev._ei_cache == good, "a failed rebuild must not empty the cache"
        assert not ev._STALE_REFRESH_INFLIGHT, (
            "the in-flight flag must clear on failure too, or the cache can "
            "never refresh again for the life of the process"
        )

    def test_with_no_running_loop_the_caller_is_told_to_build(self):
        """No loop means nothing can run behind the caller, so serving stale
        would serve it forever. Refuse instead."""
        assert ev._serve_stale_and_refresh("nothing", None) is False
        assert not ev._STALE_REFRESH_INFLIGHT

    @pytest.mark.asyncio
    async def test_the_refresh_task_is_strongly_referenced(self, monkeypatch):
        """`asyncio` holds only a WEAK reference to a bare task, so without the
        module-level set the GC can collect a rebuild mid-flight and the cache
        silently never refreshes."""
        started = asyncio.Event()
        release = asyncio.Event()

        class SlowSession(FakeSession):
            async def execute(self, _stmt):
                started.set()
                await release.wait()
                return FakeResult(EI_ROWS)

        db = FakeSession(EI_ROWS)
        await ev._load_ei_percentiles(db)
        monkeypatch.setattr(
            "app.services.database.async_session_maker", lambda: SlowSession(EI_ROWS)
        )
        ev._ei_cache_time -= ev._EI_CACHE_TTL + 1

        await ev._load_ei_percentiles(db)
        await started.wait()
        assert ev._STALE_REFRESH_TASKS, "the in-flight task must be held"
        release.set()
        await _settle()
        assert not ev._STALE_REFRESH_TASKS, "and released when it finishes"


# ---------------------------------------------------------------------------
# 4. THE CACHES THIS TOUCHES ARE STILL THE ONES THE ROUTE USES.
# ---------------------------------------------------------------------------


class TestTheAliasStillPointsHere:
    def test_gei_alias_is_the_function_that_was_fixed(self):
        """`_load_gei_percentiles` is what `/api/events/search` calls; the fix
        landed on `_load_ei_percentiles`. If the alias is ever re-pointed, the
        search path silently loses this and the tests above still pass."""
        assert ev._load_gei_percentiles is ev._load_ei_percentiles
