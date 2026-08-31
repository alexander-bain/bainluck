"""LAT-P158 — an offseason team page stops paying a 9-13 s cold build.

WHAT A READER SAW BEFORE THIS FILE
----------------------------------
`_warm_prop_families` kept the team prop-families mirror warm for teams with a
fixture in ``[now - 1d, now + 14d]``. Prop families are season-long questions —
`routes/prop_families.py` says so in its own cache comment: *"whose probabilities
move on the futures poll cadence, not on a game clock"* — so a fixture window is
the wrong question, and it excluded exactly the pages whose futures are most
alive.

Measured on production `767db311`, 2026-08-31, first touch, five team pages:

    oklahoma-city-thunder    13,262 ms   99 props   no fixture -> never warmed
    golden-state-warriors    11,896 ms   84 props   no fixture -> never warmed
    new-york-knicks           8,924 ms   76 props   no fixture -> never warmed
    los-angeles-dodgers-mlb     251 ms              fixture    -> warm (mirror)
    detroit-tigers-mlb          272 ms              fixture    -> warm (mirror)

The fifteen teams holding the most prop markets in the database were all NBA,
59-99 outcomes each, and on that date every one of them sat outside the warm set.
Census the same day: 367 rostered teams, 100 fixture-reachable, 182 rostered
teams holding props with no fixture in the window (96 of them holding >= 10).

WHAT THESE GUARDS ASSERT
------------------------
Behaviour of the selection and the rotation, driven through the real task with a
recording session. Nothing here reads the source of the thing it guards — this
lane has been burned by a `getsource` guard that asserted a variable name and
passed for the entire life of the defect (CERT-506).
"""

import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.tasks import prop_families_warm as warm
from app.utils import event_concept_cache as cache_mod

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.store: dict = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, _ttl, v):
        self.store[k] = v

    def set(self, k, v, **kw):
        self.store.setdefault(k, v)
        return True

    def delete(self, *ks):
        for k in ks:
            self.store.pop(k, None)

    def eval(self, *a, **kw):
        return 1


class _RecordingSession:
    """Returns a fixed team-id list and KEEPS the statement, so a guard can ask
    what the selection actually asked Postgres for."""

    def __init__(self, team_ids):
        self._team_ids = list(team_ids)
        self.statements: list = []

    async def execute(self, stmt, *a, **kw):
        self.statements.append(stmt)
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = list(self._team_ids)
        result.scalars.return_value = scalars
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _session_for(team_ids):
    session = _RecordingSession(team_ids)

    def _factory(*a, **kw):
        return session

    _factory.session = session
    return _factory


def _built_recorder():
    built: list = []

    async def _build(team, db, cap, rc=None, **kw):
        built.append(int(getattr(team, "id", team)))
        return {"families": [], "total_families": 0}, False

    return built, _build


def _team_lookup_session(team_ids):
    """A session whose `execute` answers BOTH the selection query and the
    per-team `select(Team)` the rebuild path issues."""
    session = _RecordingSession(team_ids)
    calls = {"n": 0}

    async def execute(stmt, *a, **kw):
        session.statements.append(stmt)
        calls["n"] += 1
        result = MagicMock()
        scalars = MagicMock()
        if calls["n"] == 1:
            scalars.all.return_value = list(team_ids)
            scalars.first.return_value = None
        else:
            # 🔴 Resolve the id the task actually asked for. A fixture that
            # always answers `id=1` would make the rotation guard below assert
            # nothing at all — every build would record team 1 and `tail in
            # built` could only ever be false.
            params = stmt.compile().params
            requested = next(
                (v for v in params.values() if isinstance(v, int)), None
            )
            scalars.all.return_value = []
            scalars.first.return_value = SimpleNamespace(
                id=requested, name="T", slug="t", roster_players=[]
            )
        result.scalars.return_value = scalars
        return result

    session.execute = execute

    def _factory(*a, **kw):
        return session

    _factory.session = session
    return _factory


# ---------------------------------------------------------------------------
# 1. THE SHIP — a prop-holding team is reachable without a fixture
# ---------------------------------------------------------------------------


class TestPropHoldingTeamsAreReachable:
    async def test_the_selection_does_not_require_a_fixture(self):
        """The defect, as the SQL a reader's warmth depends on.

        Before LAT-P158 the selection was a single INNER JOIN to `events`, so a
        team with no row in the fixture window could not appear in the result at
        any prop count. The union must be reachable without one.
        """
        factory = _session_for([])
        with patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()), \
             patch("app.tasks.base.get_task_session", factory):
            await warm._warm_prop_families()

        sql = str(factory.session.statements[0].compile(
            compile_kwargs={"literal_binds": False}
        ))
        assert "futures_outcomes" in sql, (
            "the selection never looks at prop markets, so a team without a "
            f"fixture can never be warmed:\n{sql}"
        )
        # The fixture path must SURVIVE — this is a union, not a replacement.
        assert "events" in sql, sql

    async def test_the_prop_count_threshold_is_applied(self):
        factory = _session_for([])
        with patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()), \
             patch("app.tasks.base.get_task_session", factory):
            await warm._warm_prop_families()

        sql = str(factory.session.statements[0].compile(
            compile_kwargs={"literal_binds": True}
        ))
        assert "HAVING" in sql.upper(), sql
        assert str(warm.MIN_PROPS_TO_WARM) in sql, sql

    async def test_only_non_event_markets_count_as_props(self):
        """The warm set must count props the way the BUILDER counts them.

        `build_prop_families` filters `FuturesMarket.event_id IS NULL` — game
        markets are not prop families. A warmer that counted game markets would
        select a population the builder does not serve, and warm empty pages
        while the 99-prop teams waited.
        """
        factory = _session_for([])
        with patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()), \
             patch("app.tasks.base.get_task_session", factory):
            await warm._warm_prop_families()

        sql = str(factory.session.statements[0].compile(
            compile_kwargs={"literal_binds": True}
        )).lower()
        assert "event_id is null" in sql, sql

    async def test_a_rosterless_team_is_still_excluded(self):
        """The one thing the widening must NOT do: 9,258 rosterless teams were
        never slow (one ILIKE pattern, not 41) and must stay out."""
        factory = _session_for([])
        with patch("app.utils.event_concept_cache.get_client", return_value=_FakeRedis()), \
             patch("app.tasks.base.get_task_session", factory):
            await warm._warm_prop_families()

        sql = str(factory.session.statements[0].compile(
            compile_kwargs={"literal_binds": True}
        )).lower()
        assert "roster_players" in sql, sql
        assert sql.count("jsonb_array_length") >= 2, (
            "both ways in must require a roster, or the prop path becomes a "
            f"back door for the 9,258 rosterless teams:\n{sql}"
        )


# ---------------------------------------------------------------------------
# 2. THE WIDENING'S PRECONDITION — a capped pass must not starve its tail
# ---------------------------------------------------------------------------


class TestRotateThenCap:
    async def test_a_team_past_the_cap_is_reached_on_a_later_pass(self):
        """The latent bug the widening would otherwise have activated.

        The cap used to be applied to the id-ordered list BEFORE the rotation, so
        `MAX_TEAMS_PER_PASS` was a permanent membership test: every team past
        position N by primary key was dropped by EVERY pass, forever. With the set
        at 100 it never bound; LAT-P158 pushes the set towards the ceiling.
        """
        oversized = list(range(1, warm.MAX_TEAMS_PER_PASS + 6))
        tail = oversized[-1]

        rc = _FakeRedis()
        # The previous pass finished just before the tail.
        rc.store[warm.CURSOR_KEY] = str(tail - 1)

        built, build = _built_recorder()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _team_lookup_session(oversized)), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=build):
            out = await warm._warm_prop_families()

        assert out["selected"] == len(oversized)
        assert tail in built, (
            f"team {tail} sits past the cap by id and the cursor pointed right "
            "at it; it was still never built — the cap is being applied before "
            "the rotation"
        )

    async def test_a_pass_still_never_exceeds_the_cap(self):
        """Rotating first must not turn the backstop off."""
        oversized = list(range(1, warm.MAX_TEAMS_PER_PASS + 6))
        rc = _FakeRedis()
        built, build = _built_recorder()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch("app.tasks.base.get_task_session", _team_lookup_session(oversized)), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=build):
            out = await warm._warm_prop_families()

        assert len(built) <= warm.MAX_TEAMS_PER_PASS
        assert out["truncated"] == len(oversized) - warm.MAX_TEAMS_PER_PASS

    async def test_the_cap_is_still_reported_never_silent(self):
        oversized = list(range(1, warm.MAX_TEAMS_PER_PASS + 8))
        rc = _FakeRedis()
        built, build = _built_recorder()
        with patch("app.utils.event_concept_cache.get_client", return_value=rc), \
             patch.object(warm, "PASS_BUDGET_SECONDS", 0), \
             patch("app.tasks.base.get_task_session", _team_lookup_session(oversized)), \
             patch("app.routes.prop_families.build_and_cache_prop_families",
                   side_effect=build):
            out = await warm._warm_prop_families()
        assert out["selected"] == len(oversized)
        assert out["truncated"] == len(oversized) - warm.MAX_TEAMS_PER_PASS == 7


# ---------------------------------------------------------------------------
# 3. THE COVERAGE CONTRACT — still satisfied by the widened population
# ---------------------------------------------------------------------------


class TestCoverageArithmeticStillHolds:
    def test_a_maxed_out_set_is_still_covered_inside_the_mirror(self):
        """The contract LAT-P138 asserted, re-asserted against the widening.

        The population is now a UNION, so the thing that must stay true is that a
        set the size of `MAX_TEAMS_PER_PASS` is rebuilt before the 24 h mirror
        lapses — at the pessimistic rate of one slowest-measured build per team.
        """
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["warm-prop-families"]
        sched = entry["schedule"]
        period_seconds = 3600 // len(sched.minute)

        teams_per_pass = warm.PASS_BUDGET_SECONDS // warm.SLOWEST_MEASURED_BUILD_SECONDS
        assert teams_per_pass >= 1
        passes = math.ceil(warm.MAX_TEAMS_PER_PASS / teams_per_pass)
        assert passes * period_seconds <= cache_mod.STALE_TTL, (
            f"{passes} passes x {period_seconds}s exceeds the "
            f"{cache_mod.STALE_TTL}s mirror"
        )

    def test_the_threshold_keeps_the_measured_union_inside_the_cap(self):
        """Measured 2026-08-31: 100 fixture-reachable + 96 prop-reachable at
        `MIN_PROPS_TO_WARM = 10`. The threshold is what keeps the union under the
        population bound the contract above is asserted against — if it is
        lowered, that arithmetic has to be re-derived, not assumed.
        """
        measured_fixture_reachable = 100
        measured_prop_reachable_at_10 = 96
        assert warm.MIN_PROPS_TO_WARM >= 10, (
            "lowering the threshold widens the union past the measured 196; "
            "re-measure the census before changing it"
        )
        assert (
            measured_fixture_reachable + measured_prop_reachable_at_10
            <= warm.MAX_TEAMS_PER_PASS
        )

    def test_the_pass_budget_bounds_the_work_not_the_population(self):
        """Why widening the set is not a load increase: a pass stops at
        `PASS_BUDGET_SECONDS` whatever the population, so a wider set changes
        WHICH teams a pass builds and how long a full cycle takes — never how
        hard any one hour hits an already-saturated Postgres."""
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.warm_prop_families"]
        worst = warm.PASS_BUDGET_SECONDS + warm.PER_TEAM_TIMEOUT_SECONDS
        assert worst <= task.soft_time_limit < task.time_limit < 300


# ---------------------------------------------------------------------------
# 4. THE RIDER — the ring stops dropping the counter that explains `app_ms`
# ---------------------------------------------------------------------------


class TestRingCarriesUnfinishedQueries:
    def test_unfinished_queries_survives_into_the_ring_record(self):
        """`app_ms` is a RESIDUAL (`wall - db_ms`), and a cancelled statement is
        recorded in `DbTiming.unfinished`, never in `total_ms` — so its whole
        duration lands in `app_ms` and reads as CPU. The ring copied five keys and
        dropped the one that says otherwise. LAT-P145 had to take `unfinished=1`
        off response headers to diagnose this ring's own subject.
        """
        from app.utils import latency_stats

        raw = latency_stats.build_slow_event(
            timestamp=1788115730.956,
            path="/api/teams/{identifier}/prop-families",
            duration_ms=12394.5,
            cache_bucket="none",
            split={
                "db_ms": 326.5,
                "app_ms": 12068.0,
                "router_queue_ms": 2.2,
                "queries": 3,
                "max_query_ms": 159.1,
                "unfinished_queries": 1,
            },
        )
        record = latency_stats.parse_slow_event(raw)
        assert record is not None
        assert record.get("unfinished_queries") == 1, record

    def test_a_clean_request_record_is_unchanged(self):
        """`build_split` omits the key when it is zero, so this only ever ADDS a
        field to a record that had something to declare."""
        from app.utils import latency_stats

        raw = latency_stats.build_slow_event(
            timestamp=1788115730.956,
            path="/api/feed",
            duration_ms=7000.0,
            cache_bucket="miss",
            split={"db_ms": 6000.0, "app_ms": 1000.0, "queries": 12},
        )
        record = latency_stats.parse_slow_event(raw)
        assert "unfinished_queries" not in record, record

    def test_a_zero_count_is_not_written(self):
        from app.utils import latency_stats

        raw = latency_stats.build_slow_event(
            timestamp=1788115730.956,
            path="/api/feed",
            duration_ms=7000.0,
            cache_bucket="miss",
            split={"db_ms": 6000.0, "app_ms": 1000.0, "unfinished_queries": 0},
        )
        assert "unfinished_queries" not in latency_stats.parse_slow_event(raw)
