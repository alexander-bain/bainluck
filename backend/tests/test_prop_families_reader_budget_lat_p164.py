"""Guards for LAT-P164 (#2383): the first reader of a team page stops waiting
twelve seconds for a branch that was going to be cancelled anyway.

WHAT WAS MEASURED, production `6043c1c0`, 2026-08-31.

The slow-event ring, age-stratified (and the stratification is the finding —
`/api/events/typeahead` has the most entries in the 6.5-day ring and ZERO in the
last 24 h, so a ranking on ring totals re-fixes a fixed route). In the last
24 hours `/api/teams/{identifier}/prop-families` is second by count and FIRST by
cost, nine events, **every one `cache=none`**:

    7,716  8,703  11,610  12,376  12,377  12,390  12,394  12,650  12,969  ms

Six of those nine sit inside 600 ms of each other against
`_BRANCH_TIMEOUT_MS = 12000`. That cluster is not a cost, it is THE TIMEOUT: a
reader waiting out an expiry and then being handed the page without the content
they waited for. LAT-P145 already stopped that expiry erasing its sibling
branches; what it deliberately did not change is how long the reader waits for it.

WHERE THE TIME GOES — `EXPLAIN (ANALYZE)` on production, Virginia Cavaliers'
own 41 patterns, the outcome-name branch:

    Bitmap Index Scan on ix_futures_outcomes_name_trgm   11,789 ms   23 rows

The whole branch is that one scan. The index is 464 MB over 4.17M rows and the
box is at 103% of plan, so each probe is a cold read. Cost is LINEAR IN PROBE
COUNT and the curve was re-measured this session:

    patterns    1      2      5     10     20     41
    exec ms   222    107    646    768  1,990  4,752    (warm; 11,830 cold)

The team's OWN name is one probe and returns all six of its real rows. The forty
roster probes are 97% of the bill. So the two are separated, and the reader is
given a TOTAL budget that the cheap probes fit inside and the roster probes do
not — with the roster handed to the background rebuild, which has nobody waiting
on it and publishes the complete answer for every reader after the first.

🔴 WHAT THESE GUARDS REFUSE TO LET THE FIX BUY ITS WIN WITH. A latency change on
a matching surface can always go faster by returning less, and this one is one
`continue` away from doing exactly that permanently. So the load-bearing
assertions here are NOT about speed:

  * `budget_ms=None` — the background path — must behave EXACTLY as it did, all
    branches, 12,000 ms each. If the producer ever inherits the reader's budget,
    the deferral has no destination and the roster content is gone for good.
  * a deferred build must DISPATCH the rebuild. Without it the deferral is a
    silent narrowing of the page, one primary TTL at a time.
  * `branch_deferred:` and `branch_timeout:` must stay DIFFERENT reason strings,
    so a branch that starts genuinely timing out cannot hide inside a reason
    that is expected and benign.

Every assertion is on SHAPE, CALL COUNT and REASON STRINGS. The clock is
injected, never slept on, so nothing here is timing-dependent in CI.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Select

from app.routes import prop_families as route
from app.utils import event_concept_cache as cache_mod

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Doubles — local, so collection order is never load-bearing.
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)

    def eval(self, script, numkeys, *args):
        key = args[0]
        if script is cache_mod._SETEX_IF_UNCHANGED_LUA:
            absent_only, expected, ttl, value = args[1], args[2], args[3], args[4]
            current = self.store.get(key)
            if absent_only == "1":
                if current is not None:
                    return 0
            elif current != (expected.encode() if isinstance(expected, str) else expected):
                return 0
            self.ttls[key] = int(ttl)
            self.store[key] = value.encode() if isinstance(value, str) else value
            return 1
        expected = args[1].encode() if isinstance(args[1], str) else args[1]
        if self.store.get(key) == expected:
            self.store.pop(key, None)
            return 1
        return 0


class QueryCanceledError(Exception):
    """Spelled with asyncpg's exact class name — `is_statement_timeout` matches
    on `type(exc).__name__`, so a differently-named double would exercise only
    the message arm."""


def _timeout():
    return QueryCanceledError("canceling statement due to statement timeout")


def _outcome(oid, name, prob, market_id):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        market_id=market_id, is_winner=False,
    )


def _market(mid, name):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", group_id=None, status="open",
        resolution_date=None, market_metadata={},
    )


def _pair(oid, oname, prob, mid, mname):
    return (_outcome(oid, oname, prob, mid), _market(mid, mname))


#: Award-shaped names on purpose: `group_prop_families` drops any family with
#: fewer than two distinct entities, so a fixture that grouped to nothing would
#: make the payload assertions vacuously true.
FK_ROWS = [
    _pair(1, "Dexter Lawrence", 0.04, 100, "Defensive Player of the Year"),
    _pair(2, "Brian Burns", 0.06, 100, "Defensive Player of the Year"),
]
TEAM_NAME_ROWS = [
    _pair(3, "Jaxson Dart", 0.02, 200, "NFL MVP 2026"),
    _pair(4, "Patrick Mahomes", 0.14, 200, "NFL MVP 2026"),
]
ROSTER_ROWS = [
    _pair(5, "Malik Nabers", 0.09, 300, "Offensive Player of the Year"),
    _pair(6, "Saquon Barkley", 0.21, 300, "Offensive Player of the Year"),
]


def _rows_result(items):
    result = MagicMock()
    result.all.return_value = list(items)
    scalars = MagicMock()
    scalars.all.return_value = list(items)
    scalars.first.return_value = items[0] if items else None
    result.scalars.return_value = scalars
    return result


def _is_branch(stmt) -> bool:
    return isinstance(stmt, Select) and "futures_outcomes" in str(stmt)


class _BranchDB:
    """An AsyncSession double driven BY BRANCH, and a clock it advances itself.

    `costs_ms` is how long each branch is pretended to take. The route reads the
    clock, so charging the elapsed time HERE — at the branch — is what lets a
    deferral be provoked deterministically without a `sleep`.
    """

    def __init__(self, plan, *, costs_ms=None, team=None):
        self.plan = list(plan)
        self.costs_ms = list(costs_ms or [])
        self.branch_index = 0
        self.rollbacks = 0
        self.timeouts_set: list[str] = []
        self.branch_stmts: list = []
        self._team = team if team is not None else _team()
        self.now = 0.0

    def monotonic(self):
        return self.now

    async def execute(self, stmt, *args, **kwargs):
        rendered = str(stmt)
        if "statement_timeout" in rendered:
            self.timeouts_set.append(rendered)
            return _rows_result([])
        if not _is_branch(stmt):
            return _rows_result([self._team])
        i = self.branch_index
        self.branch_index += 1
        self.branch_stmts.append(stmt)
        if i < len(self.costs_ms):
            self.now += self.costs_ms[i] / 1000.0
        step = self.plan[i] if i < len(self.plan) else []
        if isinstance(step, BaseException):
            raise step
        return _rows_result(step)

    async def rollback(self):
        self.rollbacks += 1


def _team(*, tid=547, name="New York Giants", slug="new-york-giants", roster=None):
    return SimpleNamespace(
        id=tid, name=name, slug=slug,
        roster_players=[{"name": n} for n in (roster or ["Malik Nabers"])],
    )


def _clock_of(db):
    """Patch ONLY the route module's `time`, so the injected clock cannot leak
    into anything else running in this event loop."""
    return patch.object(route, "time", SimpleNamespace(monotonic=db.monotonic))


async def _build(plan, *, costs_ms=None, team=None, budget_ms=None, cap=400):
    db = _BranchDB(plan, costs_ms=costs_ms, team=team)
    team = team if team is not None else _team()
    with _clock_of(db):
        result = await route.build_prop_families(team, db, cap, budget_ms=budget_ms)
    return result, db


def _reasons(payload):
    """The loss reasons, from wherever this payload is holding them.

    A raw `build_prop_families` result carries them in the PRIVATE list that
    `take_build_quality` later pops; a stamped one carries them in the envelope.
    Reading only the envelope would make every raw-build assertion here compare
    `set()` to `set()` and pass for the wrong reason — the vacuous-guard trap.
    """
    env = payload.get(cache_mod.ENVELOPE_FIELD)
    if isinstance(env, dict):
        return env.get("quality_reasons") or []
    _quality, reasons = cache_mod.take_build_quality(payload)
    return reasons


def _timeout_values(db):
    """The ms figure out of each `SET LOCAL statement_timeout = 'N'`."""
    out = []
    for stmt in db.timeouts_set:
        digits = "".join(c for c in stmt if c.isdigit())
        out.append(int(digits))
    return out


# ---------------------------------------------------------------------------
# 1. THE SHIP — the reader stops paying for the roster probe
# ---------------------------------------------------------------------------


class TestTheReaderIsBounded:
    async def test_the_reader_stops_at_the_budget_not_at_the_branch_ceiling(self):
        """The production shape, modelled honestly.

        The route cannot know a branch is slow before running it, so the roster
        probe IS started — and is cancelled by the remaining budget rather than
        by the 12 s ceiling. That is the whole ship: the same reader who waited
        12,376 ms now waits 2,500, and the branch AFTER the one that spent the
        budget is never started at all.
        """
        (payload, unusable), db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], _timeout(), ROSTER_ROWS],
            costs_ms=[10, 250, 250, 1990, 4500],
            budget_ms=2500,
        )
        assert unusable is False
        assert db.branch_index == 4, "the last branch was started past the budget"
        assert db.now * 1000 == pytest.approx(2500), "the reader overran the budget"
        assert set(_reasons(payload)) == {
            f"branch_timeout:{route._BRANCH_OUTCOME_ROSTER}",
            f"branch_deferred:{route._BRANCH_MARKET_ROSTER}",
        }
        # The cancelled probe was bounded by what was LEFT (1,990 ms), never by
        # the 12,000 ms ceiling — that difference is the ten seconds.
        assert _timeout_values(db) == [2500, 2490, 2240, 1990]

    async def test_a_deferred_branch_is_never_started_at_all(self):
        """NOT "started and cancelled". A cancelled statement still costs the
        reader its whole remaining wait and returns nothing, so the budget guard
        would become the failure mode it exists to prevent."""
        (_payload, _unusable), db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], _timeout(), _timeout()],
            costs_ms=[10, 250, 2200, 0, 0],
            budget_ms=2500,
        )
        # Only 40 ms of budget remained, which is under the floor. If either
        # roster branch had been STARTED, its planted timeout would have raised
        # and been rolled back. Neither happened.
        assert db.branch_index == 3
        assert db.rollbacks == 0
        assert len(db.timeouts_set) == 3, db.timeouts_set

    async def test_the_content_the_reader_does_get_is_the_cheap_branches_content(self):
        (payload, _unusable), _db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[10, 250, 2200, 0, 0],
            budget_ms=2500,
        )
        entities = {r["entity"] for f in payload["families"] for r in f["rows"]}
        assert entities == {
            "Dexter Lawrence", "Brian Burns", "Jaxson Dart", "Patrick Mahomes",
        }
        # Named, not counted: the roster rows must be ABSENT from this reader's
        # payload, which is what makes the dispatch guard below load-bearing.
        assert "Saquon Barkley" not in entities

    async def test_a_budget_that_fits_everything_defers_nothing(self):
        """The fast team must be untouched — most teams have no roster at all,
        and a guard suite that only proved the slow case would not notice the
        budget clipping a build that was always fine."""
        (payload, unusable), db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[10, 20, 20, 30, 30],
            budget_ms=2500,
        )
        assert unusable is False
        assert db.branch_index == 5
        assert _reasons(payload) == []
        entities = {r["entity"] for f in payload["families"] for r in f["rows"]}
        assert "Saquon Barkley" in entities

    async def test_a_rosterless_team_runs_three_branches_and_defers_nothing(self):
        team = SimpleNamespace(
            id=901, name="Some Club", slug="some-club", roster_players=[]
        )
        (payload, unusable), db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, []],
            costs_ms=[10, 20, 20], team=team, budget_ms=2500,
        )
        assert unusable is False
        assert db.branch_index == 3
        assert _reasons(payload) == []


# ---------------------------------------------------------------------------
# 2. THE THING THE FIX MUST NOT BUY ITS WIN WITH
# ---------------------------------------------------------------------------


class TestTheBackgroundPathIsUnchanged:
    """`budget_ms=None` is the producer. If it ever inherits a reader's budget,
    the deferral has no destination and the roster content is gone permanently —
    a matching regression wearing a latency fix's clothes."""

    async def test_no_budget_runs_every_branch_however_slow(self):
        (payload, unusable), db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[10, 250, 250, 11800, 4500],
            budget_ms=None,
        )
        assert unusable is False
        assert db.branch_index == 5
        assert _reasons(payload) == []
        entities = {r["entity"] for f in payload["families"] for r in f["rows"]}
        assert "Saquon Barkley" in entities

    async def test_no_budget_still_bounds_each_branch_at_twelve_seconds(self):
        _r, db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[10, 250, 250, 11800, 4500],
            budget_ms=None,
        )
        assert _timeout_values(db) == [12000] * 5

    async def test_the_default_is_no_budget(self):
        """A producer that forgot to pass one must NOT silently become bounded.
        Asserted on the signature's default, because the call sites are what
        change under a refactor."""
        import inspect

        sig = inspect.signature(route.build_prop_families)
        assert sig.parameters["budget_ms"].default is None
        sig2 = inspect.signature(route.build_and_cache_prop_families)
        assert sig2.parameters["budget_ms"].default is None

    async def test_the_warmer_passes_no_budget(self):
        """The producer's own call sites, read from source. If the warmer ever
        starts passing a budget, every deferred branch becomes unrecoverable."""
        import inspect

        from app.tasks import prop_families_warm as warm

        src = inspect.getsource(warm)
        assert "budget_ms" not in src, (
            "the producer must not pass a reader budget — it IS the destination "
            "the reader's deferral is handed to"
        )


class TestDeferralIsReportedDistinctlyFromExpiry:
    async def test_a_deferral_and_an_expiry_do_not_share_a_reason_string(self):
        """Collapsing the two would hide a real regression — a branch that
        starts genuinely timing out — inside a reason that is expected."""
        (payload, _unusable), _db = await _build(
            [FK_ROWS, _timeout(), [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[10, 250, 2200, 0, 0],
            budget_ms=2500,
        )
        reasons = set(_reasons(payload))
        assert f"branch_timeout:{route._BRANCH_OUTCOME_NAME}" in reasons
        assert f"branch_deferred:{route._BRANCH_OUTCOME_ROSTER}" in reasons
        assert f"branch_deferred:{route._BRANCH_MARKET_ROSTER}" in reasons

    async def test_a_partial_from_a_deferral_is_stamped_partial(self):
        rc = _FakeRedis()
        db = _BranchDB(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[10, 250, 250, 11800, 4500],
        )
        with _clock_of(db):
            payload, unusable = await route.build_and_cache_prop_families(
                _team(), db, 400, rc, budget_ms=2500
            )
        assert unusable is False
        env = payload[cache_mod.ENVELOPE_FIELD]
        assert env["quality"] == cache_mod.QUALITY_PARTIAL

    async def test_everything_lost_or_deferred_is_still_the_unusable_answer(self):
        """A build where nothing ran must stay the shape that is never cached —
        an empty `families` is then an artefact of the bound, not an answer
        about this team (gotcha #53)."""
        (payload, unusable), _db = await _build(
            [_timeout()] * 5,
            costs_ms=[3000, 0, 0, 0, 0],
            budget_ms=2500,
        )
        assert unusable is True
        assert payload["total_families"] == 0
        assert cache_mod.ENVELOPE_FIELD not in payload


# ---------------------------------------------------------------------------
# 3. THE DEFERRAL MUST HAVE A DESTINATION
# ---------------------------------------------------------------------------


class TestADeferredBuildSchedulesItsCompletion:
    async def test_a_partial_cold_build_dispatches_the_rebuild(self):
        rc = _FakeRedis()
        db = _BranchDB(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[10, 250, 250, 11800, 4500],
        )
        sent = MagicMock()
        with _clock_of(db), \
             patch.object(route, "get_client", return_value=rc), \
             patch("app.tasks.celery_app.send_task", sent):
            await route.get_team_prop_families("new-york-giants", 400, db)
        assert sent.call_count == 1, "the deferred roster branches were abandoned"
        assert sent.call_args.args[0] == "app.tasks.refresh_prop_families"

    async def test_a_complete_cold_build_dispatches_nothing(self):
        """The dispatch is not unconditional. A team whose whole build fits in
        the budget must not cost a background rebuild on every cold read."""
        rc = _FakeRedis()
        db = _BranchDB(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[10, 20, 20, 30, 30],
        )
        sent = MagicMock()
        with _clock_of(db), \
             patch.object(route, "get_client", return_value=rc), \
             patch("app.tasks.celery_app.send_task", sent):
            await route.get_team_prop_families("new-york-giants", 400, db)
        assert sent.call_count == 0

    async def test_the_rebuild_it_schedules_is_the_unbudgeted_one(self):
        """Closing the loop the ship depends on: the task the route dispatches
        must reach `build_and_cache_prop_families` WITHOUT a budget, or the
        deferred content is never fetched by anyone."""
        import inspect

        from app.tasks import prop_families_warm as warm

        src = inspect.getsource(warm._refresh_prop_families)
        assert "build_and_cache_prop_families" in src
        assert "budget_ms" not in src


# ---------------------------------------------------------------------------
# 4. THE INDEPENDENT WIN — the split, on its own terms
# ---------------------------------------------------------------------------


class TestTheSplitStopsTheRosterErasingTheTeamName:
    """LAT-P145 stopped one branch erasing its SIBLINGS. The two name branches
    were still one query each, so a roster expiry took the team-name rows down
    with it — the expensive half erasing the cheap half. This holds even with no
    budget in play, which is why it is asserted at `budget_ms=None`."""

    async def test_a_roster_expiry_keeps_the_team_name_rows(self):
        (payload, unusable), db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], _timeout(), _timeout()],
            budget_ms=None,
        )
        assert unusable is False
        entities = {r["entity"] for f in payload["families"] for r in f["rows"]}
        # The team-name branch's rows survive an expiry in the roster probe that
        # used to share its statement.
        assert {"Jaxson Dart", "Patrick Mahomes"} <= entities
        assert db.rollbacks == 2

    async def test_the_branch_order_spends_the_budget_cheapest_first(self):
        """A budget spends itself in order, so the ORDER is the policy. Asserted
        by reading the compiled SQL, not by trusting the constant list."""
        (_payload, _unusable), db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            team=_team(roster=["Malik Nabers", "Saquon Barkley"]),
            budget_ms=None,
        )
        sql = [str(s.compile(compile_kwargs={"literal_binds": True}))
               for s in db.branch_stmts]
        assert len(sql) == 5
        assert "team_id" in sql[0] and "ILIKE" not in sql[0].upper()
        # The two cheap probes come before the two expensive ones.
        for cheap in sql[1:3]:
            assert "New York Giants" in cheap
            assert "Malik Nabers" not in cheap
        for pricey in sql[3:5]:
            assert "Malik Nabers" in pricey
            assert "New York Giants" not in pricey


# ---------------------------------------------------------------------------
# 5. THE BUDGET ARITHMETIC
# ---------------------------------------------------------------------------


class TestTheBudgetArithmetic:
    async def test_each_branch_is_bounded_by_what_is_LEFT_not_by_the_whole(self):
        """A per-branch bound of the FULL budget would let three branches spend
        three budgets — the 48-second reader the total budget exists to prevent."""
        _r, db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[1000, 500, 0, 0, 0],
            budget_ms=2500,
        )
        assert _timeout_values(db) == [2500, 1500, 1000, 1000, 1000]

    async def test_a_branch_is_skipped_below_the_floor_not_given_a_sliver(self):
        """Handing a branch 40 ms is a cancelled statement dressed as a budget."""
        _r, db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[2400, 0, 0, 0, 0],
            budget_ms=2500,
        )
        assert db.branch_index == 1, "a branch ran on less than the floor"
        assert route._MIN_BRANCH_MS == 250

    async def test_the_budget_never_exceeds_the_per_branch_ceiling(self):
        """A caller passing a huge budget must not lift the 12 s statement
        ceiling this route has carried since #1197."""
        _r, db = await _build(
            [FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
            costs_ms=[0, 0, 0, 0, 0],
            budget_ms=90_000,
        )
        assert _timeout_values(db) == [12000] * 5

    def test_the_reader_budget_is_the_declared_constant(self):
        assert route._READER_BUDGET_MS == 2500
        assert route._BRANCH_TIMEOUT_MS == 12000

    async def test_the_route_passes_the_reader_budget_and_not_something_else(self):
        rc = _FakeRedis()
        db = _BranchDB([FK_ROWS, TEAM_NAME_ROWS, [], ROSTER_ROWS, ROSTER_ROWS],
                       costs_ms=[0, 0, 0, 0, 0])
        seen = {}

        async def _spy(team, _db, cap, rc_=None, budget_ms=None):
            seen["budget_ms"] = budget_ms
            return {"families": [], cache_mod.ENVELOPE_FIELD: {"quality": "full"}}, False

        with _clock_of(db), \
             patch.object(route, "get_client", return_value=rc), \
             patch.object(route, "build_and_cache_prop_families", _spy):
            await route.get_team_prop_families("new-york-giants", 400, db)
        assert seen["budget_ms"] == route._READER_BUDGET_MS
