"""CAL-P1012 / #3195 — the fabricated-loss census can finish, so the drain can be
proved finished.

#2528's runbook is census -> dry-run -> read the plan -> apply -> re-census, and
its completion test is *finished = the addressed bands measure 0*. The census was
one whole-table aggregate over ``futures_outcomes`` — ``GROUP BY fo.market_id``
across every leg, ``HAVING`` the all-loser predicate — with no bound but a
statement timeout. Measured twice warm against production on 2026-09-05 it died
both times at ``elapsed_s`` 22.1 / 22.2 with ``QueryCanceledError``. The rail
reported that honestly (``measured: false``, never a zero), so this was never a
false green: it was a missing gate. The drain could run and nothing could say it
was done.

The census is now a WALK over a half-open ``market_id`` range: one bounded
statement per chunk, the width HALVED on a chunk that trips the bound and grown
back afterwards, accumulated in a durable slot across calls, and stopped by a
wall clock rather than by a query dying.

WHY THE FAKE HONOURS ITS RANGE PARAMETERS, and why the suite is worth anything.
A fake session that ignores the bound parameters it is handed cannot tell a
chunked walk from a whole-table one — it would pass against the very defect being
repaired. So ``_CensusSession`` really does filter its population by ``(lo, hi]``,
really does raise a statement timeout for a range wider than it was told it can
serve, and counts any call that arrives with NO range bound. The catching test in
:class:`TestACensusThatCouldNotFinishNowFinishes` sets a servable width narrower
than the id space and asserts ``measured: true`` — against the old unbounded
query that is ``measured: false``, every time.
"""

from __future__ import annotations

import json
import math

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.durable_state import DEFAULT_MAX_AGE_S, canonical_json, decode_envelope
from app.utils.kalshi_fabricated_loss import (
    POPULATION_HAVING_SQL,
    RETENTION_BAND_SQL,
)


class _StatementTimeout(Exception):
    """What asyncpg raises through SQLAlchemy when a statement is cancelled."""

    def __init__(self) -> None:
        super().__init__("canceling statement due to statement timeout")


class _Row:
    def __init__(self, source, mutex, retention_band, markets, outcomes) -> None:
        self.source = source
        self.mutex = mutex
        self.retention_band = retention_band
        self.markets = markets
        self.outcomes = outcomes


class _Result:
    def __init__(self, rows=(), scalar=None) -> None:
        self._rows = list(rows)
        self._scalar = scalar

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _Clock:
    """A monotonic clock the test drives, so a wall-budget stop is deterministic.

    Wall-clock behaviour tested against the real clock is a flake with a
    schedule; here the fake session ticks it by a known step per chunk and the
    budget is arithmetic.
    """

    def __init__(self, step: float = 0.0) -> None:
        self.t = 0.0
        self.step = step

    def monotonic(self) -> float:
        return self.t

    def tick(self) -> None:
        self.t += self.step


#: The population, as rows that already satisfy ``POPULATION_HAVING_SQL``.
#: Spread across a wide, SPARSE id space on purpose — production runs
#: market_id 1 .. 60,261,730 over 3.97M legs, and the density is skewed ~6x
#: toward the recent end, which is why no single chunk width is safe.
#: (market_id, source, mutually_exclusive, retention_band, legs)
_POPULATION = [
    (10, "kalshi", True, "reachable", 3),
    (150_000, "kalshi", True, "reachable", 2),
    (399_999, "kalshi", False, "at_risk", 5),
    (400_000, "kalshi", True, "provably_purged", 4),
    (400_001, "polymarket", True, "reachable", 2),
    (900_000, "kalshi", True, "future_date", 6),
    (1_100_000, "kalshi", True, "reachable", 2),
    (1_599_999, "polymarket", False, "unknown_date", 3),
    (1_600_000, "kalshi", True, "at_risk", 7),
    (1_999_999, "kalshi", False, "reachable", 2),
]

_MAX_MARKET_ID = 2_000_000


def _expected_cells(population=_POPULATION):
    """The answer, computed in the test rather than by the code under test."""
    cells: dict[tuple, dict[str, int]] = {}
    for _mid, source, mutex, band, legs in population:
        cell = cells.setdefault((source, mutex, band), {"markets": 0, "outcomes": 0})
        cell["markets"] += 1
        cell["outcomes"] += legs
    return cells


def _cells_from(breakdown):
    return {
        (b["source"], b["mutually_exclusive"], b["retention_band"]): {
            "markets": b["markets"],
            "outcomes": b["outcomes"],
        }
        for b in breakdown
    }


class _CensusSession:
    """A session that HONOURS the bounds it is handed.

    Three levers, each modelling something production really does:

    * ``servable_width`` — a range wider than this raises a statement timeout,
      which is the production behaviour the walk must narrow through;
    * ``die_always`` — every width dies, so the floor path is reachable;
    * ``clock`` — ticked once per population query, so the wall budget is
      deterministic.

    ``unbounded_calls`` counts population queries that arrive with no range at
    all. It is asserted to be zero: that count is the #3195 defect itself.
    """

    def __init__(
        self,
        population=_POPULATION,
        *,
        servable_width: int | None = None,
        die_always: bool = False,
        max_market_id: int = _MAX_MARKET_ID,
        clock: _Clock | None = None,
    ) -> None:
        self.population = list(population)
        self.servable_width = servable_width
        self.die_always = die_always
        self.max_market_id = max_market_id
        self.clock = clock
        self.ranges: list[tuple[int, int]] = []
        self.served: list[tuple[int, int]] = []
        self.unbounded_calls = 0
        self.rollbacks = 0
        self.timeouts_set: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "statement_timeout" in sql:
            self.timeouts_set.append(sql)
            return _Result()
        if "MAX(market_id)" in sql:
            return _Result(scalar=self.max_market_id)

        if not params or "lo" not in params or "hi" not in params:
            # The defect: one whole-table aggregate, no range, dies at its bound.
            self.unbounded_calls += 1
            raise _StatementTimeout()

        lo, hi = int(params["lo"]), int(params["hi"])
        self.ranges.append((lo, hi))
        if self.clock is not None:
            self.clock.tick()
        if self.die_always or (
            self.servable_width is not None and hi - lo > self.servable_width
        ):
            raise _StatementTimeout()

        self.served.append((lo, hi))
        cells: dict[tuple, dict[str, int]] = {}
        for mid, source, mutex, band, legs in self.population:
            if lo < mid <= hi:
                cell = cells.setdefault(
                    (source, mutex, band), {"markets": 0, "outcomes": 0}
                )
                cell["markets"] += 1
                cell["outcomes"] += legs
        return _Result(
            _Row(s, m, b, c["markets"], c["outcomes"])
            for (s, m, b), c in cells.items()
        )

    async def rollback(self):
        self.rollbacks += 1


class _FaithfulDurableStore:
    """The durable slot, read back through the PRODUCTION DECODER.

    CERT-1903 blocked the first presentation of this change on exactly the gap a
    permissive fake leaves. ``_save_census`` banked each partial checkpoint with
    the envelope flag ``complete=False`` — reading "the walk is not finished" —
    and ``decode_envelope`` classifies such an envelope ``malformed /
    IncompleteArtifact`` and refuses to return it. So in production every
    checkpoint was unreadable, the next ``?after_id=`` call got
    ``CENSUS_CURSOR_MOVED``, and the multi-call walk could never resume. The
    suite was green throughout, because the fake it ran against answered ``ok``
    for an incomplete envelope.

    So this store does not judge envelopes itself. It stores the same field dict
    the production upsert writes (``publish_snapshot_in_txn``) and reads it back
    through the real :func:`decode_envelope` — the same function the real reader
    calls. Every completeness, checksum, version and age rule is therefore the
    shipped one, and a fake can no longer be more forgiving than the database.

    The three levers of the store it replaces are kept, because tests here use
    them: ``no_op`` (answers without persisting), ``forced_status`` (a status of
    our choosing), ``unreadable`` (a read that fails, which must never read as
    absent).
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.reads: list[str] = []
        self.publishes: list[str] = []
        self.no_op: set[str] = set()
        self.forced_status: dict[str, str] = {}
        self.unreadable: dict[str, str] = {}

    def install(self, monkeypatch) -> "_FaithfulDurableStore":
        import app.services.durable_snapshots as ds

        monkeypatch.setattr(ds, "read_snapshot_standalone", self.read)
        monkeypatch.setattr(ds, "publish_snapshot_standalone", self.publish)
        return self

    async def publish(self, envelope):
        self.publishes.append(envelope.identity)
        status = self.forced_status.get(envelope.identity, "ok")
        if envelope.identity in self.no_op or status != "ok":
            return {
                "status": status,
                "identity": envelope.identity,
                "generation": envelope.generation,
            }
        existing = self.rows.get(envelope.identity)
        if existing is not None and existing["generation"] > envelope.generation:
            return {
                "status": "superseded",
                "identity": envelope.identity,
                "generation": envelope.generation,
            }
        # The same columns `_UPSERT_SQL` writes, and the payload round-tripped
        # through canonical_json exactly as the JSONB column would.
        self.rows[envelope.identity] = {
            "identity": envelope.identity,
            "schema_version": envelope.schema_version,
            "generation": envelope.generation,
            "generated_at": envelope.generated_at,
            "payload": json.loads(canonical_json(envelope.payload)),
            "checksum": envelope.checksum,
            "complete": envelope.complete,
            "source": envelope.source,
        }
        return {
            "status": "ok",
            "identity": envelope.identity,
            "generation": envelope.generation,
        }

    async def read(self, identity, *, expected_version=None, max_age_s=None):
        self.reads.append(identity)
        if identity in self.unreadable:
            raise RuntimeError(f"durable read failed: {self.unreadable[identity]}")
        return decode_envelope(
            self.rows.get(identity),
            tier="durable",
            expected_version=expected_version,
            max_age_s=max_age_s if max_age_s is not None else DEFAULT_MAX_AGE_S,
        )


@pytest.fixture
def store(monkeypatch):
    """The durable slot the walk accumulates in."""
    return _FaithfulDurableStore().install(monkeypatch)


# =============================================================================
# The bound has to be in the place that was timing out
# =============================================================================


class TestTheBoundIsInsideTheAggregate:
    """A predicate on the OUTER join would change the answer, not the cost.

    Postgres does not push a join qualifier through a ``GROUP BY`` on the join
    key, so a bound applied after the join leaves the whole-table pass over
    ``futures_outcomes`` exactly as expensive as it was. This is a source-text
    guard because it is the one property no runtime double can observe: a fake
    that filters correctly cannot tell you WHERE the filter would run.
    """

    def test_the_range_bound_precedes_the_grouping_it_bounds(self):
        sql = rail._CENSUS_SQL
        where = sql.index("WHERE fo.market_id >")
        group = sql.index("GROUP BY fo.market_id")
        assert where < group, (
            "the range bound must restrict the grouped subquery over "
            "futures_outcomes — the aggregate that was timing out. Below its "
            "GROUP BY it is a filter on the join above, which changes the "
            "answer without changing the cost (#3195)."
        )

    def test_both_bounds_are_cast(self):
        # asyncpg prepares with no parameter types and infers from the text
        # alone; the sibling `_WORK_SQL` carries a whole comment about the
        # AmbiguousParameterError this prevents.
        assert "CAST(:lo AS bigint)" in rail._CENSUS_SQL
        assert "CAST(:hi AS bigint)" in rail._CENSUS_SQL

    def test_the_population_and_band_fragments_are_still_single_sourced(self):
        # The walk changed the BOUND, never the predicate. If these drift, the
        # census stops measuring the population the repair acts on.
        assert POPULATION_HAVING_SQL.strip() in rail._CENSUS_SQL
        assert RETENTION_BAND_SQL.strip() in rail._CENSUS_SQL

    def test_the_chunk_bound_was_lowered_not_raised(self):
        # #3195's own instruction: a bound raised until the query fits is not a
        # bound, and this population only grows.
        assert rail._CENSUS_TIMEOUT_MS < 22_000
        assert rail._CENSUS_MIN_CHUNK_IDS < rail._CENSUS_CHUNK_IDS

    def test_the_wall_budget_leaves_room_to_bank_what_it_measured(self):
        # A walk that spends its whole HTTP budget reading and dies before it
        # writes has done the work twice and kept neither half.
        assert rail._CENSUS_WALL_BUDGET_S < rail._MAX_SECONDS


# =============================================================================
# THE CATCHING TEST
# =============================================================================


class TestACensusThatCouldNotFinishNowFinishes:
    """The control. Against the pre-#3195 census every one of these is
    ``measured: false`` — one unbounded query, one statement timeout, no number.
    """

    @pytest.mark.asyncio
    async def test_a_width_the_database_cannot_serve_is_narrowed_through(
        self, store
    ):
        session = _CensusSession(servable_width=200_000)

        result = await rail.census(session)

        assert result["measured"] is True, (
            "the walk must narrow through a width the database refuses. "
            f"reason={result.get('reason')}"
        )
        assert session.unbounded_calls == 0, (
            "a population query with no range bound IS the #3195 defect"
        )
        assert result["walk"]["complete"] is True
        assert _cells_from(result["breakdown"]) == _expected_cells()

    @pytest.mark.asyncio
    async def test_it_really_did_narrow(self, store):
        session = _CensusSession(servable_width=200_000)

        await rail.census(session)

        widths = [hi - lo for lo, hi in session.served]
        assert widths, "nothing was served"
        assert max(widths) <= 200_000
        assert min(hi - lo for lo, hi in session.ranges) < rail._CENSUS_CHUNK_IDS, (
            "the walk must have tried a narrower width than it started at"
        )

    @pytest.mark.asyncio
    async def test_the_served_ranges_partition_the_id_space_exactly(self, store):
        """No gap and no overlap — the reason the chunk totals can be summed.

        This is the property a ``?sport=`` shard could not have: the totals are
        a partition of the population by construction, not by an operator adding
        up four responses and hoping the shards were exhaustive.
        """
        session = _CensusSession(servable_width=200_000)

        await rail.census(session)

        covered = sorted(session.served)
        assert covered[0][0] == 0
        assert covered[-1][1] == _MAX_MARKET_ID
        for (_lo_a, hi_a), (lo_b, _hi_b) in zip(covered, covered[1:]):
            assert hi_a == lo_b, f"gap or overlap between {hi_a} and {lo_b}"


# =============================================================================
# Chunking must not change the answer
# =============================================================================


class TestTheChunkedTotalsAreThePopulation:
    @pytest.mark.asyncio
    async def test_many_chunks_and_one_chunk_agree(self, store, monkeypatch):
        many = _CensusSession()
        result_many = await rail.census(many)

        monkeypatch.setattr(rail, "_CENSUS_CHUNK_IDS", _MAX_MARKET_ID * 10)
        one = _CensusSession()
        result_one = await rail.census(one)

        assert len(many.served) > 1, "this arm needs more than one chunk to mean anything"
        assert len(one.served) == 1
        assert _cells_from(result_many["breakdown"]) == _cells_from(
            result_one["breakdown"]
        )
        assert result_many["totals"] == result_one["totals"]

    @pytest.mark.asyncio
    async def test_a_market_on_a_chunk_boundary_is_counted_once(self, store):
        """The half-open range is what makes this true — ``lo <`` and ``<= hi``.

        The fixture puts markets at 399,999 / 400,000 / 400,001 for exactly this:
        an inclusive-both-ends range would double-count the boundary market, and
        a market counted twice is a drain that can never measure zero.
        """
        session = _CensusSession()

        result = await rail.census(session)

        assert result["totals"]["markets"] == len(_POPULATION)
        assert result["totals"]["outcomes"] == sum(p[4] for p in _POPULATION)

    @pytest.mark.asyncio
    async def test_the_kalshi_split_survives_the_walk(self, store):
        result = await rail.census(_CensusSession())

        kalshi = result["kalshi"]
        assert kalshi["markets"] == sum(1 for p in _POPULATION if p[1] == "kalshi")
        # reachable + at_risk + future_date, never provably_purged (ruling 054:
        # the excluded number is PUBLISHED, not folded into the denominator).
        assert kalshi["repairable_bands"] == 7  # 4 reachable + 2 at_risk + 1 future
        assert kalshi["declared_exclusion_provably_purged"] == 1
        assert kalshi["at_risk_before_the_cliff"] == 2


# =============================================================================
# The walk resumes, and only from where it actually stopped
# =============================================================================


def _budgeted(monkeypatch, *, step: float, budget: float):
    clock = _Clock(step=step)
    monkeypatch.setattr(rail, "time", clock)
    monkeypatch.setattr(rail, "_CENSUS_WALL_BUDGET_S", budget)
    return clock


class TestTheWalkResumes:
    @pytest.mark.asyncio
    async def test_a_budget_stop_is_partial_and_never_a_total(
        self, store, monkeypatch
    ):
        clock = _budgeted(monkeypatch, step=0.6, budget=1.0)
        session = _CensusSession(clock=clock)

        result = await rail.census(session)

        assert result["measured"] is False, "an unfinished walk has no total"
        assert "totals" not in result, (
            "a partial named as a total is the fabricated number this rail exists "
            "to refuse"
        )
        assert result["partial"]["totals"]["markets"] > 0
        assert result["walk"]["complete"] is False
        assert result["walk"]["next_after_id"] == 2 * rail._CENSUS_CHUNK_IDS
        assert "resume_with" in result["walk"]

    @pytest.mark.asyncio
    async def test_the_resumed_walk_totals_the_whole_population(
        self, store, monkeypatch
    ):
        clock = _budgeted(monkeypatch, step=0.6, budget=1.0)
        first = await rail.census(_CensusSession(clock=clock))
        cursor = first["walk"]["next_after_id"]

        monkeypatch.setattr(rail, "_CENSUS_WALL_BUDGET_S", 1000.0)
        second = await rail.census(_CensusSession(clock=_Clock()), after_id=cursor)

        assert second["measured"] is True
        assert second["walk"]["complete"] is True
        assert second["walk"]["calls"] == 2
        assert _cells_from(second["breakdown"]) == _expected_cells(), (
            "the resumed call must return the WHOLE population, not its own half — "
            "a total the operator has to assemble from four responses is not a "
            "completion test"
        )

    @pytest.mark.asyncio
    async def test_a_cursor_that_is_not_the_banked_one_is_refused(
        self, store, monkeypatch
    ):
        clock = _budgeted(monkeypatch, step=0.6, budget=1.0)
        first = await rail.census(_CensusSession(clock=clock))
        cursor = first["walk"]["next_after_id"]

        session = _CensusSession()
        result = await rail.census(session, after_id=cursor + 1)

        assert result["measured"] is False
        assert result["reason"] == rail.REASON_CENSUS_CURSOR_MOVED
        assert result["banked_next_after_id"] == cursor
        assert session.ranges == [], "a refused resume must read nothing"

    @pytest.mark.asyncio
    async def test_resuming_a_finished_walk_is_refused_and_hands_back_its_totals(
        self, store
    ):
        done = await rail.census(_CensusSession())
        assert done["walk"]["complete"] is True

        result = await rail.census(_CensusSession(), after_id=12345)

        assert result["reason"] == rail.REASON_CENSUS_ALREADY_COMPLETE
        assert result["banked_walk"]["complete"] is True

    @pytest.mark.asyncio
    async def test_omitting_the_cursor_starts_fresh_and_does_not_double_count(
        self, store, monkeypatch
    ):
        clock = _budgeted(monkeypatch, step=0.6, budget=1.0)
        await rail.census(_CensusSession(clock=clock))

        monkeypatch.setattr(rail, "_CENSUS_WALL_BUDGET_S", 1000.0)
        fresh = await rail.census(_CensusSession(clock=_Clock()))

        assert fresh["walk"]["calls"] == 1
        assert _cells_from(fresh["breakdown"]) == _expected_cells(), (
            "a fresh walk must not inherit the abandoned walk's counts"
        )

    @pytest.mark.asyncio
    async def test_a_resume_against_an_unreadable_record_is_refused_not_restarted(
        self, store
    ):
        # gotcha #53: a read that fails is not "nothing was banked". Silently
        # restarting would fold a second copy of the low id range into a walk
        # the operator believes is a resume.
        store.unreadable[rail.CENSUS_IDENTITY] = "error"

        result = await rail.census(_CensusSession(), after_id=400_000)

        assert result["measured"] is False
        assert result["reason"] == rail.REASON_CENSUS_CURSOR_MOVED


# =============================================================================
# A failure is still NOT RUN, never a zero
# =============================================================================


class TestAFailureIsNeverAZero:
    @pytest.mark.asyncio
    async def test_a_chunk_that_dies_at_the_floor_reports_not_run(self, store):
        session = _CensusSession(die_always=True)

        result = await rail.census(session)

        assert result["measured"] is False
        assert "totals" not in result
        assert "NOT RUN, not zero" in result["note"]
        assert result["failed_range"]["after_market_id"] == 0

    @pytest.mark.asyncio
    async def test_it_narrows_to_the_floor_before_giving_up(self, store):
        session = _CensusSession(die_always=True)

        await rail.census(session)

        widths = sorted({hi - lo for lo, hi in session.ranges})
        assert widths[0] == rail._CENSUS_MIN_CHUNK_IDS, (
            "the walk must reach the floor width before it reports a failure — "
            "giving up at the first timeout is the old behaviour with extra steps"
        )
        assert session.rollbacks == len(session.ranges), (
            "every dead chunk must roll back: SET LOCAL does not survive it, and "
            "the next chunk re-issues its own bound"
        )

    @pytest.mark.asyncio
    async def test_a_partial_walk_that_then_dies_publishes_only_a_partial(
        self, store
    ):
        # Serves the first chunk, then nothing: the fixture's low ids are real
        # measurements, and they are returned — under `partial`, beside the id
        # range they cover, and never as the census.
        class _DiesAfterOne(_CensusSession):
            async def execute(self, stmt, params=None):
                if params and "lo" in params and self.served:
                    self.die_always = True
                return await super().execute(stmt, params)

        session = _DiesAfterOne()
        result = await rail.census(session)

        assert result["measured"] is False
        assert result["partial"]["totals"]["markets"] > 0
        assert result["walk"]["measured_id_range"]["to_market_id"] < _MAX_MARKET_ID
        assert "totals" not in result

    @pytest.mark.asyncio
    async def test_an_unreadable_upper_bound_is_not_an_empty_table(self, store):
        class _NoMax(_CensusSession):
            async def execute(self, stmt, params=None):
                if "MAX(market_id)" in str(stmt):
                    raise _StatementTimeout()
                return await super().execute(stmt, params)

        result = await rail.census(_NoMax())

        assert result["measured"] is False
        assert "NOT RUN, not zero" in result["note"]


# =============================================================================
# It terminates, and it says what it cannot claim
# =============================================================================


class TestTheWalkTerminates:
    @pytest.mark.asyncio
    async def test_a_healthy_walk_takes_exactly_the_chunks_the_id_space_needs(
        self, store
    ):
        session = _CensusSession()

        result = await rail.census(session)

        expected = math.ceil(_MAX_MARKET_ID / rail._CENSUS_CHUNK_IDS)
        assert len(session.served) == expected
        assert result["walk"]["chunks_measured"] == expected

    @pytest.mark.asyncio
    async def test_an_empty_table_completes_without_reading_a_chunk(self, store):
        session = _CensusSession(population=[], max_market_id=0)

        result = await rail.census(session)

        assert result["measured"] is True
        assert result["walk"]["complete"] is True
        assert result["totals"] == {"markets": 0, "outcomes": 0}
        assert session.served == []

    @pytest.mark.asyncio
    async def test_the_response_states_what_a_multi_call_walk_cannot_claim(
        self, store
    ):
        # Ruling 095: a census of a moving population fails INVISIBLY. The walk
        # spans an interval and says so, in the response, beside the number.
        result = await rail.census(_CensusSession())

        limits = result["walk"]["limits"]
        assert "this_is_a_walk_not_an_instant" in limits
        assert "what_the_interval_can_miss" in limits
        assert "the_completion_test" in limits


class TestTheCheckpointIsReadableByTheProductionDecoder:
    """CERT-1903's named repair, and its named test.

    THE DEFECT: ``_save_census`` banked each partial checkpoint with the ENVELOPE
    flag ``complete=False``, reading it as "the walk is not finished". But that
    flag means "the artifact is intact" — ``decode_envelope`` classifies
    ``complete=False`` as ``malformed / IncompleteArtifact`` and refuses to
    return it, which is correct: the flag exists to reject a torn write. So every
    checkpoint was unreadable, the next ``?after_id=`` call got
    ``CENSUS_CURSOR_MOVED``, and the multi-call walk — the entire point of the
    change — could never resume. Two different completions, conflated.

    The shape the BLOCK asked for: first call persists, the REAL decoder reads,
    second call completes.
    """

    @pytest.mark.asyncio
    async def test_first_call_persists_real_decoder_reads_second_call_completes(
        self, store, monkeypatch
    ):
        clock = _budgeted(monkeypatch, step=0.6, budget=1.0)
        first = await rail.census(_CensusSession(clock=clock))
        assert first["walk"]["complete"] is False, "this arm needs a PARTIAL walk"
        assert first["walk"]["progress_banked"] is True

        # The production reader, not a fake's opinion of it.
        banked, reason = await rail._load_census()

        assert banked is not None, (
            f"the checkpoint must survive the production decoder — got {reason}. "
            "A partial walk still writes a WHOLE artifact."
        )
        assert banked["complete"] is False, (
            "and the WALK's completion still lives in the payload, where a "
            "reader can act on it"
        )

        monkeypatch.setattr(rail, "_CENSUS_WALL_BUDGET_S", 1000.0)
        second = await rail.census(
            _CensusSession(clock=_Clock()), after_id=first["walk"]["next_after_id"]
        )

        assert second["measured"] is True, second.get("detail") or second.get("reason")
        assert second["walk"]["complete"] is True
        assert _cells_from(second["breakdown"]) == _expected_cells()

    @pytest.mark.asyncio
    async def test_the_envelope_flag_is_intactness_not_walk_completion(self, store):
        """Stated directly, so a future edit cannot re-conflate them quietly."""
        clock = _Clock()
        await rail.census(_CensusSession(clock=clock))
        complete_walk = store.rows[rail.CENSUS_IDENTITY]

        assert complete_walk["complete"] is True
        assert complete_walk["payload"]["complete"] is True

    @pytest.mark.asyncio
    async def test_a_partial_checkpoint_is_stored_intact(self, store, monkeypatch):
        clock = _budgeted(monkeypatch, step=0.6, budget=1.0)
        await rail.census(_CensusSession(clock=clock))
        partial = store.rows[rail.CENSUS_IDENTITY]

        assert partial["complete"] is True, (
            "the ARTIFACT is whole even when the walk is halfway — this is the "
            "flag decode_envelope refuses on"
        )
        assert partial["payload"]["complete"] is False, "the WALK is not"

    @pytest.mark.asyncio
    async def test_a_torn_checkpoint_is_still_refused(self, store, monkeypatch):
        """The repair must not buy resumability by disarming the real check.

        `complete=True` is now unconditional, so the guard that has to still bite
        is the checksum: a payload that does not match its own address is a torn
        write and must not be resumed from.
        """
        clock = _budgeted(monkeypatch, step=0.6, budget=1.0)
        first = await rail.census(_CensusSession(clock=clock))
        assert first["walk"]["complete"] is False, "this arm needs a PARTIAL walk"
        store.rows[rail.CENSUS_IDENTITY]["payload"]["next_after_id"] = 999_999

        banked, reason = await rail._load_census()

        assert banked is None, "a payload that does not match its checksum is torn"
        assert "malformed" in reason

        resumed = await rail.census(
            _CensusSession(), after_id=first["walk"]["next_after_id"]
        )
        assert resumed["reason"] == rail.REASON_CENSUS_CURSOR_MOVED


class TestProgressIsBanked:
    @pytest.mark.asyncio
    async def test_a_completed_walk_banks_its_totals(self, store):
        result = await rail.census(_CensusSession())

        assert result["walk"]["progress_banked"] is True
        banked = store.rows[rail.CENSUS_IDENTITY]["payload"]
        assert banked["complete"] is True
        assert _cells_from(banked["breakdown"]) == _expected_cells()

    @pytest.mark.asyncio
    async def test_a_bank_that_answers_without_persisting_is_reported(self, store):
        # The sentinel-evidence lesson: a swallowed write failure lets a run
        # record progress that no longer exists, and the operator finds out when
        # their resume is refused for a cursor the rail has forgotten.
        store.no_op.add(rail.CENSUS_IDENTITY)

        result = await rail.census(_CensusSession())

        assert result["walk"]["progress_banked"] is True or result["walk"][
            "progress_bank_note"
        ] != "ok"
        assert rail.CENSUS_IDENTITY not in store.rows

    @pytest.mark.asyncio
    async def test_a_rejected_bank_is_named_in_the_response(self, store):
        store.forced_status[rail.CENSUS_IDENTITY] = "invalidated"

        result = await rail.census(_CensusSession())

        assert result["walk"]["progress_banked"] is False
        assert "invalidated" in result["walk"]["progress_bank_note"]
