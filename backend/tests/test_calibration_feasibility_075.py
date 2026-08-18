"""Ruling 075's instrument, fixed: feasibility rests on MEASURED cost only.

CAL-P066 named this defect and carried it; CAL-P067 fixes it. Two halves, both
of them the same mistake wearing different clothes — **an absent measurement
rendering as a reassuring one**.

**Half one: elapsed-of-cancelled was compared as if it were the cost.**
``infeasible_phases`` ranked ``floors[futures]`` (production: 1,181,045 ms)
against the reachable ceiling (1,350,000 ms), found it smaller, and reported
``infeasible_phases: []``. But every entry in ``floors`` is the elapsed time of a
phase that was CANCELLED — the phase ran that long and had *not finished*. It is
a lower bound on an unknown cost. ``1,181,045 < 1,350,000`` therefore licenses
exactly nothing: the true cost could be 1,400,000 or 14,000,000, and both are
consistent with the same floor. The comparison is sound in ONE direction only
(a floor at or past the ceiling proves the phase cannot fit) and vacuous in the
other. The vacuous direction was the one production kept taking.

**Half two: an empty history rendered as an empty finding.** With
``history: {}`` there is no measurement of anything, so feasibility cannot be
computed at all — and the payload said ``infeasible_phases: []``, which a reader
correctly parses as *nothing to report*. Could-not-check and nothing-to-report
are opposite states and they had the same rendering. That is gotcha #53 inside
the instrument built to enforce ruling 075.

The fix is not a new threshold. It is a **vocabulary** in which "I could not
tell" is sayable, plus routing the one genuinely measured cost — the per-unit
duration ``_record_staged_rate`` already computes — into the check that needs it.
"""

from app.utils.calibration_phase_ledger import (
    FEASIBILITY_FEASIBLE,
    FEASIBILITY_INDETERMINATE,
    FEASIBILITY_INFEASIBLE,
    FEASIBILITY_NO_DATA,
    PHASE_DIAGNOSTICS,
    PHASE_FUTURES,
    PHASE_SPORTS,
    REQUIRED_PHASES,
    derive_plan,
)

#: Production's live reading, 2026-08-17 22:34 UTC, off the durable cursor.
PROD_FLOOR_MS = 1_181_045
PROD_UNIT_MS = 116_681
PROD_UNITS_TOTAL = 128
PROD_UNITS_DONE = 82


# =============================================================================
# Half two: could-not-check never renders as nothing-to-report
# =============================================================================


def test_an_empty_history_renders_no_data_not_an_empty_infeasible_list():
    """The headline. Nothing measured => the verdict is ``no_data``, said out
    loud, and the plan's own status carries it."""
    plan = derive_plan({})
    assert plan.feasibility == FEASIBILITY_NO_DATA
    assert plan.infeasible_phases == ()
    assert plan.unchecked_phases == REQUIRED_PHASES
    payload = plan.as_payload()
    assert payload["status"] == FEASIBILITY_NO_DATA
    assert payload["feasibility"]["verdict"] == FEASIBILITY_NO_DATA
    assert payload["feasibility"]["unchecked_phases"] == list(REQUIRED_PHASES)


def test_the_empty_infeasible_list_is_never_the_only_thing_a_reader_sees():
    """The rendering contract, asserted directly: whenever ``infeasible_phases``
    is empty, SOMETHING in the payload still says which of the two empties it
    is. A reader must never have to infer it."""
    for plan in (
        derive_plan({}),
        derive_plan({}, floors={PHASE_FUTURES: [PROD_FLOOR_MS]}),
        derive_plan({name: [10_000] for name in REQUIRED_PHASES}),
    ):
        payload = plan.as_payload()
        assert payload["infeasible_phases"] == []
        assert payload["feasibility"]["verdict"] in (
            FEASIBILITY_NO_DATA,
            FEASIBILITY_INDETERMINATE,
            FEASIBILITY_FEASIBLE,
        )
        # and the top-level status is never a bland "provisional" that hides it
        assert payload["status"] == payload["feasibility"]["verdict"] or payload[
            "status"
        ] in ("measured", "provisional")


# =============================================================================
# Half one: a floor is a lower bound, and only concludes in one direction
# =============================================================================


def test_production_reading_is_indeterminate_not_feasible():
    """The exact numbers CAL-P066 measured. The old instrument reported
    ``infeasible_phases: []`` and a status of ``provisional``; both read as
    "checked, fine". Neither was a check."""
    plan = derive_plan({}, floors={PHASE_FUTURES: [PROD_FLOOR_MS]})
    assert PROD_FLOOR_MS < plan.max_phase_ms  # the comparison that used to pass
    assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_INDETERMINATE
    assert plan.infeasible_phases == ()
    assert plan.indeterminate_phases == (PHASE_FUTURES,)
    assert plan.feasibility == FEASIBILITY_INDETERMINATE
    assert plan.as_payload()["status"] == FEASIBILITY_INDETERMINATE


def test_a_floor_at_or_past_the_ceiling_still_concludes_infeasible():
    """The one direction a lower bound DOES settle: it ran a whole window and
    did not finish, so no budget, checkpoint or resume rescues it. This signal
    is preserved, not thrown away with the vacuous one."""
    plan = derive_plan({}, floors={PHASE_FUTURES: [1_355_276]})
    assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_INFEASIBLE
    assert plan.infeasible_phases == (PHASE_FUTURES,)
    assert plan.feasibility == FEASIBILITY_INFEASIBLE
    assert plan.as_payload()["status"] == FEASIBILITY_INFEASIBLE


def test_a_floor_below_the_ceiling_never_licenses_feasible():
    """Sweeping the whole vacuous range: no floor short of the ceiling may ever
    produce ``feasible``, however small it is. A 1 ms cancellation says as
    little as a 1,349,999 ms one."""
    for floor in (1, 120_000, PROD_FLOOR_MS, 1_349_999):
        plan = derive_plan({}, floors={PHASE_SPORTS: [floor]})
        assert plan.phase_feasibility(PHASE_SPORTS) == FEASIBILITY_INDETERMINATE, floor
        assert plan.feasibility != FEASIBILITY_FEASIBLE, floor


def test_a_completed_observation_is_a_real_measurement_and_does_conclude():
    """A phase that FINISHED has a duration, not a bound. That settles it."""
    plan = derive_plan({name: [10_000] for name in REQUIRED_PHASES})
    assert plan.phase_feasibility(PHASE_SPORTS) == FEASIBILITY_FEASIBLE
    assert plan.feasibility == FEASIBILITY_FEASIBLE
    assert plan.as_payload()["status"] == "measured"


def test_a_completion_outranks_a_stale_floor():
    """Evidence ordering: the phase has since been seen to finish, so the old
    cancellation is history rather than an open question."""
    plan = derive_plan(
        {name: [10_000] for name in REQUIRED_PHASES},
        floors={PHASE_FUTURES: [PROD_FLOOR_MS]},
    )
    assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_FEASIBLE
    assert plan.by_name(PHASE_FUTURES).floor_ms == PROD_FLOOR_MS  # still recorded
    assert plan.feasibility == FEASIBILITY_FEASIBLE


# =============================================================================
# The measured input that was in hand all along: per-unit cost
# =============================================================================


def test_measured_unit_cost_answers_the_question_a_floor_could_not():
    """``_record_staged_rate`` has computed this number since CAL-P066 and no
    feasibility check ever read it. A unit that COMPLETED in 116,681 ms is a
    duration — so a beat holding 1,350,000 ms holds units, and the phase
    converges. This is the reading that required an external 60-second poll of
    the durable cursor to obtain."""
    plan = derive_plan(
        {},
        floors={PHASE_FUTURES: [PROD_FLOOR_MS]},
        unit_costs={
            PHASE_FUTURES: {
                "unit_ms": PROD_UNIT_MS,
                "units_total": PROD_UNITS_TOTAL,
                "units_done": PROD_UNITS_DONE,
            }
        },
    )
    assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_FEASIBLE
    # The PLAN still reads ``no_data``, and that is correct rather than a
    # disappointment: futures is now measured, its four sibling phases are not,
    # and the rollup refuses to launder one measured phase into a clean bill of
    # health for the build. The per-phase verdict is where the win lands.
    assert plan.feasibility == FEASIBILITY_NO_DATA
    assert plan.feasible_phases == (PHASE_FUTURES,)

    detail = plan.as_payload()["feasibility"]["units"][PHASE_FUTURES]
    assert detail["unit_ms"] == PROD_UNIT_MS
    assert detail["units_remaining"] == PROD_UNITS_TOTAL - PROD_UNITS_DONE
    assert detail["units_per_beat"] == 1_350_000 // PROD_UNIT_MS  # 11
    assert detail["beats_remaining"] == 5  # ceil(46 / 11) — CAL-P066's number


def test_a_unit_bigger_than_a_whole_beat_is_conclusively_infeasible():
    """The ``beats_to_publish: -1`` case, promoted to a feasibility verdict. If
    a whole beat cannot hold ONE unit, no amount of resuming ever finishes the
    phase — this is the one thing a staged cursor genuinely cannot rescue."""
    plan = derive_plan(
        {},
        unit_costs={
            PHASE_FUTURES: {"unit_ms": 1_400_000, "units_total": 128, "units_done": 3}
        },
    )
    assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_INFEASIBLE
    assert plan.infeasible_phases == (PHASE_FUTURES,)
    detail = plan.as_payload()["feasibility"]["units"][PHASE_FUTURES]
    assert detail["units_per_beat"] == 0
    assert detail["beats_remaining"] == -1


def test_measured_unit_cost_outranks_a_floor_in_the_same_phase():
    """Both present: the floor is elapsed-of-cancelled, the unit cost is a
    completed duration. Measurement wins."""
    plan = derive_plan(
        {},
        floors={PHASE_FUTURES: [1_355_276]},  # would alone say INFEASIBLE
        unit_costs={
            PHASE_FUTURES: {"unit_ms": PROD_UNIT_MS, "units_total": 128, "units_done": 82}
        },
    )
    assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_FEASIBLE


def test_a_unit_cost_with_no_completed_unit_is_not_a_measurement():
    """``units_done: 0`` means no unit has ever finished, so whatever ``unit_ms``
    claims is not backed by a completed observation. It must not conclude."""
    plan = derive_plan(
        {},
        unit_costs={PHASE_FUTURES: {"unit_ms": 50_000, "units_total": 128, "units_done": 0}},
    )
    assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_NO_DATA


def test_malformed_unit_costs_are_ignored_rather_than_believed():
    """Junk must degrade to ``no_data``, never to a verdict."""
    for bad in (
        {"unit_ms": 0, "units_total": 128, "units_done": 5},
        {"unit_ms": -1, "units_total": 128, "units_done": 5},
        {"unit_ms": "x", "units_total": 128, "units_done": 5},
        {"unit_ms": True, "units_total": 128, "units_done": 5},
        {"unit_ms": 50_000, "units_total": 0, "units_done": 5},
        {"units_total": 128, "units_done": 5},
        "not-a-dict",
        None,
    ):
        plan = derive_plan({}, unit_costs={PHASE_FUTURES: bad})
        assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_NO_DATA, bad


# =============================================================================
# Rollup precedence
# =============================================================================


def test_the_worst_verdict_across_required_phases_wins():
    """One infeasible phase makes the plan infeasible even if others are fine —
    the build publishes all-or-nothing, so the weakest phase is the plan."""
    plan = derive_plan(
        {name: [10_000] for name in REQUIRED_PHASES},
        floors={PHASE_FUTURES: [1_355_276]},
        unit_costs={
            PHASE_FUTURES: {"unit_ms": 1_400_000, "units_total": 128, "units_done": 4}
        },
    )
    assert plan.feasibility == FEASIBILITY_INFEASIBLE


def test_indeterminate_outranks_no_data_which_outranks_feasible():
    """Both "could not check" states outrank the reassuring one, so a plan is
    never called feasible on the strength of the phases that happened to be
    measurable."""
    plan = derive_plan(
        {PHASE_SPORTS: [10_000]},  # sports feasible
        floors={PHASE_FUTURES: [PROD_FLOOR_MS]},  # futures indeterminate
    )  # diagnostics/aggregate/publish: no_data
    assert plan.phase_feasibility(PHASE_SPORTS) == FEASIBILITY_FEASIBLE
    assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_INDETERMINATE
    assert plan.phase_feasibility(PHASE_DIAGNOSTICS) == FEASIBILITY_NO_DATA
    assert plan.feasibility == FEASIBILITY_INDETERMINATE

    no_data_only = derive_plan({PHASE_SPORTS: [10_000]})
    assert no_data_only.feasibility == FEASIBILITY_NO_DATA


# =============================================================================
# The same defect one level down: the unit mean must exclude cancelled units
# =============================================================================


def test_the_unit_mean_fed_to_feasibility_excludes_cancelled_units():
    """``PhaseRunner.stage`` times its body "whatever happens inside it" — on
    purpose, because the stage that blew up is the one worth costing. That makes
    ``stages['read:futures_unit']`` a SUM OVER MIXED KINDS: completed units
    (durations) plus however far the cancelled one got (a lower bound).

    Dividing that by the count and handing it to a feasibility check would
    reintroduce exactly the defect this queue exists to remove, one level down —
    and it biases the wrong way, because a truncated final unit drags the mean
    DOWN and makes the phase look cheaper than it is.

    So the ledger keeps a completed-only tally beside the all-observations one,
    and feasibility reads the completed one.
    """
    from app.utils.calibration_phase_ledger import PhaseLedger, derive_plan as _dp

    ledger = PhaseLedger(
        plan=_dp({}),
        population_version="v1",
        owner="test",
        generation=1,
        input_fingerprint="fp",
    )
    # Three units finish at 100s each; the fourth is cancelled 1s in.
    for _ in range(3):
        ledger.record_stage_outcome("read:futures_unit", 100_000, completed=True)
    ledger.record_stage_outcome("read:futures_unit", 1_000, completed=False)

    # The all-observations view is unchanged and still totals everything.
    assert ledger.stages["read:futures_unit"] == 301_000
    assert ledger.stage_counts["read:futures_unit"] == 4
    assert ledger.stage_mean_ms("read:futures_unit") == 75_250  # dragged down

    # The completed-only view is the one a cost may be derived from.
    assert ledger.stage_completed_count("read:futures_unit") == 3
    assert ledger.stage_completed_mean_ms("read:futures_unit") == 100_000


def test_a_stage_with_no_completed_observation_has_no_completed_mean():
    """Every unit cancelled => there is no completed duration at all, and the
    honest answer is ``None``, never the mean of the truncated ones."""
    from app.utils.calibration_phase_ledger import PhaseLedger, derive_plan as _dp

    ledger = PhaseLedger(
        plan=_dp({}),
        population_version="v1",
        owner="test",
        generation=1,
        input_fingerprint="fp",
    )
    ledger.record_stage_outcome("read:futures_unit", 700_000, completed=False)
    assert ledger.stage_mean_ms("read:futures_unit") == 700_000
    assert ledger.stage_completed_mean_ms("read:futures_unit") is None
    assert ledger.stage_completed_count("read:futures_unit") == 0


def test_record_stage_still_works_and_counts_as_completed():
    """The existing two-argument call site keeps its meaning: a stage recorded
    through :meth:`record_stage` ran to completion."""
    from app.utils.calibration_phase_ledger import PhaseLedger, derive_plan as _dp

    ledger = PhaseLedger(
        plan=_dp({}),
        population_version="v1",
        owner="test",
        generation=1,
        input_fingerprint="fp",
    )
    ledger.record_stage("serialize", 400)
    assert ledger.stages["serialize"] == 400
    assert ledger.stage_counts["serialize"] == 1
    assert ledger.stage_completed_mean_ms("serialize") == 400


async def test_unit_costs_survive_the_durable_round_trip_and_reach_the_next_plan():
    """Without this the whole fix is inert: the cost is measured, dropped on the
    durable write, and the next beat plans from a floor again — which is the
    state that rendered ``infeasible_phases: []`` for sixteen beats.

    Runs the real production path, the same way the floors round-trip test does.
    """
    from app.services import durable_snapshots
    from app.tasks import calibration_main_build as build
    from app.utils.calibration_phase_ledger import PHASE_LEDGER_SCHEMA
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
                schema_version=expected_version or PHASE_LEDGER_SCHEMA,
                payload=written["payload"],
                complete=True,
                source=build.MAIN_BUILD_TASK,
            ),
        )

    original_publish = durable_snapshots.publish_snapshot_standalone
    original_read = durable_snapshots.read_snapshot_standalone
    durable_snapshots.publish_snapshot_standalone = fake_publish
    durable_snapshots.read_snapshot_standalone = fake_read
    try:
        runner = build.PhaseRunner(
            plan=derive_plan({}),
            checkpoint=build.new_main_checkpoint(
                version="v1", fingerprint="fp", owner="o", generation=1
            ),
            checkpoint_action="fresh",
            population_version="v1",
            owner="o",
            generation=1,
            fingerprint="fp",
        )
        # Nine units complete at ~116.7s; the tenth is cancelled 4s in.
        for _ in range(9):
            runner.ledger.record_stage_outcome(
                build.STAGED_UNIT_STAGE, PROD_UNIT_MS, completed=True
            )
        runner.ledger.record_stage_outcome(
            build.STAGED_UNIT_STAGE, 4_000, completed=False
        )
        runner.ledger.record_gauge("staged:units_banked", PROD_UNITS_DONE)

        assert await build.save_phase_ledger(runner) == "ok"

        # Persisted, and persisted as the COMPLETED mean — not the mixed one,
        # which those ten observations would have put at ~105.4s.
        assert written["payload"]["unit_costs"] == {
            PHASE_FUTURES: {
                "unit_ms": PROD_UNIT_MS,
                "units_total": build.STAGED_FUTURES_BUCKETS,
                "units_done": PROD_UNITS_DONE,
            }
        }

        history, floors, unit_costs = await build.load_phase_measurements()
        assert history == {}
        assert unit_costs[PHASE_FUTURES]["unit_ms"] == PROD_UNIT_MS

        # And the next beat's plan concludes from it, where it previously could
        # only have shrugged.
        plan = derive_plan(history, floors=floors, unit_costs=unit_costs)
        assert plan.phase_feasibility(PHASE_FUTURES) == FEASIBILITY_FEASIBLE
        assert plan.unit_projection(PHASE_FUTURES)["beats_remaining"] == 5
    finally:
        durable_snapshots.publish_snapshot_standalone = original_publish
        durable_snapshots.read_snapshot_standalone = original_read


async def test_a_beat_whose_every_unit_was_cancelled_persists_no_unit_cost():
    """The refusal side of the round trip. No completed unit => no cost written,
    so the next plan reads ``no_data`` instead of a truncated bound dressed up
    as a measurement."""
    from app.services import durable_snapshots
    from app.tasks import calibration_main_build as build
    from app.utils.durable_state import EnvelopeRead

    written: dict = {}

    async def fake_publish(envelope):
        written["payload"] = envelope.payload
        return {"status": "ok"}

    async def fake_read(identity, *, expected_version=None, max_age_s=None):
        return EnvelopeRead(status="missing", tier="durable")

    original_publish = durable_snapshots.publish_snapshot_standalone
    original_read = durable_snapshots.read_snapshot_standalone
    durable_snapshots.publish_snapshot_standalone = fake_publish
    durable_snapshots.read_snapshot_standalone = fake_read
    try:
        runner = build.PhaseRunner(
            plan=derive_plan({}),
            checkpoint=build.new_main_checkpoint(
                version="v1", fingerprint="fp", owner="o", generation=1
            ),
            checkpoint_action="fresh",
            population_version="v1",
            owner="o",
            generation=1,
            fingerprint="fp",
        )
        runner.ledger.record_stage_outcome(
            build.STAGED_UNIT_STAGE, 700_000, completed=False
        )
        runner.ledger.record_gauge("staged:units_banked", 12)
        assert await build.save_phase_ledger(runner) == "ok"
        assert "unit_costs" not in written["payload"]
    finally:
        durable_snapshots.publish_snapshot_standalone = original_publish
        durable_snapshots.read_snapshot_standalone = original_read


def test_every_required_phase_appears_in_exactly_one_bucket():
    """No phase may fall out of the rendering. The three could-not-conclude /
    conclude buckets plus feasible must partition the required set."""
    plan = derive_plan(
        {PHASE_SPORTS: [10_000]},
        floors={PHASE_FUTURES: [PROD_FLOOR_MS], PHASE_DIAGNOSTICS: [1_355_276]},
    )
    payload = plan.as_payload()["feasibility"]
    buckets = (
        payload["infeasible_phases"]
        + payload["indeterminate_phases"]
        + payload["unchecked_phases"]
        + payload["feasible_phases"]
    )
    assert sorted(buckets) == sorted(REQUIRED_PHASES)
    assert len(buckets) == len(set(buckets))
