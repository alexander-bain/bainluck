"""CAL-P1301 (#6599): two stuck slots at the head of the plan starve 95 healthy
ones, and the slots themselves are finished by cutting them, never by skipping.

THE SPECIMEN, measured on production 2026-09-16 (durable ledger
``calibration:main:phase_ledger``, single row, ``updated_at 21:38:00.771716+00``)::

    terminal   cancelled
    banked     31
    unit_costs futures {"units_done": 31, "units_total": 128, "level_refuted": true}

31 of 128 units banked and MOTIONLESS for a day — including across the beat that
first ran with a withdrawn unit level (#6275, live on ``bainluck-heavy`` v36 at
19:58Z), which was the last remaining explanation that did not require a code
change. Every beat: two units admitted, two cancelled at their own fence,
``staged:window_stop:units_cancelling``, zero banked. The 95 healthy units behind
them were not slow, not drifted and not refused — they were never ATTEMPTED.

**The mechanism is the composition of two correct rules.** CAL-P081 skips a
cancelled unit rather than ending the beat (right: ending it banks nothing), and
:data:`STAGED_UNIT_MAX_CANCELLATIONS` stops a beat after two (right: a third says
the BEAT is slow). But the loop skips units the cursor already holds, so the
first unbanked slot leads every beat — and two reproducibly cancelling slots at
the head spend the whole budget before the third unit is reached. Nothing in the
loop remembered, between beats, that it had already watched those two slots
cancel; the evidence went into each beat's ledger and died there.

**The two halves this file pins, which are independent and separately falsifiable:**

* **DEFERRAL — the tail moves.** A cancellation is recorded against the SLOT, on
  the cursor, durably. The next beat attempts slots in ascending recorded
  cancellations, so the stuck heads go last and the budget is spent only after
  the work that can progress has. ``TestStarvation`` reproduces the production
  shape exactly and shows the strawman — forget the cancellation and the tail is
  never reached, every beat, forever.
* **COMPLETION — the stuck slots finish.** A slot that cancels twice is REFINED:
  ``bucket_of(vm, 128*m) mod 128 == bucket_of(vm, 128)``, so its children exactly
  partition it, whole virtual questions and all, and they are ordinary planned
  units in every other respect. ``TestEventualCompletion`` runs the beats until
  the generation is COMPLETE — not until it reaches 126/128.

**Nothing is skipped and no gate is waived.** ``TestNothingIsWaived`` holds a
single-virtual-question slot that cannot be read inside any bound: it is never
dropped, the generation never completes, nothing publishes, and the reason is
named in the ledger. That is the honest end state for a question we cannot read,
and it is the one this design must not be able to paper over.

The loop tests drive the REAL ``_run_staged_futures``, the real planner and the
real cursor codec across MULTIPLE BEATS against a fake database that cancels at
whatever ``statement_timeout`` the loop actually armed. Unit cost is a property
of the QUESTIONS in the chunk, not of the call order, because the order is
exactly what this change moves.
"""

from __future__ import annotations

import contextlib
import types

import pytest

from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils import calibration_staged_futures as sf
from app.utils.calibration_phase_ledger import (
    PHASE_FUTURES,
    STAGED_UNIT_MAX_CANCELLATIONS,
    STAGED_UNIT_SPLIT_AFTER,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)

# The population: 8 slots of 8 virtual questions, small enough to read in a
# failure message and large enough to have a head and a tail.
BUCKETS = 8
MARKETS = 64

#: What one ordinary virtual question costs to read. The slot totals ~64 s,
#: which is the production order (72,202 ms measured mean over completions).
HEALTHY_VM_MS = 8_000
#: What a question in a stuck slot costs. Eight of them is 800 s — past any
#: fence the build can derive from an 8 s question, which is the specimen: a
#: slot that exceeds even the phase bound.
SLOW_VM_MS = 100_000
#: One beat's window. ~22 min, the production order.
WINDOW_MS = 1_350_000


# =============================================================================
# The rig: a real ledger, a real cursor, a fake clock, N beats
# =============================================================================


class _StatementCancelled(Exception):
    """Postgres cancelling a statement at its own backstop.

    The message is the one Postgres emits, because ``is_statement_timeout``
    matches on the message.
    """


def _ledger(*, window_ms: int, unit_ms: int | None) -> PhaseLedger:
    plan = PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=None,
                statement_timeout_ms=None,
                measured_input=True,
                unit_ms=unit_ms,
                units_total=BUCKETS,
                units_done=5 if unit_ms else 0,
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


class _Runner:
    """One beat. The clock is advanced by the database (gotcha #44)."""

    def __init__(self, *, window_ms: int, prior_unit_ms: int | None, generation: int):
        self.ledger = _ledger(window_ms=window_ms, unit_ms=prior_unit_ms)
        self._elapsed = 0
        self.population_version = "q268"
        self.fingerprint = "fp"
        self.owner = "test:1"
        self.generation = generation
        self.armed: list[int] = []

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

    The existing CAL-P081 harness pops costs off a list in call order, which
    cannot express this defect at all: the whole change is that the ORDER moves,
    so a cost tied to position would follow the reordering around and measure
    nothing. Here a chunk costs the sum of its virtual questions' costs, which is
    what a chunk statement actually does — read the markets of the questions it
    was handed.
    """

    def __init__(self, runner: _Runner, roster, slow_vm_ids, slow_ms: int = SLOW_VM_MS):
        self.runner = runner
        self.roster = roster
        self.slow = set(slow_vm_ids)
        self.slow_ms = int(slow_ms)
        self.by_market = {int(row.market_id): str(row.vm_id) for row in roster}
        self.completed: list[frozenset[str]] = []
        self.cancelled: list[frozenset[str]] = []
        self._generation_read_done = False

    def cost_of(self, vm_ids) -> int:
        return sum(
            self.slow_ms if vm in self.slow else HEALTHY_VM_MS for vm in set(vm_ids)
        )

    async def execute(self, _sql, params=None):
        if not self._generation_read_done:
            self._generation_read_done = True
            return types.SimpleNamespace(all=lambda: self.roster)
        market_ids = list((params or {}).get(pc.VM_ROSTER_MARKET_IDS_PARAM) or ())
        vm_ids = frozenset(self.by_market[int(m)] for m in market_ids)
        cost = self.cost_of(vm_ids)
        armed = self.runner.armed[-1] if self.runner.armed else 10**9
        window_left = self.runner.ledger.remaining_ms(elapsed_ms=self.runner.elapsed_ms())
        cap = min(armed, window_left)
        if cost > cap:
            self.runner.advance(cap)
            self.cancelled.append(vm_ids)
            raise _StatementCancelled("canceling statement due to statement timeout")
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


def _vm_ids_in_slot(roster, index: int, buckets: int = BUCKETS) -> set[str]:
    return {
        str(row.vm_id)
        for row in roster
        if sf.bucket_of(str(row.vm_id), buckets) == index
    }


class _Bus:
    """The durable cursor, across beats. One dict, read and written by the real codec."""

    def __init__(self):
        self.payload = None
        self.writes = 0

    async def load(self, **kwargs):
        cursor, action, reason = sf.decode_staged_cursor_detailed(
            self.payload,
            expected_population_version=kwargs["population_version"],
            expected_input_fingerprint=kwargs["input_fingerprint"],
            expected_generation_fingerprint=kwargs["generation_fingerprint"],
            owner=kwargs["owner"],
            generation=kwargs["generation"],
            now=0.0,
            legacy_input_fingerprint=kwargs.get("legacy_input_fingerprint"),
        )
        return cursor, action, reason

    async def save(self, cursor, terminal=None):
        self.payload = cursor.as_payload()
        self.payload["terminal"] = terminal or self.payload.get("terminal")
        self.writes += 1
        return True


@pytest.fixture
def beats(monkeypatch):
    """Run N beats against one durable cursor. Returns ``(run_beat, bus)``."""
    bus = _Bus()
    monkeypatch.setattr(cmb, "load_staged_cursor", bus.load)
    monkeypatch.setattr(cmb, "save_staged_cursor", bus.save)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", BUCKETS)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")

    state = {"generation": 0}

    async def run_beat(
        roster,
        slow_vm_ids,
        *,
        window_ms=WINDOW_MS,
        prior_unit_ms=None,
        slow_ms=SLOW_VM_MS,
    ):
        state["generation"] += 1
        runner = _Runner(
            window_ms=window_ms,
            # The build's measured cost of an ordinary unit. Carried on the plan
            # exactly as production carries it between beats.
            prior_unit_ms=(
                HEALTHY_VM_MS * (MARKETS // BUCKETS) if prior_unit_ms is None
                else prior_unit_ms
            ),
            generation=state["generation"],
        )
        db = _Db(runner, roster, slow_vm_ids, slow_ms=slow_ms)
        monkeypatch.setattr(
            pc,
            "time",
            types.SimpleNamespace(monotonic=lambda: runner.elapsed_ms() / 1000.0),
        )
        rows = await pc._run_staged_futures(db, runner, lambda frozen=False: "SELECT 1")
        return types.SimpleNamespace(rows=rows, runner=runner, db=db)

    return run_beat, bus


def _banked(bus) -> int:
    return len((bus.payload or {}).get("committed_units") or [])


# =============================================================================
# 1. THE STARVATION — reproduced, then ended
# =============================================================================


class TestStarvation:
    @pytest.mark.asyncio
    async def test_two_stuck_heads_starve_the_tail_when_the_cancellation_is_forgotten(
        self, beats, monkeypatch
    ):
        """THE STRAWMAN, and the reason this file is not vacuous.

        Disable the one new fact — the durable per-slot cancellation count — and
        the production specimen reproduces exactly: every beat attempts the same
        two slots, cancels twice, stops on
        ``staged:window_stop:units_cancelling`` and banks NOTHING, while six
        healthy slots sit untouched. Three beats in a row, identical, which is
        what "motionless at 31 for a day" is made of.
        """
        run_beat, bus = beats
        # The loop imports from the pure module at call time, so this reaches the
        # real call site. It removes exactly one thing — the memory — and leaves
        # every other line of the loop as it ships.
        monkeypatch.setattr(sf, "note_unit_cancelled", lambda cursor, ref: cursor)
        roster = _roster()
        slow = _vm_ids_in_slot(roster, 0) | _vm_ids_in_slot(roster, 1)

        for _ in range(3):
            beat = await run_beat(roster, slow)
            assert beat.rows is None
            assert len(beat.db.cancelled) == STAGED_UNIT_MAX_CANCELLATIONS
            assert beat.db.completed == [], (
                "the tail must never be reached — this is the production shape"
            )
            assert "staged:window_stop:units_cancelling" in beat.runner.ledger.stages
            assert _banked(bus) == 0

    @pytest.mark.asyncio
    async def test_the_tail_progresses_on_the_very_next_beat(self, beats):
        """The deferral, end to end.

        Beat 1 meets the two stuck slots first (nothing is known about them yet)
        and spends its budget on them, exactly as before — this change cannot
        see the future. Beat 2 has their cancellations on the cursor, attempts
        them LAST, and banks the whole healthy tail.
        """
        run_beat, bus = beats
        roster = _roster()
        slow = _vm_ids_in_slot(roster, 0) | _vm_ids_in_slot(roster, 1)

        first = await run_beat(roster, slow)
        assert len(first.db.cancelled) == STAGED_UNIT_MAX_CANCELLATIONS
        assert _banked(bus) == 0, "the head still leads the first beat"
        assert (bus.payload or {}).get("unit_cancels"), (
            "the cancellation must be durable, or the next beat repeats this one"
        )

        second = await run_beat(roster, slow)
        assert len(second.db.completed) == BUCKETS - 2, (
            "every healthy slot must be banked once the stuck ones are deferred"
        )
        assert _banked(bus) == BUCKETS - 2
        assert second.runner.ledger.stages.get("staged:units_deferred") == 2

    @pytest.mark.asyncio
    async def test_the_deferral_is_not_a_skip(self, beats):
        """A deferred slot is attempted every beat — last, but attempted.

        The difference matters: the attempts are what earn the second
        cancellation that cuts the slot, so a design that parked them would
        never finish them. This asserts the stuck slots are still being tried
        after the tail is banked.
        """
        run_beat, bus = beats
        roster = _roster()
        slow = _vm_ids_in_slot(roster, 0) | _vm_ids_in_slot(roster, 1)

        await run_beat(roster, slow)
        second = await run_beat(roster, slow)
        assert second.db.cancelled, "the deferred slots must still be attempted"
        # ...and they were attempted AFTER the healthy ones, not instead of them.
        assert len(second.db.completed) == BUCKETS - 2


# =============================================================================
# 2. COMPLETION — 126 of 128 is not recovery
# =============================================================================


class TestEventualCompletion:
    @pytest.mark.asyncio
    async def test_the_stuck_slots_are_finished_by_refinement_and_the_build_completes(
        self, beats
    ):
        """The generation reaches COMPLETE, not 6-of-8.

        A slot that cancels twice is cut into children of a finer partition that
        exactly covers it. The children are ordinary units: they are planned,
        admitted, banked and folded by the same code, so completion is the same
        predicate it always was — every planned unit banked, nothing unplanned
        banked.
        """
        run_beat, bus = beats
        roster = _roster()
        slow = _vm_ids_in_slot(roster, 0) | _vm_ids_in_slot(roster, 1)

        rows = None
        for _ in range(12):
            beat = await run_beat(roster, slow)
            if beat.rows is not None:
                rows = beat.rows
                break
        assert rows is not None, (
            "the build must FINISH; stopping at the healthy tail is the defect "
            "this queue exists to end, one unit further along"
        )
        payload = bus.payload or {}
        assert payload.get("unit_splits"), "the stuck slots were cut"
        # Every question in the population is banked exactly once: the children
        # of a refined slot partition it, so the count of distinct virtual
        # questions read equals the roster's.
        assert set(payload.get("planned_units") or []) == set(
            payload.get("committed_units") or []
        ) or set(payload.get("served_units") or []) == set(
            payload.get("planned_units") or []
        )

    @pytest.mark.asyncio
    async def test_deferral_ALONE_leaves_the_build_short_and_that_is_not_recovery(
        self, beats, monkeypatch
    ):
        """The control for the second half, and codex's bar in one test.

        Take away only the refinement and the deferral still does its job: the
        healthy tail banks, the beats stop failing, the operator window fills
        with progress — and the generation never completes, because two slots
        are still unreadable and nothing publishes until every planned unit is
        in. "126 of 128" is a better-looking livelock, not a recovery.
        """
        run_beat, bus = beats
        monkeypatch.setattr(
            sf, "refine_unit", lambda cursor, chunk, **kwargs: (cursor, sf.SPLIT_ALREADY)
        )
        roster = _roster()
        slow = _vm_ids_in_slot(roster, 0) | _vm_ids_in_slot(roster, 1)

        for _ in range(12):
            beat = await run_beat(roster, slow)
            assert beat.rows is None
        payload = bus.payload or {}
        assert len(payload.get("committed_units") or []) == BUCKETS - 2
        assert not payload.get("unit_splits")

    @pytest.mark.asyncio
    async def test_a_refinement_never_costs_a_banked_unit(self, beats):
        """The carry-over question, measured on the running loop.

        A refinement removes its parent slot from the plan, and
        ``retain_planned_units`` fails CLOSED on a banked unit the plan no longer
        contains — it throws away the whole bank, serving one included. So the
        banked set must only ever GROW across the beats in which a refinement
        lands (the one exception being promotion, which moves a complete bank
        into the serving slot and starts the next one empty).
        """
        run_beat, bus = beats
        roster = _roster()
        slow = _vm_ids_in_slot(roster, 0) | _vm_ids_in_slot(roster, 1)

        held: set[str] = set()
        refined_at: int | None = None
        for beat_no in range(1, 13):
            beat = await run_beat(roster, slow)
            payload = bus.payload or {}
            now = set(payload.get("committed_units") or [])
            if payload.get("unit_splits") and refined_at is None:
                refined_at = beat_no
            if beat.rows is None:
                assert held <= now, (
                    f"beat {beat_no} lost banked units {sorted(held - now)} — a "
                    "refinement must never un-plan a unit that is already banked"
                )
                held = now
                continue
            # The publishing beat promotes: the serving bank must be everything
            # that was held plus whatever this beat added.
            assert held <= set(payload.get("served_units") or [])
            break
        assert refined_at is not None, "the specimen must actually refine a slot"

    @pytest.mark.asyncio
    async def test_every_virtual_question_is_read_exactly_once_across_the_build(
        self, beats
    ):
        """No skipped units, no double-counted ones.

        The census sums over chunks, so a question read twice inflates it and a
        question never read deflates it. Refinement's whole safety argument is
        that ``bucket_of`` mod a multiple is a refinement — this is that argument
        measured on the running loop rather than asserted about the arithmetic.
        """
        run_beat, bus = beats
        roster = _roster()
        slow = _vm_ids_in_slot(roster, 0) | _vm_ids_in_slot(roster, 1)

        read: list[str] = []
        for _ in range(12):
            beat = await run_beat(roster, slow)
            for unit in beat.db.completed:
                read.extend(unit)
            if beat.rows is not None:
                break
        # Units banked in an earlier beat are not re-read, so a duplicate here is
        # a real double-read rather than a retry.
        assert len(read) == len(set(read)), "a question was read twice"
        assert set(read) == {str(row.vm_id) for row in roster}, (
            "every question in the population must be read"
        )


# =============================================================================
# 3. NOTHING IS WAIVED
# =============================================================================


class TestNothingIsWaived:
    @pytest.mark.asyncio
    async def test_a_single_question_that_cannot_be_read_is_never_skipped(self, beats):
        """The honest dead end, and the one this design must not paper over.

        A slot holding ONE virtual question cannot be refined — ``plan_units``
        never splits a ``vm_id``, and a chunk that fits by splitting one would be
        a chunk that is wrong. So: the slot is not dropped, the generation never
        completes, nothing is published, and the ledger says ``atomic`` rather
        than falling silent (gotcha #53). A build stuck at 7 of 8 with a named
        blocker is the correct state; 8 of 8 with a question quietly missing is
        ``PARTIAL_GENERATION_PUBLISHED``.
        """
        run_beat, bus = beats
        # One market, alone in its slot, that no bound can read.
        roster = _roster()
        lonely = str(roster[0].vm_id)
        # Give the lonely question its own slot by refusing every other question
        # in that slot a place in the population.
        index = sf.bucket_of(lonely, BUCKETS)
        roster = [
            row
            for row in roster
            if str(row.vm_id) == lonely
            or sf.bucket_of(str(row.vm_id), BUCKETS) != index
        ]
        slow = {lonely}

        atomic_seen = False
        for _ in range(8):
            # Past the whole beat window, so no bound this build can derive — and
            # no refinement, since there is nothing to divide — can read it.
            beat = await run_beat(roster, slow, slow_ms=WINDOW_MS * 4)
            assert beat.rows is None, "an unreadable question must not publish"
            atomic_seen = atomic_seen or any(
                name.startswith("staged:unit_split:atomic:")
                for name in beat.runner.ledger.stages
            )
        assert atomic_seen, "the blocker must be named in the ledger"
        payload = bus.payload or {}
        assert set(payload.get("planned_units") or []) - set(
            payload.get("committed_units") or []
        ), "the unreadable slot is still planned and still unbanked"
        # ...and the rest of the population was banked meanwhile.
        assert _banked(bus) == len(payload.get("planned_units") or []) - 1


# =============================================================================
# 4. THE BANK — 31 units that must survive this change
# =============================================================================


class TestTheBankIsPreserved:
    def test_a_banked_slot_is_never_refined(self):
        """The one way this change could destroy the bank, refused at the source.

        A refinement removes its parent slot from the plan. If the parent were
        BANKED, ``retain_planned_units`` would find a committed unit the plan no
        longer contains and — correctly, because a fold cannot be inverted —
        throw the WHOLE bank away, serving one included. So a banked chunk is
        never refined, and the refusal is a named outcome rather than a silent
        no-op.
        """
        roster = _roster()
        chunks = sf.plan_units(roster, buckets=BUCKETS)
        cursor = sf.new_staged_cursor(
            population_version="q268",
            input_fingerprint="fp",
            generation_fingerprint="gen",
            owner="test:1",
            generation=1,
        )
        cursor = sf.advance(
            cursor, chunks[0].key, [], owner="test:1", lease_expires_at=0.0
        )
        refined, outcome = sf.refine_unit(cursor, chunks[0], factor=4)
        assert outcome == sf.SPLIT_BANKED
        assert refined.unit_splits == {}

    def test_refining_one_slot_leaves_every_other_banked_unit_planned(self):
        """The 31, concretely: a refinement must not drop a single one of them.

        This is the production carry-over question. The banked slots keep their
        keys because a key is ``(buckets, index)`` and neither moves for a slot
        nobody refined.
        """
        roster = _roster()
        base = sf.plan_units(roster, buckets=BUCKETS)
        cursor = sf.new_staged_cursor(
            population_version="q268",
            input_fingerprint="fp",
            generation_fingerprint="gen",
            owner="test:1",
            generation=1,
        )
        for chunk in base[2:]:
            cursor = sf.advance(
                cursor, chunk.key, [], owner="test:1", lease_expires_at=0.0
            )
        banked_before = set(cursor.committed_units)

        refined_plan = sf.plan_units(
            roster, buckets=BUCKETS, refinements={sf.slot_ref(base[0]): 4}
        )
        kept, dropped = sf.retain_planned_units(cursor, refined_plan)
        assert dropped == ()
        assert set(kept.committed_units) == banked_before

    def test_a_cursor_written_before_this_change_decodes_with_no_learning_and_no_loss(
        self,
    ):
        """Additive and optional, like CAL-P078's serving bank.

        The cursor on disk right now carries 31 units and neither new field. It
        must decode with its bank intact and both maps empty — "this build has
        not measured a slot cancelling yet" — so the deploy costs no units and
        opens no dark window.
        """
        roster = _roster()
        chunks = sf.plan_units(roster, buckets=BUCKETS)
        cursor = sf.new_staged_cursor(
            population_version="q268",
            input_fingerprint="fp",
            generation_fingerprint="gen",
            owner="test:1",
            generation=1,
        )
        cursor = sf.advance(
            cursor, chunks[0].key, [], owner="test:1", lease_expires_at=0.0
        )
        legacy = cursor.as_payload()
        legacy.pop("unit_cancels")
        legacy.pop("unit_splits")

        decoded, action, _reason = sf.decode_staged_cursor_detailed(
            legacy,
            expected_population_version="q268",
            expected_input_fingerprint="fp",
            expected_generation_fingerprint="gen",
            owner="test:1",
            generation=1,
            now=0.0,
        )
        assert action == "resume"
        assert decoded.committed_units == cursor.committed_units
        assert decoded.unit_cancels == {}
        assert decoded.unit_splits == {}


# =============================================================================
# 5. THE PARTITION — why a refined plan is the same census
# =============================================================================


class TestRefinementIsExact:
    def test_children_partition_their_parent_and_touch_nothing_else(self):
        roster = _roster(400)
        base = sf.plan_units(roster, buckets=BUCKETS)
        ref = sf.slot_ref(base[0])
        fine = sf.plan_units(roster, buckets=BUCKETS, refinements={ref: 4})

        children = [chunk for chunk in fine if chunk.buckets != BUCKETS]
        assert children, "the slot was cut"
        assert {vm for chunk in children for vm in chunk.vm_ids} == set(base[0].vm_ids)
        # Disjoint: a question in two children is a question counted twice.
        seen: set[str] = set()
        for chunk in children:
            assert not (seen & set(chunk.vm_ids))
            seen |= set(chunk.vm_ids)
        # Every other slot is byte-for-byte the slot it was.
        untouched = {chunk.key: chunk.vm_ids for chunk in fine if chunk.buckets == BUCKETS}
        assert untouched == {chunk.key: chunk.vm_ids for chunk in base[1:]}

    def test_a_vm_id_is_never_split_by_a_refinement(self):
        """The dependency every census sum rests on (:func:`plan_units`).

        A grouped question's markets must stay in one chunk, or two chunks each
        compute their own view of it and ``COUNT(DISTINCT ...)`` double-counts.
        """
        roster = [
            types.SimpleNamespace(
                market_id=i, source="kalshi", vm_id=f"g:{i % 12}", is_grouped=True
            )
            for i in range(1, 121)
        ]
        base = sf.plan_units(roster, buckets=BUCKETS)
        fine = sf.plan_units(
            roster,
            buckets=BUCKETS,
            refinements={sf.slot_ref(chunk): 4 for chunk in base},
        )
        homes: dict[str, str] = {}
        for chunk in fine:
            for vm in chunk.vm_ids:
                assert vm not in homes
                homes[vm] = chunk.key
        assert len(homes) == 12

    def test_the_merged_census_is_the_same_under_a_refined_plan(self):
        """The number a reader sees does not move because a slot was cut.

        Census columns are chunk-local ``COUNT``s that the merge SUMS, so the
        claim "a refined plan is the same census" is only true if the children
        partition the parent — which is what this measures, through the real
        merge rather than around it.
        """
        def rows_for(chunk):
            # One bucket row per chunk carrying its own mass and its own census.
            # Every quantity is a per-QUESTION property summed over the chunk —
            # which is what the real statement emits, and the only shape for
            # which "the same census" is even a well-posed claim.
            winners = sum(1 for vm in chunk.vm_ids if int(vm.split(":")[1]) % 2 == 0)
            return [
                types.SimpleNamespace(
                    bucket_idx=0,
                    source="kalshi",
                    category="sports",
                    price_moved=False,
                    is_nonexclusive_bundle=False,
                    n=len(chunk.vm_ids),
                    winners=winners,
                    sum_prob=0.5 * len(chunk.vm_ids),
                    sum_sq_err=0.25 * len(chunk.vm_ids),
                    avg_prob=0.5,
                    published_questions=len(chunk.vm_ids),
                )
            ]

        roster = _roster(400)
        base = sf.plan_units(roster, buckets=BUCKETS)
        fine = sf.plan_units(
            roster, buckets=BUCKETS, refinements={sf.slot_ref(base[0]): 4}
        )
        census = ("published_questions",)
        merged_base = sf.merge_futures_rows(
            [rows_for(chunk) for chunk in base], census_columns=census
        )
        merged_fine = sf.merge_futures_rows(
            [rows_for(chunk) for chunk in fine], census_columns=census
        )
        assert len(merged_base) == len(merged_fine) == 1
        for name in ("n", "winners", "sum_prob", "sum_sq_err", "published_questions"):
            assert getattr(merged_base[0], name) == getattr(merged_fine[0], name), name


# =============================================================================
# 6. THE RULES THEMSELVES
# =============================================================================


class TestTheRules:
    def test_the_split_factor_is_a_multiple_of_a_measurement(self):
        # 800 s observed against an 80 s measured unit: ten units' worth.
        assert sf.split_factor(800_000, 80_000) == 10
        # Capped, because the observation is a floor and one split is not asked
        # to be the last word.
        assert sf.split_factor(10_000_000, 80_000) == sf.STAGED_UNIT_SPLIT_MAX_FACTOR
        # Never below a real refinement.
        assert sf.split_factor(10_000, 80_000) == 2

    def test_with_no_measured_unit_cost_the_smallest_refinement_is_taken(self):
        """Ruling 075: no measurement, no invented number — the minimum step."""
        assert sf.split_factor(800_000, 0) == 2
        assert sf.split_factor(800_000, None) == 2
        assert sf.split_factor(None, None) == 2

    def test_the_attempt_order_defers_only_slots_that_have_cancelled(self):
        roster = _roster()
        chunks = sf.plan_units(roster, buckets=BUCKETS)
        cursor = sf.new_staged_cursor(
            population_version="q268",
            input_fingerprint="fp",
            generation_fingerprint="gen",
            owner="test:1",
            generation=1,
        )
        assert sf.attempt_order(chunks, cursor) == tuple(chunks), (
            "with nothing recorded the order is the plan's, unchanged"
        )
        cursor = sf.note_unit_cancelled(cursor, sf.slot_ref(chunks[0]))
        order = sf.attempt_order(chunks, cursor)
        assert order[-1].key == chunks[0].key
        assert [chunk.key for chunk in order[:-1]] == [
            chunk.key for chunk in chunks[1:]
        ]
        # Every unit is still there. A deferral is not a filter.
        assert len(order) == len(chunks)

    def test_the_count_is_what_the_split_threshold_reads(self):
        roster = _roster()
        chunks = sf.plan_units(roster, buckets=BUCKETS)
        cursor = sf.new_staged_cursor(
            population_version="q268",
            input_fingerprint="fp",
            generation_fingerprint="gen",
            owner="test:1",
            generation=1,
        )
        ref = sf.slot_ref(chunks[0])
        for expected in range(1, STAGED_UNIT_SPLIT_AFTER + 1):
            cursor = sf.note_unit_cancelled(cursor, ref)
            assert cursor.unit_cancels[ref] == expected

    def test_a_refinement_map_the_planner_cannot_honour_is_dropped_entry_by_entry(self):
        clean = sf.sanitize_refinements(
            {
                "8:0": 4,           # kept
                "8:0:extra": 4,     # unparseable
                "nonsense": 2,      # unparseable
                "8:1": 1,           # not a refinement
                "8:2": "4",         # not an int
                "12:3": 4,          # not a partition reachable from 8
                "8:3": 10**9,       # past the ceiling
            },
            base_buckets=BUCKETS,
        )
        assert clean == {"8:0": 4}

    def test_a_refinement_chain_cannot_outrun_its_ceiling(self):
        roster = _roster()
        chunks = sf.plan_units(roster, buckets=BUCKETS)
        cursor = sf.new_staged_cursor(
            population_version="q268",
            input_fingerprint="fp",
            generation_fingerprint="gen",
            owner="test:1",
            generation=1,
        )
        _cursor, outcome = sf.refine_unit(cursor, chunks[0], factor=4, max_buckets=8)
        assert outcome == sf.SPLIT_TOO_DEEP

    def test_resolving_a_slot_walks_the_chain_to_the_finest_partition_holding_it(self):
        vm = "m:7"
        first = sf.bucket_of(vm, 8)
        second = sf.bucket_of(vm, 32)
        assert sf.resolve_slot(vm, buckets=8, refinements={}) == (8, first)
        assert sf.resolve_slot(vm, buckets=8, refinements={f"8:{first}": 4}) == (
            32,
            second,
        )
        # Two levels: the child of the child.
        chain = {f"8:{first}": 4, f"32:{second}": 4}
        assert sf.resolve_slot(vm, buckets=8, refinements=chain) == (
            128,
            sf.bucket_of(vm, 128),
        )

    def test_a_refinement_is_a_refinement_at_every_level(self):
        """``(h mod 128m) mod 128 == h mod 128`` — the whole safety argument."""
        for i in range(500):
            vm = f"m:{i}"
            for factor in (2, 3, 4, 16):
                assert sf.bucket_of(vm, BUCKETS * factor) % BUCKETS == sf.bucket_of(
                    vm, BUCKETS
                )

    def test_cancellation_memory_is_pruned_to_the_plan_but_keeps_split_parents(self):
        roster = _roster()
        chunks = sf.plan_units(roster, buckets=BUCKETS)
        cursor = sf.new_staged_cursor(
            population_version="q268",
            input_fingerprint="fp",
            generation_fingerprint="gen",
            owner="test:1",
            generation=1,
        )
        parent = sf.slot_ref(chunks[0])
        cursor = sf.note_unit_cancelled(cursor, parent)
        cursor = sf.note_unit_cancelled(cursor, "8:999999")  # a slot of no plan
        cursor, _ = sf.refine_unit(cursor, chunks[0], factor=4)
        fine = sf.plan_units(roster, buckets=BUCKETS, refinements=cursor.unit_splits)

        pruned = sf.prune_unit_cancels(cursor, fine)
        assert parent in pruned.unit_cancels, (
            "the evidence that produced a refinement outlives the slot it cut"
        )
        assert "8:999999" not in pruned.unit_cancels
