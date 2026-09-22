"""#6599 follow-on: the rebuild's RECOVERY half, reproduced locally and deterministically.

CAL-P1301 (#6599) shipped two halves. The production after-check at 04:52Z
(verdict + gauge table on #6599 comment 5708848156) found the first PASSES and
the second does NOT follow: the deferral works, and the build still never
reaches 128 of 128.

**This file is the local reproduction of why, and it is a REPRODUCTION, not a
guard.** Every test here asserts the CURRENT, DEFECTIVE behaviour so the cause is
pinned in the tree everyone reads rather than argued in prose. A fix changes
these assertions; that is the point of them.

The rig is the one from ``test_calibration_stuck_head_deferral_6599`` — the real
``_run_staged_futures``, the real planner, the real cursor codec, a fake database
whose cost is a property of the QUESTIONS in a chunk — re-used here rather than
re-written, because a toy scheduler cannot reproduce a defect that lives in the
composition of the window bound, the cancellation budget and the cursor codec.

WHAT IS REPRODUCED (all measured, none reasoned):

0. ``TestTheProductionRegimeBeatLevelSlowness`` — **THE ONE THAT MATCHES
   PRODUCTION.** The after-check's gauge row is beat-level slowness, not two
   pathological slots: zero completions, the whole 2-cancellation budget burned,
   terminal ``cancelled``, and slots never attempted before cancelling on FIRST
   contact (one after 21 minutes). Reproduced beat for beat, it yields a LAW:

       the first refinement cannot land before beat ``N/2 + 1``

   because ``refine_unit`` needs a slot's SECOND cancellation while
   ``attempt_order`` sorts ascending on cancellations, so no slot earns a second
   until every slot has earned a first — at two slots a beat. Measured 8 → 5,
   16 → 9, 32 → 17. **At 128 units that is beat 65, hourly, against resets
   observed every ~15–16 beats, so no slot is EVER cut.** The after-check
   reasoned its way to ~64 h; this file runs it, with a control beside it.

   The deferral is what makes this so, and it is correct and live: by sending a
   cancelled slot to the back it also sends the evidence that would refine it to
   the back. The fix is not to revert #6599.

   Non-vacuity is measured, not asserted: replacing ``attempt_order`` with the
   pre-#6599 plan order kills all four of these tests.

1. ``test_the_build_grinds_to_completion_without_refinement_ever_running`` — the
   ADJACENT regime, kept because the two need DIFFERENT fixes and telling them
   apart is the whole diagnostic question. Here the beat ends on the WINDOW
   rather than on the cancellation budget.

   #6599 refines a slot on its SECOND cancellation. But a unit that
   is slow and still *completable* does not supply one: the armed bound ratchets
   up with ``worst_unit_ms``, so the unit is BANKED — after eating most of the
   beat window. At 16 slow units no slot ever reaches a second cancellation, so
   ``refine_unit`` is never called once and the build still finishes, purely by
   grinding one unit per beat. Refinement is therefore not what recovers this
   build, and cannot be relied on to.

   Measured across sizes, refinement arrives late or not at all — 8 units: first
   cut at beat 7 of 9; 16: never; 32: beat 27 of 30; 64: beat 51 of 61. It is
   always near the END, which is precisely when it can no longer help. #6599's
   premise was a beat ending on ``window_stop:units_cancelling``; once deferral
   works, beats end on the WINDOW instead, and the trigger refinement hangs off
   is pulled rarely or never.

2. ``test_the_build_needs_about_one_beat_per_unit`` — the consequence. One slow
   unit per window means completion takes ~N beats for N units. Measured:
   8 slots → 9 beats, 16 → 14, 32 → 30, 64 → 61.

3. ``test_an_invalidation_shorter_than_the_build_never_completes`` — the
   livelock. The cursor is refused wholesale on a population change, so a build
   needing ~N beats and invalidated every K < N beats loses its bank every era
   and never publishes. Measured at 32 units: K=25/15/10/5 all run 120 beats with
   zero splits and a bank that never survives.

4. ``test_the_same_build_completes_when_the_cursor_outlives_it`` — THE CONTROL,
   and the reason 3 is not vacuous. Identical population, identical slowness,
   invalidation period LONGER than the build: it completes. So 3 is a statement
   about the period, not about a rig that cannot finish anything.

WHAT THIS FILE DELIBERATELY DOES NOT CLAIM. It reproduces the LIVENESS defect —
that the build's own recovery mechanism cannot fire on this cadence — and takes
no position whatever on WHY a production beat is slow. A lock, a plan flip and a
vacuum are all consistent with everything measured here, and separating those is
measurement-lane work. Nothing in this file is evidence for any of them.
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
    STAGED_UNIT_SPLIT_AFTER,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)

#: One ordinary virtual question. Eight of them is the ~64 s unit the production
#: plan carries (72,202 ms measured mean over completions).
HEALTHY_VM_MS = 8_000
#: A question in a SLOW slot. Eight is 800 s — most of a beat window, but inside
#: any bound the build ratchets up to, which is exactly the regime this file is
#: about: slow enough to starve the beat, not slow enough to cancel twice.
SLOW_VM_MS = 100_000
#: One beat's window. ~22 min, the production order.
WINDOW_MS = 1_350_000
VMS_PER_SLOT = 8

#: The genuine repair predicate, captured at import so the BEFORE arm can be
#: turned back ON again within one test (see the fixture).
_REAL_PACKING = sf.packing_split_factor


class _StatementCancelled(Exception):
    """Postgres cancelling at its own backstop; the message is what it emits."""


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
        population_version="q268",
        owner="test:1",
        generation=1,
        input_fingerprint="fp",
        phases=(PHASE_FUTURES,),
    )


class _Runner:
    """One beat. The clock is advanced by the database (gotcha #44)."""

    def __init__(
        self,
        *,
        window_ms: int,
        prior_unit_ms: int | None,
        generation: int,
        buckets: int,
    ):
        self.ledger = _ledger(
            window_ms=window_ms, unit_ms=prior_unit_ms, buckets=buckets
        )
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
    """Cost is a property of the QUESTIONS asked about, never of the call order.

    The order is exactly what #6599 moves, so a cost tied to position would
    follow the reordering around and measure nothing.
    """

    def __init__(self, runner: _Runner, roster, slow_vm_ids, *, beat_is_slow=False):
        self.runner = runner
        self.roster = roster
        self.slow = set(slow_vm_ids)
        #: BEAT-level slowness — a lock, a plan flip, a vacuum. Every unit
        #: cancels regardless of which questions it holds, which is the
        #: production shape at 04:37:55Z: slots never attempted before cancelled
        #: on first contact, one of them after 21 minutes, zero banked. Modelled
        #: as a property of the BEAT because that is what the evidence says it
        #: is; this file takes no position on what causes it.
        self.beat_is_slow = bool(beat_is_slow)
        self.by_market = {int(r.market_id): str(r.vm_id) for r in roster}
        self.completed: list[frozenset[str]] = []
        self.cancelled: list[frozenset[str]] = []
        self._gen_done = False

    def cost_of(self, vm_ids) -> int:
        return sum(SLOW_VM_MS if v in self.slow else HEALTHY_VM_MS for v in set(vm_ids))

    async def execute(self, _sql, params=None):
        if not self._gen_done:
            self._gen_done = True
            return types.SimpleNamespace(all=lambda: self.roster)
        market_ids = list((params or {}).get(pc.VM_ROSTER_MARKET_IDS_PARAM) or ())
        vm_ids = frozenset(self.by_market[int(m)] for m in market_ids)
        cost = self.cost_of(vm_ids)
        armed = self.runner.armed[-1] if self.runner.armed else 10**9
        window_left = self.runner.ledger.remaining_ms(
            elapsed_ms=self.runner.elapsed_ms()
        )
        cap = min(armed, window_left)
        if self.beat_is_slow or cost > cap:
            self.runner.advance(cap)
            self.cancelled.append(vm_ids)
            raise _StatementCancelled("canceling statement due to statement timeout")
        self.runner.advance(cost)
        self.completed.append(vm_ids)
        return types.SimpleNamespace(all=lambda: [])

    async def rollback(self) -> None:
        return None


def _roster(n: int):
    return [
        types.SimpleNamespace(
            market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False
        )
        for i in range(1, n + 1)
    ]


def _slots(roster, buckets: int) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for row in roster:
        out.setdefault(sf.bucket_of(str(row.vm_id), buckets), set()).add(str(row.vm_id))
    return out


class _Bus:
    """The durable cursor across beats, read and written by the REAL codec."""

    def __init__(self):
        self.payload = None

    async def load(self, **kw):
        return sf.decode_staged_cursor_detailed(
            self.payload,
            expected_population_version=kw["population_version"],
            expected_input_fingerprint=kw["input_fingerprint"],
            expected_generation_fingerprint=kw["generation_fingerprint"],
            owner=kw["owner"],
            generation=kw["generation"],
            now=0.0,
            legacy_input_fingerprint=kw.get("legacy_input_fingerprint"),
        )

    async def save(self, cursor, terminal=None, banks_a_unit=True):
        self.payload = cursor.as_payload()
        self.payload["terminal"] = terminal or self.payload.get("terminal")
        return True


class _Run:
    """What N beats over one durable cursor did."""

    def __init__(self):
        self.beats = 0
        self.completed_at: int | None = None
        self.first_split_beat: int | None = None
        self.max_split_count = 0
        self.max_cancel_count = 0
        self.max_banked = 0
        self.per_beat_banked: list[int] = []
        self.per_beat_cancelled: list[int] = []
        #: How many slots carry a recorded cancellation after each beat. This is
        #: the clock the split threshold actually runs against.
        self.per_beat_cancel_entries: list[int] = []
        #: The most virtual questions this build ever had banked at once, reset
        #: at each invalidation the way the cursor itself is.
        #:
        #: **Units are not a measure of progress once a plan can be refined**
        #: and this is the number that is. Cutting a slot raises the unit count
        #: without doing any work, so "21 of a 30-unit plan" and "9 of a 16-unit
        #: plan" cannot be compared — the underlying QUESTIONS can, because a
        #: partition conserves them. Every arm below that compares the repair
        #: against its absence compares this.
        self.max_banked_vms = 0


@pytest.fixture
def drive(monkeypatch):
    """Drive the real beat loop over one durable cursor. Returns a callable.

    ``packing_splits=False`` is the BEFORE: :func:`packing_split_factor`, the
    #6599 repair, stubbed to its own "no cut is owed" answer, which is the loop
    exactly as it stood when this file was written. Sections 1 and 3 reproduce
    the defect on that arm and assert the repair on the live one, in the same
    test — the reproduction is preserved rather than refreshed from a tree that
    no longer has the defect in it (notice 50).
    """

    async def _drive(
        *,
        buckets,
        slow_slots,
        max_beats,
        reset_every=None,
        window_ms=WINDOW_MS,
        beat_is_slow=False,
        packing_splits=True,
    ):
        roster = _roster(buckets * VMS_PER_SLOT)
        slots = _slots(roster, buckets)
        slow: set[str] = set()
        for index in sorted(slots)[:slow_slots]:
            slow |= slots[index]

        bus = _Bus()
        monkeypatch.setattr(cmb, "load_staged_cursor", bus.load)
        monkeypatch.setattr(cmb, "save_staged_cursor", bus.save)
        monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
        monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", buckets)
        monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
        # Set both ways round on EVERY call: the loop imports this predicate
        # inside ``_run_staged_futures``, and ``monkeypatch`` is function-scoped,
        # so an arm patched mid-test otherwise leaks into every later arm of the
        # same test and reports the BEFORE as the AFTER.
        monkeypatch.setattr(
            sf,
            "packing_split_factor",
            _REAL_PACKING if packing_splits else (lambda *_a, **_kw: 0),
        )

        out = _Run()
        banked_vms: set[str] = set()
        for beat_no in range(1, max_beats + 1):
            runner = _Runner(
                window_ms=window_ms,
                prior_unit_ms=HEALTHY_VM_MS * VMS_PER_SLOT,
                generation=beat_no,
                buckets=buckets,
            )
            if reset_every and beat_no > 1 and (beat_no - 1) % reset_every == 0:
                # A GENUINE invalidation: the population this build is over has
                # changed, so the real codec refuses the carried cursor whole.
                era = (beat_no - 1) // reset_every
                runner.population_version = f"q268+{era}"
                runner.ledger.population_version = f"q268+{era}"
                # The cursor is refused whole, so the questions it had banked are
                # gone with it — counting them across an invalidation would credit
                # the build with work it has to do again.
                banked_vms = set()
            db = _Db(runner, roster, slow, beat_is_slow=beat_is_slow)
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

            payload = bus.payload or {}
            cancels = payload.get("unit_cancels") or {}
            splits = payload.get("unit_splits") or {}
            out.beats = beat_no
            out.per_beat_banked.append(len(db.completed))
            out.per_beat_cancelled.append(len(db.cancelled))
            out.per_beat_cancel_entries.append(len(cancels))
            if cancels:
                out.max_cancel_count = max(out.max_cancel_count, max(cancels.values()))
            if splits:
                out.max_split_count = max(out.max_split_count, len(splits))
                if out.first_split_beat is None:
                    out.first_split_beat = beat_no
            out.max_banked = max(
                out.max_banked,
                len(payload.get("committed_units") or []),
                len(payload.get("served_units") or []),
            )
            for vms in db.completed:
                banked_vms |= vms
            out.max_banked_vms = max(out.max_banked_vms, len(banked_vms))
            if rows is not None:
                out.completed_at = beat_no
                break
        return out

    return _drive


# =============================================================================
# 0. PRODUCTION'S OWN REGIME — the beat is slow, and the split is out of reach
# =============================================================================


class TestTheProductionRegimeBeatLevelSlowness:
    """The shape the after-check actually read, reproduced beat for beat.

    At 04:37:55Z on heavy v38: ``units_completed_this_beat`` 0,
    ``units_cancelled`` 2 (the whole budget), terminal ``cancelled``, and slots
    ``128:3`` / ``128:4`` — never attempted before — cancelling on FIRST contact,
    one after 21 minutes. So the slowness is not a property of two pathological
    slots; it belongs to the beat.
    """

    @pytest.mark.asyncio
    async def test_every_beat_burns_the_budget_banks_nothing_and_enrols_two_more(
        self, drive
    ):
        """The production gauge row, reproduced exactly.

        Two cancellations, zero completions, nothing banked, and ``unit_cancels``
        two entries longer than the beat before. The reorder changes WHICH two
        slots burn the budget, never THAT it is burned.
        """
        run = await drive(buckets=16, slow_slots=0, max_beats=3, beat_is_slow=True)

        assert run.per_beat_banked == [0, 0, 0], (
            "the production shape banks nothing at all; this rig must too, or it "
            "is reproducing a different defect"
        )
        assert run.per_beat_cancelled == [
            2,
            2,
            2,
        ], "each beat must burn exactly STAGED_UNIT_MAX_CANCELLATIONS and stop"
        assert run.per_beat_cancel_entries == [2, 4, 6], (
            "and each beat enrols two MORE slots into unit_cancels — which is the "
            "clock the split threshold is really running against"
        )

    @pytest.mark.asyncio
    async def test_the_first_split_cannot_land_before_half_the_plan_has_cancelled(
        self, drive
    ):
        """THE LAW, measured rather than argued: first split at N/2 + 1 beats.

        ``refine_unit`` needs a SECOND cancellation on one slot, and
        ``attempt_order`` sorts ascending on recorded cancellations — so no slot
        can earn a second until every slot has earned a first. At two slots per
        beat that is exactly ``N/2 + 1`` beats, measured here at 8 → 5, 16 → 9
        and 32 → 17.

        **At the production plan of 128 units that is beat 65, and a beat is
        hourly.** The after-check reasoned its way to ~64 h; this runs it.

        The deferral is what makes this so: it is correct, it is live, and by
        sending a cancelled slot to the back it also sends the evidence that
        would refine it to the back. The fix must not be to revert it.
        """
        for buckets in (8, 16, 32):
            run = await drive(
                buckets=buckets, slow_slots=0, max_beats=60, beat_is_slow=True
            )
            assert run.first_split_beat == buckets // 2 + 1, (
                f"{buckets} units: first cut landed at beat {run.first_split_beat}, "
                f"expected {buckets // 2 + 1} — one full pass at two slots a beat"
            )

    @pytest.mark.asyncio
    async def test_an_invalidation_before_that_beat_no_longer_costs_the_cut(
        self, drive
    ):
        """The permanent livelock — **ENDED by CAL-P1304, and this measures it.**

        As written for CERT-3051's tree this asserted the opposite, and it was
        right then: 16 units need 9 beats to reach the first cut, an era of 5
        wiped ``unit_cancels`` back to empty, and no slot ever reached two — not
        late, NEVER. Production's ring was the same inequality, first cut
        possible at beat 65 against resets every ~15–16 beats.

        :func:`~app.utils.calibration_staged_futures.carry_refinement` carries
        the cancellation evidence across the boundary the bank cannot cross, and
        the livelock closes completely on this shape: the cut lands on **beat
        9** — the same beat the unbroken-cursor control below reaches — so an
        invalidation now costs the refinement NOTHING. It still costs the bank,
        which is a different and unavoidable price.

        The control that follows this one stubs the carry back out and shows the
        old ``None``, so the difference cannot be read as anything else.
        """
        run = await drive(
            buckets=16, slow_slots=0, max_beats=60, reset_every=5, beat_is_slow=True
        )

        assert run.first_split_beat == 9, (
            "the era no longer delays the cut at all; got "
            f"{run.first_split_beat}"
        )
        assert run.max_cancel_count >= STAGED_UNIT_SPLIT_AFTER, (
            "a slot reaching two cancellations at once is the precondition the "
            "whole refinement hangs off, and it was unreachable across eras"
        )

    @pytest.mark.asyncio
    async def test_without_the_carry_that_same_era_never_cuts_a_slot(
        self, drive, monkeypatch
    ):
        """THE CONTROL for the repair: the pre-CAL-P1304 decoder, same era.

        ``carry_refinement`` handing back the blank it was given is byte-for-byte
        what the decoder did before, so this is the livelock exactly as
        CERT-3051 read it — and the only difference between the two tests is
        that one line.
        """
        monkeypatch.setattr(sf, "carry_refinement", lambda blank, raw: blank)

        run = await drive(
            buckets=16, slow_slots=0, max_beats=60, reset_every=5, beat_is_slow=True
        )

        assert run.first_split_beat is None and run.max_split_count == 0, (
            "not one slot is cut in 60 beats — the state the repair ends"
        )
        assert run.max_cancel_count < STAGED_UNIT_SPLIT_AFTER

    @pytest.mark.asyncio
    async def test_the_cut_does_arrive_when_the_cursor_outlives_the_pass(self, drive):
        """THE CONTROL. Same population, same slowness, longer-lived cursor.

        Without this the test above shows only that the rig never splits. With
        it, the single difference is the invalidation period.
        """
        run = await drive(
            buckets=16, slow_slots=0, max_beats=60, reset_every=40, beat_is_slow=True
        )

        assert run.first_split_beat == 9, (
            "with the cursor outliving one full pass the cut lands on schedule; "
            f"got {run.first_split_beat}"
        )


# =============================================================================
# 1. THE ADJACENT REGIME — a slow unit BANKS, so the trigger is never pulled
# =============================================================================


class TestRefinementIsInertWhenBeatsEndOnTheWindow:
    @pytest.mark.asyncio
    async def test_the_build_grinds_to_completion_without_refinement_ever_running(
        self, drive
    ):
        """#6599's recovery half never runs, and the build finishes anyway.

        Refinement hangs off a SECOND cancellation of one slot. A unit that is
        slow but completable does not supply one: the armed bound is raised by
        ``worst_unit_ms`` as big units succeed, so the unit is banked — after
        eating most of the window.

        So what finishes this build is not the recovery mechanism; it is one unit
        per beat, sixteen times. That distinction is the whole point: a mechanism
        that does not fire cannot be what rescues production either, and the
        after-check found exactly that — deferral passes, recovery does not
        follow.

        Reproduced without a database and without any claim about WHY a unit is
        slow.

        **The BEFORE is preserved and the repair is asserted beside it.** The
        third clause below — not one slot cut in the whole build — is the
        sentence #6599 exists to falsify, so the repair reddens it by
        construction. It is kept as the ``packing_splits=False`` arm, which is
        this loop as it stood when the defect was filed, rather than deleted or
        re-snapshotted from a tree that no longer contains the defect
        (notice 50). What the live arm adds is that the cut which now happens
        cannot have come from the cancellation path: there is still not one
        cancellation anywhere in the build.
        """
        before = await drive(
            buckets=16, slow_slots=16, max_beats=40, packing_splits=False
        )

        assert before.completed_at is not None, "the build does finish, by grinding"
        assert before.max_cancel_count < STAGED_UNIT_SPLIT_AFTER, (
            "a slot must cancel twice to be refined; across this whole build no "
            f"slot cancels more than {before.max_cancel_count} time(s)"
        )
        assert before.first_split_beat is None, (
            "not one slot is cut across the entire build — the refinement exists "
            "and is never reached, so it is not the recovery"
        )

        after = await drive(buckets=16, slow_slots=16, max_beats=40)

        assert after.max_cancel_count == 0, (
            "the repair must not be reached through a cancellation — if this "
            "build starts cancelling, the cut below is the OLD mechanism and "
            f"this test is measuring nothing new: {after.max_cancel_count}"
        )
        assert after.first_split_beat == 1, (
            "the slow success is evidence on the beat it is measured, not after "
            f"a quorum: {after.first_split_beat}"
        )
        assert after.completed_at is not None and (
            after.completed_at < before.completed_at
        ), (
            "and the build that cuts finishes sooner than the one that grinds: "
            f"{after.completed_at} vs {before.completed_at} beats"
        )

    @pytest.mark.asyncio
    async def test_the_beat_banks_about_one_unit_at_a_time(self, drive):
        """The throughput this leaves behind: ~1 unit per beat.

        One slow unit consumes most of the window, so the next one does not fit
        and the beat stops. That is the rate the whole build runs at, and it is
        what makes completion proportional to the unit count. The repair's whole
        claim is that this number moves, so the BEFORE is pinned on the arm that
        does not have it and the lift is asserted against that arm rather than
        against a constant somebody chose.
        """
        before = await drive(
            buckets=16, slow_slots=16, max_beats=40, packing_splits=False
        )

        banking_beats = [n for n in before.per_beat_banked if n]
        assert banking_beats, "the rig must bank something, or it measures nothing"
        assert max(before.per_beat_banked) <= 2, (
            f"a beat banked {max(before.per_beat_banked)} units; this regime is "
            "defined by one slow unit filling the window"
        )

        after = await drive(buckets=16, slow_slots=16, max_beats=40)

        assert max(after.per_beat_banked) > max(before.per_beat_banked), (
            "the pin is what the repair is for: "
            f"{max(after.per_beat_banked)} vs {max(before.per_beat_banked)} "
            "units in the best beat"
        )
        assert after.max_banked_vms == before.max_banked_vms, (
            "and it is the same work, re-partitioned — a repair that banked "
            "FEWER questions while banking more units would be counting its own "
            f"cuts: {after.max_banked_vms} vs {before.max_banked_vms}"
        )


# =============================================================================
# 2. THE CONSEQUENCE — completion costs about one beat per unit
# =============================================================================


class TestCompletionScalesWithThePopulation:
    @pytest.mark.asyncio
    async def test_the_build_needs_about_one_beat_per_unit(self, drive):
        """Doubling the population roughly doubles the beats to finish.

        8 → 9 beats and 16 → 14 here; 32 → 30 and 64 → 61 on the same rig, left
        out of CI for runtime. At the production plan of 128 units this is ~120
        beats, and a beat is hourly.

        Measured on the arm WITHOUT the #6599 packing cut, because the law being
        stated is the one that makes the defect a defect: with a fixed partition
        the build costs a beat per unit. The repair's job is to break that
        proportionality, and it does — which is why leaving it live here would
        quietly turn this into a test of the repair.

        **RE-BASED 2026-09-22 (CAL-P1335, #6868): 8 → 7, not 8 → 9.** The floor
        below is a REGIME sentinel, not a target — it exists so that a build
        which suddenly finishes in a fraction of a beat per unit is read as "the
        rig stopped measuring the defect" rather than as good news. CAL-P1335
        made the unit loop pass over a candidate too big for the remainder
        instead of ending the beat on it, so a beat now banks the smaller slots
        behind a refused one and the count fell by one beat in eight. That is a
        12.5% move with a named cause, which is exactly the kind this sentinel
        should NOT fire on; a drop to 4 or 2 is the kind it should. So the floor
        moves to the new measurement and keeps its margin, and the scaling
        assertion above it — the actual claim of this class — is untouched.
        """
        small = await drive(
            buckets=8, slow_slots=8, max_beats=40, packing_splits=False
        )
        large = await drive(
            buckets=16, slow_slots=16, max_beats=40, packing_splits=False
        )

        assert small.completed_at is not None, "the small build must finish"
        assert large.completed_at is not None, "the large build must finish"
        assert large.completed_at > small.completed_at, (
            "completion time must grow with the population — that growth is what "
            "eventually outruns the cursor's survival"
        )
        assert small.completed_at >= 7, (
            f"finished in {small.completed_at} beats for 8 units; if this ever "
            "drops far below one beat per unit the regime has changed and the "
            "rest of this file is measuring something else"
        )


# =============================================================================
# 3. THE LIVELOCK — an invalidation shorter than the build, and its control
# =============================================================================


class TestAnInvalidationShorterThanTheBuild:
    @pytest.mark.asyncio
    async def test_an_invalidation_shorter_than_the_build_never_completes(self, drive):
        """The bank is discarded every era, so the build never publishes.

        The cursor is refused wholesale on a population change — correctly, as
        far as the codec is concerned — and with it go every banked unit and
        every recorded cancellation. A build that needs ~N beats and is
        invalidated every K < N beats can never reach the end, no matter how
        many beats it is given.

        **And the #6599 repair does not fix this, which is the honest half.**
        The live arm below cuts from beat one and gets measurably further into
        the population each era — but an invalidation period shorter than the
        build it interrupts is a livelock about the PERIOD, and better packing
        shortens the build without ever making it shorter than eight beats. The
        repair is worth what it banks, not a claim that the page publishes.
        """
        before = await drive(
            buckets=16, slow_slots=16, max_beats=60, reset_every=8,
            packing_splits=False,
        )

        assert before.completed_at is None, (
            "the build must NOT complete — this is the reproduction of "
            "'the rebuild has never once reached 128 of 128 before a reset'"
        )
        assert before.max_split_count == 0, (
            "and no slot is ever cut across the whole run, so the recovery half "
            "cannot rescue it either"
        )

        after = await drive(buckets=16, slow_slots=16, max_beats=60, reset_every=8)

        assert after.completed_at is None, (
            "THE LIMIT: the repair does not publish a build whose invalidation "
            "period is shorter than it is, and a test that let this pass "
            f"silently would be selling one: completed at {after.completed_at}"
        )
        assert after.max_banked_vms > before.max_banked_vms, (
            "what it does buy is depth into the population before each reset: "
            f"{after.max_banked_vms} vs {before.max_banked_vms} questions"
        )

    @pytest.mark.asyncio
    async def test_the_same_build_completes_when_the_cursor_outlives_it(self, drive):
        """THE CONTROL. Same population, same slowness, longer-lived cursor.

        Without this the test above proves only that the rig cannot finish
        anything. With it, the difference between the two is the invalidation
        PERIOD and nothing else.
        """
        run = await drive(buckets=16, slow_slots=16, max_beats=60, reset_every=40)

        assert run.completed_at is not None, (
            "with an invalidation period longer than the build, the very same "
            "population completes — so the livelock is about the period"
        )
