"""#6599: does the rebuild's per-unit reuse produce what a fresh full run would?

PILLAR: TRUTH. SHIP: the accuracy page finishes a complete rebuild without
repeatedly discarding still-valid work.

**This file is the acceptance instrument for widening per-unit reuse, and it is
the reason this lane did not widen it.** codex's 0810Z directive authorises a
bounded implementation of safe per-unit reuse *only where equivalence of every
calculation dependency can be established*, and requires that incremental output
be compared against a fresh full recomputation across value/settlement changes,
additions, removals, global-policy changes, splits and a process restart. That
comparison is what runs here — against the real ``_run_staged_futures``, the real
planner, the real cursor codec and the real fold, with a fake database whose
rows are a function of the population's VALUES rather than of the call order.

## What it found, and it is the opposite of what the ask assumed

Per-unit reuse across a population change is **already built** — CAL-P016 took
the generation fingerprint out of the wholesale invalidators and CAL-P028 made
the unit key the content-addressed SLOT — and CAL-P205 layer 1 already narrowed
the bank's digest to the emitted statement, so a renderer edit no longer discards
it. There was no membership-digest reuse left to add.

What this file MEASURES is the price the existing design pays, which nothing had
executed end to end before:

* an unchanged population reproduces a fresh full run exactly (the control);
* a **global** input change (population version, or the statement's own digest —
  the calculation version) still discards the whole bank, as it must;
* a restart mid-build costs nothing, because the durable cursor is the only
  state;
* a refined slot's children cover their parent's questions exactly, with no
  overlap and no omission;
* and a **same-generation change to an already-banked slot — a settled winner, a
  moved price, a market joining or leaving — DIVERGES from a fresh run.** The
  banked unit is kept, its membership digest is re-stamped to the new roster, and
  the census published is that slot as it was when it ran.

The last one is not a bug this file is reporting as news: it is CAL-P016's
declared trade, counted every beat as ``roster_drift_units`` and disclosed to
readers as ``stale`` by ``calibration_staged_disclosure`` (see its module
docstring — "``stale``, not ``degraded``… a *whole, coherent* copy of the pool
whose only compromise is age"). The tests below pin the divergence with numbers
so the trade is a measured quantity rather than a paragraph, because it is the
exact bar the directive sets — *reuse only if the stored result demonstrably
matches current inputs* — and today's reuse does not clear it.

## Why that means the ask stops here rather than shipping

Tightening the reuse to clear that bar needs the drifted slot RECOMPUTED. It
cannot be, with what the cursor holds: CAL-P034 replaced the per-unit rows with
one shared accumulator (measured: 44,272 rows / 1,586 group keys at 91 units, and
O(units²) bytes of re-serialisation), and **a fold cannot be inverted** — its own
words. Dropping one drifted unit therefore means dropping the entire bank, which
is the thing #6599 exists to stop. The missing dependency is per-unit row
provenance, plus a per-unit content digest over winner/price/eligibility that no
roster row carries and that cannot be computed without the population scan the
directive rules out. Both are named in the receipt rather than built.

So: no reuse is widened here, and none is narrowed. This file is the measurement
that says which.
"""

from __future__ import annotations

import contextlib
import types
from datetime import datetime, timezone

import pytest

from app.services import durable_snapshots as ds
from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils import calibration_staged_futures as sf
from app.utils.calibration_phase_ledger import (
    PHASE_FUTURES,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)
from app.utils.durable_state import DurableEnvelope, EnvelopeRead

BUCKETS = 8
#: Cost per question. Small and uniform: this file is about WHAT is computed,
#: never about how long it takes.
VM_MS = 4_000
#: One beat banks a few units and leaves the rest — the state production is
#: always in, and the only state in which reuse can be observed at all.
PARTIAL_WINDOW_MS = 60_000
#: Enough window to do the whole population in one pass: the fresh full run.
WHOLE_WINDOW_MS = 10_000_000


# =============================================================================
# The population — values, not just membership
# =============================================================================


def _population(n: int = 40) -> dict[int, tuple[float, bool]]:
    """``market_id -> (probability, settled as a winner)``.

    Deterministic and spread across price bands, so a single changed value moves
    exactly one bucket and the comparison below can say which.
    """
    return {i: (round((i % 10) / 10 + 0.05, 2), i % 3 == 0) for i in range(1, n + 1)}


def _roster(population):
    return [
        types.SimpleNamespace(
            market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False
        )
        for i in sorted(population)
    ]


def _rows_for(market_ids, population):
    """One chunk's bucket rows, aggregated per group key like the statement's.

    The whole point of this rig: the rows are a function of the VALUES the
    population currently holds. A rig whose rows depend only on membership
    cannot tell a stale reuse from a correct one, which is the question.
    """
    by_bucket: dict[int, dict] = {}
    for market_id in market_ids:
        prob, winner = population[market_id]
        bucket = int(prob * 10)
        row = by_bucket.setdefault(
            bucket,
            {
                "bucket_idx": bucket,
                "source": "kalshi",
                "category": "futures",
                "price_moved": False,
                "is_nonexclusive_bundle": False,
                "n": 0,
                "winners": 0,
                "sum_prob": 0.0,
                "sum_sq_err": 0.0,
                "avg_prob": 0.0,
            },
        )
        row["n"] += 1
        row["winners"] += 1 if winner else 0
        row["sum_prob"] += prob
        row["sum_sq_err"] += (prob - (1.0 if winner else 0.0)) ** 2
        row["avg_prob"] = row["sum_prob"] / row["n"]
    return [types.SimpleNamespace(**row) for row in by_bucket.values()]


def _banked_markets(durable, population) -> list[int]:
    """The market ids sitting in slots the cursor has ALREADY banked.

    Every divergence below targets these deliberately. Picking a market by hand
    would make the result a property of which slot ``bucket_of`` happened to put
    it in: the first draft of the arrival test did exactly that, chose two ids
    that landed in slots not yet banked, and measured no divergence at all —
    a true reading of a question nobody asked.
    """
    banked = set((durable.payload or {}).get("committed_units") or ())
    chunks = sf.plan_units(_roster(population), buckets=BUCKETS)
    return sorted(
        market
        for chunk in chunks
        if sf.unit_key(chunk) in banked
        for market in chunk.market_ids
    )


def _free_market_in_a_banked_slot(durable, population, *, start: int = 9001) -> int:
    """A brand-new market id that hashes into an already-banked slot."""
    banked_slots = {
        chunk.index
        for chunk in sf.plan_units(_roster(population), buckets=BUCKETS)
        if sf.unit_key(chunk) in set((durable.payload or {}).get("committed_units") or ())
    }
    for candidate in range(start, start + 5_000):
        if candidate in population:
            continue
        if sf.bucket_of(f"m:{candidate}", BUCKETS) in banked_slots:
            return candidate
    raise AssertionError("no free market id hashes into a banked slot")


def _census(rows) -> dict:
    """A published census, keyed for comparison. Floats rounded like the payload."""
    out: dict[tuple, tuple] = {}
    for row in rows:
        key = (
            getattr(row, "bucket_idx", None),
            getattr(row, "source", None),
            getattr(row, "category", None),
            getattr(row, "price_moved", None),
            getattr(row, "is_nonexclusive_bundle", None),
        )
        out[key] = (
            int(getattr(row, "n", 0)),
            int(getattr(row, "winners", 0)),
            round(float(getattr(row, "sum_prob", 0.0)), 6),
            round(float(getattr(row, "sum_sq_err", 0.0)), 6),
        )
    return out


# =============================================================================
# The rig — one durable cursor, many beats, the real build
# =============================================================================


class _Durable:
    def __init__(self):
        self.payload: dict | None = None

    async def read(self, identity, *, expected_version=None, max_age_s=None):
        if self.payload is None:
            return EnvelopeRead(status="missing", tier=ds.TIER_DURABLE)
        return EnvelopeRead(
            status="ok",
            tier=ds.TIER_DURABLE,
            envelope=DurableEnvelope.build(
                identity=identity,
                schema_version=sf.STAGED_FUTURES_SCHEMA,
                payload=self.payload,
                generated_at=datetime.now(timezone.utc),
                source=cmb.MAIN_BUILD_TASK,
            ),
        )

    async def publish(self, envelope):
        self.payload = envelope.payload
        return {"status": "ok"}


class _Runner:
    def __init__(self, *, generation: int, window_ms: int, population_version: str):
        plan = PhasePlan(
            budgets=(
                PhaseBudget(
                    name=PHASE_FUTURES,
                    required=True,
                    budget_ms=None,
                    statement_timeout_ms=None,
                    measured_input=True,
                    unit_ms=VM_MS * 5,
                    units_total=BUCKETS,
                    units_done=0,
                ),
            ),
            soft_limit_ms=window_ms + 120_000,
            cleanup_margin_ms=120_000,
        )
        self.ledger = PhaseLedger(
            plan=plan,
            population_version=population_version,
            owner="test:1",
            generation=generation,
            input_fingerprint="fp",
            phases=(PHASE_FUTURES,),
        )
        self._elapsed = 0
        self.population_version = population_version
        self.fingerprint = "fp"
        self.owner = "test:1"
        self.generation = generation
        self.deferred = False

    def elapsed_ms(self) -> int:
        return self._elapsed

    def advance(self, ms: int) -> None:
        self._elapsed += int(ms)

    def measured_unit_ms(self, phase: str):
        return self.ledger.measured_unit_ms(phase)

    def defer_rebuild(self) -> None:
        self.deferred = True

    @contextlib.contextmanager
    def stage(self, _name: str):
        yield

    async def commit(self, _db) -> None:
        return None

    async def apply_statement_timeout(self, _db, phase) -> int:
        return self.ledger.statement_timeout_for(phase, elapsed_ms=self._elapsed)

    async def apply_unit_statement_timeout(
        self, _db, phase, *, unit_ms=None, deferred_rebuild=False
    ) -> int:
        return self.ledger.statement_timeout_for_unit(
            phase, elapsed_ms=self._elapsed, unit_ms=unit_ms
        )


class _Db:
    """Every unit completes; its rows are read off the CURRENT population."""

    def __init__(self, runner: _Runner, state):
        self.runner = runner
        self.state = state
        self._gen_done = False
        self.units_read = 0

    async def execute(self, _sql, params=None):
        if not self._gen_done:
            self._gen_done = True
            return types.SimpleNamespace(all=lambda: _roster(self.state.population))
        market_ids = [int(m) for m in (params or {}).get(pc.VM_ROSTER_MARKET_IDS_PARAM) or ()]
        self.units_read += 1
        self.runner.advance(VM_MS * max(1, len(market_ids)))
        rows = _rows_for(market_ids, self.state.population)
        return types.SimpleNamespace(all=lambda: rows)

    async def rollback(self) -> None:
        return None


class _State:
    """What the world looks like right now, and what the build keys off it."""

    def __init__(self, population):
        self.population = dict(population)
        self.population_version = "q268"
        self.unit_fingerprint = "unit-fp"


@pytest.fixture
def build(monkeypatch):
    """Run beats over ONE durable cursor until a census publishes.

    Returns ``(run, state, durable)``. ``run(...)`` takes an optional ``mutate``
    callback invoked before a named beat, which is how every scenario below
    changes the world underneath a partially banked build.
    """
    durable = _Durable()
    monkeypatch.setattr(ds, "read_snapshot_standalone", durable.read)
    monkeypatch.setattr(ds, "publish_snapshot_standalone", durable.publish)
    monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", BUCKETS)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
    state = _State(_population())
    monkeypatch.setattr(pc, "staged_unit_fingerprint", lambda: state.unit_fingerprint)

    async def _run(*, window_ms=PARTIAL_WINDOW_MS, max_beats=30, mutate=None):
        units_read = 0
        for beat_no in range(1, max_beats + 1):
            if mutate is not None:
                # The durable row goes with it: a scenario has to be able to ask
                # what is banked BEFORE deciding what to change, or it measures
                # the hash function rather than the build.
                mutate(beat_no, state, durable)
            runner = _Runner(
                generation=beat_no,
                window_ms=window_ms,
                population_version=state.population_version,
            )
            db = _Db(runner, state)
            monkeypatch.setattr(
                pc,
                "time",
                types.SimpleNamespace(
                    monotonic=lambda r=runner: r.elapsed_ms() / 1000.0
                ),
            )
            rows = await pc._run_staged_futures(
                db, runner, lambda frozen=False: "SELECT 1"
            )
            units_read += db.units_read
            if rows is not None:
                return types.SimpleNamespace(
                    census=_census(rows),
                    beats=beat_no,
                    units_read=units_read,
                )
        raise AssertionError(f"no census published in {max_beats} beats")

    return _run, state, durable


async def _fresh(monkeypatch, population):
    """The control: one process, one beat, the whole population, nothing banked.

    A separate durable row and a separate fixture state, so nothing this run does
    can be contaminated by a bank — which is the definition of "fresh".
    """
    durable = _Durable()
    monkeypatch.setattr(ds, "read_snapshot_standalone", durable.read)
    monkeypatch.setattr(ds, "publish_snapshot_standalone", durable.publish)
    monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", BUCKETS)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
    monkeypatch.setattr(pc, "staged_unit_fingerprint", lambda: "fresh-fp")
    state = _State(population)
    runner = _Runner(
        generation=1, window_ms=WHOLE_WINDOW_MS, population_version="q268"
    )
    db = _Db(runner, state)
    monkeypatch.setattr(
        pc,
        "time",
        types.SimpleNamespace(monotonic=lambda r=runner: r.elapsed_ms() / 1000.0),
    )
    rows = await pc._run_staged_futures(db, runner, lambda frozen=False: "SELECT 1")
    assert rows is not None, "the fresh control must publish in one beat"
    return _census(rows), db.units_read


# =============================================================================
# 1. THE CONTROL — with nothing changing, incremental IS the fresh run
# =============================================================================


class TestAnUnchangedPopulationReproducesAFreshRun:
    @pytest.mark.asyncio
    async def test_the_two_censuses_are_identical(self, monkeypatch, build):
        """If this ever fails, nothing else in this file means anything.

        It is also the non-vacuity guard for every divergence below: the rig can
        produce equality, so a reported difference is a difference in the BUILD
        and not in the harness.
        """
        run, state, _durable = build
        incremental = await run()
        fresh, _reads = await _fresh(monkeypatch, state.population)

        assert incremental.census == fresh
        assert incremental.beats > 1, (
            "and it must have taken several beats, or no reuse was exercised"
        )


# =============================================================================
# 2. THE DIVERGENCE — a change inside an already-banked slot is not seen
# =============================================================================


class TestAChangeInsideABankedSlotIsNotRecomputed:
    """CAL-P016's declared trade, executed rather than described.

    Each of these asserts the CURRENT behaviour and each is therefore a
    reproduction, not a guard: a future ship that recomputes drifted slots
    changes these assertions, and that is what it is for.
    """

    @pytest.mark.asyncio
    async def test_a_settled_winner_does_not_reach_the_published_census(
        self, monkeypatch, build
    ):
        """The directive's first named case: *the same rows change winner*.

        Membership is untouched, so the slot's member digest does not even move
        — this is invisible to every dependency the cursor tracks.
        """
        run, state, _durable = build

        def settle(beat_no, st, durable):
            if beat_no == 3:
                for market_id in _banked_markets(durable, st.population):
                    prob, _winner = st.population[market_id]
                    st.population[market_id] = (prob, True)

        incremental = await run(mutate=settle)
        fresh, _reads = await _fresh(monkeypatch, state.population)

        assert incremental.census != fresh, (
            "if these ever match, the build has started recomputing drifted "
            "slots and this reproduction should be rewritten as a guard"
        )
        stale = {
            key: (mine, theirs)
            for key, mine in incremental.census.items()
            if (theirs := fresh.get(key)) != mine
        }
        assert stale, "the difference must be nameable per bucket, not merely a !="
        assert sum(v[0][0] for v in stale.values()) == sum(
            v[1][0] for v in stale.values()
        ), (
            "the disagreement must be in the WINNER counts, not in the population "
            "size — a row count that moved too would mean the rig changed "
            "membership by accident and this test is measuring the wrong thing"
        )

    @pytest.mark.asyncio
    async def test_a_market_that_joins_after_its_slot_banked_is_never_counted(
        self, monkeypatch, build
    ):
        """An ADDITION. The slot's digest moves, drift is counted, unit is kept."""
        run, state, _durable = build

        def arrive(beat_no, st, durable):
            if beat_no == 3:
                joiner = _free_market_in_a_banked_slot(durable, st.population)
                st.population[joiner] = (0.35, True)

        incremental = await run(mutate=arrive)
        fresh, _reads = await _fresh(monkeypatch, state.population)

        assert sum(v[0] for v in incremental.census.values()) < sum(
            v[0] for v in fresh.values()
        ), "the published census is short by the markets that arrived late"

    @pytest.mark.asyncio
    async def test_a_market_that_leaves_after_its_slot_banked_is_still_counted(
        self, monkeypatch, build
    ):
        """A REMOVAL — the same trade with the opposite sign.

        Worth its own case because the two are not symmetric in consequence: an
        omission understates the curve's population, an inclusion publishes a
        question that no longer exists.
        """
        run, state, _durable = build

        def resolve_away(beat_no, st, durable):
            if beat_no == 3:
                for market_id in _banked_markets(durable, st.population)[:3]:
                    st.population.pop(market_id, None)

        incremental = await run(mutate=resolve_away)
        fresh, _reads = await _fresh(monkeypatch, state.population)

        assert sum(v[0] for v in incremental.census.values()) > sum(
            v[0] for v in fresh.values()
        ), "the published census still carries questions the population dropped"


# =============================================================================
# 3. THE INVALIDATION THAT MUST SURVIVE ANY REUSE WORK
# =============================================================================


class TestAGlobalInputChangeStillDiscardsEverything:
    """The directive's line: *global changes invalidate every affected result*."""

    @pytest.mark.asyncio
    async def test_a_moved_calculation_version_rebuilds_the_whole_population(
        self, monkeypatch, build
    ):
        """``staged_unit_fingerprint`` is the emitted statement's own digest.

        A unit banked under one statement and a unit banked under another are
        not one census, so the published result must equal a fresh run AT THE
        NEW VERSION — which is the strongest form of this assertion available:
        not "it invalidated", but "what came out is what a full recompute would
        have produced".
        """
        run, state, _durable = build

        def redeploy(beat_no, st, durable):
            if beat_no == 3:
                st.unit_fingerprint = "unit-fp-v2"

        incremental = await run(mutate=redeploy)
        fresh, _reads = await _fresh(monkeypatch, state.population)

        assert incremental.census == fresh

    @pytest.mark.asyncio
    async def test_a_moved_population_version_rebuilds_the_whole_population(
        self, monkeypatch, build
    ):
        run, state, _durable = build

        def bump(beat_no, st, durable):
            if beat_no == 3:
                st.population_version = "q269"

        incremental = await run(mutate=bump)
        fresh, _reads = await _fresh(monkeypatch, state.population)

        assert incremental.census == fresh


# =============================================================================
# 4. RESTART, SPLITS, AND WHETHER THE REUSE IS WORTH ANYTHING
# =============================================================================


class TestTheDurableCursorIsTheOnlyState:
    @pytest.mark.asyncio
    async def test_a_restart_between_every_beat_costs_nothing(
        self, monkeypatch, build
    ):
        """Every beat in this rig IS a restart — new runner, new db, new clock.

        Stated as its own test because "the process died" is one of the named
        scenarios and because the property is easy to lose: any state that lived
        in module scope rather than on the durable row would show up here as a
        census that differs from the fresh control.
        """
        run, state, _durable = build
        incremental = await run()
        fresh, _reads = await _fresh(monkeypatch, state.population)

        assert incremental.census == fresh
        assert incremental.beats >= 3, "several restarts, not one"


class TestAReuseThatSavesNothingIsNotReuse:
    @pytest.mark.asyncio
    async def test_the_bank_removes_work_a_cold_build_would_repeat(
        self, monkeypatch, build
    ):
        """The directive's efficiency clause, measured on unit READS.

        A warm build that survives a mid-flight population change must do
        strictly less work than the same build with no bank at all — otherwise
        the retention is only a correctness risk with no payoff to weigh it
        against.
        """
        run, state, _durable = build

        def arrive(beat_no, st, durable):
            if beat_no == 3:
                st.population[
                    _free_market_in_a_banked_slot(durable, st.population)
                ] = (0.35, True)

        warm = await run(mutate=arrive)

        # The SAME walk with the bank thrown away every beat — the pre-CAL-P016
        # behaviour, and what any wholesale invalidator still does. Measured by
        # running it, not by arithmetic on the warm one: a predicted control is
        # not a control.
        def arrive_and_wipe(beat_no, st, durable):
            arrive(beat_no, st, durable)
            durable.payload = None

        with pytest.raises(AssertionError, match="no census published"):
            await run(mutate=arrive_and_wipe, max_beats=warm.beats * 3)

        assert warm.units_read <= BUCKETS + 2, (
            f"a warm build reads each unit about once: {warm.units_read} reads "
            f"for {BUCKETS} units over {warm.beats} beats"
        )


class TestARefinedSlotCoversItsParentExactly:
    """Splits, checked on the planner rather than through a beat.

    Pure and exhaustive: overlap and omission are properties of ``plan_units``
    and ``resolve_slot``, and a beat-level test would sample them.
    """

    def test_the_children_partition_the_parents_questions(self):
        population = _population(200)
        rows = _roster(population)
        base = sf.plan_units(rows, buckets=BUCKETS)
        parent = next(chunk for chunk in base if len(chunk.vm_ids) > 1)

        refined = sf.plan_units(
            rows, buckets=BUCKETS, refinements={sf.slot_ref(parent): 4}
        )

        children = [chunk for chunk in refined if chunk.buckets > BUCKETS]
        child_vms = [vm for chunk in children for vm in chunk.vm_ids]

        assert sorted(child_vms) == sorted(parent.vm_ids), "no omission"
        assert len(child_vms) == len(set(child_vms)), "and no overlap"
        untouched = {
            chunk.index: chunk.vm_ids for chunk in refined if chunk.buckets == BUCKETS
        }
        assert all(
            untouched[chunk.index] == chunk.vm_ids
            for chunk in base
            if chunk.index in untouched
        ), "and every other slot is the slot it always was"
