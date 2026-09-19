"""CAL-P1304 (#6599, repairing CERT-3051) — a withdrawal is not an erasure.

CERT-3051 blocked PR #6817's conclusive-cancellation cut with two findings, and
this file is the guard for both repairs.

── FINDING 1: the cut was inert on the only row it was written for ────────────

``cancellation_is_conclusive`` asks two questions, and the second is *did this
unit run longer than the longest unit this build has ever COMPLETED?* Production
could not answer it. ``unit_costs.futures`` carried
``{'units_done': 1, 'units_total': 128, 'level_refuted': True}`` — CAL-P1300's
withdrawal marker — and ``load_phase_measurements`` skips the worst-unit fold
while that marker is set, so ``worst_completed_ms`` resolved empty and the
predicate declined. The ring was intact the whole time: 24 genuine completions,
worst 1,181,085 ms, unreadable.

The skip itself is right and is UNCHANGED here. Withdrawing the level means the
next unit must not be admitted against ``1.5 x worst``, which on the #6275
specimen was 403,347 ms — TIGHTER than the 483,000 ms bound that had just been
proven too small, i.e. exactly the closed door the withdrawal exists to open.

What was wrong is that the same marker also erased the ring as a FACT. So the
two readings are now two fields: ``unit_ms_worst`` is the admission BASIS and is
still withheld, ``unit_ms_worst_observed`` is the observation and never is. A
bound may be withdrawn; a completion may not be un-observed.

── FINDING 2: the withdrawal outlived the evidence for it ─────────────────────

The marker was designed to extinguish itself on the next completion, because
``_unit_costs_from`` then builds a fresh dict without it. That is the only exit
it had, and it assumes the wide honest attempt the withdrawal buys either
completes or refutes the level again. Since #6599 corrected
``_level_refuted_by_cancellation``'s third condition, a unit cancelled by the
WINDOW does neither — so ``_carry_unit_costs``'s non-refuted path found the
withdrawn entry truthy, re-stamped ``units_done``, and carried the marker
forward unexamined. Production held it for fourteen hours at 1 of 128 units
banked. Reaching that branch IS the re-evaluation, and an unsupported claim is
now dropped there rather than inherited.

── FINDING 3: every era threw away what the last one learned ──────────────────

``carry_refinement``. An invalidation must discard the bank — those are rows
computed against inputs we can no longer vouch for — but ``unit_splits`` is not
rows. It is one sentence about the SHAPE of the work (*slot 37 of 128 is too
expensive for one statement*), it is bounded by an existing ceiling, and the
census is partition-invariant, so keeping it cannot change a published number.
Discarding it is what made the build re-learn the same thing every era and
publish nothing. The era threshold this moves is measured in
``test_calibration_oversized_slot_is_cut_on_its_proof_6599.py``
(``TestTheLimitThisCandidateDoesNotReach``): 24 beats to 16.

Every number below is production's own, from the row #6599 was filed on.
"""

from __future__ import annotations

import pytest

from app.tasks import calibration_main_build as cmb
from app.utils import calibration_staged_futures as sf
from app.utils.calibration_phase_ledger import (
    PHASE_FUTURES,
    PhaseBudget,
    PhaseLedger,
    PhasePlan,
    derive_plan,
)

#: ``unit_worst_history['futures']`` as the durable row carries it — 24 real
#: completions, the last of them the one the cut needs to compare against.
PROD_WORST_RING = [
    217_564, 170_991, 228_426, 208_277, 205_168, 226_716, 318_050, 246_180,
    200_187, 199_446, 181_321, 189_981, 260_459, 180_105, 195_359, 175_089,
    256_688, 193_207, 156_509, 181_332, 194_011, 171_845, 222_972, 1_181_085,
]
PROD_WORST_MS = 1_181_085
#: ``unit_costs.futures``, verbatim, on the beat #6599 was filed from.
PROD_LATCHED_COST = {"units_done": 1, "units_total": 128, "level_refuted": True}


def _plan_for(unit_costs: dict) -> PhasePlan:
    return derive_plan(
        {PHASE_FUTURES: [600_000]},
        unit_costs=unit_costs,
        phases=(PHASE_FUTURES,),
    )


def _ledger_for(unit_costs: dict) -> PhaseLedger:
    """A ledger whose plan was derived the way a real beat derives it."""
    return PhaseLedger(
        plan=_plan_for(unit_costs),
        population_version="q271",
        owner="test:1",
        generation=1,
        input_fingerprint="fp",
    )


#: The #6275 specimen: a unit killed by the LEVEL's own fence, which leaves far
#: more headroom than a deadline bound ever could. Verified against
#: ``deadline_bound_headroom_ceiling_ms`` by ``test_the_rig_refutes_only_where_
#: production_did`` below, so no test here rests on an unchecked arithmetic.
REFUTING_BOUND_MS = 483_000
REFUTING_HEADROOM_MS = 347_841
#: The #6599 specimen: the same shape bounded by the WINDOW, which is not a
#: refutation and is the correction PR #6817 shipped.
WINDOW_BOUND_MS = 59_087
WINDOW_HEADROOM_MS = 6_565


class _Ledger:
    """Exactly the reads ``_carry_unit_costs`` and its two predicates take.

    Deliberately not a ``Mock``: a stub that answers every attribute would let
    a carry that consulted something else entirely pass as one that did not,
    and #6732 found five suites where precisely that happened.
    """

    def __init__(self, *, stage_counts=None, stages=None, completed_mean_ms=None):
        self.stage_counts = dict(stage_counts or {})
        self.stages = dict(stages or {})
        self._completed_mean_ms = completed_mean_ms
        self.gauges: dict[str, int] = {}

    def stage_completed_mean_ms(self, _stage):
        return self._completed_mean_ms

    def record_gauge(self, name, value):
        self.gauges[name] = value


class _Runner:
    def __init__(self, ledger):
        self.ledger = ledger


def _beat(*, refutes: bool, banked: int = 1) -> _Runner:
    """A beat as ``_level_refuted_by_cancellation`` reads one.

    ``refutes=False`` is an ordinary beat: units ran and one completed, so the
    predicate stops at its second condition. ``refutes=True`` is the #6275
    specimen: units ran, none completed, and the headroom the fence recorded is
    far past anything a window bound could leave.
    """
    stages = {"staged:units_banked": banked}
    if refutes:
        stages["staged:units_cancelled"] = 2
        stages[f"staged:unit_bound_headroom_ms:{PHASE_FUTURES}"] = REFUTING_HEADROOM_MS
        stages[f"staged:unit_bound_ms:{PHASE_FUTURES}"] = REFUTING_BOUND_MS
    return _Runner(
        _Ledger(
            stage_counts={cmb.STAGED_UNIT_STAGE: 2},
            stages=stages,
            completed_mean_ms=None if refutes else 180_000,
        )
    )


# =============================================================================
# 1. THE RING IS EVIDENCE, AND A WITHDRAWAL DOES NOT UN-OBSERVE IT
# =============================================================================


class TestTheWithdrawalWithholdsTheBasisAndNotTheFact:
    def test_the_latched_row_still_yields_the_worst_completion(self):
        """Production's own row, through the real plan. The headline repair."""
        ledger = _ledger_for(
            {
                PHASE_FUTURES: {
                    **PROD_LATCHED_COST,
                    "unit_ms_worst_observed": PROD_WORST_MS,
                }
            }
        )

        assert ledger.observed_unit_worst_ms(PHASE_FUTURES) == PROD_WORST_MS, (
            "the 24 completions in the ring are what the cut compares against; "
            "unreadable, it declines on the rows the defect is worst on"
        )

    def test_the_admission_basis_is_still_withheld_on_that_same_row(self):
        """The half of CAL-P1300 that must NOT move.

        If this ever returns a number, the next unit is admitted against
        ``1.5 x worst`` — on the #6275 specimen 403,347 ms against a 483,000 ms
        bound already proven too small — and the door #6275 opened shuts again.
        """
        ledger = _ledger_for(
            {
                PHASE_FUTURES: {
                    **PROD_LATCHED_COST,
                    "unit_ms_worst_observed": PROD_WORST_MS,
                }
            }
        )

        assert ledger.measured_unit_worst_ms(PHASE_FUTURES) is None

    def test_an_unwithdrawn_level_reports_the_same_number_to_both(self):
        """The ordinary case: one ring, two readings, no daylight between them."""
        ledger = _ledger_for(
            {
                PHASE_FUTURES: {
                    "unit_ms": 220_000,
                    "units_total": 128,
                    "units_done": 40,
                    "unit_ms_worst": PROD_WORST_MS,
                    "unit_ms_worst_observed": PROD_WORST_MS,
                }
            }
        )

        assert (
            ledger.measured_unit_worst_ms(PHASE_FUTURES)
            == ledger.observed_unit_worst_ms(PHASE_FUTURES)
            == PROD_WORST_MS
        )

    def test_a_plan_that_predates_the_field_still_reports_its_observation(self):
        """The fallback, and why it is not a convenience.

        ``unit_ms_worst`` is ITSELF a worst completed duration. A budget built
        before ``unit_ms_worst_observed` existed — or by any caller that fills
        the basis directly — holds the observation under the other key, and
        reporting ``None`` for it would say "nothing has ever completed" while
        holding the number.
        """
        ledger = PhaseLedger(
            plan=PhasePlan(
                budgets=(
                    PhaseBudget(
                        name=PHASE_FUTURES,
                        required=True,
                        budget_ms=600_000,
                        statement_timeout_ms=600_000,
                        measured_input=True,
                        unit_ms_worst=PROD_WORST_MS,
                    ),
                )
            ),
            population_version="q271",
            owner="test:1",
            generation=1,
            input_fingerprint="fp",
        )

        assert ledger.observed_unit_worst_ms(PHASE_FUTURES) == PROD_WORST_MS

    def test_nothing_completed_anywhere_is_still_none_and_never_zero(self):
        """Gotcha #53 in a return value: absent may not read as a measured 0.

        A zero here would make ``cancelled_after_ms > worst_completed_ms`` true
        for every cancellation ever, and the cut would fire on no evidence at
        all — which is the ruling-075 mutant the subject's own battery kills.
        """
        ledger = _ledger_for({PHASE_FUTURES: dict(PROD_LATCHED_COST)})

        assert ledger.observed_unit_worst_ms(PHASE_FUTURES) is None
        assert ledger.measured_unit_worst_ms(PHASE_FUTURES) is None


class TestTheFoldWritesBothKeysFromOneRing:
    @pytest.mark.asyncio
    async def test_a_withdrawn_level_gets_the_observation_and_not_the_basis(
        self, monkeypatch
    ):
        """``load_phase_measurements`` on production's exact carried state."""

        async def _carry():
            return (
                {PHASE_FUTURES: [600_000]},
                {},
                {PHASE_FUTURES: dict(PROD_LATCHED_COST)},
                {PHASE_FUTURES: list(PROD_WORST_RING)},
            )

        monkeypatch.setattr(cmb, "load_phase_carryover", _carry)

        _history, _floors, merged = await cmb.load_phase_measurements()

        assert merged[PHASE_FUTURES]["unit_ms_worst_observed"] == PROD_WORST_MS
        assert "unit_ms_worst" not in merged[PHASE_FUTURES], (
            "the basis stays withheld — this is CAL-P1300's fix, not a regression"
        )

    @pytest.mark.asyncio
    async def test_an_ordinary_level_gets_both(self, monkeypatch):
        async def _carry():
            return (
                {PHASE_FUTURES: [600_000]},
                {},
                {PHASE_FUTURES: {"unit_ms": 220_000, "units_total": 128, "units_done": 40}},
                {PHASE_FUTURES: list(PROD_WORST_RING)},
            )

        monkeypatch.setattr(cmb, "load_phase_carryover", _carry)

        _history, _floors, merged = await cmb.load_phase_measurements()

        assert merged[PHASE_FUTURES]["unit_ms_worst"] == PROD_WORST_MS
        assert merged[PHASE_FUTURES]["unit_ms_worst_observed"] == PROD_WORST_MS


# =============================================================================
# 2. THE WITHDRAWAL EXPIRES WHEN ITS EVIDENCE DOES
# =============================================================================


class TestTheRefutationIsReEvaluatedAndNotLatched:
    def test_the_rig_refutes_only_where_production_did(self):
        """THE RIG'S OWN CONTROL, before anything below is believed.

        Both arms of ``_beat`` are put to the real predicate, and the window
        specimen is put to it too. If the "non-refuting" arm ever started
        refuting, every expiry test below would pass by never reaching the
        branch it names — the vacuous-guard failure this asserts away.
        """
        assert cmb._level_refuted_by_cancellation(_beat(refutes=True)) is True
        assert cmb._level_refuted_by_cancellation(_beat(refutes=False)) is False

        window_bounded = _beat(refutes=True)
        window_bounded.ledger.stages[
            f"staged:unit_bound_headroom_ms:{PHASE_FUTURES}"
        ] = WINDOW_HEADROOM_MS
        window_bounded.ledger.stages[f"staged:unit_bound_ms:{PHASE_FUTURES}"] = (
            WINDOW_BOUND_MS
        )
        assert cmb._level_refuted_by_cancellation(window_bounded) is False, (
            "PR #6817's correction: a unit the WINDOW killed refutes nothing"
        )

    def test_a_beat_that_does_not_refute_clears_the_marker(self):
        """Production's latched row through one ordinary beat.

        Units ran and one completed, so neither predicate fires. Before this
        repair the marker came out the other side untouched and the ring stayed
        unreadable for another beat, and the next, and the next.
        """
        runner = _beat(refutes=False, banked=7)

        carried = cmb._carry_unit_costs(runner, {PHASE_FUTURES: dict(PROD_LATCHED_COST)})

        assert cmb.LEVEL_REFUTED_KEY not in carried[PHASE_FUTURES]
        assert (
            runner.ledger.gauges.get(
                f"{cmb.UNIT_COST_REASON_PREFIX}refutation_expired"
            )
            == 1
        ), "a withdrawal and its expiry are two events and neither may be silent"

    def test_the_progress_facts_survive_the_expiry(self):
        """Clearing the claim is not clearing the bookkeeping.

        ``units_total`` and ``units_done`` are what the operator window reads,
        and ``units_done`` is re-stamped from this beat's own cursor reading.
        """
        runner = _beat(refutes=False, banked=7)

        carried = cmb._carry_unit_costs(runner, {PHASE_FUTURES: dict(PROD_LATCHED_COST)})

        assert carried[PHASE_FUTURES]["units_total"] == 128
        assert carried[PHASE_FUTURES]["units_done"] == 7

    def test_the_withdrawn_mean_does_not_come_back_with_it(self):
        """Only a COMPLETION restores ``unit_ms``, and this is not one.

        The expiry returns the ring to the basis; it does not re-assert a mean
        nobody measured. If this ever carried a ``unit_ms``, the fence would be
        ``max(4 x mean, 1.5 x worst)`` built partly on a level the build had
        already withdrawn.
        """
        runner = _beat(refutes=False, banked=7)

        carried = cmb._carry_unit_costs(runner, {PHASE_FUTURES: dict(PROD_LATCHED_COST)})

        assert "unit_ms" not in carried[PHASE_FUTURES]

    def test_a_beat_that_refutes_again_re_sets_it(self):
        """THE CONTROL. The expiry may not become an unconditional clear.

        Units ran, none completed, and the fence that killed them was the
        level's own — so the refutation is live evidence on THIS beat and the
        marker belongs on the row. Without this, a latch bug is traded for a
        withdrawal that can never be written.
        """
        runner = _beat(refutes=True)
        assert cmb._level_refuted_by_cancellation(runner) is True, (
            "the rig must actually reproduce a refutation, or this control "
            "passes by not reaching the branch it is about"
        )

        carried = cmb._carry_unit_costs(runner, {PHASE_FUTURES: dict(PROD_LATCHED_COST)})

        assert carried[PHASE_FUTURES].get(cmb.LEVEL_REFUTED_KEY) is True
        assert (
            f"{cmb.UNIT_COST_REASON_PREFIX}refutation_expired"
            not in runner.ledger.gauges
        )

    def test_a_level_that_was_never_withdrawn_records_no_expiry(self):
        """The gauge names an event, not a beat. A clean level did not expire."""
        runner = _beat(refutes=False, banked=7)

        cmb._carry_unit_costs(
            runner,
            {PHASE_FUTURES: {"unit_ms": 220_000, "units_total": 128, "units_done": 7}},
        )

        assert (
            f"{cmb.UNIT_COST_REASON_PREFIX}refutation_expired"
            not in runner.ledger.gauges
        )


# =============================================================================
# 3. THE REFINEMENT CROSSES AN INVALIDATION; THE BANK DOES NOT
# =============================================================================


def _stored(**over) -> dict:
    """A cursor payload as ``save_staged_cursor`` writes one."""
    payload = {
        "schema": sf.STAGED_FUTURES_SCHEMA,
        "task": sf.MAIN_BUILD_TASK,
        "unit_key": sf.UNIT_KEY_VM_ID,
        "population_version": "q271",
        "input_fingerprint": "fp-old",
        "generation_fingerprint": "gen",
        "generation": 1,
        "owner": "beat:1",
        "lease_expires_at": 0.0,
        "committed_units": ["u1", "u2"],
        "accumulator": None,
        "unit_cancels": {"128:37": 2},
        "unit_splits": {"128:37": 4},
    }
    payload.update(over)
    return payload


def _decode(raw, *, version="q271", fingerprint="fp-old"):
    return sf.decode_staged_cursor_detailed(
        raw,
        expected_population_version=version,
        expected_input_fingerprint=fingerprint,
        expected_generation_fingerprint="gen",
        owner="beat:2",
        generation=2,
        now=0.0,
    )


class TestTheEarnedPartitionSurvivesAnInvalidation:
    def test_a_population_version_bump_keeps_the_refinement(self):
        cursor, action, _reason = _decode(_stored(), version="q272")

        assert action == sf.INVALIDATE
        assert cursor.unit_splits == {"128:37": 4}
        assert cursor.unit_cancels == {"128:37": 2}

    def test_a_deploy_that_moves_the_input_digest_keeps_it_too(self):
        """THE one that fires in practice, per the decoder's own comment."""
        cursor, action, _reason = _decode(_stored(), fingerprint="fp-new")

        assert action == sf.INVALIDATE
        assert cursor.unit_splits == {"128:37": 4}

    def test_the_bank_is_still_discarded_whole(self):
        """The half that may never soften. Rows outlive nothing.

        If a committed unit or an accumulator ever crossed this boundary, the
        payload would mix rows computed against two definitions of the same
        unit, which is the entire reason the digest exists.
        """
        cursor, action, _reason = _decode(
            _stored(committed_units=["u1", "u2"], accumulator="whatever"),
            version="q272",
        )

        assert action == sf.INVALIDATE
        assert cursor.committed_units == ()
        assert cursor.accumulator is None
        assert cursor.served_units == ()

    def test_a_different_partition_key_drops_it(self):
        """The exclusion that makes the rest safe.

        A cursor cut on another unit key has slot references that mean something
        else entirely, so ``128:37`` is not a claim about our slot 37 and may not
        be read as one.
        """
        cursor, action, _reason = _decode(_stored(unit_key="market_id"))

        assert action == sf.INVALIDATE
        assert cursor.unit_splits == {}
        assert cursor.unit_cancels == {}

    @pytest.mark.parametrize(
        "over", [{"schema": "other/v9"}, {"task": "some_other_task"}]
    )
    def test_an_unrecognised_payload_drops_it(self, over):
        cursor, action, _reason = _decode(_stored(**over))

        assert action == sf.INVALIDATE
        assert cursor.unit_splits == {}

    def test_a_payload_that_is_not_a_dict_drops_it_without_raising(self):
        cursor, action, _reason = _decode(["not", "a", "cursor"])

        assert action == sf.INVALIDATE
        assert cursor.unit_splits == {}

    def test_the_resume_path_is_unchanged(self):
        """The regression guard: a cursor that RESUMES still carries both maps.

        CAL-P1304 moved this decode into a shared helper, and a shared helper
        that changed the resume path would be a silent behaviour change on every
        healthy beat.
        """
        cursor, action, _reason = _decode(
            _stored(committed_units=[], accumulator=None, owner="beat:2")
        )

        assert action in (sf.RESUME, sf.FRESH)
        assert cursor.unit_splits == {"128:37": 4}
        assert cursor.unit_cancels == {"128:37": 2}


class TestTheCarriedRefinementIsReadWithTheSameRulesAsAResumedOne:
    @pytest.mark.parametrize(
        "splits",
        [
            {"not-a-ref": 4},
            {"128:999": 4},
            {"128:37": 1},
            {"128:37": True},
            {"128:37": "4"},
            "not a mapping",
        ],
    )
    def test_an_unreadable_entry_costs_that_entry_and_nothing_else(self, splits):
        cancels, kept = sf.refinement_from_raw({"unit_splits": splits, "unit_cancels": {"128:37": 2}})

        assert kept == {}
        assert cancels == {"128:37": 2}, (
            "a per-entry refusal may not take the sibling map with it"
        )

    def test_a_readable_entry_survives_beside_an_unreadable_one(self):
        _cancels, kept = sf.refinement_from_raw(
            {"unit_splits": {"128:37": 4, "128:999": 8}}
        )

        assert kept == {"128:37": 4}

    def test_nothing_stored_is_an_empty_pair_and_not_a_crash(self):
        assert sf.refinement_from_raw({}) == ({}, {})
        assert sf.refinement_from_raw(None) == ({}, {})

    def test_the_carry_returns_the_blank_untouched_when_there_is_nothing_to_keep(self):
        """Identity on the empty case, so a fresh cursor is not re-allocated
        into something subtly different from the one every other path returns."""
        blank = sf.new_staged_cursor(
            population_version="q271",
            input_fingerprint="fp",
            generation_fingerprint="gen",
            owner="beat:2",
            generation=2,
        )

        assert sf.carry_refinement(blank, {}) is blank
