"""CAL-P163 (#1978): a fence built from the survivors cannot see what it killed.

``statement_timeout_for_unit`` bounded a unit at ``unit_ms *
STAGED_UNIT_OVERRUN_FACTOR``, where ``unit_ms`` is the mean over units that
COMPLETED — and a unit only completes if it fit under the bound that same mean
produced. **The reference was therefore computed exclusively from the units
that survived it, and it ratchets one way:** cancel the expensive units, the
completed mean falls, the bound tightens, more expensive units cancel.

Measured on the producer's own ring, 2026-08-31. The ratchet closed at 06:37Z
and stayed closed for sixteen consecutive beats, every one of them identical::

    units_completed_this_beat  5      units_this_beat  7
    units_cancelled            2      terminal         cancelled
    outcome.published          false

Before it: 11-14 units per beat and ``complete`` terminals. The 22:29Z ledger
(``calibration:main:phase_ledger``, generation 1788214500243) names the
mechanism outright::

    staged:unit_ms_mean_completed        58,279 ms   <- the carried mean
    staged:unit_ms_worst                 76,208 ms   <- this beat's worst
    staged:unit_cancelled_after_ms      274,893 ms   <- 76,208 x 4 - 30,000
    staged:window_stop:units_cancelling       fired

and the units it killed are not pathological: ``staged:unit_ms_worst`` had
recorded COMPLETIONS at 175,574 / 179,665 / 250,681 / 308,586 ms on earlier
beats of the same population. The fence was cancelling at 275 s a population it
had already watched finish at 309 s.

**And it was not the phase budget.** That beat's ``futures`` phase held
1,188,617 ms of ``measured_elastic_cut`` and spent 878,583 — it stopped 310 s
short of its own budget and 501 s short of the window, and
``_unit_fits_in_window`` never fired. A budget you do not reach is not what is
capping you, which is why nothing in this file adjusts one.

The repair is a second reference: ``max(observed completions)`` over a rolling
window, scaled by ``BUDGET_SAFETY`` — the same ``max(observed) * 1.5`` rule
every phase budget in this module already uses — and the LOOSER of the two
bounds wins. A max needs less headroom than a mean does, which is why the two
carry different multipliers.

The loop tests drive the REAL ``_run_staged_futures`` against a real
``PhaseLedger`` and a database that cancels at whatever ``statement_timeout``
the loop actually armed, reusing the CAL-P081 harness's shape for the same
reason it was built: revert the fix and
``test_the_pinned_beat_banks_its_expensive_units`` goes red with exactly the
production shape — 5 banked, 2 cancelled.
"""

from __future__ import annotations

import contextlib
import types

import pytest

from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils import calibration_staged_futures as sf
from app.utils.calibration_phase_ledger import (
    BUDGET_SAFETY,
    HISTORY_WINDOW,
    PHASE_FUTURES,
    STAGED_UNIT_MAX_CANCELLATIONS,
    STAGED_UNIT_OVERRUN_FACTOR,
    UNIT_WORST_WINDOW,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
    merge_history,
)

# --- The 22:29:39Z beat, verbatim from the durable ledger --------------------
CARRIED_MEAN_MS = 58_279
BEAT_WORST_MS = 76_208
CANCELLED_AFTER_MS = 274_893
#: Worst COMPLETED units this population has actually produced, from
#: ``staged:unit_ms_worst`` on beats that published.
COMPLETED_WORST_RING = [
    175_574, 179_665, 250_681, 308_586, 146_637, 135_937, 126_015, 122_002,
]
#: A cost inside the band the pin created: above the 274,893 ms the real units
#: were cancelled at, and at or below a size this population has been MEASURED
#: to complete (308,586 ms). Not an invented number — the point of the band is
#: that the fence, not the unit, decided the outcome.
EXPENSIVE_UNIT_MS = 300_000
WINDOW_MS = 1_380_000

# The CAL-P081 specimen, which this change must not re-admit.
RUNAWAY_MS = 901_266


def _ledger(
    *,
    window_ms: int = WINDOW_MS,
    unit_ms: int | None,
    unit_ms_worst: int | None = None,
    units_done: int = 5,
) -> PhaseLedger:
    """A real ledger whose plan carries a measured mean and/or a measured max."""
    plan = PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=None,
                statement_timeout_ms=None,
                measured_input=True,
                unit_ms=unit_ms,
                unit_ms_worst=unit_ms_worst,
                units_total=128,
                units_done=units_done if unit_ms else 0,
            ),
        ),
        soft_limit_ms=window_ms + 120_000,
        cleanup_margin_ms=120_000,
    )
    return PhaseLedger(
        plan=plan,
        population_version="q268",
        owner="test:1",
        generation=1,
        input_fingerprint="fp",
        phases=(PHASE_FUTURES,),
    )


# =============================================================================
# 1. THE BOUND — the max is read, and it only ever loosens
# =============================================================================


class TestTheBound:
    def test_the_pinned_bound_is_reproduced_without_the_carried_max(self):
        """The pre-fix number, computed rather than quoted, so the guard is
        anchored to the mechanism and not to a constant someone typed."""
        led = _ledger(unit_ms=CARRIED_MEAN_MS, unit_ms_worst=None)
        bound = led.statement_timeout_for_unit(
            PHASE_FUTURES, elapsed_ms=300_000, unit_ms=BEAT_WORST_MS
        )
        # 76,208 * 4 - 30,000 = 274,832 — the ledger recorded 274,893.
        assert bound == pytest.approx(CANCELLED_AFTER_MS, abs=1_000)
        assert bound < EXPENSIVE_UNIT_MS, "pre-fix, the 300s unit cannot survive"

    def test_the_carried_max_widens_the_bound_past_what_the_pin_killed(self):
        led = _ledger(
            unit_ms=CARRIED_MEAN_MS, unit_ms_worst=max(COMPLETED_WORST_RING)
        )
        bound = led.statement_timeout_for_unit(
            PHASE_FUTURES, elapsed_ms=300_000, unit_ms=BEAT_WORST_MS
        )
        assert bound > CANCELLED_AFTER_MS
        assert bound >= EXPENSIVE_UNIT_MS

    def test_the_max_is_scaled_by_budget_safety_not_the_overrun_factor(self):
        """A max needs less headroom than a mean. Using 4.0 on a max would
        re-admit the CAL-P081 runaway, which is the whole thing being kept."""
        worst = max(COMPLETED_WORST_RING)
        led = _ledger(unit_ms=None, unit_ms_worst=worst, units_done=0)
        bound = led.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)
        assert bound <= worst * BUDGET_SAFETY
        assert bound < worst * STAGED_UNIT_OVERRUN_FACTOR

    @pytest.mark.parametrize("mean_ms", [10_000, 58_279, 200_000, 400_000])
    @pytest.mark.parametrize("worst_ms", [None, 1, 76_208, 308_586, 900_000])
    def test_the_new_bound_is_never_tighter_than_the_old_one(self, mean_ms, worst_ms):
        """Monotone in the safe direction, over a grid.

        The fence may only stop refusing units; it may never start refusing one
        it used to admit. Anything else is a second failure mode shipped to fix
        the first.
        """
        old = _ledger(unit_ms=mean_ms, unit_ms_worst=None).statement_timeout_for_unit(
            PHASE_FUTURES, elapsed_ms=200_000, unit_ms=mean_ms
        )
        new = _ledger(unit_ms=mean_ms, unit_ms_worst=worst_ms).statement_timeout_for_unit(
            PHASE_FUTURES, elapsed_ms=200_000, unit_ms=mean_ms
        )
        assert new >= old

    def test_with_neither_reference_measured_the_phase_bound_still_stands(self):
        """Ruling 075: the build is never bounded by a number it did not measure."""
        led = _ledger(unit_ms=None, unit_ms_worst=None, units_done=0)
        phase = led.statement_timeout_for(PHASE_FUTURES, elapsed_ms=200_000)
        assert led.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=200_000) == phase

    def test_the_unit_bound_can_never_exceed_the_phase_bound(self):
        """However large the carried max grows, a unit cannot outlive the beat."""
        led = _ledger(unit_ms=CARRIED_MEAN_MS, unit_ms_worst=10_000_000)
        for elapsed in (0, 400_000, 900_000, 1_300_000):
            phase = led.statement_timeout_for(PHASE_FUTURES, elapsed_ms=elapsed)
            unit = led.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=elapsed)
            assert unit <= phase

    def test_the_cal_p081_runaway_is_still_cancelled(self):
        """The guarantee this change is not allowed to trade away.

        Widening requires a COMPLETION at the wider size. To admit 901,266 ms
        the ring would need a completed unit of 600,844 ms, and this population
        has never produced one — its measured worst completion is 308,586.
        """
        led = _ledger(
            unit_ms=72_202, unit_ms_worst=max(COMPLETED_WORST_RING)
        )
        bound = led.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=437_000)
        assert bound < RUNAWAY_MS / 2


# =============================================================================
# 2. THE EVIDENCE — completed-only, and a memory long enough to hold the truth
# =============================================================================


class TestTheEvidence:
    def test_a_cancelled_stretch_never_raises_the_completed_max(self):
        """A cancellation is a lower bound on an unknown cost. Letting it set
        the max would make the fence widen on its own failures — the CAL-P081
        runaway re-admitted through the back door."""
        led = _ledger(unit_ms=None, unit_ms_worst=None, units_done=0)
        led.record_stage_outcome("read:futures_unit", 60_000, completed=True)
        led.record_stage_outcome("read:futures_unit", 900_000, completed=False)
        assert led.stage_completed_max_ms("read:futures_unit") == 60_000

    def test_a_beat_that_completed_nothing_reports_no_max_rather_than_zero(self):
        """Ruling 075, second clause. Zero is the one value that makes the
        fence maximally tight, so it may never stand in for 'unknown'."""
        led = _ledger(unit_ms=None, unit_ms_worst=None, units_done=0)
        led.record_stage_outcome("read:futures_unit", 900_000, completed=False)
        assert led.stage_completed_max_ms("read:futures_unit") is None

    def test_the_worst_ring_outlives_the_sixteen_beat_pin(self):
        """The reason UNIT_WORST_WINDOW is not HISTORY_WINDOW.

        The observed collapse ran sixteen beats. A ten-beat memory is INSIDE
        it: the healthy worst case is evicted, the ring refills entirely from
        the collapsed regime, and the fence confirms itself. This is the guard
        that fails if someone 'simplifies' the two windows into one.
        """
        collapsed = [76_208, 84_791, 146_637, 135_937, 111_773, 115_470, 118_107,
                     126_015, 122_002, 132_452, 127_410, 112_521, 116_142,
                     108_694, 124_267, 250_681]
        assert len(collapsed) == 16

        ring = {PHASE_FUTURES: [308_586]}
        short = dict(ring)
        for beat in collapsed:
            ring = merge_history(ring, {PHASE_FUTURES: beat}, window=UNIT_WORST_WINDOW)
            short = merge_history(short, {PHASE_FUTURES: beat}, window=HISTORY_WINDOW)

        assert 308_586 in ring[PHASE_FUTURES], "a day of beats remembers the truth"
        assert 308_586 not in short[PHASE_FUTURES], "ten beats does not — the pin wins"
        assert max(ring[PHASE_FUTURES]) > max(short[PHASE_FUTURES])

    def test_the_ring_still_ages_out(self):
        """A genuinely cheaper population reclaims the fence within a day —
        the memory is long, not permanent."""
        ring = {PHASE_FUTURES: [308_586]}
        for _ in range(UNIT_WORST_WINDOW):
            ring = merge_history(ring, {PHASE_FUTURES: 40_000}, window=UNIT_WORST_WINDOW)
        assert max(ring[PHASE_FUTURES]) == 40_000

    def test_default_window_is_unchanged_for_every_existing_caller(self):
        long_run = merge_history({}, {}, )
        assert long_run == {}
        ring = {}
        for i in range(HISTORY_WINDOW + 5):
            ring = merge_history(ring, {PHASE_FUTURES: i})
        assert len(ring[PHASE_FUTURES]) == HISTORY_WINDOW


# =============================================================================
# 3. THE ROUND TRIP — the ring reaches the next plan, and nothing erases it
# =============================================================================


def _durable(monkeypatch):
    """Fake the durable snapshot pair; return the dict the writes land in."""
    from app.services import durable_snapshots
    from app.utils.durable_state import DurableEnvelope, EnvelopeRead

    written: dict = {}

    async def fake_publish(envelope):
        written["payload"] = envelope.payload
        return {"status": "ok"}

    async def fake_read(identity, *, expected_version=None, max_age_s=None):
        if "payload" not in written:
            return EnvelopeRead(status="missing", tier="durable")
        return EnvelopeRead(
            status="ok",
            tier="durable",
            envelope=DurableEnvelope.build(
                identity=identity,
                schema_version=expected_version or "v1",
                payload=written["payload"],
                complete=True,
                source=cmb.MAIN_BUILD_TASK,
            ),
        )

    monkeypatch.setattr(durable_snapshots, "publish_snapshot_standalone", fake_publish)
    monkeypatch.setattr(durable_snapshots, "read_snapshot_standalone", fake_read)
    return written


def _save_runner(*, completed: list[int], cancelled: list[int], banked: int):
    runner = cmb.PhaseRunner(
        plan=_ledger(unit_ms=None, unit_ms_worst=None, units_done=0).plan,
        checkpoint=cmb.new_main_checkpoint(
            version="q268", fingerprint="fp", owner="test:1", generation=1
        ),
        checkpoint_action="fresh",
        owner="test:1",
        generation=1,
        fingerprint="fp",
        population_version="q268",
    )
    for ms in completed:
        runner.ledger.record_stage_outcome(cmb.STAGED_UNIT_STAGE, ms, completed=True)
    for ms in cancelled:
        runner.ledger.record_stage_outcome(cmb.STAGED_UNIT_STAGE, ms, completed=False)
    if banked:
        runner.ledger.record_stage("staged:units_banked", banked)
    return runner


class TestTheRoundTrip:
    async def test_the_worst_reaches_the_next_beats_plan(self, monkeypatch):
        """Without this the change is inert: the max is measured, dropped on
        the durable write, and the next beat plans exactly like this one."""
        _durable(monkeypatch)
        runner = _save_runner(completed=[50_000, 308_586], cancelled=[], banked=7)
        assert await cmb.save_phase_ledger(runner) == "ok"

        _h, _f, unit_costs = await cmb.load_phase_measurements()
        assert unit_costs[PHASE_FUTURES]["unit_ms_worst"] == 308_586

        plan = cmb.derive_plan({PHASE_FUTURES: [1000]}, unit_costs=unit_costs)
        assert plan.by_name(PHASE_FUTURES).unit_ms_worst == 308_586

    async def test_the_fold_takes_the_max_over_the_window_not_the_last_beat(
        self, monkeypatch
    ):
        """One collapsed beat must not pin the worst case low — that is the
        ratchet, one level down in the persistence layer."""
        written = _durable(monkeypatch)
        assert await cmb.save_phase_ledger(
            _save_runner(completed=[308_586], cancelled=[], banked=7)
        ) == "ok"
        assert await cmb.save_phase_ledger(
            _save_runner(completed=[41_000], cancelled=[900_000], banked=1)
        ) == "ok"

        assert written["payload"][cmb.UNIT_WORST_HISTORY_KEY] == {
            PHASE_FUTURES: [308_586, 41_000]
        }
        _h, _f, unit_costs = await cmb.load_phase_measurements()
        assert unit_costs[PHASE_FUTURES]["unit_ms_worst"] == 308_586

    async def test_a_beat_that_completed_nothing_erases_neither_ring_nor_level(
        self, monkeypatch
    ):
        """``payload`` is rebuilt from scratch each beat, so a barren beat used
        to write the row back with no ``unit_costs`` at all — silently erasing
        what earlier beats measured and sending the next plan to no-data.
        Refusing to INVENT a cost and refusing to KEEP one are different
        things, and only the first was ever intended.
        """
        written = _durable(monkeypatch)
        assert await cmb.save_phase_ledger(
            _save_runner(completed=[60_000, 250_681], cancelled=[], banked=9)
        ) == "ok"
        before = dict(written["payload"]["unit_costs"])

        assert await cmb.save_phase_ledger(
            _save_runner(completed=[], cancelled=[274_893, 274_968], banked=0)
        ) == "ok"

        assert written["payload"]["unit_costs"] == before
        assert written["payload"][cmb.UNIT_WORST_HISTORY_KEY] == {
            PHASE_FUTURES: [250_681]
        }, "a beat with no completion contributes NOTHING — never a zero"


# =============================================================================
# 4. THE LOOP — the real ``_run_staged_futures``, against a cancelling database
# =============================================================================


class _StatementCancelled(Exception):
    """Postgres's message verbatim: ``is_statement_timeout`` matches on it."""


class _Runner:
    def __init__(self, *, prior_unit_ms: int | None, prior_worst_ms: int | None):
        self.ledger = _ledger(unit_ms=prior_unit_ms, unit_ms_worst=prior_worst_ms)
        self._elapsed = 0
        self.population_version = "q268"
        self.fingerprint = "fp"
        self.owner = "test:1"
        self.generation = 1
        self.armed: list[int] = []

    def elapsed_ms(self) -> int:
        return self._elapsed

    def advance(self, ms: int) -> None:
        self._elapsed += ms

    def measured_unit_ms(self, phase: str):
        return self.ledger.measured_unit_ms(phase)

    @contextlib.contextmanager
    def stage(self, _name: str):
        yield

    async def commit(self, _db) -> None:
        return None

    async def apply_statement_timeout(self, _db, phase) -> int:
        return self.ledger.statement_timeout_for(phase, elapsed_ms=self._elapsed)

    async def apply_unit_statement_timeout(self, _db, phase, *, unit_ms=None, deferred_rebuild=False) -> int:
        armed = self.ledger.statement_timeout_for_unit(
            phase, elapsed_ms=self._elapsed, unit_ms=unit_ms
        )
        self.armed.append(armed)
        return armed


class _Db:
    """Cancels at whatever timeout the loop ARMED — what Postgres does."""

    def __init__(self, runner: _Runner, roster, costs):
        self.runner = runner
        self.roster = roster
        self.costs = list(costs)
        self.completed = 0
        self.cancelled = 0
        self._generation_read_done = False

    async def execute(self, _sql, _params=None):
        if not self._generation_read_done:
            self._generation_read_done = True
            return types.SimpleNamespace(all=lambda: self.roster)
        cost = self.costs.pop(0) if self.costs else 1
        armed = self.runner.armed[-1] if self.runner.armed else 10**9
        window_left = self.runner.ledger.remaining_ms(elapsed_ms=self.runner.elapsed_ms())
        cap = min(armed, window_left)
        if cost > cap:
            self.runner.advance(cap)
            self.cancelled += 1
            raise _StatementCancelled("canceling statement due to statement timeout")
        self.runner.advance(cost)
        self.completed += 1
        return types.SimpleNamespace(all=lambda: [])

    async def rollback(self) -> None:
        return None


@pytest.fixture
def loop_env(monkeypatch):
    async def _load(**kwargs):
        return (
            sf.new_staged_cursor(
                population_version=kwargs["population_version"],
                input_fingerprint=kwargs["input_fingerprint"],
                generation_fingerprint=kwargs["generation_fingerprint"],
                owner=kwargs["owner"],
                generation=kwargs["generation"],
            ),
            "resume",
            "resumable",
        )

    async def _save(cursor, terminal=None):
        return True

    monkeypatch.setattr(cmb, "load_staged_cursor", _load)
    monkeypatch.setattr(cmb, "save_staged_cursor", _save)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")

    def _build(*, costs, prior_unit_ms, prior_worst_ms, buckets):
        monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", buckets)
        runner = _Runner(prior_unit_ms=prior_unit_ms, prior_worst_ms=prior_worst_ms)
        db = _Db(runner, _roster(buckets * 2), costs)
        monkeypatch.setattr(
            pc, "time", types.SimpleNamespace(monotonic=lambda: runner.elapsed_ms() / 1000.0)
        )
        return runner, db

    return _build


def _roster(n: int):
    return [
        types.SimpleNamespace(market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False)
        for i in range(1, n + 1)
    ]


async def _run(runner, db):
    return await pc._run_staged_futures(db, runner, lambda frozen=False: "SELECT 1")


#: ``plan_units`` hash-buckets the roster, so 20 markets over 10 buckets lands
#: 9 non-empty chunks. Derived rather than assumed, because a test that asserts
#: "every unit banked" against a hard-coded count silently passes when the
#: partition changes shape underneath it.
_CHUNKS = len(sf.plan_units(
    [types.SimpleNamespace(market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False)
     for i in range(1, 21)],
    buckets=10,
))

#: The 22:29Z beat's own shape: five cheap units, then the expensive tail that
#: the fence killed twice and stopped on.
PINNED_COSTS = [
    50_000, 55_000, 58_000, 52_000, BEAT_WORST_MS,
    EXPENSIVE_UNIT_MS, EXPENSIVE_UNIT_MS,
    60_000, 60_000, 60_000,
]


class TestTheLoop:
    @pytest.mark.asyncio
    async def test_the_pin_reproduces_without_the_carried_max(self, loop_env):
        """The control. Five completed, two cancelled, stopped — production."""
        runner, db = loop_env(
            costs=PINNED_COSTS, prior_unit_ms=CARRIED_MEAN_MS,
            prior_worst_ms=None, buckets=10,
        )
        await _run(runner, db)
        assert db.completed == 5
        assert db.cancelled == STAGED_UNIT_MAX_CANCELLATIONS
        assert "staged:window_stop:units_cancelling" in runner.ledger.stages

    @pytest.mark.asyncio
    async def test_the_pinned_beat_banks_its_expensive_units(self, loop_env):
        """The fix, on the beat it was written for.

        Same costs, same window, same carried mean — the only difference is a
        ring that remembers this population completing at 250,681 ms. The two
        units the fence killed now finish, the cancellation budget is never
        spent, and the beat keeps going instead of stopping at five.
        """
        runner, db = loop_env(
            costs=PINNED_COSTS, prior_unit_ms=CARRIED_MEAN_MS,
            prior_worst_ms=max(COMPLETED_WORST_RING), buckets=10,
        )
        await _run(runner, db)
        assert db.cancelled == 0
        assert db.completed == _CHUNKS, "every unit in the partition banked"
        assert runner.ledger.stages["staged:units_done"] == _CHUNKS
        # No stop of any kind: the beat ran out of WORK, not out of fence. The
        # control above stops at five with `units_cancelling`.
        assert not [k for k in runner.ledger.stages if k.startswith("staged:window_stop")]

    @pytest.mark.asyncio
    async def test_the_beat_still_stops_on_a_genuinely_runaway_unit(self, loop_env):
        """CAL-P081's containment, unchanged: a unit far outside anything this
        population has completed is still cancelled, and two of them still end
        the beat rather than converting the window into one statement."""
        costs = [50_000, 55_000, RUNAWAY_MS] + [60_000] * 6
        runner, db = loop_env(
            costs=costs, prior_unit_ms=CARRIED_MEAN_MS,
            prior_worst_ms=max(COMPLETED_WORST_RING), buckets=10,
        )
        await _run(runner, db)
        # Cancelled, not admitted: the widened fence is still ~2x below the
        # runaway, so it can never convert the window into one statement.
        assert db.cancelled == 1
        assert max(runner.armed) < RUNAWAY_MS / 2
        # ...and the beat carries on and banks the units behind it, which is
        # the containment half of CAL-P081.
        assert db.completed == _CHUNKS - 1
        assert STAGED_UNIT_MAX_CANCELLATIONS == 2


# =============================================================================
# 5. THE UPGRADE — CAL-P167 (#1978), repairing CERT-637
#
# Everything above proves the fence widens WHEN THE RING IS ALREADY THERE. The
# ring is never already there. Every durable ledger written before CAL-P163
# deployed carries ``unit_costs`` and no ``unit_worst_history``, so the first
# new-code beat reads ``unit_ms_worst = None``, falls back to the mean, and
# reproduces the pin — and then banks only the cheap units that pin admitted,
# which is not enough evidence to widen the second beat either.
#
# ``test_the_pin_reproduces_without_the_carried_max`` above is that state,
# labelled "the control". CERT-637's finding is that the control IS the
# rollout. These tests start from the legacy payload rather than from a
# pre-seeded ``COMPLETED_WORST_RING``, because that ring cannot exist on the
# first beat after deploy.
# =============================================================================


#: The durable row as it exists on production right now: a mean measured under
#: the old bound, the level CAL-P067 carries, and no ring of any kind.
LEGACY_PAYLOAD = {
    "schema": cmb.PHASE_LEDGER_SCHEMA,
    "task": cmb.MAIN_BUILD_TASK,
    "history": {PHASE_FUTURES: [878_583]},
    "floors": {},
    "unit_costs": {
        PHASE_FUTURES: {"unit_ms": CARRIED_MEAN_MS, "units_total": 10, "units_done": 5}
    },
}


async def _worst_from_legacy(monkeypatch, payload=None):
    """What the plan carries on the first beat after deploy."""
    written = _durable(monkeypatch)
    written["payload"] = dict(LEGACY_PAYLOAD if payload is None else payload)
    _h, _f, unit_costs = await cmb.load_phase_measurements()
    # Read it the way the plan does, so a malformed entry is a ``None`` here
    # for the same reason it is a ``None`` there rather than a test-only crash.
    plan = cmb.derive_plan({PHASE_FUTURES: [1000]}, unit_costs=unit_costs)
    budget = plan.by_name(PHASE_FUTURES)
    return written, budget.unit_ms_worst if budget else None


class TestTheLegacyUpgrade:
    async def test_the_legacy_row_has_no_ring_at_all(self, monkeypatch):
        """The premise, asserted rather than assumed: this really is a payload
        with a measured mean and no ``unit_worst_history`` key."""
        assert cmb.UNIT_WORST_HISTORY_KEY not in LEGACY_PAYLOAD
        assert LEGACY_PAYLOAD["unit_costs"][PHASE_FUTURES]["unit_ms"] > 0

    async def test_the_seed_is_the_bound_the_legacy_code_was_running(self, monkeypatch):
        """Not a chosen number. ``mean * STAGED_UNIT_OVERRUN_FACTOR`` is the
        admission bound the old fence used, so it is the largest unit the legacy
        regime could have completed — the honest ceiling on a worst case whose
        real value that payload cannot recover."""
        _written, worst = await _worst_from_legacy(monkeypatch)
        assert worst == int(CARRIED_MEAN_MS * STAGED_UNIT_OVERRUN_FACTOR)

    async def test_a_ledger_with_no_measured_mean_seeds_nothing(self, monkeypatch):
        """Ruling 075: with nothing measured there is nothing to scale, and the
        phase bound must stand. A fresh install must not inherit a fence."""
        for costs in ({}, {PHASE_FUTURES: {"unit_ms": 0}}, {PHASE_FUTURES: "nonsense"}):
            payload = dict(LEGACY_PAYLOAD, unit_costs=costs)
            _written, worst = await _worst_from_legacy(monkeypatch, payload)
            assert worst is None, costs

    async def test_a_real_ring_is_never_overwritten_by_the_seed(self, monkeypatch):
        """The seed fires on ABSENCE. A ledger that already carries observations
        — including a collapsed beat's small ones — keeps them, or the upgrade
        would be a permanent widening rather than a one-time one."""
        payload = dict(LEGACY_PAYLOAD)
        payload[cmb.UNIT_WORST_HISTORY_KEY] = {PHASE_FUTURES: [41_000]}
        _written, worst = await _worst_from_legacy(monkeypatch, payload)
        assert worst == 41_000

    @pytest.mark.asyncio
    async def test_beat_one_banks_the_expensive_units_from_the_legacy_payload(
        self, monkeypatch, loop_env
    ):
        """The repair, on the state that actually exists at deploy.

        Same specimen as ``test_the_pinned_beat_banks_its_expensive_units``, but
        the worst case is not handed to the ledger — it is derived from the
        legacy durable row by the upgrade path. Revert
        ``_bootstrap_worst_history`` and this goes red with the production
        shape: five banked, two cancelled.
        """
        _written, worst = await _worst_from_legacy(monkeypatch)
        runner, db = loop_env(
            costs=PINNED_COSTS, prior_unit_ms=CARRIED_MEAN_MS,
            prior_worst_ms=worst, buckets=10,
        )
        await _run(runner, db)
        assert db.cancelled == 0, "the two 300,000 ms units are no longer killed"
        assert db.completed == _CHUNKS
        assert not [k for k in runner.ledger.stages if k.startswith("staged:window_stop")]

    @pytest.mark.asyncio
    async def test_the_seeded_fence_still_refuses_the_runaway(
        self, monkeypatch, loop_env
    ):
        """The containment half. The seed is derived from the legacy bound, so
        it widens by a bounded factor — CAL-P081's 901,266 ms specimen is still
        cancelled, and two of them still end the beat."""
        _written, worst = await _worst_from_legacy(monkeypatch)
        costs = [50_000, 55_000, RUNAWAY_MS] + [60_000] * 6
        runner, db = loop_env(
            costs=costs, prior_unit_ms=CARRIED_MEAN_MS,
            prior_worst_ms=worst, buckets=10,
        )
        await _run(runner, db)
        assert db.cancelled == 1
        assert max(runner.armed) < RUNAWAY_MS / 2
        assert db.completed == _CHUNKS - 1

    async def test_beat_two_reads_a_real_observation_and_the_seed_never_recurs(
        self, monkeypatch
    ):
        """The other half of CERT-637: the second beat must not re-pin, and the
        seed must not be recomputed from a mean that the widened fence has since
        raised — that would be a fence feeding itself.

        Beat one banks a 300,000 ms unit. The save writes a ring, so the key
        exists; beat two therefore reads a MEASURED worst and the upgrade path
        is inert forever after.
        """
        written = _durable(monkeypatch)
        written["payload"] = dict(LEGACY_PAYLOAD)

        assert await cmb.save_phase_ledger(
            _save_runner(completed=[60_000, EXPENSIVE_UNIT_MS], cancelled=[], banked=9)
        ) == "ok"

        ring = written["payload"][cmb.UNIT_WORST_HISTORY_KEY][PHASE_FUTURES]
        assert ring == [int(CARRIED_MEAN_MS * STAGED_UNIT_OVERRUN_FACTOR), EXPENSIVE_UNIT_MS], (
            "the seed is banked as an ordinary ring entry beside the real one"
        )

        _h, _f, unit_costs = await cmb.load_phase_measurements()
        assert unit_costs[PHASE_FUTURES]["unit_ms_worst"] == EXPENSIVE_UNIT_MS

        # And it is now driven by measurement: a beat whose mean has risen does
        # not raise the seed, because the seed is never computed again.
        assert await cmb.save_phase_ledger(
            _save_runner(completed=[EXPENSIVE_UNIT_MS], cancelled=[], banked=9)
        ) == "ok"
        after = written["payload"][cmb.UNIT_WORST_HISTORY_KEY][PHASE_FUTURES]
        assert after == ring + [EXPENSIVE_UNIT_MS]
        assert after.count(int(CARRIED_MEAN_MS * STAGED_UNIT_OVERRUN_FACTOR)) == 1

    async def test_the_seed_ages_out_of_the_window(self, monkeypatch):
        """A floor for one day, not a permanent widening. After a full window of
        real observations the seed is gone and the fence is measurement-only."""
        written = _durable(monkeypatch)
        written["payload"] = dict(LEGACY_PAYLOAD)
        seed = int(CARRIED_MEAN_MS * STAGED_UNIT_OVERRUN_FACTOR)
        for _ in range(UNIT_WORST_WINDOW):
            assert await cmb.save_phase_ledger(
                _save_runner(completed=[41_000], cancelled=[], banked=9)
            ) == "ok"
        ring = written["payload"][cmb.UNIT_WORST_HISTORY_KEY][PHASE_FUTURES]
        assert len(ring) == UNIT_WORST_WINDOW
        assert seed not in ring, "the seed ages out like any other entry"
