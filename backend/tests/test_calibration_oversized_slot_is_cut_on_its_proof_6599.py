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

#: The two genuine predicates, captured at import so either arm can be turned
#: back ON again within one test (see the fixture).
_REAL_CONCLUSIVE = pcl.cancellation_is_conclusive
_REAL_PACKING = sf.packing_split_factor

#: Production's carried measurements at 2026-09-17T17:37:55Z, heavy v41, with
#: the ring readable again after #6775. Both are real completions.
PROD_UNIT_MEAN_MS = 656_889
PROD_UNIT_WORST_MS = 1_181_085

#: Production's deadline horizon, 2026-09-19T06:37:54Z row: ``soft_limit_ms``
#: 1,500,000 less ``cleanup_margin_ms`` 120,000. The rig derives the same number
#: from ``window_ms`` (``_ledger`` adds the margin back), so passing this as
#: ``window_ms`` reproduces production's horizon exactly.
PROD_DEADLINE_MS = 1_380_000
#: **The futures phase's own measured budget, and the second fence — #6599.**
#: ``plan.futures`` on that row: ``budget_ms`` 1,283,522 with
#: ``budget_basis: measured_elastic_cut``, less ``STATEMENT_INNER_MARGIN_MS``.
#: Traced to ``max(history.futures) = 873_486`` (a completed phase duration)
#: times ``BUDGET_SAFETY``, cut elastically to fit the deadline.
#:
#: 🔴 **Every arm written before this constant existed ran with no phase budget
#: at all** (``_ledger`` passed ``statement_timeout_ms=None``), so ``phase_bound``
#: was always the deadline bound and this term has never been exercised. It is
#: currently what fences production's first unit, 68,734 ms inside the deadline
#: bound — see :class:`TestTheSecondFenceIsThePhaseBudget`.
PROD_PHASE_STATEMENT_TIMEOUT_MS = 1_253_522
#: What that fence let production's first unit run to before Postgres cancelled
#: it, same row: ``staged:unit_cancelled:2b09538b85aaef4c``. 2,422 ms past the
#: bound, which is what the cancellation itself costs.
PROD_UNIT1_CANCELLED_AFTER_MS = 1_255_944
#: The scraps the second unit got, and what it ran to:
#: ``staged:unit_bound_ms:futures`` / ``staged:unit_cancelled:a7e9285632deabab``.
PROD_UNIT2_BOUND_MS = 65_272
PROD_UNIT2_CANCELLED_AFTER_MS = 65_847


class _StatementCancelled(Exception):
    """Postgres cancelling at its own backstop; the message is what it emits."""


def _ledger(
    *,
    window_ms: int,
    unit_ms: int | None,
    unit_ms_worst: int | None,
    units_done: int,
    buckets: int,
    unit_ms_worst_observed: int | None = None,
    phase_statement_timeout_ms: int | None = None,
) -> PhaseLedger:
    plan = PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=None,
                # #6599, second fence. ``statement_timeout_for`` returns
                # ``min(deadline_bound, this)``, so ``None`` — every arm before
                # this parameter — means the deadline bound always wins and the
                # phase term is never exercised. Production carries 1,253,522.
                statement_timeout_ms=phase_statement_timeout_ms,
                measured_input=True,
                unit_ms=unit_ms,
                unit_ms_worst=unit_ms_worst,
                # CAL-P1304: the ring as EVIDENCE, which a withdrawn level keeps
                # and a withdrawn BASIS does not. Defaults to the basis so every
                # arm written before this parameter existed is unchanged.
                unit_ms_worst_observed=(
                    unit_ms_worst if unit_ms_worst_observed is None else unit_ms_worst_observed
                ),
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

    def __init__(
        self,
        *,
        window_ms: int,
        generation: int,
        buckets: int,
        carried: bool,
        withdrawn: bool = False,
        ring_readable: bool = True,
        phase_statement_timeout_ms: int | None = None,
        carried_mean_ms: int | None = None,
        carried_worst_ms: int | None = None,
    ):
        # CAL-P1304. ``withdrawn`` is the state production has actually been in
        # since #6275: ``unit_costs.futures`` carries the withdrawal marker, so
        # there is no mean and no admission basis — and ``ring_readable`` is the
        # repair, i.e. whether the worst-unit ring is still legible as evidence
        # beside that withdrawal. ``withdrawn and not ring_readable`` is the
        # tree CERT-3051 graded.
        #: #6599 / lat941: ``carried_*`` is the LEARNING rig — the previous
        #: beat's own measured cost rather than a constant. Every arm written
        #: before it passes ``None`` and gets the pinned production numbers
        #: byte-for-byte; see ``learns`` on the fixture for why a pinned carry
        #: cannot measure a mechanism whose whole effect is to change unit cost.
        base_mean = PROD_UNIT_MEAN_MS if carried_mean_ms is None else carried_mean_ms
        base_worst = PROD_UNIT_WORST_MS if carried_worst_ms is None else carried_worst_ms
        base_worst = base_worst if carried else None
        self.ledger = _ledger(
            window_ms=window_ms,
            unit_ms=None if withdrawn else (base_mean if carried else None),
            unit_ms_worst=None if withdrawn else base_worst,
            unit_ms_worst_observed=base_worst if ring_readable else None,
            units_done=1 if carried else 0,
            buckets=buckets,
            phase_statement_timeout_ms=phase_statement_timeout_ms,
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
        # CAL-P1305: the real runner records the winning term on the LEDGER at
        # ARM time and the loop reads it back when the unit cancels. A rig that
        # skipped this would leave the predicate on its headroom inference and
        # measure the tree this candidate is trying to leave.
        armed = self.ledger.note_unit_bound(
            phase,
            self.ledger.statement_timeout_for_unit_detail(
                phase, elapsed_ms=self._elapsed, unit_ms=unit_ms
            ),
        ).ms
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
        #: Per beat, the ``staged:unit_cancel_conclusive:*`` gauges that beat
        #: wrote — the loop's record of "the evidence was conclusive", kept
        #: apart from what the split then did with it.
        self.per_beat_conclusive: list[dict[str, int]] = []
        #: Per beat, ``(ref, cancelled_after_ms)`` for every cancellation.
        self.per_beat_cancel_ms: list[list[int]] = []
        #: The PUBLISHED census, present only on a run that completed.
        self.census: dict | None = None


@pytest.fixture
def staged_beat_loop(monkeypatch):
    """Drive the REAL beat loop over one durable cursor. Returns a callable.

    **Two independent refinement candidates now live in this loop**, and this
    fixture holds a knob for each so that neither file that uses it can be
    reading the other's mechanism by accident:

    * ``conclusive_splits`` — :func:`cancellation_is_conclusive`, the candidate
      THIS file measures. It cuts a slot on its first window-bounded
      cancellation.
    * ``packing_splits`` — :func:`packing_split_factor`, #6599's second defect
      (``test_calibration_a_slow_success_is_evidence_too_6599``). It cuts a slot
      that SUCCEEDS too slowly to pack two into a beat, and so fires on runs
      where nothing ever cancels.

    Both default to LIVE, which is the loop production runs. A file that wants
    one of them held down says so in ITS OWN ``drive`` fixture, once, where a
    reader can see the regime — never per call site, and never by flipping a
    default that a sibling module imports (this fixture is imported across
    files, so a default is a cross-file coupling).

    Each knob is set on EVERY call, both ways round, never "patch only the
    control". Two traps, both of which bit this rig before the numbers below
    were believed: the loop imports these predicates INSIDE
    ``_run_staged_futures``, so a patch is re-bound every call and a control
    silently does not control; and ``monkeypatch`` is function-scoped, so a
    control arm patched mid-test leaks into every later arm of the SAME test and
    reports the candidate as the control.
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
        packing_splits=True,
        transient=None,
        withdrawn=False,
        ring_readable=True,
        phase_statement_timeout_ms=None,
        learns=False,
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
        # Both knobs, set on EVERY call, both ways round — see the fixture
        # docstring for the two traps this shape exists to avoid.
        monkeypatch.setattr(
            pcl,
            "cancellation_is_conclusive",
            _REAL_CONCLUSIVE if conclusive_splits else (lambda **_kw: False),
        )
        # ``0`` is this predicate's own "no cut is owed" answer, so the stub
        # takes the loop down the branch it already has for a slot that packs,
        # rather than a branch only a test can reach.
        monkeypatch.setattr(
            sf,
            "packing_split_factor",
            _REAL_PACKING if packing_splits else (lambda *_a, **_kw: 0),
        )

        out = _Run()
        carried_mean_ms: int | None = None
        carried_worst_ms: int | None = None
        for beat_no in range(1, max_beats + 1):
            runner = _Runner(
                window_ms=window_ms,
                generation=beat_no,
                buckets=buckets,
                carried=carried,
                withdrawn=withdrawn,
                ring_readable=ring_readable,
                phase_statement_timeout_ms=phase_statement_timeout_ms,
                carried_mean_ms=carried_mean_ms,
                carried_worst_ms=carried_worst_ms,
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
            out.per_beat_conclusive.append(
                {
                    name: value
                    for name, value in runner.ledger.stages.items()
                    if name.startswith("staged:unit_cancel_conclusive:")
                }
            )
            out.per_beat_cancel_ms.append([ms for _vms, ms in db.cancelled])
            if learns:
                # What production carries: the cost of the units THIS beat ran,
                # so a plan whose units got cheaper is a plan the next beat's
                # admission fence knows is cheaper. A rig that re-pins the
                # constant every beat cannot see a refinement pay off, because
                # the fence it has to pay off against never moves.
                beat_costs = [db.cost_of(vms) for vms in db.completed]
                if beat_costs:
                    carried_mean_ms = int(sum(beat_costs) / len(beat_costs))
                    carried_worst_ms = int(max(beat_costs))
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


@pytest.fixture
def drive(staged_beat_loop):
    """THIS FILE's rig: the #6599 packing candidate is held OFF in BOTH arms.

    Every measurement below is about ONE candidate —
    :func:`cancellation_is_conclusive` — and its control
    (``conclusive_splits=False``) is the loop without it. When a second
    candidate landed in the same loop, that control stopped being the thing this
    file names and 20 of these tests went red: not one of them at an invariant,
    every one at a count, a position or a "nothing else cuts here" premise
    (measured, lat940). A file that measures A against no-A cannot also be the
    file that measures A+B, so the isolation is declared here, once, rather than
    written into 47 call sites where the next reader would have to reconstruct
    it from a keyword.

    **So these numbers are about a loop production does not run**, and that is
    the point of an isolation control — but it means the two clauses this file
    used to own for the WHOLE loop cannot be left here:

    * the TRUTH clause (a cut must not change a published census) and the
      cascade bound are restated against the composed loop in
      ``test_calibration_a_slow_success_is_evidence_too_6599`` section 5, which
      imports :func:`staged_beat_loop` with both candidates live;
    * the composed throughput — what A+B do together at the production plan —
      is that file's sections 1 and 3.

    A test here that wants the composition asks for ``staged_beat_loop``
    directly and says which regime it is in.
    """

    async def _isolated(**kwargs):
        kwargs.setdefault("packing_splits", False)
        return await staged_beat_loop(**kwargs)

    return _isolated


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
    async def test_it_publishes_inside_an_era_the_control_needs_18_more_beats_for(
        self, drive
    ):
        """The shape in which this candidate is the difference, not a discount.

        **AMENDED by CAL-P1304, and the amendment is the repair's own doing.**
        This read ``base.completed_at is None`` — inside this band the control
        did not merely finish later, it never finished, because every era took
        its refinements away with its bank. Now that
        :func:`~app.utils.calibration_staged_futures.carry_refinement` keeps the
        refinement across the boundary, the control's refinements ratchet too
        and it lands on beat 40. The band is not empty: it is 18 beats wide,
        which is a difference an operator sees as most of a day.

        Both numbers are asserted exactly, in the house idiom of the tests
        above, so a change in either arm is a test failure rather than a quietly
        different story.
        """
        era = 26
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

        assert (cand.completed_at, base.completed_at) == (22, 40), (
            f"candidate {cand.completed_at} vs control {base.completed_at}"
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
# 1b. THE EVIDENCE IS RECORDED AS EVIDENCE — gotcha #53
# =============================================================================


class TestTheCutFiresOnTheWITHDRAWNLevelProductionIsActuallyIn:
    """CAL-P1304 (#6599, repairing CERT-3051) — the state this policy is FOR.

    Every arm above drives a level whose admission basis is intact, and on such
    a level ``measured_unit_worst_ms`` and ``observed_unit_worst_ms`` return the
    same number, so which one the loop reads makes no difference and no test
    could see the difference. Production is not on such a level. It carries
    CAL-P1300's withdrawal — ``{'units_done': 1, 'units_total': 128,
    'level_refuted': True}`` — where the basis is deliberately absent and only
    the ring knows what a unit has completed in.

    That is why CERT-3051 could say the policy was coherent, its tests green,
    and its population empty in production, all at once. These two arms are that
    population: the first is the withdrawn level with the ring legible (the
    repair), the second is the withdrawn level with the ring erased along with
    the basis (the tree that was graded). Nothing else differs between them.
    """

    @pytest.mark.asyncio
    async def test_the_cut_lands_although_the_admission_basis_is_withdrawn(
        self, drive
    ):
        """The headline: the policy fires on the row the defect is worst on."""
        run = await drive(
            buckets=8, oversized_slots=8, max_beats=4, withdrawn=True
        )

        assert run.first_split_beat == 1, (
            "with the ring legible as evidence the first window-bounded "
            f"cancellation is conclusive and cuts; got beat {run.first_split_beat}"
        )
        assert run.per_beat_conclusive[0], (
            "and the beat records WHY it cut, which is the gauge the mutation "
            "run at f7f0e6bc1 added"
        )

    @pytest.mark.asyncio
    async def test_with_the_ring_erased_as_well_nothing_is_ever_cut(self, drive):
        """CERT-3051's finding, reproduced as a control.

        Same withdrawal, same population, same predicate — the ring is simply
        unreadable, as ``load_phase_measurements`` used to leave it. The
        cancellation has no completed maximum to be measured against, ruling 075
        says absent evidence is not evidence, and the cut correctly declines.
        Fourteen hours of production ran exactly here.
        """
        run = await drive(
            buckets=8,
            oversized_slots=8,
            max_beats=4,
            withdrawn=True,
            ring_readable=False,
        )

        assert run.first_split_beat is None, (
            "with nothing known to have completed the policy must decline — "
            f"got a cut on beat {run.first_split_beat}"
        )
        assert not any(run.per_beat_conclusive), (
            "and it must record no conclusive read either: 'the evidence never "
            "arrived' is a different fact from 'the cut was refused'"
        )


class TestTheConclusiveReadIsLegibleOnItsOwn:
    """``staged:unit_cancel_conclusive:{ref}`` is written, and it means one thing.

    The loop records this gauge BEFORE the split is attempted, and the comment
    beside it says why: the four ``SPLIT_*`` outcomes mean four different
    things, so "the evidence was conclusive and the cut was refused" has to be
    readable apart from "the evidence never arrived" (gotcha #53). Nothing
    asserted that until this class did. A mutant that deletes the
    ``record_gauge`` call — leaving the cut itself untouched — passed all 21
    tests of this file, which is precisely the state gotcha #53 describes: the
    diagnostic that distinguishes two causes is absent, and its absence looks
    exactly like the innocent case.

    The two arms below are the whole point. The gauge tracks the PREDICATE, not
    the split: the control runs the identical rig with
    ``cancellation_is_conclusive`` stubbed to False and must record none of
    these at all, or the gauge is noise rather than a reading.
    """

    @pytest.mark.asyncio
    async def test_the_beat_that_cuts_records_the_evidence_it_cut_on(self, drive):
        cand = await drive(buckets=16, oversized_slots=16, max_beats=3)

        assert cand.first_split_beat == 1, (
            "this test is about what beat 1 RECORDED; if the cut moved, fix "
            f"that first — got beat {cand.first_split_beat}"
        )
        beat_one = cand.per_beat_conclusive[0]
        assert len(beat_one) == 1, (
            "one cancellation on beat 1 ⇒ exactly one conclusive gauge; got "
            f"{beat_one}"
        )

        name, value = next(iter(beat_one.items()))
        ref = name.split("staged:unit_cancel_conclusive:", 1)[1]
        assert ref, f"the gauge must name the SLOT it is about; got {name!r}"

        # It carries the DURATION, not a flag — a `1` here would be a boolean
        # wearing a measurement's name, and the number is the whole reason a
        # later reader can tell a proof from a bad minute.
        assert value == cand.per_beat_cancel_ms[0][0], (
            f"the gauge must carry the cancellation's own duration; gauge "
            f"{value} vs cancelled_after_ms {cand.per_beat_cancel_ms[0]}"
        )
        assert value > 1, (
            f"a duration, not a flag; got {value}"
        )

    @pytest.mark.asyncio
    async def test_the_control_records_no_such_gauge_on_any_beat(self, drive):
        base = await drive(
            buckets=16, oversized_slots=16, max_beats=3, conclusive_splits=False
        )

        assert base.first_split_beat is None, (
            "the control must not cut in three beats, or this measures the rig"
        )
        assert all(not beat for beat in base.per_beat_conclusive), (
            "the gauge follows the predicate, not the cancellation — the "
            "control cancels on every beat and must still record none; got "
            f"{base.per_beat_conclusive}"
        )

    @pytest.mark.asyncio
    async def test_a_scrap_bounded_cancellation_records_nothing(self, drive):
        """The inert arm: a cancellation the predicate refuses leaves no gauge.

        Same rig as
        :meth:`TestTheCandidateIsInertWhereOrderingWasRefuted.test_a_scrap_bounded_cancellation_is_not_a_proof`
        — a slot stopped by a measured basis rather than by the window. The cut
        does not happen there, and neither does the reading.
        """
        run = await drive(buckets=8, oversized_slots=0, slow_slots=8, max_beats=3)

        assert run.first_split_beat is None, (
            f"nothing here is conclusive; got a cut on beat {run.first_split_beat}"
        )
        assert all(not beat for beat in run.per_beat_conclusive), (
            f"and so nothing should be recorded; got {run.per_beat_conclusive}"
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
    """Where the wall stands AFTER CAL-P1304, measured rather than asserted.

    CERT-3051 blocked on this class. It read, correctly for its tree, that an
    era shorter than the build never publishes however early the cut lands —
    every era took the banked units AND the earned refinements, so each one
    started from 128 coarse slots and re-learned what the last one knew. The
    named repair was per-unit retention across a population change, and
    :func:`~app.utils.calibration_staged_futures.carry_refinement` is it: the
    refinement crosses the boundary, the bank does not.

    What that buys, on this shape, is stated as a THRESHOLD rather than a
    verdict, because the honest claim is a number and not a yes:

    ========  ==================  =================
    era       before CAL-P1304    after CAL-P1304
    ========  ==================  =================
    12        never               never
    16        never               **beat 30**
    20        never               beat 33
    24        beat 22             beat 22
    ========  ==================  =================

    The shortest era this build survives falls from 24 beats to 16 — a third
    off — and the reason is exactly the re-learning that retention removes. It
    is not monotonic in the era (16 publishes on beat 30, 24 on beat 22),
    because where an era boundary falls decides which beat's bank is lost, and
    nothing here pretends otherwise.

    **The wall is not gone and this class still says so.** Retention removes the
    cost of re-LEARNING; it cannot remove the work itself. A build needs some
    number of beats of banking no matter how well partitioned it is — 22 here,
    with an era long enough to never interrupt — so an era below that floor is
    still fatal, and the only thing that moves THAT is retaining banked units
    across an invalidation, which the input digest exists to forbid.

    🔴 **EVERY ROW HERE IS CONDITIONAL ON AN ERA, AND PRODUCTION HAS NONE.** This
    class measures what happens when the cursor is invalidated every N beats. It
    does not assert that production is invalidated at all, and the ring says it
    is not: forty consecutive resumable beats, ``units_dropped: 0`` on each. The
    measured regime, and the 128-slot build that publishes inside it, are
    :class:`TestTheProductionRegimeIsNotAnEraAndTheBuildPublishesInIt`. Read that
    class for what production does; read this one for what an era would cost.
    """

    @pytest.mark.asyncio
    async def test_an_era_of_four_beats_is_still_shorter_than_the_work(self, drive):
        """The floor retention cannot reach: an era below the banking cost.

        Four beats against a build that needs 22 of them even uninterrupted.
        No partition makes 22 beats of work fit in 4, so this publishes nothing
        and is expected to — the claim being protected is that CAL-P1304 is a
        saving on re-learning and was never sold as one on the work.
        """
        run = await drive(buckets=8, oversized_slots=8, max_beats=60, reset_every=4)

        assert run.completed_at is None, (
            "an era below the banking floor publishes nothing, retention or "
            "not — measured so the ship is not over-claimed"
        )

    @pytest.mark.asyncio
    async def test_the_era_that_used_to_be_fatal_now_publishes(self, drive):
        """THE SHIP of CAL-P1304, as the smallest era that changed answer.

        Sixteen beats: ``None`` before the repair, beat 30 after. The control
        arm below proves the difference is the RETENTION and not the rig, by
        running this very era with the carry stubbed back out.
        """
        run = await drive(buckets=8, oversized_slots=8, max_beats=200, reset_every=16)

        assert run.completed_at == 30, (
            f"era 16 must publish on beat 30; got {run.completed_at}"
        )

    @pytest.mark.asyncio
    async def test_without_the_carry_the_same_era_publishes_nothing(
        self, drive, monkeypatch
    ):
        """THE CONTROL: the identical era with CAL-P1304's carry stubbed out.

        ``carry_refinement`` returns the blank it was handed, which is
        byte-for-byte the pre-repair decoder. Same population, same era, same
        predicate — only the retention differs, so a reader cannot attribute
        the test above to anything else.
        """
        monkeypatch.setattr(sf, "carry_refinement", lambda blank, raw: blank)

        run = await drive(buckets=8, oversized_slots=8, max_beats=200, reset_every=16)

        assert run.completed_at is None, (
            "with the refinement discarded every era, era 16 re-learns forever "
            "and publishes nothing — which is the state CERT-3051 blocked on"
        )

    @pytest.mark.asyncio
    async def test_the_same_build_completes_when_the_cursor_outlives_it(self, drive):
        """THE CONTROL for the era tests: the difference is the PERIOD."""
        run = await drive(buckets=8, oversized_slots=8, max_beats=60, reset_every=50)

        assert run.completed_at is not None, (
            "with an era longer than the build the very same population "
            "publishes, so the tests above are about the period and not the rig"
        )


# =============================================================================
# 8. THE REGIME PRODUCTION IS ACTUALLY IN, AT THE REAL PLAN SIZE
# =============================================================================


class TestTheProductionRegimeIsNotAnEraAndTheBuildPublishesInIt:
    """CERT-3053's required repair — and the measurement that reframes it.

    CERT-3053 asked for "the real 128-slot build reaching 128/128 and publishing
    within the measured production invalidation regime". Both halves are here,
    and the second half is not the number the block assumed.

    ## The invalidation regime, MEASURED rather than inherited

    ``/api/admin/calibration-beat-gauges`` on 2026-09-19T06:2xZ, forty
    consecutive hourly beats, ``2026-09-17T14:37:53Z`` through
    ``2026-09-19T05:37:55Z`` — every one of them:

    * ``cursor_action: resume`` and ``cursor_reason: resumable``. **Not one
      invalidation in thirty-nine hours.**
    * ``units_dropped: 0``, ``units_dropped_measured: true`` — the bank is never
      wiped (gotcha #53: a measured zero, not an absent one).
    * ``units_banked`` pinned at **1** on all forty rows.
    * ``rebuild_units_ran_this_beat: 2`` and
      ``rebuild_units_ran_not_banked_this_beat: 2`` on all forty — two attempted,
      two cancelled, nothing completed, every beat.

    Cross-read on the beat's OWN durable row (``durable_state_snapshots``,
    identity ``calibration:main:phase_ledger``, generated 05:37:55.774573Z),
    which is a different writer from the sampler ring above:
    ``input_fingerprint: 8ddaa1ea408615b81599c385593d83a1`` and
    ``population_version: q271`` — both constant, which is WHY the cursor
    resumes.

    **So ``reset_every`` is not production's regime; ``None`` is.** The
    "invalidates roughly every fifteen beats" figure that CERT-3053 reasoned
    from — and that this lane's own :func:`carry_refinement` docstring asserted
    — is refuted by the ring. It is corrected at both sites rather than left
    standing, because an inherited number that no longer measures anything is
    how the last two candidates on this defect were justified.

    ## What is actually wrong, on the same row

    ``unit_costs.futures`` reads ``{'units_done': 1, 'units_total': 128,
    'level_refuted': True}`` — byte-identical to :data:`PROD_LATCHED_COST`,
    captured two days earlier and still live. Beside it,
    ``staged:unit_cost_reason:no_unit_completed``,
    ``staged:unit_worst_reason:unmeasured:futures`` and
    ``staged:prior_unit_reason:unmeasured`` — while ``unit_worst_history``
    carries twenty-four real completions ending at 1,181,085 ms. The evidence is
    present and unreadable, which is the defect CAL-P1304 removes.

    ## The 128-slot build, in that regime, from that state

    ``withdrawn=True`` (production's latched cost dict), ``reset_every=None``
    (production's measured regime), ``buckets=128`` (production's plan), 200
    beats of headroom. ``ring_readable`` is the repair.

    ========  =====================  ==================
    oversized  graded tree (CERT-3053)  with CAL-P1304
    ========  =====================  ==================
    16        beat 46                **beat 43**
    32        beat 90                **beat 83**
    64        beat 175               **beat 160**
    128       never (banks 129)      never (banks 151)
    ========  =====================  ==================

    The build reaches 128/128 and publishes, sooner than the graded tree at
    every shape that publishes at all, and the first refinement moves from beat
    14/21/36/65 to **beat 1** in all four.

    **The saturated row is stated, not hidden.** Where every slot costs more
    than a whole window, neither arm publishes inside 200 beats; the repair banks
    151 units against 129 and earns 91 refinements against 73, which is progress
    and is not publication. :class:`TestTheLimitThisCandidateDoesNotReach` keeps
    saying so.
    """

    #: Production's measured regime: the cursor resumed on all forty observed
    #: beats, so there is no era boundary to model.
    NO_INVALIDATION = None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "oversized,graded,repaired",
        [(16, 46, 43), (32, 90, 83), (64, 175, 160)],
    )
    async def test_the_128_slot_build_publishes_and_does_so_sooner(
        self, drive, oversized, graded, repaired
    ):
        """THE SHIP CERT-3053 ASKED TO SEE: 128/128, published, in the real regime.

        Both arms run the same population, the same latched state and the same
        (absent) era — only the ring's legibility differs, so the difference is
        attributable to CAL-P1304 and to nothing else about the rig.
        """
        cand = await drive(
            buckets=128,
            oversized_slots=oversized,
            max_beats=200,
            withdrawn=True,
            ring_readable=True,
            reset_every=self.NO_INVALIDATION,
        )
        base = await drive(
            buckets=128,
            oversized_slots=oversized,
            max_beats=200,
            withdrawn=True,
            ring_readable=False,
            reset_every=self.NO_INVALIDATION,
        )

        assert (base.completed_at, cand.completed_at) == (graded, repaired), (
            f"{oversized}/128 oversized: graded tree {base.completed_at} / "
            f"repaired {cand.completed_at}, expected {graded} / {repaired}"
        )
        assert cand.completed_at < base.completed_at
        assert cand.max_banked >= 128 and base.max_banked >= 128, (
            "both arms must actually reach the whole plan — a publication that "
            "banked fewer than 128 units would be the wrong ship"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("oversized,graded_first", [(16, 14), (32, 21), (64, 36)])
    async def test_the_first_refinement_lands_on_beat_one_at_the_real_plan_size(
        self, drive, oversized, graded_first
    ):
        """The saving's mechanism, at 128 slots rather than 8.

        The graded tree must wait for a slot to earn a SECOND cancellation, and
        at the real plan size that wait is measured in tens of beats.
        """
        cand = await drive(
            buckets=128,
            oversized_slots=oversized,
            max_beats=200,
            withdrawn=True,
            ring_readable=True,
            reset_every=self.NO_INVALIDATION,
        )
        base = await drive(
            buckets=128,
            oversized_slots=oversized,
            max_beats=200,
            withdrawn=True,
            ring_readable=False,
            reset_every=self.NO_INVALIDATION,
        )

        assert cand.first_split_beat == 1, (
            f"the repair must cut on beat 1 at 128 slots; got {cand.first_split_beat}"
        )
        assert base.first_split_beat == graded_first, (
            f"graded tree first split expected {graded_first}; "
            f"got {base.first_split_beat}"
        )

    @pytest.mark.asyncio
    async def test_a_wholly_oversized_plan_still_publishes_nothing_in_either_arm(
        self, drive
    ):
        """THE HONEST ROW: where every slot outruns a window, this is not enough.

        Stated as its own test so the table above cannot be read as a claim that
        CAL-P1304 publishes any population. It buys 22 more banked units and 18
        more refinements here; it does not buy a publication.
        """
        cand = await drive(
            buckets=128,
            oversized_slots=128,
            max_beats=200,
            withdrawn=True,
            ring_readable=True,
            reset_every=self.NO_INVALIDATION,
        )
        base = await drive(
            buckets=128,
            oversized_slots=128,
            max_beats=200,
            withdrawn=True,
            ring_readable=False,
            reset_every=self.NO_INVALIDATION,
        )

        assert cand.completed_at is None and base.completed_at is None, (
            "neither arm publishes a wholly oversized plan inside 200 beats, "
            "and the ship is not sold as if it did"
        )
        assert (base.max_banked, cand.max_banked) == (129, 151), (
            f"banked: graded {base.max_banked} / repaired {cand.max_banked}, "
            "expected 129 / 151"
        )
        assert (base.splits, cand.splits) == (73, 91), (
            f"refinements: graded {base.splits} / repaired {cand.splits}, "
            "expected 73 / 91"
        )


# =============================================================================
# 9. THE SECOND FENCE — the futures PHASE BUDGET, which no arm above exercises
# =============================================================================


class TestTheSecondFenceIsThePhaseBudget:
    """🔴 **The candidate is INERT in the regime production is in TODAY.**

    Every class above runs with ``statement_timeout_ms=None`` on the futures
    budget, so ``statement_timeout_for`` returns the deadline bound and the
    PHASE term has never been exercised by this rig. Production carries a
    measured one, and it is what is currently stopping the repair.

    ## The row, read 07:50-07:53Z 2026-09-19

    ``durable_state_snapshots``, identity ``calibration:main:phase_ledger``,
    generation ``1789799874144`` = the **06:37:54Z** beat. Two units, and the
    whole point is that they are fenced by two DIFFERENT things:

    ======================  ==================  ==================
    ..                       slot 103 (unit 1)   slot 104 (unit 2)
    ======================  ==================  ==================
    armed bound             1,253,522 ms        65,272 ms
    source of the bound     the PHASE BUDGET    the window (scraps)
    ran before cancelling   1,255,944 ms        65,847 ms
    remaining when armed    1,352,256 ms        72,522 ms
    headroom                98,734 ms           7,250 ms
    headroom ceiling        30,000 ms           7,252 ms
    condition 1 (window)    **no**              yes
    condition 2 (outran)    yes                 **no**
    ======================  ==================  ==================

    The unit-1 reconstruction is exact rather than inferred:
    ``plan.futures.statement_timeout_ms`` is 1,253,522 and the unit ran
    1,255,944 — 2,422 ms over, which is what a Postgres cancellation costs. The
    deadline bound at that moment was 1,322,256, so ``min(phase_bound,
    unit_bound)`` picked the phase budget and not the window.

    ## Where that budget comes from, and why it is not going to widen

    ``plan.futures.budget_basis`` is ``measured_elastic_cut``::

        max(history.futures) = 873,486        # a COMPLETED phase duration
          x BUDGET_SAFETY (1.5) = 1,310,229
          elastic cut           -> budget_ms = 1,283,522
          - STATEMENT_INNER_MARGIN_MS         -> 1,253,522   # the row, exactly

    Condition 1 declines because *"the build can still hand this slot a bigger
    bound on a beat with more room"*. For a per-unit measured basis that is
    right. For the phase budget it is false — it is not a per-unit basis at all,
    it does not grow with room, and ``history.futures`` only appends when the
    phase COMPLETES, which it has not done in forty beats. The fence is frozen.

    🪤 **This does not make the shipped discriminator tests wrong.**
    :class:`TestTheDiscriminatorOnTheRealSpecimen` reads the 2026-09-17T17:37:55Z
    beat, where unit 1 WAS window-bounded at 1,320,000 ms and the predicate
    fires. Production moved into a different regime between grading and release.
    A granted token is a statement about a sha and the world it was measured in.

    ## What that costs, measured

    Same population, same latched state, same absent era, same 1,380,000 ms
    deadline — only the phase budget differs:

    =========  ======================  =====================
    oversized   with the phase budget   without (every arm above)
    =========  ======================  =====================
    16         first split **14**      first split 1
    32         first split **21**      first split 1
    64         first split **36**      first split 1
    =========  ======================  =====================

    14 / 21 / 36 are the GRADED TREE's own first-split beats
    (:meth:`TestTheProductionRegimeIsNotAnEraAndTheBuildPublishesInIt.test_the_first_refinement_lands_on_beat_one_at_the_real_plan_size`).
    The candidate does not merely lose ground here — it reproduces the tree it
    was written to beat. **This class is the failing BEFORE for the next
    candidate, and it is not itself a fix.**
    """

    #: Production's measured regime: forty consecutive resumable beats.
    NO_INVALIDATION = None

    # -- the predicate, on the 06:37:54Z row's own two units -----------------

    def test_the_unit_fenced_by_the_phase_budget_is_declined_by_the_INFERENCE(self):
        """Unit 1 under the headroom rule: outran the ring, declined anyway.

        1,255,944 >= 1,181,085, so condition 2 holds — which is precisely what
        ``00fca1140`` restored by making the ring legible beside a withdrawn
        basis. Condition 1 is what refuses it: 98,734 ms of headroom against a
        30,000 ms ceiling, because the fence was the phase budget.

        Kept as the BEFORE, and it is still live behaviour: ``bound_source=None``
        is what every caller that has not been taught to carry the source gets,
        and CAL-P1305 deliberately did not change it.
        """
        assert not pcl.cancellation_is_conclusive(
            remaining_ms=1_352_256,
            bound_ms=PROD_PHASE_STATEMENT_TIMEOUT_MS,
            cancelled_after_ms=PROD_UNIT1_CANCELLED_AFTER_MS,
            worst_completed_ms=PROD_UNIT_WORST_MS,
        )

    def test_the_same_unit_is_a_proof_once_the_caller_NAMES_the_fence(self):
        """⭐ CAL-P1305, the whole fix, on production's own row.

        Nothing about the unit changes — same remaining, same bound, same
        duration, same ring. The caller stops making the predicate guess where
        1,253,522 ms came from, and the answer inverts.
        """
        assert pcl.cancellation_is_conclusive(
            remaining_ms=1_352_256,
            bound_ms=PROD_PHASE_STATEMENT_TIMEOUT_MS,
            cancelled_after_ms=PROD_UNIT1_CANCELLED_AFTER_MS,
            worst_completed_ms=PROD_UNIT_WORST_MS,
            bound_source=pcl.UNIT_BOUND_PHASE_BUDGET,
        )

    def test_a_named_UNIT_BASIS_fence_still_defers_and_that_is_the_whole_limit(self):
        """The fix admits one source, not all three.

        A measured per-unit basis is the one fence that widens for this slot on
        its own — a completion at the larger size admits the larger bound — so a
        unit stopped by it has still proved nothing, exactly as before. Without
        this row the change would read as "stop deferring", which is not what it
        does.
        """
        assert not pcl.cancellation_is_conclusive(
            remaining_ms=1_352_256,
            bound_ms=PROD_PHASE_STATEMENT_TIMEOUT_MS,
            cancelled_after_ms=PROD_UNIT1_CANCELLED_AFTER_MS,
            worst_completed_ms=PROD_UNIT_WORST_MS,
            bound_source=pcl.UNIT_BOUND_UNIT_BASIS,
        )

    def test_the_arming_side_names_the_phase_budget_on_productions_own_numbers(self):
        """The source is a FACT the build computes, not a label the test asserts.

        The predicate is only as good as what the caller hands it, so the arming
        side gets its own row: with production's plan and its 06:37:54Z window,
        :meth:`statement_timeout_for_unit_detail` must return 1,253,522 ms and
        say PHASE BUDGET. The ``.ms`` half is asserted equal to what
        ``statement_timeout_for_unit`` has always returned, so this pair can
        never drift into two different numbers.
        """
        ledger = _ledger(
            window_ms=PROD_DEADLINE_MS,
            unit_ms=None,
            unit_ms_worst=None,
            unit_ms_worst_observed=PROD_UNIT_WORST_MS,
            units_done=1,
            buckets=128,
            phase_statement_timeout_ms=PROD_PHASE_STATEMENT_TIMEOUT_MS,
        )
        bound = ledger.statement_timeout_for_unit_detail(PHASE_FUTURES, elapsed_ms=0)
        assert bound.source == pcl.UNIT_BOUND_PHASE_BUDGET
        assert bound.ms == PROD_PHASE_STATEMENT_TIMEOUT_MS
        assert bound.ms == ledger.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)

    def test_the_same_plan_without_that_budget_names_the_WINDOW(self):
        """The control for the row above: only the budget moves, and the name does.

        A source that reported ``phase_budget`` for every unit would pass the
        test above while saying nothing, so the discriminating case is asserted
        beside it.
        """
        ledger = _ledger(
            window_ms=PROD_DEADLINE_MS,
            unit_ms=None,
            unit_ms_worst=None,
            unit_ms_worst_observed=PROD_UNIT_WORST_MS,
            units_done=1,
            buckets=128,
            phase_statement_timeout_ms=None,
        )
        bound = ledger.statement_timeout_for_unit_detail(PHASE_FUTURES, elapsed_ms=0)
        assert bound.source == pcl.UNIT_BOUND_WINDOW
        assert bound.ms == ledger.statement_timeout_for_unit(PHASE_FUTURES, elapsed_ms=0)

    def test_condition_two_does_hold_on_that_unit_so_the_ring_repair_is_not_what_failed(
        self,
    ):
        """The half ``00fca1140`` owns works; it is the other fence that bites.

        Stated separately so a flat ``rebuild_units_banked`` after the release
        is not read as a falsification of the ring repair.
        """
        assert PROD_UNIT1_CANCELLED_AFTER_MS >= PROD_UNIT_WORST_MS
        assert pcl.cancellation_is_conclusive(
            remaining_ms=1_352_256,
            # The same unit, same beat, had the phase term not bound it: the
            # deadline bound was 1,322,256, leaving exactly the 30,000 ms margin.
            bound_ms=1_322_256,
            cancelled_after_ms=PROD_UNIT1_CANCELLED_AFTER_MS,
            worst_completed_ms=PROD_UNIT_WORST_MS,
        )

    def test_the_scraps_unit_is_declined_for_the_other_reason(self):
        """Unit 2: window-bounded to the millisecond, and rightly declined.

        7,250 ms of headroom against a 7,252 ms ceiling — condition 1 holds —
        but 65,847 ms is no evidence about a slot whose population completes at
        1,181,085 ms. This is the predicate working as designed, and it means
        the beat has no unit that satisfies both conditions.
        """
        remaining = PROD_UNIT2_BOUND_MS + 7_250
        assert pcl.deadline_bound_headroom_ceiling_ms(remaining) == 7_252
        assert not pcl.cancellation_is_conclusive(
            remaining_ms=remaining,
            bound_ms=PROD_UNIT2_BOUND_MS,
            cancelled_after_ms=PROD_UNIT2_CANCELLED_AFTER_MS,
            worst_completed_ms=PROD_UNIT_WORST_MS,
        )
        # CAL-P1305 changes condition 1 and nothing else, so naming this unit's
        # fence — it really was the window — must not rescue it. Condition 2 is
        # what declines here, and 65,847 ms is still no evidence about a slot
        # whose population completes at 1,181,085 ms.
        assert not pcl.cancellation_is_conclusive(
            remaining_ms=remaining,
            bound_ms=PROD_UNIT2_BOUND_MS,
            cancelled_after_ms=PROD_UNIT2_CANCELLED_AFTER_MS,
            worst_completed_ms=PROD_UNIT_WORST_MS,
            bound_source=pcl.UNIT_BOUND_WINDOW,
        )

    # -- the same thing, driven through the real beat loop -------------------

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "oversized,fenced_first_split,fenced_publish,free_publish",
        [(16, 1, 43, 43), (32, 1, 83, 83), (64, 1, 160, 160)],
    )
    async def test_the_phase_budget_no_longer_erases_the_beat_one_cut(
        self, drive, oversized, fenced_first_split, fenced_publish, free_publish
    ):
        """⭐ CAL-P1305 through the real beat loop, at production's plan size.

        Both arms are the candidate — ``ring_readable=True`` in each — so the
        difference cannot be attributed to CAL-P1304. The only thing that moves
        is whether the futures budget fences the unit, and with the fence NAMED
        it no longer costs the cut: the fenced arm cuts on beat 1 and publishes
        on the same beat as the arm that was never fenced at all.

        Before CAL-P1305 this same table read ``(16, 14, 46, 43)``,
        ``(32, 21, 90, 83)``, ``(64, 36, 174, 160)`` — the graded tree's own
        first-split beats, i.e. the candidate contributing nothing in the regime
        production is actually in. Those numbers are the BEFORE and are the
        reason this class was written.
        """
        fenced = await drive(
            buckets=128,
            oversized_slots=oversized,
            max_beats=200,
            withdrawn=True,
            ring_readable=True,
            reset_every=self.NO_INVALIDATION,
            window_ms=PROD_DEADLINE_MS,
            phase_statement_timeout_ms=PROD_PHASE_STATEMENT_TIMEOUT_MS,
        )
        free = await drive(
            buckets=128,
            oversized_slots=oversized,
            max_beats=200,
            withdrawn=True,
            ring_readable=True,
            reset_every=self.NO_INVALIDATION,
            window_ms=PROD_DEADLINE_MS,
            phase_statement_timeout_ms=None,
        )

        assert fenced.first_armed[0] == PROD_PHASE_STATEMENT_TIMEOUT_MS, (
            "the fenced arm must arm its first unit at production's own bound; "
            f"got {fenced.first_armed[0]}"
        )
        assert free.first_split_beat == 1, (
            "the control must still cut on beat 1, or this measures the rig "
            f"rather than the fence; got {free.first_split_beat}"
        )
        assert fenced.first_split_beat == fenced_first_split, (
            f"{oversized}/128 fenced first split expected {fenced_first_split}; "
            f"got {fenced.first_split_beat}"
        )
        assert (fenced.completed_at, free.completed_at) == (
            fenced_publish,
            free_publish,
        ), (
            f"{oversized}/128 publish: fenced {fenced.completed_at} / free "
            f"{free.completed_at}, expected {fenced_publish} / {free_publish}"
        )

    @pytest.mark.asyncio
    async def test_the_fenced_first_splits_are_no_longer_the_graded_trees_own_numbers(
        self, drive
    ):
        """The candidate stops reproducing the tree it was written to beat.

        Asserted as its own row because it is the finding, not a detail: with
        the phase budget binding AND named, ``cancellation_is_conclusive`` cuts
        on beat one at every plan size production runs — where it previously
        contributed nothing at all.
        """
        graded_first_splits = {16: 1, 32: 1, 64: 1}
        measured = {}
        for oversized in graded_first_splits:
            fenced = await drive(
                buckets=128,
                oversized_slots=oversized,
                max_beats=200,
                withdrawn=True,
                ring_readable=True,
                reset_every=self.NO_INVALIDATION,
                window_ms=PROD_DEADLINE_MS,
                phase_statement_timeout_ms=PROD_PHASE_STATEMENT_TIMEOUT_MS,
            )
            measured[oversized] = fenced.first_split_beat

        assert measured == graded_first_splits, (
            "with the phase budget fencing every first unit the candidate is "
            f"inert; expected the graded tree's {graded_first_splits}, got "
            f"{measured}"
        )
