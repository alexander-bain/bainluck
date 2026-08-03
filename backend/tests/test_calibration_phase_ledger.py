"""Queue 300M — the main calibration build's phase ledger, budgets and resume.

C124 committed the ORACLE
(``scripts/evals/calibration_main_phase_budget_contract.py``). These tests
drive the PRODUCTION objects and feed what they emit back through that same
evaluator, so the contract is graded against what the build actually does
rather than against a hand-written row.

The cases mirror Queue 300M's acceptance list: first/middle/last phase,
timeout, cancellation, hard loss, checkpoint-write failure, duplicate owner,
poison phase, missing timer, version change, and partial-across-beats.
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.tasks.calibration_main_build import (
    CHECKPOINT_MAX_BYTES,
    PHASE_OUTPUT_MAX_BYTES,
    NullPhaseRunner,
    PhaseRunner,
    decode_rows,
    encode_rows,
    _decode,
    _encode,
    _decode_value,
    _encode_value,
)
from app.utils.calibration_phase_ledger import (
    BUDGET_SAFETY,
    CANCELLED,
    FAILED,
    FRESH,
    INVALIDATE,
    MAIN_CHECKPOINT_SCHEMA,
    MAIN_BUILD_TASK,
    PHASE_AGGREGATE,
    PHASE_DIAGNOSTICS,
    PHASE_OUTPUT_KEYS,
    PHASE_FUTURES,
    PHASE_PUBLISH,
    PHASE_SPORTS,
    REFUSE,
    RESUME,
    RESUMED,
    REQUIRED_PHASES,
    RESUMABLE_PHASES,
    TERMINAL_CANCELLED,
    TERMINAL_COMPLETE,
    TERMINAL_FAILED,
    TERMINAL_PARTIAL,
    TIMEOUT,
    GREEN,
    RED,
    UNKNOWN,
    MainBuildCheckpoint,
    decode_main_checkpoint,
    derive_plan,
    health_for,
    input_fingerprint,
    merge_history,
    new_main_checkpoint,
    phase_ledger_row,
    terminal_for,
)

from scripts.evals.calibration_main_phase_budget_contract import evaluate_case

VERSION = "q267"
FINGERPRINT = "fp-abc"
OWNER = "worker-a"


# =============================================================================
# Item 0 — budgets are measured, never guessed
# =============================================================================


def test_plan_with_no_history_is_provisional_and_declares_no_budgets():
    """The first instrumented run must not invent a number for anything."""
    plan = derive_plan({})
    assert plan.provisional is True
    assert [b.budget_ms for b in plan.budgets] == [None] * len(REQUIRED_PHASES)
    assert [b.statement_timeout_ms for b in plan.budgets] == [None] * len(REQUIRED_PHASES)
    assert all(b.measured_input is False for b in plan.budgets)


def test_plan_becomes_measured_only_once_every_phase_has_an_observation():
    partial = derive_plan({PHASE_FUTURES: [500_000]})
    assert partial.provisional is True
    assert partial.by_name(PHASE_FUTURES).measured_input is True
    assert partial.by_name(PHASE_SPORTS).measured_input is False

    full = derive_plan(
        {
            PHASE_FUTURES: [400_000],
            PHASE_SPORTS: [100_000],
            PHASE_DIAGNOSTICS: [80_000],
            PHASE_AGGREGATE: [30_000],
            PHASE_PUBLISH: [20_000],
        }
    )
    assert full.provisional is False
    assert all(b.measured_input for b in full.budgets)


def test_budget_is_derived_from_the_worst_observation_with_headroom():
    plan = derive_plan(
        {
            PHASE_FUTURES: [100_000, 300_000, 200_000],
            PHASE_SPORTS: [10_000],
            PHASE_DIAGNOSTICS: [10_000],
            PHASE_AGGREGATE: [10_000],
            PHASE_PUBLISH: [10_000],
        }
    )
    assert plan.by_name(PHASE_FUTURES).budget_ms == int(300_000 * BUDGET_SAFETY)
    assert plan.by_name(PHASE_FUTURES).observations == 3


def test_statement_timeout_sits_strictly_inside_its_phase_budget():
    plan = derive_plan({name: [60_000] for name in REQUIRED_PHASES})
    for budget in plan.budgets:
        assert budget.statement_timeout_ms < budget.budget_ms


def test_measured_budgets_are_scaled_down_to_preserve_publication_headroom():
    """The build must never budget away its own ability to publish."""
    plan = derive_plan({name: [900_000] for name in REQUIRED_PHASES})
    assert plan.provisional is False
    assert plan.declared_ms + plan.cleanup_margin_ms <= plan.soft_limit_ms


# =============================================================================
# Queue 300N Item 1 — what the beats that never finish a phase are allowed to say
# =============================================================================
#
# The first organic ledger (production, generation 1785719700083) recorded
# ``futures`` cancelled at 1,355,276ms against a 1,380,000ms window, with every
# later phase pending and nothing banked. Sixteen consecutive beats did that and
# taught the next plan nothing, because a timeout is not a duration and was
# dropped on the floor. It is still not a duration — these tests pin the narrow
# thing it IS allowed to become.


def test_a_floor_never_becomes_a_budget():
    """The whole point: a cancelled phase took LONGER than it ran, by an
    unknown amount. Budgeting off that number under-budgets by construction."""
    plan = derive_plan({}, floors={PHASE_FUTURES: [1_355_276]})
    futures = plan.by_name(PHASE_FUTURES)
    assert futures.budget_ms is None
    assert futures.statement_timeout_ms is None
    assert futures.measured_input is False
    assert plan.provisional is True
    assert futures.floor_ms == 1_355_276
    assert futures.floor_observations == 1


def test_the_worst_floor_wins_and_junk_is_ignored():
    plan = derive_plan({}, floors={PHASE_FUTURES: [900_000, "x", -5, True, 1_100_000, None]})
    assert plan.by_name(PHASE_FUTURES).floor_ms == 1_100_000
    assert plan.by_name(PHASE_FUTURES).floor_observations == 2


def test_a_floor_past_the_window_makes_the_plan_infeasible_not_provisional():
    """Production's actual state: no budget can rescue a phase this size."""
    plan = derive_plan({}, floors={PHASE_FUTURES: [1_355_276]})
    assert plan.available_ms == 1_380_000
    assert plan.infeasible_phases == (PHASE_FUTURES,)
    payload = plan.as_payload()
    assert payload["status"] == "infeasible"
    assert payload["infeasible_phases"] == [PHASE_FUTURES]


def test_infeasibility_is_measured_against_the_reachable_ceiling_not_the_window():
    """The bound a phase is actually cancelled at is the window MINUS the inner
    statement margin, so comparing a floor to the raw window would make
    infeasibility unreachable — the exact number production emits (1,355,276)
    sits below 1,380,000 and would have scored feasible forever."""
    plan = derive_plan({}, floors={PHASE_FUTURES: [1_355_276]})
    assert plan.max_phase_ms == 1_350_000
    assert plan.max_phase_ms < plan.available_ms
    assert 1_355_276 < plan.available_ms  # would NOT have tripped the naive test
    assert plan.infeasible_phases == (PHASE_FUTURES,)

    # One millisecond under the ceiling is still just a slow phase.
    assert derive_plan({}, floors={PHASE_FUTURES: [1_349_999]}).infeasible_phases == ()


def test_a_floor_inside_the_window_is_recorded_but_not_infeasible():
    """A phase that merely ran long once is not condemned — it just has a floor."""
    plan = derive_plan({}, floors={PHASE_SPORTS: [120_000]})
    assert plan.by_name(PHASE_SPORTS).floor_ms == 120_000
    assert plan.infeasible_phases == ()
    assert plan.as_payload()["status"] == "provisional"


def test_a_measured_phase_keeps_its_budget_even_with_an_older_floor():
    """A phase that has since completed is measured; the floor stays as history."""
    plan = derive_plan(
        {name: [10_000] for name in REQUIRED_PHASES},
        floors={PHASE_FUTURES: [200_000]},
    )
    assert plan.provisional is False
    assert plan.by_name(PHASE_FUTURES).budget_ms == int(10_000 * BUDGET_SAFETY)
    assert plan.by_name(PHASE_FUTURES).floor_ms == 200_000
    assert plan.infeasible_phases == ()


def test_no_floors_leaves_every_plan_field_exactly_as_before():
    """Item 1's constraint: absent evidence, nothing about the plan moves."""
    plan = derive_plan({})
    assert plan.infeasible_phases == ()
    assert plan.as_payload()["status"] == "provisional"
    assert all(b.floor_ms is None and b.floor_observations == 0 for b in plan.budgets)


def test_ledger_reports_a_floor_for_a_timed_out_phase_and_no_observation():
    runner = _runner()
    runner.begin(PHASE_FUTURES)
    runner.abort(Exception("canceling statement due to statement timeout"))
    assert runner.ledger.observations() == {}
    assert PHASE_FUTURES in runner.ledger.floors()
    assert runner.ledger.floors()[PHASE_FUTURES] >= 0


def test_a_completed_phase_is_an_observation_and_never_a_floor():
    runner = _runner()
    runner.begin(PHASE_SPORTS)
    runner.complete(PHASE_SPORTS)
    assert PHASE_SPORTS in runner.ledger.observations()
    assert PHASE_SPORTS not in runner.ledger.floors()


def test_pending_phases_contribute_neither_observation_nor_floor():
    """The four phases downstream of the timeout never ran — they say nothing."""
    runner = _runner()
    runner.begin(PHASE_FUTURES)
    runner.abort(Exception("canceling statement due to statement timeout"))
    for name in (PHASE_SPORTS, PHASE_DIAGNOSTICS, PHASE_AGGREGATE, PHASE_PUBLISH):
        assert name not in runner.ledger.floors()
        assert name not in runner.ledger.observations()


async def test_floors_survive_the_durable_round_trip_and_reach_the_next_plan():
    """End-to-end on the real production path: a beat that only ever times out
    must leave a floor behind, and the NEXT beat's plan must read it.

    Without this the change is inert — the floor is computed, dropped on the
    durable write, and the sixteenth beat plans exactly like the first.
    """
    from app.services import durable_snapshots
    from app.tasks import calibration_main_build as build
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
                source=MAIN_BUILD_TASK,
            ),
        )

    original_publish = durable_snapshots.publish_snapshot_standalone
    original_read = durable_snapshots.read_snapshot_standalone
    durable_snapshots.publish_snapshot_standalone = fake_publish
    durable_snapshots.read_snapshot_standalone = fake_read
    try:
        runner = _runner()
        runner.begin(PHASE_FUTURES)
        runner.ledger.records[PHASE_FUTURES].status = TIMEOUT
        runner.ledger.records[PHASE_FUTURES].duration_ms = 1_355_276
        assert await build.save_phase_ledger(runner) == "ok"

        assert written["payload"]["floors"] == {PHASE_FUTURES: [1_355_276]}
        assert written["payload"]["history"] == {}

        history, floors = await build.load_phase_history()
        assert history == {}
        assert floors == {PHASE_FUTURES: [1_355_276]}

        # The next beat plans with the floor: still no budget, but no longer
        # blandly "provisional".
        plan = derive_plan(history, floors=floors)
        assert plan.by_name(PHASE_FUTURES).budget_ms is None
        assert plan.infeasible_phases == (PHASE_FUTURES,)
    finally:
        durable_snapshots.publish_snapshot_standalone = original_publish
        durable_snapshots.read_snapshot_standalone = original_read


def test_history_ignores_junk_and_keeps_a_bounded_window():
    merged = merge_history(
        {PHASE_FUTURES: [1, 2, "x", -5, True, None]}, {PHASE_FUTURES: 9}
    )
    assert merged[PHASE_FUTURES] == [1, 2, 9]

    long_run = {PHASE_FUTURES: list(range(50))}
    assert len(merge_history(long_run, {PHASE_FUTURES: 99})[PHASE_FUTURES]) == 10


# =============================================================================
# Item 0 — the ledger records every ending, including the bad ones
# =============================================================================


def _runner(
    *,
    history=None,
    checkpoint=None,
    action=FRESH,
    owner=OWNER,
    version=VERSION,
    fingerprint=FINGERPRINT,
) -> PhaseRunner:
    return PhaseRunner(
        plan=derive_plan(history or {}),
        checkpoint=checkpoint
        or new_main_checkpoint(
            version=version, fingerprint=fingerprint, owner=owner, generation=1
        ),
        checkpoint_action=action,
        population_version=version,
        owner=owner,
        generation=1,
        fingerprint=fingerprint,
    )


@pytest.mark.parametrize(
    "phase",
    [PHASE_FUTURES, PHASE_SPORTS, PHASE_DIAGNOSTICS, PHASE_AGGREGATE, PHASE_PUBLISH],
)
def test_a_phase_that_times_out_anywhere_is_recorded_with_its_elapsed_time(phase):
    """First, middle and last phase all have to leave evidence behind."""
    runner = _runner()
    runner.begin(phase)
    status = runner.abort(
        Exception("canceling statement due to statement timeout")
    )
    assert status == TIMEOUT
    record = runner.ledger.records[phase]
    assert record.status == TIMEOUT
    assert record.committed is False
    assert record.duration_ms >= 0
    assert runner.ledger.all_required_done is False


def test_cancellation_is_recorded_not_swallowed():
    import asyncio

    runner = _runner()
    runner.begin(PHASE_SPORTS)
    assert runner.abort(asyncio.CancelledError()) == CANCELLED
    assert runner.ledger.records[PHASE_SPORTS].status == CANCELLED


def test_an_ordinary_error_is_a_failure_not_a_timeout():
    runner = _runner()
    runner.begin(PHASE_DIAGNOSTICS)
    assert runner.abort(ValueError("boom")) == FAILED
    assert runner.ledger.records[PHASE_DIAGNOSTICS].status == FAILED


def test_a_hard_loss_leaves_no_phase_stuck_running():
    """Whatever was in flight when the worker died is closed out, not left open."""
    runner = _runner()
    runner.begin(PHASE_FUTURES)
    runner.ledger.close_open_phase(now_ms=999, status=CANCELLED, detail="SIGKILL")
    assert runner.ledger.records[PHASE_FUTURES].status == CANCELLED
    assert runner.ledger.records[PHASE_FUTURES].duration_ms == 999


def test_only_phases_that_ran_to_completion_this_run_feed_the_next_plan():
    """A timeout says 'slower than the bound', not 'takes this long'."""
    runner = _runner()
    runner.begin(PHASE_FUTURES)
    runner.complete(PHASE_FUTURES)
    runner.begin(PHASE_SPORTS)
    runner.abort(Exception("canceling statement due to statement timeout"))
    runner.carry(PHASE_DIAGNOSTICS)

    observations = runner.ledger.observations()
    assert PHASE_FUTURES in observations
    assert PHASE_SPORTS not in observations
    assert PHASE_DIAGNOSTICS not in observations  # carried, so it cost nothing here


def test_a_carried_phase_counts_as_done_without_being_timed():
    runner = _runner()
    runner.carry(PHASE_FUTURES)
    assert runner.is_carried(PHASE_FUTURES) is True
    assert runner.ledger.records[PHASE_FUTURES].status == RESUMED
    assert runner.ledger.records[PHASE_FUTURES].duration_ms == 0
    assert PHASE_FUTURES in runner.ledger.completed_required


def test_missing_timer_cannot_produce_a_negative_duration():
    """A phase completed without ever being begun records 0, never nonsense."""
    runner = _runner()
    assert runner.complete(PHASE_FUTURES) == 0
    assert runner.ledger.records[PHASE_FUTURES].duration_ms == 0


def test_ledger_write_failure_makes_progress_unknown_never_green():
    assert (
        health_for(
            terminal=TERMINAL_COMPLETE,
            ledger_write="error",
            artifact_fresh=True,
            artifact_generation=200,
        )
        == UNKNOWN
    )
    assert (
        health_for(
            terminal=TERMINAL_COMPLETE,
            ledger_write="ok",
            artifact_fresh=True,
            artifact_generation=200,
        )
        == GREEN
    )


def test_a_stale_artifact_is_never_green_even_on_a_complete_run():
    assert (
        health_for(
            terminal=TERMINAL_COMPLETE,
            ledger_write="ok",
            artifact_fresh=False,
            artifact_generation=200,
        )
        == UNKNOWN
    )
    assert (
        health_for(
            terminal=TERMINAL_FAILED,
            ledger_write="ok",
            artifact_fresh=False,
            artifact_generation=None,
        )
        == RED
    )


# =============================================================================
# Item 1 — checkpoint ownership, versioning and invalidation
# =============================================================================


def _stored(phase: str, values: dict) -> dict:
    return {
        "stored": True,
        "values": {k: {"kind": "value", "value": v} for k, v in values.items()},
    }


def _raw_checkpoint(**overrides) -> dict:
    raw = {
        "schema": MAIN_CHECKPOINT_SCHEMA,
        "task": MAIN_BUILD_TASK,
        "version": VERSION,
        "generation": 5,
        "owner": OWNER,
        "lease_expires_at": 0.0,
        "input_fingerprint": FINGERPRINT,
        "completed_phases": [PHASE_FUTURES],
        "phase_outputs": {PHASE_FUTURES: _stored(PHASE_FUTURES, {"rows": []})},
        "terminal": TERMINAL_PARTIAL,
    }
    raw.update(overrides)
    return raw


def _decode_cp(raw, *, owner=OWNER, version=VERSION, fingerprint=FINGERPRINT, now=100.0):
    return decode_main_checkpoint(
        raw,
        expected_version=version,
        expected_fingerprint=fingerprint,
        owner=owner,
        generation=9,
        now=now,
    )


def test_absent_checkpoint_is_fresh_not_an_error():
    checkpoint, action = _decode_cp(None)
    assert action == FRESH
    assert checkpoint.completed_phases == ()


@pytest.mark.parametrize(
    "override",
    [
        {"schema": "something-else"},
        {"task": "other_task"},
        {"version": "q299"},
        {"input_fingerprint": "fp-changed"},
        {"completed_phases": "not-a-list"},
        {"phase_outputs": "not-a-dict"},
    ],
)
def test_anything_we_cannot_vouch_for_is_invalidated(override):
    _, action = _decode_cp(_raw_checkpoint(**override))
    assert action == INVALIDATE


def test_a_population_version_change_invalidates_every_carried_phase():
    checkpoint, action = _decode_cp(_raw_checkpoint(), version="q299")
    assert action == INVALIDATE
    assert checkpoint.completed_phases == ()
    assert checkpoint.version == "q299"


def test_a_live_lease_held_by_another_owner_is_refused_not_stolen():
    _, action = _decode_cp(
        _raw_checkpoint(owner="worker-b", lease_expires_at=500.0), now=100.0
    )
    assert action == REFUSE


def test_an_expired_lease_from_another_owner_is_resumable():
    """A worker that died holding the lease must not block the next beat forever."""
    _, action = _decode_cp(
        _raw_checkpoint(owner="worker-b", lease_expires_at=50.0), now=100.0
    )
    assert action == RESUME


def test_our_own_lease_is_never_refused_to_us():
    _, action = _decode_cp(_raw_checkpoint(owner=OWNER, lease_expires_at=500.0), now=100.0)
    assert action == RESUME


def test_a_phase_marked_done_with_a_partial_output_is_not_resumed():
    """Half a phase is not a phase — resume is all-or-nothing, per phase."""
    raw = _raw_checkpoint(
        completed_phases=[PHASE_SPORTS],
        phase_outputs={PHASE_SPORTS: _stored(PHASE_SPORTS, {"events_rows": []})},
    )
    checkpoint, action = _decode_cp(raw)
    assert checkpoint.completed_phases == ()
    assert action == FRESH


def test_a_phase_marked_done_with_no_output_at_all_is_not_resumed():
    raw = _raw_checkpoint(completed_phases=[PHASE_FUTURES], phase_outputs={})
    checkpoint, _ = _decode_cp(raw)
    assert checkpoint.completed_phases == ()


def test_the_publish_phase_can_never_be_carried():
    """It consumes every other phase and must run in the run that publishes."""
    raw = _raw_checkpoint(
        completed_phases=[PHASE_PUBLISH],
        phase_outputs={PHASE_PUBLISH: _stored(PHASE_PUBLISH, {})},
    )
    checkpoint, _ = _decode_cp(raw)
    assert PHASE_PUBLISH not in checkpoint.completed_phases


def test_a_complete_sports_output_round_trips():
    raw = _raw_checkpoint(
        completed_phases=[PHASE_SPORTS],
        phase_outputs={
            PHASE_SPORTS: _stored(
                PHASE_SPORTS,
                {"events_rows": [], "spreads_rows": [], "totals_rows": []},
            )
        },
    )
    checkpoint, action = _decode_cp(raw)
    assert action == RESUME
    assert checkpoint.completed_phases == (PHASE_SPORTS,)


def test_the_input_fingerprint_moves_when_the_queries_do():
    assert input_fingerprint("q267", "SELECT 1") != input_fingerprint("q267", "SELECT 2")
    assert input_fingerprint("q267", "SELECT 1") != input_fingerprint("q299", "SELECT 1")
    assert input_fingerprint("q267", "SELECT 1") == input_fingerprint("q267", "SELECT 1")


# =============================================================================
# Item 1/2 — banking phase output
# =============================================================================


def test_a_completed_phase_is_banked_with_its_whole_output():
    runner = _runner()
    runner.begin(PHASE_SPORTS)
    runner.record(PHASE_SPORTS, "events_rows", [], kind="rows")
    runner.record(PHASE_SPORTS, "spreads_rows", [], kind="rows")
    runner.record(PHASE_SPORTS, "totals_rows", [], kind="rows")
    runner.complete(PHASE_SPORTS)

    checkpoint, banked = runner.build_checkpoint()
    assert banked[PHASE_SPORTS] == "stored"
    assert checkpoint.completed_phases == (PHASE_SPORTS,)
    assert checkpoint.owner == OWNER
    assert checkpoint.lease_expires_at > 0


def test_a_phase_that_did_not_complete_is_never_banked():
    runner = _runner()
    runner.begin(PHASE_FUTURES)
    runner.record(PHASE_FUTURES, "rows", [])
    runner.abort(Exception("canceling statement due to statement timeout"))

    checkpoint, banked = runner.build_checkpoint()
    assert checkpoint.completed_phases == ()
    assert PHASE_FUTURES not in banked


def test_a_partially_captured_phase_is_refused_rather_than_stored_truncated():
    runner = _runner()
    runner.begin(PHASE_SPORTS)
    runner.record(PHASE_SPORTS, "events_rows", [], kind="rows")  # missing two keys
    runner.complete(PHASE_SPORTS)

    checkpoint, _ = runner.build_checkpoint()
    assert checkpoint.completed_phases == ()


def test_oversize_phase_output_is_dropped_not_truncated():
    runner = _runner()
    runner.begin(PHASE_FUTURES)
    runner.record(
        PHASE_FUTURES, "rows", [{"blob": "x" * (PHASE_OUTPUT_MAX_BYTES + 1000)}]
    )
    runner.complete(PHASE_FUTURES)

    checkpoint, banked = runner.build_checkpoint()
    assert banked[PHASE_FUTURES] == "oversize"
    assert checkpoint.completed_phases == ()
    assert runner.ledger.records[PHASE_FUTURES].output_stored is False
    assert runner.ledger.records[PHASE_FUTURES].output_bytes > PHASE_OUTPUT_MAX_BYTES


def test_the_checkpoint_as_a_whole_stays_under_its_ceiling():
    """Largest-first drop, and the drop is recorded rather than silent."""
    chunk = "y" * 3_000_000  # under the per-phase cap, three of them are not
    runner = _runner()
    for phase, keys in (
        (PHASE_FUTURES, ["rows"]),
        (PHASE_SPORTS, ["events_rows", "spreads_rows", "totals_rows"]),
        (
            PHASE_DIAGNOSTICS,
            [
                "total_markets", "closing_row", "void_excluded",
                "heuristic_excluded", "soccer_2way_excluded", "truth_by_class",
                "date_range",
            ],
        ),
    ):
        runner.begin(phase)
        for index, key in enumerate(keys):
            runner.record(phase, key, chunk if index == 0 else "")
        runner.complete(phase)

    checkpoint, banked = runner.build_checkpoint()
    total = len(json.dumps(checkpoint.phase_outputs, default=str))
    assert total <= CHECKPOINT_MAX_BYTES
    assert "checkpoint_full" in banked.values()


def test_a_carried_phase_is_re_banked_verbatim_without_re_encoding():
    stored = _stored(PHASE_FUTURES, {"rows": []})
    checkpoint = MainBuildCheckpoint(
        version=VERSION,
        generation=3,
        owner=OWNER,
        input_fingerprint=FINGERPRINT,
        completed_phases=(PHASE_FUTURES,),
        phase_outputs={PHASE_FUTURES: stored},
    )
    runner = _runner(checkpoint=checkpoint, action=RESUME)
    runner.carry(PHASE_FUTURES)

    rebuilt, banked = runner.build_checkpoint()
    assert banked[PHASE_FUTURES] == "stored"
    assert rebuilt.phase_outputs[PHASE_FUTURES] == stored


# =============================================================================
# Item 2 — the deadline, the inner backstop, and lossless carry
# =============================================================================


def test_the_statement_timeout_is_always_inside_the_absolute_deadline():
    runner = _runner()
    timeout = runner.ledger.statement_timeout_for(PHASE_FUTURES, elapsed_ms=0)
    deadline = runner.ledger.plan.soft_limit_ms - runner.ledger.plan.cleanup_margin_ms
    assert 0 < timeout < deadline


def test_the_statement_timeout_shrinks_as_the_window_closes():
    runner = _runner()
    early = runner.ledger.statement_timeout_for(PHASE_FUTURES, elapsed_ms=0)
    late = runner.ledger.statement_timeout_for(PHASE_FUTURES, elapsed_ms=1_000_000)
    assert late < early
    assert late >= 1


def test_a_measured_budget_tightens_the_backstop_further():
    plan_history = {name: [10_000] for name in REQUIRED_PHASES}
    runner = _runner(history=plan_history)
    provisional = _runner()
    assert runner.ledger.statement_timeout_for(
        PHASE_FUTURES, elapsed_ms=0
    ) < provisional.ledger.statement_timeout_for(PHASE_FUTURES, elapsed_ms=0)


def test_past_the_deadline_the_backstop_never_goes_to_zero_or_negative():
    runner = _runner()
    assert runner.ledger.statement_timeout_for(PHASE_FUTURES, elapsed_ms=10**9) >= 1


def test_decimal_survives_the_carry_unchanged():
    """`canonical_json`'s default=str would flatten this to a string."""
    rows = [SimpleNamespace(n=5, avg_prob=Decimal("0.123456789012345"))]
    restored = decode_rows(encode_rows(rows))
    assert restored[0].avg_prob == Decimal("0.123456789012345")
    assert isinstance(restored[0].avg_prob, Decimal)
    assert restored[0].n == 5


def test_a_single_row_round_trips_to_attribute_access():
    row = SimpleNamespace(has_closing=3, needs_closing=1, total_completed=4)
    restored = _decode_value("row", _encode_value("row", row))
    assert restored.has_closing == 3
    assert restored.total_completed == 4


def test_a_payload_dict_that_merely_contains_a_tag_key_is_not_mistaken_for_one():
    value = {"__t__": "not-a-tag", "other": 1}
    assert _decode(_encode(value)) == value


def test_nested_diagnostic_dicts_round_trip():
    truth = {"eligible": {"outcomes": 10, "markets": 2}, "unknown": {"outcomes": 0, "markets": 0}}
    assert _decode(_encode(truth)) == truth


# =============================================================================
# Terminal + the null path
# =============================================================================


def test_complete_requires_both_every_phase_and_an_actual_publish():
    assert (
        terminal_for(all_required_done=True, published=True) == TERMINAL_COMPLETE
    )
    # Computed everything, persisted nothing: that is not complete.
    assert (
        terminal_for(all_required_done=True, published=False) == TERMINAL_PARTIAL
    )
    assert (
        terminal_for(all_required_done=False, published=False) == TERMINAL_PARTIAL
    )
    assert (
        terminal_for(all_required_done=True, published=True, cancelled=True)
        == TERMINAL_CANCELLED
    )
    assert (
        terminal_for(all_required_done=True, published=True, error=True)
        == TERMINAL_FAILED
    )


def test_the_null_runner_does_nothing_and_never_commits():
    """The route's cold-cache path must behave exactly as it did before."""
    runner = NullPhaseRunner()
    runner.begin(PHASE_FUTURES)
    assert runner.complete(PHASE_FUTURES) == 0
    assert runner.is_carried(PHASE_FUTURES) is False
    assert runner.reuse(PHASE_FUTURES, "rows") is None
    runner.record(PHASE_FUTURES, "rows", [1, 2, 3])
    assert runner.reuse(PHASE_FUTURES, "rows") is None


@pytest.mark.asyncio
async def test_the_null_runner_touches_no_session():
    class ExplodingSession:
        async def execute(self, *_a, **_k):
            raise AssertionError("the no-runner path must not set a statement timeout")

        async def commit(self):
            raise AssertionError("the no-runner path must not commit a request session")

    runner = NullPhaseRunner()
    assert await runner.apply_statement_timeout(ExplodingSession(), PHASE_FUTURES) == 0
    assert await runner.commit(ExplodingSession()) is None


# =============================================================================
# The C124 oracle, driven by what production emits
# =============================================================================


def _production_row(runner: PhaseRunner, **overrides):
    defaults = dict(
        terminal=TERMINAL_COMPLETE,
        published=True,
        durable="ok",
        volatile="ok",
        artifact_generation=200,
        gate="pass",
        checkpoint_action=RESUME,
        checkpoint_owner=runner.owner,
        checkpoint_version=VERSION,
        checkpoint_advanced=True,
        previous_preserved=True,
        health_verdict=GREEN,
        artifact_fresh=True,
        health_generation=200,
    )
    defaults.update(overrides)
    return phase_ledger_row(runner.ledger, **defaults)


def _measured_completed_runner() -> PhaseRunner:
    history = {name: [50_000] for name in REQUIRED_PHASES}
    runner = _runner(history=history)
    for phase in REQUIRED_PHASES:
        runner.begin(phase)
        runner.complete(phase)
        if phase in RESUMABLE_PHASES:
            runner.ledger.note_checkpoint(phase, write="ok", advanced=True)
    runner.ledger.elapsed_ms = 210_000
    runner.ledger.unmeasured_overhead_ms = 10_000
    return runner


def test_a_clean_measured_production_run_satisfies_the_c124_oracle():
    row = _production_row(_measured_completed_runner())
    assert evaluate_case(row) == []


def test_a_production_run_that_published_without_durable_is_refused_by_the_oracle():
    row = _production_row(
        _measured_completed_runner(), durable="error", volatile="ok"
    )
    errors = evaluate_case(row)
    assert "PUBLISHED_WITHOUT_DURABLE" in errors
    assert "VOLATILE_AHEAD_OF_DURABLE" in errors


def test_an_interrupted_production_run_publishes_nothing_and_is_not_green():
    history = {name: [50_000] for name in REQUIRED_PHASES}
    runner = _runner(history=history)
    runner.begin(PHASE_FUTURES)
    runner.complete(PHASE_FUTURES)
    runner.ledger.note_checkpoint(PHASE_FUTURES, write="ok", advanced=True)
    runner.begin(PHASE_SPORTS)
    runner.abort(Exception("canceling statement due to statement timeout"))
    runner.ledger.elapsed_ms = 120_000

    row = _production_row(
        runner,
        terminal=TERMINAL_PARTIAL,
        published=False,
        durable="not_attempted",
        volatile="not_attempted",
        artifact_generation=None,
        checkpoint_advanced=True,
        health_verdict=UNKNOWN,
        artifact_fresh=False,
        health_generation=None,
    )
    assert evaluate_case(row) == []


def test_a_cancelled_production_run_records_its_terminal():
    import asyncio

    runner = _measured_completed_runner()
    runner.begin(PHASE_PUBLISH)
    runner.abort(asyncio.CancelledError())
    row = _production_row(
        runner,
        terminal=TERMINAL_CANCELLED,
        published=False,
        durable="not_attempted",
        volatile="not_attempted",
        artifact_generation=None,
        health_verdict=UNKNOWN,
        artifact_fresh=False,
        health_generation=None,
        cancellation={"raised": True, "terminal_recorded": True, "swallowed": False},
    )
    assert evaluate_case(row) == []


def test_the_oracle_catches_a_checkpoint_advanced_after_a_failed_write():
    runner = _measured_completed_runner()
    # Force the exact bug the contract exists to stop: the guard in
    # note_checkpoint is bypassed, as a careless future edit would.
    runner.ledger.records[PHASE_FUTURES].checkpoint_write = "error"
    runner.ledger.records[PHASE_FUTURES].checkpoint_advanced = True
    assert "CHECKPOINT_ADVANCED_AFTER_WRITE_FAILURE" in evaluate_case(
        _production_row(runner)
    )


def test_note_checkpoint_refuses_to_advance_on_a_failed_write():
    runner = _measured_completed_runner()
    runner.ledger.note_checkpoint(PHASE_FUTURES, write="error", advanced=True)
    assert runner.ledger.records[PHASE_FUTURES].checkpoint_advanced is False


def test_note_checkpoint_refuses_to_advance_before_the_work_committed():
    runner = _runner(history={name: [50_000] for name in REQUIRED_PHASES})
    runner.begin(PHASE_FUTURES)
    runner.abort(Exception("boom"))  # committed stays False
    runner.ledger.note_checkpoint(PHASE_FUTURES, write="ok", advanced=True)
    assert runner.ledger.records[PHASE_FUTURES].checkpoint_advanced is False


def test_the_oracle_catches_a_non_owner_advancing_the_checkpoint():
    row = _production_row(_measured_completed_runner(), checkpoint_owner="worker-b")
    assert "NON_OWNER_ADVANCES_CHECKPOINT" in evaluate_case(row)


def test_the_oracle_catches_a_reused_checkpoint_across_a_version_change():
    row = _production_row(
        _measured_completed_runner(),
        checkpoint_version="q299",
        checkpoint_action=RESUME,
    )
    assert "CHECKPOINT_VERSION_REUSED" in evaluate_case(row)


def test_a_version_change_that_invalidates_is_accepted_by_the_oracle():
    row = _production_row(
        _measured_completed_runner(),
        checkpoint_version="q299",
        checkpoint_action=INVALIDATE,
        checkpoint_advanced=False,
    )
    assert evaluate_case(row) == []


def test_a_provisional_plan_is_honestly_reported_as_unmeasured():
    """The first instrumented run does not get to claim a measured budget."""
    runner = _runner()
    for phase in REQUIRED_PHASES:
        runner.begin(phase)
        runner.complete(phase)
    row = _production_row(runner)
    errors = evaluate_case(row)
    assert "PHASE_BUDGET_GUESSED" in errors
    assert "PHASE_BUDGET_MISSING" in errors
    assert runner.ledger.plan.as_payload()["status"] == "provisional"


# =============================================================================
# Partial across consecutive beats — the visible payoff
# =============================================================================


def test_progress_is_monotonic_across_three_beats():
    """Beat 1 banks futures, beat 2 adds sports, beat 3 finishes and publishes."""
    fingerprint = FINGERPRINT
    carried: dict = {}
    completed_over_time = []

    def next_runner(raw):
        checkpoint, action = decode_main_checkpoint(
            raw,
            expected_version=VERSION,
            expected_fingerprint=fingerprint,
            owner=OWNER,
            generation=1,
            now=0.0,
        )
        runner = _runner(checkpoint=checkpoint, action=action)
        for phase in checkpoint.completed_phases:
            runner.carry(phase)
        return runner

    # Beat 1 — futures only, then the window closes.
    beat1 = next_runner(None)
    beat1.begin(PHASE_FUTURES)
    beat1.record(PHASE_FUTURES, "rows", [{"n": 1}], kind="rows")
    beat1.complete(PHASE_FUTURES)
    beat1.begin(PHASE_SPORTS)
    beat1.abort(Exception("canceling statement due to statement timeout"))
    checkpoint, _ = beat1.build_checkpoint()
    carried = checkpoint.as_payload()
    completed_over_time.append(len(checkpoint.completed_phases))

    # Beat 2 — carries futures, adds sports, dies again.
    beat2 = next_runner(carried)
    assert beat2.is_carried(PHASE_FUTURES) is True
    assert beat2.reuse(PHASE_FUTURES, "rows")[0].n == 1
    beat2.begin(PHASE_SPORTS)
    for key in ("events_rows", "spreads_rows", "totals_rows"):
        beat2.record(PHASE_SPORTS, key, [], kind="rows")
    beat2.complete(PHASE_SPORTS)
    beat2.begin(PHASE_DIAGNOSTICS)
    beat2.abort(Exception("canceling statement due to statement timeout"))
    checkpoint, _ = beat2.build_checkpoint()
    carried = checkpoint.as_payload()
    completed_over_time.append(len(checkpoint.completed_phases))

    # Beat 3 — carries both, finishes the rest, publishes.
    beat3 = next_runner(carried)
    assert beat3.is_carried(PHASE_FUTURES) is True
    assert beat3.is_carried(PHASE_SPORTS) is True
    beat3.begin(PHASE_DIAGNOSTICS)
    for key in (
        "total_markets", "closing_row", "void_excluded",
        "heuristic_excluded", "soccer_2way_excluded", "truth_by_class",
        "date_range",
    ):
        beat3.record(PHASE_DIAGNOSTICS, key, 0)
    beat3.complete(PHASE_DIAGNOSTICS)
    beat3.begin(PHASE_AGGREGATE)
    beat3.complete(PHASE_AGGREGATE)
    beat3.begin(PHASE_PUBLISH)
    beat3.complete(PHASE_PUBLISH)
    checkpoint, _ = beat3.build_checkpoint()
    completed_over_time.append(len(checkpoint.completed_phases))

    assert completed_over_time == sorted(completed_over_time)
    assert completed_over_time == [1, 2, 3]
    assert beat3.ledger.all_required_done is True
    assert terminal_for(all_required_done=True, published=True) == TERMINAL_COMPLETE


def test_every_read_and_the_python_aggregation_sit_inside_a_measured_phase():
    """No blind spots: the build must not do work no phase accounts for.

    ``date_range`` (the twelfth read) and the whole post-processing block used
    to run outside every boundary, so their cost landed in
    ``unmeasured_overhead`` where no budget could ever see it.
    """
    import inspect

    from app.tasks import precompute_calibration as pc

    src = inspect.getsource(pc.compute_calibration_payload)

    # Every DB read is guarded by a reuse/record pair.
    assert src.count("runner.reuse(") == src.count("runner.record(")
    for phase, keys in PHASE_OUTPUT_KEYS.items():
        for key in keys:
            assert f'runner.reuse(PHASE_{phase.upper()}, "{key}")' in src, key
            assert f'runner.record(PHASE_{phase.upper()}, "{key}"' in src, key

    # The Python aggregation is opened and closed by its own phase.
    assert "runner.begin(PHASE_AGGREGATE)" in src
    assert "runner.complete(PHASE_AGGREGATE)" in src

    # The old unmeasured copy of the date_range read is gone, not duplicated.
    assert src.count("MIN(resolution_date)") == 1


def test_every_read_and_publish_stretch_is_a_named_stage():
    """Item 0's reconciliation list, asserted against the source.

    r343's last success ran 1,502.5s with compute_ms=534.9s, serialize_ms=6 and
    publish_ms=113 — 967.5s (64% of the window) in code no timer covered. The
    baseline read and the publish gate were the only substantial part of that
    stretch, and neither was measured. Both are stages now.
    """
    import inspect

    from app.tasks import precompute_calibration as pc

    src = inspect.getsource(pc.compute_calibration_payload) + inspect.getsource(
        pc._run_calibration_main_build
    )
    for stage in (
        "read:futures_population",
        "read:events", "read:spreads", "read:totals",
        "read:total_markets", "read:closing", "read:void",
        "read:heuristic_excluded", "read:soccer_2way", "read:truth_census",
        "read:date_range",
        "serialize", "redis_client", "baseline_read", "publish_gate",
        "durable_publish", "redis_accelerate",
    ):
        assert f'runner.stage("{stage}")' in src, stage


def test_stages_accumulate_and_are_recorded_even_when_the_body_raises():
    runner = _runner()
    with runner.stage("read:events"):
        pass
    with runner.stage("read:events"):
        pass
    assert "read:events" in runner.ledger.stages

    with pytest.raises(ValueError):
        with runner.stage("publish_gate"):
            raise ValueError("boom")
    # The stage that blew up is the one worth knowing the cost of.
    assert "publish_gate" in runner.ledger.stages
    assert runner.ledger.as_payload()["stages"]["publish_gate"] >= 0


def test_unmeasured_overhead_is_what_is_left_after_every_phase():
    runner = _runner()
    for phase in REQUIRED_PHASES:
        runner.begin(phase)
        runner.complete(phase)
    runner.ledger.elapsed_ms = 100_000
    measured = sum(r.duration_ms for r in runner.ledger.records.values())
    runner.ledger.unmeasured_overhead_ms = max(0, runner.ledger.elapsed_ms - measured)
    # Session acquisition and wrapper glue only — comfortably inside the margin
    # the oracle enforces.
    assert runner.ledger.unmeasured_overhead_ms <= runner.ledger.plan.cleanup_margin_ms


def test_a_poison_phase_does_not_erase_the_healthy_ones():
    """Gotcha #42, in phase form: one bad read must not wipe the whole run."""
    runner = _runner()
    runner.begin(PHASE_FUTURES)
    runner.record(PHASE_FUTURES, "rows", [], kind="rows")
    runner.complete(PHASE_FUTURES)
    runner.begin(PHASE_SPORTS)
    runner.abort(ValueError("poison"))

    checkpoint, banked = runner.build_checkpoint()
    assert checkpoint.completed_phases == (PHASE_FUTURES,)
    assert banked[PHASE_FUTURES] == "stored"
