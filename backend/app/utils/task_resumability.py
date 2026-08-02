"""Pure resumability contract for the bounded calibration tasks (Queue 300, #1513).

C118 committed the ORACLE for this behaviour
(``scripts/evals/calibration_task_resumability_contract.py`` + its 48-case
corpus). That evaluator grades a *state row*; nothing in the codebase emitted
one. This module is the missing half: the pure helpers a task uses to build
that state row, so the thing production actually does is graded by the same
contract the corpus encodes.

Everything here is I/O-free on purpose. The runtime half (durable checkpoint
persistence, the overlap lock) lives in ``app.tasks.task_checkpoint``; the
substrate stays there so the rules stay testable without a database.

The five rules that matter, in the corpus's own vocabulary:

* ``CHECKPOINT_AHEAD_OF_COMMIT`` — the cursor moves only after the transaction
  that produced the work commits. Never on read, never on "about to".
* ``STALE_CHECKPOINT_REUSED`` — a checkpoint stamped with a different
  population version is discarded, not resumed. Resuming it would silently
  skip a chunk that must be recomputed under the new population.
* ``PARTIAL_OUTPUT_PUBLISHED`` / ``COMPLETENESS_FALSE_CLAIM`` / ``FALSE_GREEN``
  — an interrupted run may keep its progress but may never publish an artifact
  or report GREEN. Resumability is not durability and partial is not done.
* ``POISON_WIPES_SIBLINGS`` — one bad chunk fails that chunk (gotcha #42). It
  is recorded by name and the sweep continues; the run then terminates
  ``partial``, because a run with a hole in it is not complete.
* ``OLD_TAIL_STARVED`` — the sweep is a stable ascending cursor, so the oldest
  work is reached first and a bounded run can never be pinned to the head
  (gotcha #41, the combat-wps lesson).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterator, Optional

CHECKPOINT_SCHEMA = "task-checkpoint/v1"

# Terminal states. A run is exactly one of these; there is no fourth answer and
# no "probably fine".
COMPLETE = "complete"
PARTIAL = "partial"
FAILED = "failed"

# What happened to a checkpoint we found on disk.
FRESH = "fresh"  # nothing to resume
RESUME = "resume"  # same population version, pick up at the cursor
INVALIDATE = "invalidate"  # wrong/corrupt version, start over

# Health verdicts, matching the corpus's ``health.verdict`` vocabulary.
GREEN = "GREEN"
UNKNOWN = "UNKNOWN"
RED = "RED"


@dataclass(frozen=True)
class Checkpoint:
    """Where a resumable sweep got to, and what it accumulated getting there."""

    task: str
    version: str
    cursor: int = 0
    chunks_done: int = 0
    rows_committed: int = 0
    failed_chunks: tuple[str, ...] = ()
    accumulator: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": CHECKPOINT_SCHEMA,
            "task": self.task,
            "version": self.version,
            "cursor": self.cursor,
            "chunks_done": self.chunks_done,
            "rows_committed": self.rows_committed,
            "failed_chunks": list(self.failed_chunks),
            "accumulator": self.accumulator,
        }


def new_checkpoint(task: str, version: str) -> Checkpoint:
    return Checkpoint(task=task, version=version)


def decode_checkpoint(
    raw: Any, *, task: str, expected_version: str
) -> tuple[Checkpoint, str]:
    """Load a persisted checkpoint, refusing anything not provably resumable.

    Returns ``(checkpoint, action)``. On any doubt at all — missing, not a
    dict, wrong schema, wrong task, wrong population version, non-integer
    cursor, negative cursor — the answer is a fresh checkpoint, because
    resuming a checkpoint you cannot vouch for skips work while claiming to
    have done it.
    """
    if raw is None:
        return new_checkpoint(task, expected_version), FRESH
    if not isinstance(raw, dict):
        return new_checkpoint(task, expected_version), INVALIDATE
    if raw.get("schema") != CHECKPOINT_SCHEMA or raw.get("task") != task:
        return new_checkpoint(task, expected_version), INVALIDATE
    if raw.get("version") != expected_version:
        # The population moved under us. Every chunk must be recomputed.
        return new_checkpoint(task, expected_version), INVALIDATE

    cursor = raw.get("cursor")
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        return new_checkpoint(task, expected_version), INVALIDATE

    accumulator = raw.get("accumulator")
    failed = raw.get("failed_chunks")
    return (
        Checkpoint(
            task=task,
            version=expected_version,
            cursor=cursor,
            chunks_done=_non_negative_int(raw.get("chunks_done")),
            rows_committed=_non_negative_int(raw.get("rows_committed")),
            failed_chunks=tuple(str(x) for x in failed) if isinstance(failed, list) else (),
            accumulator=accumulator if isinstance(accumulator, dict) else {},
        ),
        RESUME,
    )


def _non_negative_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


@dataclass(frozen=True)
class Chunk:
    """One half-open ``[start, end)`` slice of the sweep."""

    start: int
    end: int

    @property
    def id(self) -> str:
        return f"{self.start}-{self.end}"


def plan_chunks(*, cursor: int, upper_bound: int, chunk_size: int) -> Iterator[Chunk]:
    """Stable ascending sweep from ``cursor`` to ``upper_bound``.

    Ascending is the whole point (gotcha #41): a bounded run ordered
    newest-first can never reach the old tail, because the head keeps
    refilling. Ascending plus a committed cursor means every id is visited
    exactly once per population version, oldest first.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    start = max(cursor, 0)
    while start < upper_bound:
        end = min(start + chunk_size, upper_bound)
        yield Chunk(start=start, end=end)
        start = end


def advance_cursor(*, before: int, chunk_end: int, committed: bool) -> int:
    """The cursor rule. Committed → the committed end. Not committed → unmoved.

    This is the single line that separates "resumed correctly" from "silently
    skipped a chunk on a soft limit": a cursor written before the commit
    survives a crash the rows do not.
    """
    return chunk_end if committed else before


def apply_chunk(
    checkpoint: Checkpoint,
    chunk: Chunk,
    *,
    committed: bool,
    rows_committed: int = 0,
    accumulator: Optional[dict[str, Any]] = None,
    failed: bool = False,
) -> Checkpoint:
    """Fold one chunk's outcome into the checkpoint.

    A failed chunk still advances the cursor — it is recorded by name so the
    run can never claim completeness, but the sweep must not stop, or one
    poison row pins the whole tail forever (gotcha #42).
    """
    if failed:
        return replace(
            checkpoint,
            cursor=chunk.end,
            failed_chunks=checkpoint.failed_chunks + (chunk.id,),
        )
    next_cursor = advance_cursor(
        before=checkpoint.cursor, chunk_end=chunk.end, committed=committed
    )
    if not committed:
        return checkpoint
    return replace(
        checkpoint,
        cursor=next_cursor,
        chunks_done=checkpoint.chunks_done + 1,
        rows_committed=checkpoint.rows_committed + max(rows_committed, 0),
        accumulator=accumulator if accumulator is not None else checkpoint.accumulator,
    )


def ledger_valid(*, attempted: int, committed: int, failed: int) -> bool:
    """``committed + failed`` can never exceed what was attempted."""
    return committed + failed <= attempted


def terminal_state(
    *,
    exhausted: bool,
    failed_chunks: tuple[str, ...] | list[str],
    interrupted: bool,
    error: bool = False,
) -> str:
    """complete | partial | failed — and ``complete`` is the hard one to earn.

    ``complete`` requires the sweep to have reached the end of the population,
    with no failed chunk and no interruption. Anything else keeps its progress
    and says so.
    """
    if error:
        return FAILED
    if exhausted and not failed_chunks and not interrupted:
        return COMPLETE
    return PARTIAL


def may_publish(
    *, terminal: str, durable_generation_committed: bool, interrupted: bool
) -> bool:
    """Only a complete, durably-committed, uninterrupted run publishes."""
    return terminal == COMPLETE and durable_generation_committed and not interrupted


def health_verdict(
    *,
    terminal: str,
    metrics_available: bool,
    checked: int,
    terminal_event_retained: bool = True,
) -> str:
    """GREEN is earned, never assumed.

    Metric loss is ``UNKNOWN``, not GREEN — a task whose own telemetry vanished
    cannot vouch for itself (the Sentry-lifetime-count lesson, gotcha #49, in
    task form). ``checked == 0`` is likewise never GREEN: nothing examined is
    not the same as nothing wrong.
    """
    if not metrics_available:
        return UNKNOWN
    if terminal == FAILED:
        return RED
    if terminal == COMPLETE and terminal_event_retained and checked > 0:
        return GREEN
    return "PARTIAL"


def contract_row(
    *,
    task: str,
    population_version: str,
    checkpoint_version: str,
    version_action: str,
    cursor_before: int,
    chunk: Chunk,
    committed: bool,
    rows_attempted: int,
    rows_committed: int,
    rows_failed: int,
    interruption: str,
    ownership: str,
    terminal: str,
    published: bool,
    durable_generation_committed: bool,
    all_phases_complete: bool,
    metrics_available: bool,
    checked: int,
    poison_position: Optional[str] = None,
    duplicate_delivery: bool = False,
    idempotent: bool = True,
    healthy_siblings_survive: bool = True,
    terminal_event_retained: bool = True,
) -> dict[str, Any]:
    """Emit exactly the row shape C118's evaluator grades.

    The point of this function is that production and the corpus speak one
    vocabulary: the task builds this from what it actually did, and the test
    feeds it to ``evaluate_case`` and asserts no errors. A future change that
    breaks the contract fails a test instead of a night of calibration.
    """
    return {
        "task": task,
        "population_version": population_version,
        "checkpoint_version": checkpoint_version,
        "version_action": version_action,
        "ordering": "stable_oldest_first",
        "old_tail_reachable": True,
        "checkpoint": {
            "before": cursor_before,
            "next": advance_cursor(
                before=cursor_before, chunk_end=chunk.end, committed=committed
            ),
        },
        "chunk": {"id": chunk.id, "start": chunk.start, "end": chunk.end},
        "transaction": {
            "committed": committed,
            "rows_attempted": rows_attempted,
            "rows_committed": rows_committed,
            "rows_failed": rows_failed,
        },
        "interruption": interruption,
        "ownership": ownership,
        "duplicate_delivery": duplicate_delivery,
        "idempotent": idempotent,
        "poison_position": poison_position,
        "healthy_siblings_survive": healthy_siblings_survive,
        "output": {
            "all_phases_complete": all_phases_complete,
            "durable_generation_committed": durable_generation_committed,
            "published": published,
            "complete": all_phases_complete
            and durable_generation_committed
            and interruption == "none",
        },
        "health": {
            "verdict": health_verdict(
                terminal=terminal,
                metrics_available=metrics_available,
                checked=checked,
                terminal_event_retained=terminal_event_retained,
            ),
            "terminal_event_retained": terminal_event_retained,
            "metrics_available": metrics_available,
            "checked": checked,
        },
    }
