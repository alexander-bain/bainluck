"""#6599 — a slot that is too big for the window announces itself by SUCCEEDING.

Every refinement the staged futures build has keys on a **cancellation**.
``STAGED_UNIT_SPLIT_AFTER`` cuts a slot killed twice at its bound;
``cancellation_is_conclusive`` cuts one killed once with the right evidence;
``attempt_order`` defers one that has cancelled at all. All three read the same
signal: *the unit failed*.

A slot can be too large for the BEAT WINDOW and still comfortably inside its
statement timeout. It then completes, banks its rows, and asks for nothing — and
under every rule above it is a healthy slot. Production sat in exactly that state
for a week: **108 of 203 units banked, one 726,124 ms unit per 1,336,679 ms beat,
46% of every window unusable**, `/api/calibration` serving a seven-day-old bank,
and no mechanism by which the build could improve its own packing, because a
build that never fails never triggers its own repair.

``packing_split_factor`` is that missing trigger: measured completed cost over
the whole window, not a cancellation.

The rig is the CAL-P1301 rig from
``test_calibration_stuck_head_deferral_6599.py`` — a real ledger, a real cursor
codec, a fake clock advanced by the database, N beats over one durable bus —
with one change that is the whole point of this file: **the slow slots here
COMPLETE.** Nothing in this file cancels a unit.
"""

import contextlib
import types

import pytest

from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils import calibration_staged_futures as sf
from app.utils.calibration_phase_ledger import (
    PHASE_FUTURES,
    STAGED_UNIT_MAX_REFINEMENT_BUCKETS,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)

#: 8 slots over 1,024 virtual questions — 128 to a slot on average.
#:
#: **1,024 and not 64, and the reason is a measurement.** ``bucket_of`` hashes,
#: so slots are not equal, and the spread is a function of the population: at 64
#: questions the largest slot holds 14 against a mean of 8 (1.75x) and cancels
#: at its bound, dragging the test onto the cancellation arm this file exists
#: NOT to be about; at 512 it is 1.22x and the smallest slot is cheap enough to
#: let a second unit in, which blurs the pin the strawman has to show. At 1,024
#: the slots run 112–144 against 128 (0.88x–1.13x): every slot completes, and
#: none is small enough for two to share a beat. Production's spread is tighter
#: still — mean 726,124 ms against worst 727,311 ms, 0.16% apart — so this rig
#: is pessimistic about uniformity rather than flattering.
BUCKETS = 8
MARKETS = 1_024

#: The average slot size, which is what the build carries between beats as its
#: measured unit cost.
SLOT_QUESTIONS = MARKETS // BUCKETS

#: One beat's window, the production order (~22 min).
WINDOW_MS = 1_350_000

#: A question in a slot that is too coarse for the window. A mean slot of 128 is
#: 720,000 ms — the production unit cost (726,124 ms) to within 1%. It is well
#: under the 1,320,000 ms bound the build arms for it, so the unit COMPLETES;
#: and 720,000 * (1 + 1.25) = 1,620,000 > 1,350,000, so no beat can hold two.
SLOW_SUCCESS_VM_MS = 5_625

#: A question in a slot that packs. A mean slot is 320,000 ms, and
#: 320,000 * 2.25 = 720,000 < 1,350,000 — two fit, so nothing is owed a cut.
PACKING_VM_MS = 2_500

#: Captured before any test can neuter it, so the strawman arm restores the real
#: one rather than whatever a previous test left behind.
_REAL_PACKING_SPLIT_FACTOR = sf.packing_split_factor


# =============================================================================
# The rig
# =============================================================================


def _ledger(*, window_ms: int, unit_ms: int | None, buckets: int) -> PhaseLedger:
    plan = PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=None,
                statement_timeout_ms=None,
                measured_input=True,
                unit_ms=unit_ms,
                units_total=buckets,
                units_done=0,
            ),
        ),
        soft_limit_ms=window_ms + 120_000,
        cleanup_margin_ms=120_000,
    )
    return PhaseLedger(
        plan=plan,
        population_version="q271",
        owner="test:1",
        generation=1,
        input_fingerprint="fp",
        phases=(PHASE_FUTURES,),
    )


class _Runner:
    """One beat. The clock is advanced by the database (gotcha #44)."""

    def __init__(self, *, window_ms: int, prior_unit_ms: int | None, generation: int,
                 buckets: int):
        self.ledger = _ledger(
            window_ms=window_ms, unit_ms=prior_unit_ms, buckets=buckets
        )
        self._elapsed = 0
        self.population_version = "q271"
        self.fingerprint = "fp"
        self.owner = "test:1"
        self.generation = generation
        self.armed: list[int] = []
        self.rebuild_deferred = False

    def defer_rebuild(self) -> None:
        """CAL-P994's publish-first flag. Reached once the served bank is
        complete and the build is rebuilding behind it, which these runs do."""
        self.rebuild_deferred = True

    def elapsed_ms(self) -> int:
        return self._elapsed

    def advance(self, ms: int) -> None:
        self._elapsed += int(ms)

    def measured_unit_ms(self, phase: str):
        return self.ledger.measured_unit_ms(phase)

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
        armed = self.ledger.statement_timeout_for_unit(
            phase, elapsed_ms=self._elapsed, unit_ms=unit_ms
        )
        self.armed.append(armed)
        return armed


class _Db:
    """A database whose cost is a property of the QUESTIONS it is asked about.

    A cost tied to call position would follow the reordering around and measure
    nothing; a chunk here costs the sum of its virtual questions, which is what
    a chunk statement actually does. A unit that outruns its cap would cancel —
    and ``cancelled`` staying empty is asserted, because a cancellation would
    silently move these tests onto the arm that already worked.
    """

    def __init__(self, runner: _Runner, roster, vm_ms: int):
        self.runner = runner
        self.roster = roster
        self.vm_ms = int(vm_ms)
        self.by_market = {int(row.market_id): str(row.vm_id) for row in roster}
        self.completed: list[frozenset[str]] = []
        self.cancelled: list[frozenset[str]] = []
        self._generation_read_done = False

    async def execute(self, _sql, params=None):
        if not self._generation_read_done:
            self._generation_read_done = True
            return types.SimpleNamespace(all=lambda: self.roster)
        market_ids = list((params or {}).get(pc.VM_ROSTER_MARKET_IDS_PARAM) or ())
        vm_ids = frozenset(self.by_market[int(m)] for m in market_ids)
        cost = self.vm_ms * len(vm_ids)
        armed = self.runner.armed[-1] if self.runner.armed else 10**9
        window_left = self.runner.ledger.remaining_ms(
            elapsed_ms=self.runner.elapsed_ms()
        )
        cap = min(armed, window_left)
        if cost > cap:
            self.runner.advance(cap)
            self.cancelled.append(vm_ids)
            raise RuntimeError("canceling statement due to statement timeout")
        self.runner.advance(cost)
        self.completed.append(vm_ids)
        return types.SimpleNamespace(all=lambda: [])

    async def rollback(self) -> None:
        return None


def _roster(n: int = MARKETS):
    return [
        types.SimpleNamespace(
            market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False
        )
        for i in range(1, n + 1)
    ]


class _Bus:
    """The durable cursor across beats, read and written by the real codec."""

    def __init__(self):
        self.payload = None
        self.writes = 0

    async def load(self, **kwargs):
        return sf.decode_staged_cursor_detailed(
            self.payload,
            expected_population_version=kwargs["population_version"],
            expected_input_fingerprint=kwargs["input_fingerprint"],
            expected_generation_fingerprint=kwargs["generation_fingerprint"],
            owner=kwargs["owner"],
            generation=kwargs["generation"],
            now=0.0,
            legacy_input_fingerprint=kwargs.get("legacy_input_fingerprint"),
        )

    async def save(self, cursor, terminal=None, banks_a_unit=True):
        self.payload = cursor.as_payload()
        self.payload["terminal"] = terminal or self.payload.get("terminal")
        self.writes += 1
        return True


@pytest.fixture
def arena(monkeypatch):
    """A factory for one independent build: its own durable cursor and clock.

    A factory rather than a fixture value because the headline measurement is a
    COMPARISON — the same population run with the trigger neutered and with it
    live — and two builds that shared a cursor would not be two builds.
    """

    def make(*, packing: bool = True):
        return _arena(monkeypatch, packing=packing)

    return make


def _arena(monkeypatch, *, packing: bool):
    """Run N beats against one durable cursor. Returns ``(run_beat, bus)``."""
    bus = _Bus()
    monkeypatch.setattr(cmb, "load_staged_cursor", bus.load)
    monkeypatch.setattr(cmb, "save_staged_cursor", bus.save)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", BUCKETS)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
    monkeypatch.setattr(
        sf,
        "packing_split_factor",
        _REAL_PACKING_SPLIT_FACTOR if packing else (lambda *a, **k: 0),
    )

    state = {"generation": 0, "prior_unit_ms": None}

    async def run_beat(roster, *, vm_ms=SLOW_SUCCESS_VM_MS, window_ms=WINDOW_MS):
        state["generation"] += 1
        runner = _Runner(
            window_ms=window_ms,
            # The build's own measured cost of a unit, CARRIED between beats the
            # way production carries it — the previous beat's mean over
            # completions, not a constant. It matters that this falls as the
            # build cuts its tail: a rig that pinned it would hold the admission
            # fence at the old unit's cost forever and hide the improvement the
            # cut buys.
            prior_unit_ms=(
                state["prior_unit_ms"]
                if state["prior_unit_ms"] is not None
                else vm_ms * SLOT_QUESTIONS
            ),
            generation=state["generation"],
            buckets=BUCKETS,
        )
        db = _Db(runner, roster, vm_ms)
        monkeypatch.setattr(
            pc,
            "time",
            types.SimpleNamespace(monotonic=lambda: runner.elapsed_ms() / 1000.0),
        )
        rows = await pc._run_staged_futures(db, runner, lambda frozen=False: "SELECT 1")
        measured = runner.ledger.stages.get("staged:unit_ms_mean")
        if measured:
            state["prior_unit_ms"] = int(measured)
        return types.SimpleNamespace(rows=rows, runner=runner, db=db)

    return run_beat, bus


def _banked(bus) -> int:
    return len((bus.payload or {}).get("committed_units") or [])


def _banked_keys(bus) -> list[str]:
    return list((bus.payload or {}).get("committed_units") or [])


def _units_this_beat(beat) -> int:
    return int(beat.runner.ledger.stages.get("staged:units_this_beat", 0))


async def _until_published(run_beat, roster, *, max_beats=40, **kwargs):
    """Beat until the build PUBLISHES, and report how it got there.

    Publication, not a unit count, is the terminating condition: it is the
    reader-visible event this issue is about, and a build that banks faster but
    never publishes has not shipped anything. ``_run_staged_futures`` returns
    the merged payload on the beat that finalizes and ``None`` on every other,
    so the return value IS the signal.
    """
    per_beat: list[int] = []
    cancels: list[int] = []
    cut_on_beat: int | None = None
    for index in range(max_beats):
        beat = await run_beat(roster, **kwargs)
        per_beat.append(_units_this_beat(beat))
        cancels.append(len(beat.db.cancelled))
        if cut_on_beat is None and any(
            "unit_packing_split:applied:" in k for k in beat.runner.ledger.stages
        ):
            cut_on_beat = index
        if beat.rows is not None:
            return types.SimpleNamespace(
                beats=index + 1,
                per_beat=per_beat,
                cancels=cancels,
                cut_on_beat=cut_on_beat,
                last=beat,
            )
    raise AssertionError(
        f"the build never published in {max_beats} beats: {per_beat}"
    )


# =============================================================================
# 1. THE DEFECT — reproduced, then ended
# =============================================================================


class TestThePinAtOneUnitPerBeat:
    @pytest.mark.asyncio
    async def test_without_the_packing_trigger_every_beat_runs_exactly_one_unit(
        self, arena
    ):
        """THE STRAWMAN, and the reason this file is not vacuous.

        With the new trigger neutered — and NOTHING else changed — the build is
        pinned at one unit per beat for its whole life, because nothing else in
        it can see a slot that is too coarse but never fails. Every unit
        completes; not one cancels; every existing refinement rule is satisfied
        and silent. This is the production state of #6599 in miniature.

        If this ever shows two units in a beat, the pin has been lifted by
        something other than the trigger, and the comparison below is measuring
        that something else instead.
        """
        run_beat, _bus = arena(packing=False)
        run = await _until_published(run_beat, _roster())

        assert run.per_beat == [1] * BUCKETS, (
            f"expected the build pinned at one unit per beat, got {run.per_beat}"
        )
        assert sum(run.cancels) == 0, (
            "a unit cancelled, so the pin cannot be attributed to slow SUCCESS "
            f"— this is the wrong arm: {run.cancels}"
        )
        assert run.cut_on_beat is None
        # 8 slots at ~720,000 ms in a 1,350,000 ms window: 53% of every beat is
        # spent and the rest is unusable, for as many beats as there are slots.
        assert run.beats == BUCKETS

    @pytest.mark.asyncio
    async def test_a_slot_that_completes_too_slowly_to_pack_is_cut_and_publishes_sooner(
        self, arena
    ):
        """THE SHIP — the same population, the same window, the trigger live.

        The build learns from a unit that SUCCEEDED that its partition is too
        coarse for the window, cuts the tail, and starts fitting more than one
        unit into a beat, which the strawman proves it can never otherwise do.
        The assertion is the one a reader cares about: **it publishes in fewer
        beats**, i.e. the accuracy page stops waiting.
        """
        baseline_run_beat, _b = arena(packing=False)
        baseline = await _until_published(baseline_run_beat, _roster())

        run_beat, _bus = arena(packing=True)
        run = await _until_published(run_beat, _roster())

        # THE ARM. The first cut must have been earned by a unit that COMPLETED:
        # had anything cancelled first, the existing cancellation rules could
        # have produced the same refinement and this would be measuring them.
        assert run.cut_on_beat is not None, "no slot was ever cut for packing"
        assert sum(run.cancels[: run.cut_on_beat + 1]) == 0, (
            "a unit cancelled before the first packing cut, so the cut cannot be "
            f"attributed to a slow success: {run.cancels}"
        )

        assert max(run.per_beat) > 1, (
            f"the build never ran two units in a beat: {run.per_beat}"
        )
        assert run.beats < baseline.beats, (
            "the build published no sooner than the pinned one — the cut bought "
            f"nothing: {run.beats} beats vs {baseline.beats} "
            f"({run.per_beat} vs {baseline.per_beat})"
        )

    @pytest.mark.asyncio
    async def test_the_cut_is_recorded_under_its_own_name_on_the_first_beat(
        self, arena
    ):
        """An absent stage reads as 'fine' (gotcha #53), so the cut is named.

        ``unit_packing_factor`` and ``unit_packing_split:applied`` are what an
        operator greps to tell "the build cut its tail because a unit succeeded
        slowly" from the four other reasons a beat can end early.
        """
        run_beat, _bus = arena()
        beat = await run_beat(_roster())
        stages = beat.runner.ledger.stages

        assert "staged:window_stop:unit_too_large" in stages
        factors = {k: v for k, v in stages.items() if "unit_packing_factor:" in k}
        applied = {k for k in stages if "unit_packing_split:applied:" in k}
        assert len(factors) == 1, f"expected exactly one slot cut, got {factors}"
        assert set(factors.values()) == {2}, (
            "720,000 ms against a 1,350,000 ms window is worth two children, and "
            f"the factor must be that measurement: {factors}"
        )
        assert len(applied) == 1, f"the cut was not applied: {sorted(stages)}"
        assert stages.get("staged:units_split") == 1
        assert "staged:unit_packing_not_persisted" not in stages


# =============================================================================
# 2. THE BANK IS UNTOUCHABLE — the property that makes this safe mid-build
# =============================================================================


class TestTheBankIsPreserved:
    @pytest.mark.asyncio
    async def test_cutting_for_packing_never_changes_a_banked_slots_address(
        self, arena
    ):
        """The 108 banked units of #6599 are why this is the first guard.

        A refinement re-addresses the virtual questions of the slot it cuts. If
        it ever cut a slot that is already banked, that slot's key would leave
        the plan, ``retain_planned_units`` would drop it as a stranger, and the
        beat would throw away work — up to a 19-hour rebuild in production.

        Asserted the strict way: every key banked before a cut is still banked,
        byte for byte and in order, after several more cuts.

        **THE MUTANT THAT CONVICTS THIS IS A CALL-SITE MUTANT, and the obvious
        one does not work.** Two independent locks protect the bank — the loop
        ``continue``s past a banked chunk before the window check, and
        ``refine_unit`` returns ``SPLIT_BANKED`` — so no SINGLE mutation can
        reach the hazard. The tempting double mutation (neuter both locks in
        place) leaves this test GREEN and reads as proof that it pins nothing.
        It is not: severing the loop's skip also removes the ``done += 1``
        beside it, so the build re-runs banked units forever, never publishes,
        and the rig stalls before it can produce the state under test. *A mutant
        destructive enough to stall the rig cannot convict a guard about what
        the rig produces — it must break the property, not the machine that
        exercises it.*

        The faithful mutant is calibration/2736's proposed PLACEMENT: at the
        decline, cut the slot that just COMPLETED rather than the one declined
        (``chunk = [c for c in planned_order if cursor.has(c.key)][0]``).

        * with ``refine_unit``'s refusal intact — logged ``refinement banked``,
          no cut, this test PASSES and the two throughput tests fail. The
          placement is **inert**, not dangerous.
        * with the refusal also severed — this test FAILS on a real bank loss,
          ``before: ['752a99293b3ed1a3'] / after: ['924f8bf47de95e44']``.

        So the guard is live, and the difference between a cut that works and a
        bank wipe is *which slot is cut*. Measured 2026-09-22 (lat939).
        """
        run_beat, bus = arena()
        roster = _roster()

        await run_beat(roster)
        banked_after_first = _banked_keys(bus)
        assert banked_after_first, "the first beat banked nothing — rig broken"

        for _ in range(3):
            await run_beat(roster)

        after = _banked_keys(bus)
        assert after[: len(banked_after_first)] == banked_after_first, (
            "a banked key changed or was dropped when a later slot was cut:\n"
            f"  before: {banked_after_first}\n  after:  {after[: len(banked_after_first)]}"
        )

    def test_refine_unit_refuses_a_banked_slot_outright(self):
        """The second lock, independent of the loop's own skip.

        The loop never offers a banked chunk — it ``continue``s past one before
        the window check — but the refusal is asserted here directly, because
        the loop's skip and this refusal protect the bank for different reasons
        and a future caller may only have one of them.
        """
        chunk = sf.UnitChunk(
            index=0, vm_ids=("m:1", "m:2"), market_ids=(1, 2), buckets=BUCKETS
        )
        empty = sf.StagedFuturesCursor(population_version="q271")
        banked = sf.advance(empty, chunk.key, [], owner="t", lease_expires_at=0.0)

        cursor, outcome = sf.refine_unit(banked, chunk, factor=2)
        assert outcome == sf.SPLIT_BANKED
        assert cursor is banked, "a refused refinement must return the cursor unchanged"


# =============================================================================
# 3. A SLOT THAT PACKS IS LEFT ALONE
# =============================================================================


class TestNothingThatFitsIsCut:
    @pytest.mark.asyncio
    async def test_a_beat_that_merely_runs_out_of_window_cuts_nothing(self, arena):
        """The false-positive guard, and the reason the predicate reads the
        WHOLE window rather than ``remaining_ms``.

        Ending a beat with time left that cannot hold another unit is the
        normal, correct end of a healthy beat — it happens on every beat of
        every well-packed build. If the trigger read ``remaining_ms`` it would
        fire there, and it would cut the whole population to dust one beat at a
        time on a build with nothing wrong with it.
        """
        run_beat, bus = arena()
        roster = _roster()

        beat = await run_beat(roster, vm_ms=PACKING_VM_MS)
        stages = beat.runner.ledger.stages

        assert _units_this_beat(beat) >= 2, (
            "the rig must pack more than one unit for this to be the healthy case"
        )
        assert "staged:window_stop:unit_too_large" in stages, (
            "the beat must have declined a unit, or this guard proves nothing"
        )
        assert stages.get("staged:unit_packs_in_window") == 1, (
            "the decline must be recorded as 'it fits, the beat is spent' rather "
            "than left absent (gotcha #53)"
        )
        assert not [k for k in stages if "unit_packing_split:" in k], (
            f"a slot that packs was cut: {sorted(stages)}"
        )
        assert "staged:units_split" not in stages


# =============================================================================
# 4. THE ARITHMETIC — a measurement over a measurement, and its refusals
# =============================================================================


class TestThePackingFactor:
    def test_the_factor_is_the_measured_cost_over_what_the_window_can_pack(self):
        # 726,124 ms against the 1,336,679 ms production window: the target is
        # 594,079 ms (two must fit under the same 1.25 margin that admits one),
        # and the slot is worth ceil(726,124 / 594,079) = 2 children.
        assert (
            sf.packing_split_factor(726_124, 1_336_679, safety=1.25) == 2
        )
        # Four times the packable cost is worth four children, not two — the
        # factor tracks the measurement rather than stepping.
        assert sf.packing_split_factor(2_400_000, 1_350_000, safety=1.25) == 4

    def test_a_slot_that_packs_is_worth_no_cut_at_all(self):
        # Exactly at the target, and just under it: two fit, nothing is owed.
        assert sf.packing_split_factor(600_000, 1_350_000, safety=1.25) == 0
        assert sf.packing_split_factor(320_000, 1_350_000, safety=1.25) == 0

    def test_one_ms_over_the_target_is_the_smallest_real_cut(self):
        """The floor is two, never one: a factor of one is a refinement that
        refines nothing, and a caller recording it would record a split that
        never happened (gotcha #53)."""
        assert sf.packing_split_factor(600_001, 1_350_000, safety=1.25) == 2

    def test_an_unreadable_measurement_declines_rather_than_guessing(self):
        """Ruling 075's second clause: "we have no measurement" must not render
        as a number. Every unreadable input declines to cut."""
        for measured, window in (
            (0, 1_350_000),
            (None, 1_350_000),
            (726_124, 0),
            (726_124, None),
            ("slow", 1_350_000),
            (726_124, "wide"),
        ):
            assert (
                sf.packing_split_factor(measured, window, safety=1.25) == 0
            ), f"{measured!r} / {window!r} should decline, not cut"

    def test_the_cut_is_capped_and_the_planner_never_raises_its_own_ceiling(self):
        assert (
            sf.packing_split_factor(10**12, 1_350_000, safety=1.25, max_factor=16) == 16
        )

    def test_a_refinement_chain_cannot_outrun_the_bucket_ceiling(self):
        """``STAGED_UNIT_MAX_REFINEMENT_BUCKETS`` still refuses, and says so.

        The factor is arithmetic and knows nothing about depth; the refusal
        lives in ``refine_unit`` and must survive this new caller, which asks
        for cuts on evidence that arrives every beat rather than only on a
        cancellation.
        """
        deep = STAGED_UNIT_MAX_REFINEMENT_BUCKETS
        chunk = sf.UnitChunk(
            index=0, vm_ids=("m:1", "m:2"), market_ids=(1, 2), buckets=deep
        )
        cursor = sf.StagedFuturesCursor(population_version="q271")
        after, outcome = sf.refine_unit(cursor, chunk, factor=2)
        assert outcome == sf.SPLIT_TOO_DEEP
        assert after is cursor
