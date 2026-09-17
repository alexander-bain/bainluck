"""#6599 defect 1: a slot that cannot fit a beat is cut on the proof, not on a quorum.

PILLAR: TRUTH. SHIP: /calibration can show a freshly rebuilt curve — today the
staged rebuild banks 1 of 128 units and has never reached 128.

**This file is a measurement first and a guard second, and the order matters.**
The candidate it exercises is the third one tried on this defect; the two before
it were refuted BY MEASUREMENT (calibration/1336, #6599 comment 5710621976) and
the reason this one is different is in the numbers below, not in its prose.

## The regime this is about, which is NEW as of #6775

Before #6775 the worst-unit ring was suppressed by a false refutation, so a beat
arrived with no measured basis at all, handed unit 1 the whole window, and spent
the SCRAPS on unit 2 — two cancellations a beat, which is the regime
``test_calibration_rebuild_recovery_reproduction_6599`` reproduces and the regime
the ``N/2 + 1`` law was measured in.

With the ring readable again the fence works, and that CHANGES THE ARITHMETIC OF
THE DEFECT rather than fixing it: ``_unit_fits_in_window`` refuses a second unit
once the carried mean no longer fits in what is left, so a beat records ONE
cancellation, not two. One full pass of ``attempt_order`` — which sorts ascending
on recorded cancellations, so no slot earns a second until every slot holds one —
therefore costs ``N`` beats rather than ``N/2``. At the production plan of 128,
the first refinement moves from beat 65 to beat 129. Hourly. Measured here at
8 → 9, 16 → 17, 32 → 33 (:class:`TestTheNewRegimeOneCancellationPerBeat`).

## What was already refuted, and is not rebuilt here

**Ordering.** calibration/1336 built the reserved re-attempt inside
``attempt_order`` (one explore + one exploit per beat, which is what a scheduling
policy on this loop can be) and measured ~80 regimes: first split beat went
5/9/17/33/65 → 2, and no regime completed that did not already complete, two
STOPPED completing, and production-scale banking went 122 → 105. Its counterexample
is structural: recovery needs ~N splits, each costing a cancellation, against a
budget of ``STAGED_UNIT_MAX_CANCELLATIONS`` per beat — an early FIRST split does
not move the LAST one. **Ordering cannot beat a per-beat budget bound over a
population**, and 1336's second finding is why it also costs: the first unit of a
beat carries the widest bound the beat ever arms, so a head-placed probe that
cancels costs the ENTIRE beat.

Both of those hold here unchanged, and this candidate is not an ordering change:
``attempt_order`` is untouched, every planned unit is still attempted every beat
in the same sequence, and the per-beat cancellation budget is unchanged.

## The candidate

``cancellation_is_conclusive``: a cancellation splits its slot IMMEDIATELY, rather
than waiting for a second, when both of these hold —

1. the bound came from the WINDOW (``deadline_bound_headroom_ceiling_ms``, the
   same discriminator #6775 gave ``_level_refuted_by_cancellation``), so the slot
   was handed everything the beat had and there is no tighter fence to blame; and
2. it ran longer than the longest unit this build has ever COMPLETED.

**This is a bounded refinement policy and NOT a proof about the slot's intrinsic
cost.** Those two conditions do not logically exclude a lock wait, a vacuum or a
plan flip — a new slow disturbance can exceed any prior maximum, and the prior
maximum is the only evidence the build holds. The policy is justified by what a
wrong answer COSTS, and that cost is measured in the real loop by
:class:`TestATransientDelayIsNotExcludedAndIsBoundedWhenItHappens`, not asserted.

Nothing is raised: not the statement timeout, not the cancellation budget, not
the refinement ceiling, not a validity rule. ``STAGED_UNIT_SPLIT_AFTER`` still
governs every other cancellation, which is the population the "a split follows a
reproduction, not an event" reasoning was written about.

## What is measured, and what is NOT claimed

Measured: the new regime (1/beat); the ``N + 1`` law it produces; that the
candidate cuts on beat 1 instead; that the build then COMPLETES where master
never does even with an immortal cursor; that it is INERT in both regimes 1336's
refutation lives in; that the completed output equals a fresh computation; and
what a TRANSIENT disturbance satisfying the predicate costs — one partition,
nothing unbanked, the same published census, no cascade over forty beats.

**NOT claimed: that this makes production's rebuild publish.** It does not, and
:class:`TestTheLimitThisCandidateDoesNotReach` measures the wall. One slot per
beat against an invalidation shorter than the build is still a build that never
finishes, and the smallest change that moves THAT is per-unit retention across a
population change (1336 §6) — a reviewed class, and not this lane's to rule.
"""

from __future__ import annotations

import contextlib
import types

import pytest

from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils import calibration_phase_ledger as pcl
from app.utils import calibration_staged_futures as sf
from tests.test_calibration_incremental_equals_fresh_6599 import _census, _rows_for
from app.utils.calibration_phase_ledger import (
    PHASE_FUTURES,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
)

#: One beat's window, the production order (~22 min).
WINDOW_MS = 1_350_000
#: Virtual questions per slot in this rig.
VMS_PER_SLOT = 8
#: What one OVERSIZED slot costs: more than a whole beat window, which is the
#: production shape — the 17:37:55Z beat's first unit was handed 1,254,562 ms
#: (everything there was) and did not finish.
OVERSIZED_SLOT_MS = 1_400_000
#: What an ordinary slot costs — 64 s, the order the plan carries.
HEALTHY_SLOT_MS = 64_000
#: A SLOW-but-completable slot, 1336's second counterexample class: most of a
#: beat, inside any bound the build ratchets up to, and therefore BANKED rather
#: than cancelled. Deliberately under the carried worst completion, because a
#: slot that outran THAT is the population the candidate is about.
SLOW_SLOT_MS = 800_000

#: The genuine predicate, captured at import so the control arm can be turned
#: back OFF again within one test (see the fixture).
_REAL_CONCLUSIVE = pcl.cancellation_is_conclusive

#: Production's carried measurements at 2026-09-17T17:37:55Z, heavy v41, with
#: the ring readable again after #6775. Both are real completions.
PROD_UNIT_MEAN_MS = 656_889
PROD_UNIT_WORST_MS = 1_181_085


class _StatementCancelled(Exception):
    """Postgres cancelling at its own backstop; the message is what it emits."""


def _ledger(
    *,
    window_ms: int,
    unit_ms: int | None,
    unit_ms_worst: int | None,
    units_done: int,
    buckets: int,
) -> PhaseLedger:
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
                units_total=buckets,
                # ``measured_unit_ms`` returns None on zero completions — a mean
                # over nothing is not a measurement — so a rig that wants the
                # post-#6775 fence must carry a real one. Production carries 1.
                units_done=units_done,
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

    def __init__(self, *, window_ms: int, generation: int, buckets: int, carried: bool):
        self.ledger = _ledger(
            window_ms=window_ms,
            unit_ms=PROD_UNIT_MEAN_MS if carried else None,
            unit_ms_worst=PROD_UNIT_WORST_MS if carried else None,
            units_done=1 if carried else 0,
            buckets=buckets,
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
        # The REAL runner records this pair beside the bound (CAL-P163) and
        # returns the bound; the loop's conclusiveness read is off the return
        # value, so a rig that dropped it would test a different writer.
        self.ledger.record_gauge(f"staged:unit_bound_ms:{phase}", int(armed))
        self.ledger.record_gauge(
            f"staged:unit_bound_headroom_ms:{phase}",
            max(0, self.ledger.remaining_ms(elapsed_ms=self._elapsed) - int(armed)),
        )
        self.armed.append(armed)
        return armed


class _Db:
    """Cost is a property of the QUESTIONS asked about, never of the call order.

    A refined child holds a SUBSET of its parent's questions, so its cost falls
    out of the same sum — which is the only reason this rig can say anything
    about whether refinement helps.
    """

    def __init__(self, runner: _Runner, roster, vm_cost: dict[str, int], population):
        self.runner = runner
        self.roster = roster
        self.vm_cost = vm_cost
        #: ``market_id -> (probability, winner)``. The unit's ROWS are a function
        #: of these values, borrowed verbatim from
        #: ``test_calibration_incremental_equals_fresh_6599`` so the output
        #: comparison below is against the same shape that file established.
        self.population = population
        self.by_market = {int(r.market_id): str(r.vm_id) for r in roster}
        self.completed: list[frozenset[str]] = []
        self.cancelled: list[tuple[frozenset[str], int]] = []
        self._gen_done = False

    def cost_of(self, vm_ids) -> int:
        return sum(self.vm_cost[v] for v in set(vm_ids))

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
        if cost > cap:
            self.runner.advance(cap)
            self.cancelled.append((vm_ids, cap))
            raise _StatementCancelled("canceling statement due to statement timeout")
        self.runner.advance(cost)
        self.completed.append(vm_ids)
        rows = _rows_for([int(m) for m in market_ids], self.population)
        return types.SimpleNamespace(all=lambda: rows)

    async def rollback(self) -> None:
        return None


def _roster(n: int):
    return [
        types.SimpleNamespace(
            market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False
        )
        for i in range(1, n + 1)
    ]


def _values(n: int) -> dict[int, tuple[float, bool]]:
    """``market_id -> (probability, winner)``, the shape ``_rows_for`` reads.

    Same generator as the equals-fresh rig, so a census produced here is
    comparable with one produced there.
    """
    return {i: (round((i % 10) / 10 + 0.05, 2), i % 3 == 0) for i in range(1, n + 1)}


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
        self.splits = 0
        self.max_banked = 0
        self.per_beat_banked: list[int] = []
        self.per_beat_cancelled: list[int] = []
        self.per_beat_cancel_entries: list[int] = []
        self.per_beat_splits: list[int] = []
        self.first_armed: list[int] = []
        #: The PUBLISHED census, present only on a run that completed.
        self.census: dict | None = None


@pytest.fixture
def drive(monkeypatch):
    """Drive the REAL beat loop over one durable cursor. Returns a callable.

    ``conclusive_splits=False`` is the CONTROL: the candidate's predicate is
    stubbed to False, which is byte-for-byte the pre-candidate behaviour of this
    loop. Every comparison below is against that, in the same rig, same beat.
    """

    async def _drive(
        *,
        buckets,
        oversized_slots=0,
        slow_slots=0,
        max_beats,
        reset_every=None,
        window_ms=WINDOW_MS,
        carried=True,
        conclusive_splits=True,
        transient=None,
    ):
        roster = _roster(buckets * VMS_PER_SLOT)
        population = _values(buckets * VMS_PER_SLOT)
        slots = _slots(roster, buckets)
        # Per-QUESTION cost derived from a per-SLOT total, because
        # ``bucket_of`` is a hash and its slots are not the same size: a flat
        # per-question cost makes "16 oversized slots" mean "the big ones are
        # oversized and the small ones fit", and the first run of this rig
        # measured exactly that artifact and called it a result. The cost is
        # still a property of the QUESTIONS — which is what lets a refined
        # child cost a fraction of its parent — it is just scaled so the
        # regime being named is the regime being run.
        vm_cost: dict[str, int] = {}
        ordered = sorted(slots)
        for position, index in enumerate(ordered):
            if position < oversized_slots:
                total = OVERSIZED_SLOT_MS
            elif position < oversized_slots + slow_slots:
                total = SLOW_SLOT_MS
            else:
                total = HEALTHY_SLOT_MS
            members = slots[index]
            for vm in members:
                vm_cost[vm] = total // len(members)

        bus = _Bus()
        monkeypatch.setattr(cmb, "load_staged_cursor", bus.load)
        monkeypatch.setattr(cmb, "save_staged_cursor", bus.save)
        monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
        monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", buckets)
        monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
        # Set on EVERY call, both ways round, never "patch only the control".
        # Two traps, both of which bit this rig before the numbers below were
        # believed: the loop imports the predicate INSIDE
        # ``_run_staged_futures``, so a patch on ``pc`` is re-bound every call
        # and the control silently does not control; and ``monkeypatch`` is
        # function-scoped, so a control arm patched mid-test leaks into every
        # later arm of the SAME test and reports the candidate as the control.
        monkeypatch.setattr(
            pcl,
            "cancellation_is_conclusive",
            _REAL_CONCLUSIVE if conclusive_splits else (lambda **_kw: False),
        )

        out = _Run()
        for beat_no in range(1, max_beats + 1):
            runner = _Runner(
                window_ms=window_ms,
                generation=beat_no,
                buckets=buckets,
                carried=carried,
            )
            if reset_every and beat_no > 1 and (beat_no - 1) % reset_every == 0:
                era = (beat_no - 1) // reset_every
                runner.population_version = f"q268+{era}"
                runner.ledger.population_version = f"q268+{era}"
            # A DISTURBANCE, not a cost: the questions of one slot are dear on
            # the named beats and ordinary on every other one, so the slot's
            # intrinsic cost is unchanged and only this beat is slow. Keyed on
            # the PARENT's questions, so the disturbance follows them into
            # whatever children a refinement produces — a lock does not respect
            # our partition either.
            beat_cost = vm_cost
            if transient and beat_no in transient["beats"]:
                members = slots[ordered[transient["slot"]]]
                beat_cost = dict(vm_cost)
                for vm in members:
                    beat_cost[vm] = transient["total_ms"] // len(members)
            db = _Db(runner, roster, beat_cost, population)
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
            out.per_beat_splits.append(len(splits))
            out.first_armed.append(runner.armed[0] if runner.armed else 0)
            if splits:
                out.splits = max(out.splits, len(splits))
                if out.first_split_beat is None:
                    out.first_split_beat = beat_no
            out.max_banked = max(
                out.max_banked,
                len(payload.get("committed_units") or []),
                len(payload.get("served_units") or []),
            )
            if rows is not None:
                out.completed_at = beat_no
                out.census = _census(rows)
                break
        return out

    return _drive


# =============================================================================
# 0. THE PREDICATE, ON PRODUCTION'S OWN TWO UNITS
# =============================================================================


class TestTheDiscriminatorOnTheRealSpecimen:
    """``calibration:main:phase_ledger`` 2026-09-17T17:37:55Z, heavy v41.

    One beat, two cancellations, and the whole candidate turns on telling them
    apart. Both were window-bounded; only one is a proof. Every number below is
    the production row, not a round one.
    """

    def test_the_unit_that_ate_the_window_is_a_proof(self):
        """Unit 1: handed 1,320,000 ms of a 1,350,000 ms window, ran 1,254,562.

        It outran the largest completion in the ring (1,181,085 ms) and there
        was no larger bound to give it, so nothing about the beat explains it.
        """
        assert pcl.cancellation_is_conclusive(
            remaining_ms=1_350_000,
            bound_ms=1_320_000,
            cancelled_after_ms=1_254_562,
            worst_completed_ms=PROD_UNIT_WORST_MS,
        )

    def test_the_unit_that_got_the_scraps_is_not(self):
        """Unit 2: bound 59,087 ms, headroom 6,565 ms — the margin to the ms.

        Window-bounded, exactly like unit 1, and cutting a slot on 59 s of
        evidence would refine a slot nobody measured. This is the condition that
        keeps roughly half of production's 30 recorded cancellations — the ones
        1342 identified as window artifacts — from cutting anything.
        """
        assert not pcl.cancellation_is_conclusive(
            remaining_ms=65_652,
            bound_ms=59_087,
            cancelled_after_ms=59_594,
            worst_completed_ms=PROD_UNIT_WORST_MS,
        )

    def test_a_unit_stopped_by_its_measured_basis_is_not(self):
        """#6275's specimen: 830,841 ms left, bounded at 483,000 by the LEVEL.

        347,841 ms of headroom against a 30,000 ms ceiling, so the fence was the
        build's own measurement and a bigger beat could still hand this slot
        more. Nothing is proved about the slot, and the two-cancellation rule
        keeps it — the same numbers #6775 uses, read by the same discriminator.
        """
        assert not pcl.cancellation_is_conclusive(
            remaining_ms=830_841,
            bound_ms=483_000,
            cancelled_after_ms=483_000,
            worst_completed_ms=400_000,
        )

    def test_with_no_completed_unit_anywhere_nothing_is_proved(self):
        """Ruling 075: absent evidence is not evidence, in both directions."""
        assert not pcl.cancellation_is_conclusive(
            remaining_ms=1_350_000,
            bound_ms=1_320_000,
            cancelled_after_ms=1_254_562,
            worst_completed_ms=None,
        )


# =============================================================================
# 1. THE REGIME #6775 CREATED — one cancellation a beat, not two
# =============================================================================


class TestTheNewRegimeOneCancellationPerBeat:
    """What a beat does now that the worst-unit ring is readable again.

    This is the state the actual writer establishes, and it is not the state the
    ``N/2 + 1`` law was measured in. It has to be shown before any candidate is
    judged, because it is what the candidate is being judged against.
    """

    @pytest.mark.asyncio
    async def test_the_first_unit_is_handed_the_whole_window_and_it_is_the_only_one(
        self, drive
    ):
        """One attempt, armed at the window, and the beat stops on the fence.

        The carried basis (mean 656,889 × 4, worst 1,181,085 × 1.5) exceeds the
        window, so ``min(phase_bound, unit_bound)`` IS the phase bound: the unit
        is handed everything the beat has. It cancels there, and
        ``_unit_fits_in_window`` then refuses a second unit against the 30 s of
        margin that is left — so the two-cancellation budget is never reached
        and the WINDOW, not the budget, is what ends the beat.
        """
        run = await drive(
            buckets=16, oversized_slots=16, max_beats=3, conclusive_splits=False
        )

        assert run.per_beat_banked == [0, 0, 0], "nothing banks in this regime"
        assert run.per_beat_cancelled == [1, 1, 1], (
            "ONE cancellation a beat — with the ring restored the beat ends on "
            f"the window fence, not on the budget; got {run.per_beat_cancelled}"
        )
        assert all(armed >= WINDOW_MS - 30_000 for armed in run.first_armed), (
            "and the one unit attempted is armed at the whole window, which is "
            f"what makes its cancellation conclusive; got {run.first_armed}"
        )

    @pytest.mark.asyncio
    async def test_the_first_cut_now_costs_a_beat_per_slot_not_two(self, drive):
        """The law moves from ``N/2 + 1`` to ``N + 1``. Measured, not argued.

        ``attempt_order`` sorts ascending on recorded cancellations, so no slot
        earns a second until every slot holds one; at ONE slot a beat that is a
        full pass of N beats. **At the production plan of 128 that is beat 129,
        hourly** — and 1342 measured invalidations that discard ``unit_cancels``
        long before then.
        """
        for buckets in (8, 16):
            run = await drive(
                buckets=buckets,
                oversized_slots=buckets,
                max_beats=40,
                conclusive_splits=False,
            )
            assert run.first_split_beat == buckets + 1, (
                f"{buckets} slots: first cut at beat {run.first_split_beat}, "
                f"expected {buckets + 1} — one full pass at one slot a beat"
            )


# =============================================================================
# 1. THE CANDIDATE — the proof is already in the first cancellation
# =============================================================================


class TestAConclusiveCancellationCutsOnBeatOne:
    @pytest.mark.asyncio
    async def test_the_slot_is_cut_on_its_first_cancellation(self, drive):
        """Beat 1, not beat N+1 — and the control is the same rig one flag away."""
        cand = await drive(buckets=16, oversized_slots=16, max_beats=3)
        base = await drive(
            buckets=16, oversized_slots=16, max_beats=3, conclusive_splits=False
        )

        assert cand.first_split_beat == 1, (
            f"the cut must land on the proof; got beat {cand.first_split_beat}"
        )
        assert base.first_split_beat is None, (
            "and the control must NOT cut in three beats, or this measures the "
            "rig rather than the candidate"
        )

    @pytest.mark.asyncio
    async def test_it_saves_exactly_one_full_pass_and_no_more(self, drive):
        """What the candidate is worth, measured — and it is ONE PASS, not a cure.

        Both arms attempt one slot a beat, so both spend N beats meeting the
        population. The control then has to meet it a SECOND time to collect the
        second cancellation each cut hangs off; the candidate cuts on contact and
        goes straight to the children. Measured, 120-beat ceiling:

        | slots | control completes | candidate | control 1st cut | candidate |
        |-------|-------------------|-----------|-----------------|-----------|
        |   4   |        16         |    13     |     beat 5      |  beat 1   |
        |   8   |        30         |    22     |     beat 9      |  beat 1   |
        |  16   |        55         |    43     |     beat 17     |  beat 1   |

        The saving tracks the population, which is the signature of a pass being
        removed rather than a constant being tuned. **It is also the ceiling on
        what this candidate can ever be worth**, and at 128 slots one pass is
        128 hourly beats — see :class:`TestTheLimitThisCandidateDoesNotReach`.
        """
        for buckets, control_beats, candidate_beats in ((4, 16, 13), (8, 30, 22)):
            cand = await drive(buckets=buckets, oversized_slots=buckets, max_beats=120)
            base = await drive(
                buckets=buckets,
                oversized_slots=buckets,
                max_beats=120,
                conclusive_splits=False,
            )
            assert (base.completed_at, cand.completed_at) == (
                control_beats,
                candidate_beats,
            ), (
                f"{buckets} oversized slots: control {base.completed_at} / "
                f"candidate {cand.completed_at}, expected {control_beats} / "
                f"{candidate_beats}"
            )
            assert cand.completed_at < base.completed_at
            assert base.first_split_beat == buckets + 1 and cand.first_split_beat == 1

    @pytest.mark.asyncio
    async def test_in_a_mixed_population_the_saving_is_the_oversized_pass(self, drive):
        """The likelier production shape: a few slots that cannot fit, many that can.

        The healthy slots bank on contact in either arm — the candidate does not
        touch them (it keys on a cancellation) — so the whole difference between
        the two arms is the second pass over the slots that cannot fit. That is
        the claim this file makes about production, stated as narrowly as it is
        measured.
        """
        cand = await drive(buckets=16, oversized_slots=4, max_beats=120)
        base = await drive(
            buckets=16, oversized_slots=4, max_beats=120, conclusive_splits=False
        )

        assert cand.completed_at is not None and base.completed_at is not None
        assert cand.completed_at < base.completed_at, (
            f"candidate {cand.completed_at} vs control {base.completed_at} — the "
            "mixed population must still show the saved pass"
        )
        assert cand.max_banked >= base.max_banked or cand.completed_at < base.completed_at

    @pytest.mark.asyncio
    async def test_it_publishes_inside_an_era_the_control_cannot_finish_in(self, drive):
        """The only shape in which this candidate is the difference, not a discount.

        An invalidation period BETWEEN the two completion costs: the candidate
        publishes, the control loses its bank one beat before it would have. The
        band exists because one pass was removed; outside the band the two arms
        agree, and the band at 128 slots sits at eras nobody has measured.
        """
        era = 26  # 8 oversized slots: candidate 22 beats, control 30.
        cand = await drive(
            buckets=8, oversized_slots=8, max_beats=120, reset_every=era
        )
        base = await drive(
            buckets=8,
            oversized_slots=8,
            max_beats=120,
            reset_every=era,
            conclusive_splits=False,
        )

        assert cand.completed_at is not None, (
            "inside the band the candidate must publish"
        )
        assert base.completed_at is None, (
            "and the control must not — otherwise the band is empty and this "
            "candidate buys nothing an operator can see"
        )

    @pytest.mark.asyncio
    async def test_a_scrap_bounded_cancellation_is_not_a_proof(self, drive):
        """The second half of the predicate, exercised where it bites.

        On production's 17:37:55Z beat the SECOND unit was window-bounded too —
        at 59,087 ms, the scraps left after the first ate the window — and
        cutting a slot on 59 s of evidence would refine a slot nobody measured.
        Here the beat has no carried measurement at all (``carried=False``), so
        there is no completed unit to outrun and the predicate must decline
        every cancellation, leaving ``STAGED_UNIT_SPLIT_AFTER`` in charge — the
        two-cancellations-a-beat regime, unchanged.
        """
        run = await drive(
            buckets=16, oversized_slots=16, max_beats=2, carried=False
        )

        assert run.per_beat_cancelled == [2, 2], (
            "with no carried basis the beat is back to spending its budget; "
            f"got {run.per_beat_cancelled}"
        )
        assert run.first_split_beat is None, (
            "and nothing may be cut on evidence the build has not got — "
            "ruling 075, and the reason this is not a tolerance"
        )


# =============================================================================
# 2. THE REFUTED CLASSES — the candidate must be INERT in both of them
# =============================================================================


class TestTheCandidateIsInertWhereOrderingWasRefuted:
    """1336's two counterexample classes, re-run against the candidate.

    An ordering change could not be inert here: it moves which slot is attempted
    first, and the first unit of a beat carries the widest bound the beat arms,
    so it changes what a healthy beat banks. This candidate touches neither the
    order nor the bound, and these two tests are where that claim is cashed.
    """

    @pytest.mark.asyncio
    async def test_a_healthy_tail_banks_exactly_what_it_banked_before(self, drive):
        cand = await drive(buckets=16, max_beats=40)
        base = await drive(buckets=16, max_beats=40, conclusive_splits=False)

        assert base.completed_at is not None, "the control must actually finish"
        assert cand.completed_at == base.completed_at, (
            "a healthy population must complete in the same beat as before; "
            f"candidate {cand.completed_at} vs control {base.completed_at}"
        )
        assert cand.per_beat_banked == base.per_beat_banked, (
            "and bank the same units in the same beats — 1336 measured its "
            "ordering candidate taking production-scale banking 122 → 105"
        )
        assert cand.splits == 0, "nothing is cut in a population with no proof"

    @pytest.mark.asyncio
    async def test_a_slow_but_completable_tail_is_untouched(self, drive):
        """The regime where units are slow enough to starve a beat and still bank.

        These units are never cancelled at all, so the candidate's predicate is
        never even reached — and that is the point: the evidence it keys on is a
        cancellation, and a unit that completes does not produce one.
        """
        cand = await drive(buckets=8, slow_slots=8, max_beats=40)
        base = await drive(buckets=8, slow_slots=8, max_beats=40, conclusive_splits=False)

        assert base.completed_at is not None, "the control must actually finish"
        assert cand.completed_at == base.completed_at
        assert cand.per_beat_banked == base.per_beat_banked
        assert cand.splits == 0


# =============================================================================
# 3. THE OUTPUT — a build that was cut must publish what an uncut one would
# =============================================================================


class TestTheCutBuildPublishesTheSameCensusAsAFreshRun:
    @pytest.mark.asyncio
    async def test_a_census_reached_through_splits_equals_one_computed_in_one_pass(
        self, drive
    ):
        """Frozen inputs, two routes to the same population, identical output.

        The candidate route takes 22 beats, cuts every one of its 8 slots on
        first contact, and folds children of children into the accumulator. The
        control route is ONE beat with a window big enough to hold the whole
        population, so it plans 8 units, splits nothing and folds each unit
        once. If refinement changed what is counted — a question dropped, a
        question counted twice, a bucket folded on the wrong key — these two
        censuses could not agree.

        This is the equality
        ``test_calibration_incremental_equals_fresh_6599`` establishes for the
        unrefined build, run again on the population this candidate exists for.
        """
        cut = await drive(buckets=8, oversized_slots=8, max_beats=120)
        fresh = await drive(
            buckets=8,
            oversized_slots=8,
            max_beats=1,
            window_ms=50_000_000,
        )

        assert fresh.completed_at == 1 and fresh.splits == 0, (
            "the control must finish in one pass having cut nothing, or it is "
            f"not a fresh run; beats={fresh.completed_at} splits={fresh.splits}"
        )
        assert cut.completed_at is not None and cut.splits >= 8, (
            f"the candidate route must actually go through splits; got "
            f"{cut.splits} across {cut.beats} beats"
        )
        assert cut.census == fresh.census, (
            "a census reached through refinement must equal the one a single "
            "pass computes — every bucket, count, winner total and error sum"
        )


# =============================================================================
# 3b. THE TRANSIENT CONTROL — what it costs when the predicate is WRONG
# =============================================================================

#: A DISTURBANCE on one otherwise healthy slot: bigger than the beat's window,
#: so the unit is cancelled at its window bound, and that bound (1,320,000 ms —
#: the 1,350,000 ms window less the 30,000 ms inner margin) is past the carried
#: worst completion of 1,181,085 ms. Both halves of the predicate therefore
#: hold, on a slot whose own cost is :data:`HEALTHY_SLOT_MS`. This is the shape
#: the predicate cannot tell from an oversized slot, and it is the whole point
#: of this section that it cannot.
TRANSIENT_MS = 1_400_000


def _transient(*, slot=0, beats=(1,), total_ms=TRANSIENT_MS):
    return {"slot": slot, "beats": tuple(beats), "total_ms": total_ms}


class TestATransientDelayIsNotExcludedAndIsBoundedWhenItHappens:
    """The predicate's one untested premise, exercised in the real loop.

    Reading ``cancellation_is_conclusive`` exposes a claim the rest of this file
    does not measure: that a window-bounded cancellation past every completed
    unit "is not a slot that met a lock, a vacuum or a plan flip". **That claim
    is false as stated** — a new slow disturbance can exceed any prior maximum,
    and the prior maximum is all the build holds. The prose has been corrected
    to say so.

    What survives the correction is a POLICY, and a policy is judged on the cost
    of its mistakes. These four tests inject a disturbance that does satisfy both
    conditions on a slot that is healthy in every other beat, and measure that
    cost: the slot is partitioned once, everything already completed stays
    banked, the build publishes in the same beat it otherwise would, the
    published census is identical to a fresh single-pass computation, and the cut
    does not cascade even when the disturbance never lifts.

    The disturbance is keyed on the PARENT slot's questions, so it follows them
    into whatever children the refinement produces — a lock does not respect our
    partition, and a rig whose disturbance evaporated at the cut would measure
    the answer it wanted.
    """

    @pytest.mark.asyncio
    async def test_a_transient_delay_past_every_completion_does_satisfy_the_predicate(
        self, drive
    ):
        """State the falsification first, in the loop, with a control.

        Slot 0 is a 64 s slot having one bad beat. The predicate cuts it, and the
        pre-candidate loop in the same rig does not. Nothing here is a defence —
        it is the measurement that makes the three tests below necessary.
        """
        cand = await drive(buckets=8, max_beats=60, transient=_transient())
        base = await drive(
            buckets=8, max_beats=60, transient=_transient(), conclusive_splits=False
        )

        assert cand.per_beat_cancelled[0] == 1, (
            "the disturbance must actually produce the cancellation the "
            f"predicate reads; got {cand.per_beat_cancelled}"
        )
        assert cand.first_split_beat == 1, (
            "and the predicate must fire on it — if it did not, this control "
            "would be vacuous and every claim below would be about nothing"
        )
        assert base.first_split_beat is None, (
            "while the pre-candidate loop, same rig, same disturbance, cuts "
            f"nothing; got beat {base.first_split_beat}"
        )

    @pytest.mark.asyncio
    async def test_the_completed_units_the_bank_and_the_publishing_beat_all_survive(
        self, drive
    ):
        """The cost of the false cut, measured against the control that avoids it.

        Measured, 8 slots, disturbance on beat 1 only:

        | arm       | beats | banked per beat | units | splits |
        |-----------|-------|-----------------|-------|--------|
        | candidate |   2   |     [0, 9]      |   9   |   1    |
        | control   |   2   |     [0, 8]      |   8   |   0    |

        The build publishes in the SAME beat either way, having banked one unit
        more because one slot is now two children. Nothing that completed was
        lost, and no beat was spent that the control did not also spend. The
        beat-1 zero is not the candidate's doing: a first unit that cancels at
        the window bound has consumed the window, and the control loses that beat
        identically.
        """
        cand = await drive(buckets=8, max_beats=60, transient=_transient())
        base = await drive(
            buckets=8, max_beats=60, transient=_transient(), conclusive_splits=False
        )

        assert (cand.completed_at, base.completed_at) == (2, 2), (
            "the false cut must not cost a beat; candidate "
            f"{cand.completed_at} vs control {base.completed_at}"
        )
        assert (cand.per_beat_banked, base.per_beat_banked) == ([0, 9], [0, 8]), (
            f"candidate {cand.per_beat_banked} / control {base.per_beat_banked}"
        )
        assert cand.max_banked >= base.max_banked, (
            f"banked output must be preserved; {cand.max_banked} < "
            f"{base.max_banked} would mean the cut dropped completed work"
        )

    @pytest.mark.asyncio
    async def test_the_refinement_is_bounded_even_when_the_disturbance_never_lifts(
        self, drive
    ):
        """The cascade this policy could have caused, and does not.

        The adversarial case for "cut on the first cancellation" is a disturbance
        that does not go away: each cut could cancel again, cut again, and shred
        the partition. Held for forty consecutive beats, it does not — the
        children absorb the same disturbance their parent could not, stop
        cancelling, and the run ends with exactly ONE split.

        The control needs a second cancellation first, so it cuts on beat 2 and
        publishes on beat 4 rather than beat 3: against a disturbance this
        durable the candidate's cut is not merely harmless, it is the same cut
        the two-cancellation rule makes one beat later.
        """
        forty = _transient(beats=range(1, 41))
        cand = await drive(buckets=8, max_beats=40, transient=forty)
        base = await drive(
            buckets=8, max_beats=40, transient=forty, conclusive_splits=False
        )

        assert cand.splits == 1 and max(cand.per_beat_splits) == 1, (
            "one disturbance, one cut, no cascade; got "
            f"{cand.splits} splits, per-beat {cand.per_beat_splits}"
        )
        assert cand.per_beat_cancelled == [1, 0, 0], (
            "and the children must stop cancelling once cut, or the bound is "
            f"the beat ceiling rather than the policy; got {cand.per_beat_cancelled}"
        )
        assert (cand.completed_at, base.completed_at) == (3, 4), (
            f"candidate {cand.completed_at} vs control {base.completed_at}"
        )
        assert base.splits == 1, (
            "the control reaches the SAME partition, one pass later — which is "
            f"why the wrong answer is cheap; got {base.splits}"
        )

    @pytest.mark.asyncio
    async def test_publication_after_a_false_cut_still_equals_a_fresh_computation(
        self, drive
    ):
        """The truth clause: a partition nobody intended must not change a number.

        Both disturbed arms, one-beat and forty-beat, against the same
        single-pass computation used by
        :class:`TestTheCutBuildPublishesTheSameCensusAsAFreshRun` — every bucket,
        count, winner total and error sum.
        """
        fresh = await drive(buckets=8, max_beats=1, window_ms=50_000_000)
        assert fresh.completed_at == 1 and fresh.splits == 0, (
            "the reference must be one uncut pass; "
            f"beats={fresh.completed_at} splits={fresh.splits}"
        )

        once = await drive(buckets=8, max_beats=60, transient=_transient())
        forever = await drive(
            buckets=8, max_beats=40, transient=_transient(beats=range(1, 41))
        )

        assert once.splits == 1 and forever.splits == 1, (
            "both arms must have gone through the false cut, or this compares "
            f"uncut runs; got {once.splits} / {forever.splits}"
        )
        assert once.census == fresh.census, (
            "a census reached through a refinement caused by a disturbance must "
            "equal the one a single pass computes"
        )
        assert forever.census == fresh.census

    @pytest.mark.asyncio
    async def test_a_false_positive_inside_the_population_the_candidate_is_for(
        self, drive
    ):
        """The realistic mixture: four slots that cannot fit, one having a bad beat.

        Slot 4 is healthy and disturbed on beat 1; slots 0-3 are genuinely
        oversized. Measured: the candidate publishes on beat 12 against the
        control's 14, both reach four splits, and both publish the same census as
        a fresh pass. The false positive is absorbed inside a saving it does not
        cancel out.
        """
        disturbed = _transient(slot=4)
        cand = await drive(
            buckets=8, oversized_slots=4, max_beats=120, transient=disturbed
        )
        base = await drive(
            buckets=8,
            oversized_slots=4,
            max_beats=120,
            transient=disturbed,
            conclusive_splits=False,
        )
        fresh = await drive(
            buckets=8, oversized_slots=4, max_beats=1, window_ms=50_000_000
        )

        assert (cand.completed_at, base.completed_at) == (12, 14), (
            f"candidate {cand.completed_at} vs control {base.completed_at}"
        )
        assert cand.max_banked >= base.max_banked
        assert cand.census == fresh.census and base.census == fresh.census


# =============================================================================
# 4. THE LIMIT — what the candidate does NOT reach
# =============================================================================


class TestTheLimitThisCandidateDoesNotReach:
    @pytest.mark.asyncio
    async def test_an_invalidation_shorter_than_the_build_still_never_publishes(
        self, drive
    ):
        """Cutting earlier does not make a build survive an era shorter than it.

        Every era the cursor is refused wholesale, and with it go the banked
        units AND the refinements that were earned. The candidate shortens the
        build; it cannot shorten it below one beat per unit, so an invalidation
        period under that is still fatal. This is the wall, and the smallest
        change that moves it is per-unit retention across a population change
        (1336 §6) — a reviewed class, not this one.
        """
        run = await drive(buckets=8, oversized_slots=8, max_beats=60, reset_every=4)

        assert run.completed_at is None, (
            "with the era shorter than the build nothing publishes, candidate "
            "or not — this is measured so the ship is not over-claimed"
        )

    @pytest.mark.asyncio
    async def test_the_same_build_completes_when_the_cursor_outlives_it(self, drive):
        """THE CONTROL for the test above: the difference is the PERIOD."""
        run = await drive(buckets=8, oversized_slots=8, max_beats=60, reset_every=50)

        assert run.completed_at is not None, (
            "with an era longer than the build the very same population "
            "publishes, so the test above is about the period and not the rig"
        )
