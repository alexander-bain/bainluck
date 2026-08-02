"""Queue 300 (#1513) — the resumability rules the calibration tasks now obey.

C118 shipped the ORACLE (``scripts/evals/calibration_task_resumability_contract``)
and its 48-case corpus, but nothing in the app emitted a row for it to grade.
These tests close that loop from both ends:

* the pure helpers in ``app.utils.task_resumability`` are tested directly, and
* every row those helpers emit is fed through C118's own ``evaluate_case`` and
  asserted to produce **no** contract errors.

So a future change that breaks checkpoint-after-commit, resurrects a stale
population version, publishes a partial artifact, or lets one poison chunk take
the sweep down fails here rather than silently on a Tuesday night.
"""

from __future__ import annotations

import pytest

from app.tasks.precompute_calibration import (
    _coverage_snapshot_from,
    _merge_coverage_groups,
)
from app.tasks.task_checkpoint import advisory_lock_key, checkpoint_identity
from app.utils.task_resumability import (
    CHECKPOINT_SCHEMA,
    COMPLETE,
    FAILED,
    PARTIAL,
    Checkpoint,
    Chunk,
    advance_cursor,
    apply_chunk,
    contract_row,
    decode_checkpoint,
    health_verdict,
    ledger_valid,
    may_publish,
    new_checkpoint,
    plan_chunks,
    terminal_state,
)

from scripts.evals.calibration_task_resumability_contract import evaluate_case

TASKS = ["calibration_prices", "coverage_metrics"]
VERSION = "q267"


def _row(**overrides):
    """A clean, contract-passing row, with room to break exactly one thing."""
    base = dict(
        task="coverage_metrics",
        population_version=VERSION,
        checkpoint_version=VERSION,
        version_action="reuse",
        cursor_before=100,
        chunk=Chunk(start=100, end=200),
        committed=True,
        rows_attempted=100,
        rows_committed=100,
        rows_failed=0,
        interruption="none",
        ownership="acquired",
        terminal=PARTIAL,
        published=False,
        durable_generation_committed=False,
        all_phases_complete=False,
        metrics_available=True,
        checked=100,
    )
    base.update(overrides)
    return contract_row(**base)


# --- The emitted rows must satisfy C118's oracle ----------------------------


@pytest.mark.parametrize("task", TASKS)
@pytest.mark.parametrize(
    "position", [(0, 100), (100, 200), (900, 1000)], ids=["first", "middle", "last"]
)
def test_first_middle_last_chunk_are_contract_clean(task, position):
    start, end = position
    assert evaluate_case(
        _row(task=task, cursor_before=start, chunk=Chunk(start=start, end=end))
    ) == []


@pytest.mark.parametrize("task", TASKS)
def test_final_chunk_may_publish_and_go_green(task):
    row = _row(
        task=task,
        terminal=COMPLETE,
        all_phases_complete=True,
        durable_generation_committed=True,
        published=True,
    )
    assert evaluate_case(row) == []
    assert row["health"]["verdict"] == "GREEN"
    assert row["output"]["complete"] is True


@pytest.mark.parametrize("task", TASKS)
def test_soft_limit_after_commit_keeps_progress_but_never_publishes(task):
    row = _row(task=task, interruption="soft_after_commit", terminal=PARTIAL)
    assert evaluate_case(row) == []
    assert row["output"]["complete"] is False
    assert row["health"]["verdict"] != "GREEN"


@pytest.mark.parametrize("task", TASKS)
def test_cancellation_before_commit_does_not_move_the_cursor(task):
    row = _row(
        task=task,
        interruption="cancel_before_commit",
        committed=False,
        rows_committed=0,
        rows_failed=0,
    )
    assert evaluate_case(row) == []
    assert row["checkpoint"]["next"] == row["checkpoint"]["before"]


def test_a_partial_run_that_claims_publication_is_caught():
    # The emitter cannot lie about `complete`, but it CAN be handed a published
    # flag it has not earned — that is the mistake the oracle exists to catch.
    row = _row(published=True)
    assert "PARTIAL_OUTPUT_PUBLISHED" in evaluate_case(row)


def test_green_on_zero_checked_is_caught():
    row = _row(
        terminal=COMPLETE,
        all_phases_complete=True,
        durable_generation_committed=True,
        published=True,
        checked=0,
    )
    # health_verdict refuses GREEN on checked=0, so the row stays contract-clean
    # by DEGRADING rather than by lying.
    assert row["health"]["verdict"] == "PARTIAL"
    assert evaluate_case(row) == []


def test_metric_loss_is_unknown_not_green():
    row = _row(
        terminal=COMPLETE,
        all_phases_complete=True,
        durable_generation_committed=True,
        published=True,
        metrics_available=False,
    )
    assert row["health"]["verdict"] == "UNKNOWN"
    assert evaluate_case(row) == []


def test_non_owner_never_mutates():
    row = _row(ownership="denied", committed=False, rows_committed=0)
    assert evaluate_case(row) == []
    row_bad = _row(ownership="denied", committed=True)
    assert "NON_OWNER_MUTATED" in evaluate_case(row_bad)


def test_duplicate_delivery_must_be_idempotent():
    assert evaluate_case(_row(duplicate_delivery=True, idempotent=True)) == []
    assert "DUPLICATE_NOT_IDEMPOTENT" in evaluate_case(
        _row(duplicate_delivery=True, idempotent=False)
    )


@pytest.mark.parametrize("position", ["first", "middle", "last"])
def test_poison_chunk_does_not_wipe_its_siblings(position):
    row = _row(poison_position=position, healthy_siblings_survive=True)
    assert evaluate_case(row) == []
    assert "POISON_WIPES_SIBLINGS" in evaluate_case(
        _row(poison_position=position, healthy_siblings_survive=False)
    )


# --- The cursor rule --------------------------------------------------------


def test_cursor_advances_only_after_commit():
    assert advance_cursor(before=100, chunk_end=200, committed=True) == 200
    assert advance_cursor(before=100, chunk_end=200, committed=False) == 100


def test_apply_chunk_uncommitted_is_a_no_op():
    cp = Checkpoint(task="t", version=VERSION, cursor=100, chunks_done=1)
    after = apply_chunk(cp, Chunk(100, 200), committed=False, rows_committed=5)
    assert after == cp


def test_apply_chunk_committed_accumulates():
    cp = Checkpoint(task="t", version=VERSION, cursor=100, chunks_done=1)
    after = apply_chunk(
        cp, Chunk(100, 200), committed=True, rows_committed=7, accumulator={"a": 1}
    )
    assert (after.cursor, after.chunks_done, after.rows_committed) == (200, 2, 7)
    assert after.accumulator == {"a": 1}


def test_failed_chunk_advances_past_the_poison_but_is_recorded():
    cp = Checkpoint(task="t", version=VERSION, cursor=100)
    after = apply_chunk(cp, Chunk(100, 200), committed=False, failed=True)
    # It must move on — one bad chunk cannot pin the whole tail (gotcha #42) —
    # and it must be named, so the run can never call itself complete.
    assert after.cursor == 200
    assert after.failed_chunks == ("100-200",)
    assert (
        terminal_state(
            exhausted=True, failed_chunks=after.failed_chunks, interrupted=False
        )
        == PARTIAL
    )


def test_ledger_cannot_exceed_what_was_attempted():
    assert ledger_valid(attempted=100, committed=90, failed=10)
    assert not ledger_valid(attempted=100, committed=95, failed=10)


# --- Versioning -------------------------------------------------------------


def test_stale_population_version_is_invalidated_not_resumed():
    stored = Checkpoint(task="t", version="q266", cursor=500).as_payload()
    cp, action = decode_checkpoint(stored, task="t", expected_version="q267")
    assert action == "invalidate"
    assert cp.cursor == 0


def test_matching_version_resumes_at_the_cursor():
    stored = Checkpoint(
        task="t", version=VERSION, cursor=500, chunks_done=5, rows_committed=50
    ).as_payload()
    cp, action = decode_checkpoint(stored, task="t", expected_version=VERSION)
    assert (action, cp.cursor, cp.chunks_done) == ("resume", 500, 5)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "not-a-dict",
        {"schema": "other/v1", "task": "t", "version": VERSION, "cursor": 5},
        {"schema": CHECKPOINT_SCHEMA, "task": "other", "version": VERSION, "cursor": 5},
        {"schema": CHECKPOINT_SCHEMA, "task": "t", "version": VERSION, "cursor": -1},
        {"schema": CHECKPOINT_SCHEMA, "task": "t", "version": VERSION, "cursor": "5"},
        {"schema": CHECKPOINT_SCHEMA, "task": "t", "version": VERSION, "cursor": True},
    ],
)
def test_any_unvouchable_checkpoint_starts_over(bad):
    cp, action = decode_checkpoint(bad, task="t", expected_version=VERSION)
    assert cp.cursor == 0
    assert action in ("fresh", "invalidate")


def test_checkpoint_roundtrips_through_its_payload():
    cp = Checkpoint(
        task="t",
        version=VERSION,
        cursor=300,
        chunks_done=3,
        rows_committed=30,
        failed_chunks=("100-200",),
        accumulator={"k": {"total": 1}},
    )
    back, action = decode_checkpoint(cp.as_payload(), task="t", expected_version=VERSION)
    assert action == "resume"
    assert back == cp


# --- The sweep --------------------------------------------------------------


def test_plan_chunks_is_ascending_contiguous_and_terminates():
    chunks = list(plan_chunks(cursor=0, upper_bound=250, chunk_size=100))
    assert [(c.start, c.end) for c in chunks] == [(0, 100), (100, 200), (200, 250)]


def test_plan_chunks_resumes_from_the_cursor_and_never_revisits():
    chunks = list(plan_chunks(cursor=200, upper_bound=250, chunk_size=100))
    assert [(c.start, c.end) for c in chunks] == [(200, 250)]


def test_empty_work_plans_nothing():
    assert list(plan_chunks(cursor=500, upper_bound=500, chunk_size=100)) == []


def test_chunk_size_must_be_positive():
    with pytest.raises(ValueError):
        list(plan_chunks(cursor=0, upper_bound=10, chunk_size=0))


# --- Terminal state and publication ----------------------------------------


def test_only_an_exhausted_clean_uninterrupted_sweep_is_complete():
    assert terminal_state(exhausted=True, failed_chunks=[], interrupted=False) == COMPLETE
    assert terminal_state(exhausted=False, failed_chunks=[], interrupted=True) == PARTIAL
    assert terminal_state(exhausted=True, failed_chunks=["1-2"], interrupted=False) == PARTIAL
    assert terminal_state(exhausted=True, failed_chunks=[], interrupted=False, error=True) == FAILED


def test_publication_needs_complete_durable_and_uninterrupted():
    assert may_publish(terminal=COMPLETE, durable_generation_committed=True, interrupted=False)
    assert not may_publish(terminal=PARTIAL, durable_generation_committed=True, interrupted=False)
    assert not may_publish(terminal=COMPLETE, durable_generation_committed=False, interrupted=False)
    assert not may_publish(terminal=COMPLETE, durable_generation_committed=True, interrupted=True)


def test_health_verdict_ladder():
    assert health_verdict(terminal=COMPLETE, metrics_available=True, checked=5) == "GREEN"
    assert health_verdict(terminal=PARTIAL, metrics_available=True, checked=5) == "PARTIAL"
    assert health_verdict(terminal=FAILED, metrics_available=True, checked=5) == "RED"
    assert health_verdict(terminal=COMPLETE, metrics_available=False, checked=5) == "UNKNOWN"
    assert health_verdict(terminal=COMPLETE, metrics_available=True, checked=0) == "PARTIAL"
    assert (
        health_verdict(
            terminal=COMPLETE, metrics_available=True, checked=5, terminal_event_retained=False
        )
        == "PARTIAL"
    )


# --- Overlap lock identity --------------------------------------------------


def test_lock_key_is_stable_distinct_and_fits_a_signed_bigint():
    for task in TASKS:
        key = advisory_lock_key(task)
        assert advisory_lock_key(task) == key
        assert -(2**63) <= key < 2**63
    assert advisory_lock_key(TASKS[0]) != advisory_lock_key(TASKS[1])


def test_checkpoint_identities_do_not_collide():
    assert checkpoint_identity("coverage_metrics") != checkpoint_identity("calibration_prices")
    assert checkpoint_identity("coverage_metrics").startswith("task_checkpoint:")


# --- Coverage accumulation maths -------------------------------------------


class _Row:
    def __init__(self, source, age, league, total, opening, cal, winner, snap_sum, snap_n):
        self.source = source
        self.age_bucket = age
        self.league = league
        self.total_resolved = total
        self.has_opening = opening
        self.has_cal_prob = cal
        self.has_winner = winner
        self.snap_sum = snap_sum
        self.snap_n = snap_n


def test_chunked_accumulation_equals_one_pass_totals():
    chunk_one = [_Row("kalshi", "7d", "nba", 100, 90, 80, 100, 300, 100)]
    chunk_two = [_Row("kalshi", "7d", "nba", 50, 50, 25, 50, 50, 50)]
    acc = _merge_coverage_groups(_merge_coverage_groups({}, chunk_one), chunk_two)
    snapshot = _coverage_snapshot_from(acc)
    cell = snapshot["by_source_age_league"][0]
    assert (cell["total"], cell["has_opening"], cell["has_cal_prob"]) == (150, 140, 105)
    assert snapshot["totals"]["kalshi"]["cal_prob_pct"] == 70.0


def test_avg_snapshots_is_weighted_not_an_average_of_averages():
    # 100 outcomes averaging 3, then 50 averaging 1 → 350/150 = 2 (not (3+1)/2).
    big = [_Row("kalshi", "7d", "nba", 100, 0, 0, 0, 300, 100)]
    small = [_Row("kalshi", "7d", "nba", 50, 0, 0, 0, 50, 50)]
    acc = _merge_coverage_groups(_merge_coverage_groups({}, big), small)
    assert _coverage_snapshot_from(acc)["by_source_age_league"][0]["avg_snapshots"] == 2


def test_null_league_becomes_unknown_and_groups_stay_separate():
    rows = [
        _Row("kalshi", "7d", None, 10, 10, 10, 10, 10, 10),
        _Row("kalshi", "30d", "nba", 5, 5, 5, 5, 5, 5),
        _Row("polymarket", "7d", None, 7, 7, 0, 7, 0, 7),
    ]
    snapshot = _coverage_snapshot_from(_merge_coverage_groups({}, rows))
    assert len(snapshot["by_source_age_league"]) == 3
    assert {c["league"] for c in snapshot["by_source_age_league"]} == {"unknown", "nba"}
    assert snapshot["totals"]["polymarket"]["cal_prob_pct"] == 0.0


def test_empty_accumulator_publishes_an_empty_but_valid_snapshot():
    snapshot = _coverage_snapshot_from({})
    assert snapshot["by_source_age_league"] == []
    assert snapshot["totals"] == {}
    assert snapshot["date"] and snapshot["computed_at"]


def test_new_checkpoint_is_at_zero():
    cp = new_checkpoint("coverage_metrics", VERSION)
    assert (cp.cursor, cp.chunks_done, cp.failed_chunks, cp.accumulator) == (0, 0, (), {})
