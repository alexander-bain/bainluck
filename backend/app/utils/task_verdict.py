"""One pure contract from a task's RETURNED summary to a health verdict.

Queue 300H Item 0. Every scheduled task runs through ``_tracked_run``, which
until now recorded SUCCESS for any invocation that returned without raising.
That is the false-GREEN defect (#1515): three calibration tasks told operators
they were healthy while

* ``compute_time_horizon_calibration`` returned ``{"status": "partial",
  "horizons_done": 0, "total": 4}`` — zero horizons computed, every 6h;
* ``calibration_prices`` returned ``terminal: partial`` with ``stopped_at`` set
  on every deadline-truncated run, against a 70% thrown-failure rate;
* ``coverage_metrics`` swallows its own exception and returns
  ``terminal: "failed"`` — a *returned* failure that raised nothing.

The fix is not per-task success guessing. It is this: a summary either carries
explicit terminal truth, or it proves nothing. The four verdicts are

``complete``
    Every required unit finished AND (where the task publishes something) the
    durable artifact landed. Hard to earn, deliberately.
``partial``
    Real, visible progress that is not a finished run. Not a failure — a
    resumable sweep returning ``partial`` is behaving as designed — but it can
    never read GREEN, because the artifact it exists to produce is not there.
``failed``
    The task itself reported a failed terminal without raising.
``unknown``
    Nothing in the summary proves what happened. Split by ``authoritative``:
    an *authoritative* unknown (the task speaks this vocabulary and told us it
    banked nothing — a skipped/overlap-refused run, a ledger write that failed)
    must not read GREEN. A *non-authoritative* unknown is the legacy case — a
    task that predates the contract and returns a bare counter dict. Its
    invocation is recorded as before, but stamped ``unverified`` so no surface
    can mistake "it returned" for "it did the work".

The module is pure: no Redis, no DB, no imports from ``app.tasks``. It is safe
to call on any object, including a poisoned or partially-decoded summary — a
shape it cannot read is ``unknown``, never an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Verdicts ---------------------------------------------------------------
COMPLETE = "complete"
PARTIAL = "partial"
FAILED = "failed"
UNKNOWN = "unknown"

#: Verdicts that must never increment a completion-success counter or leave a
#: task's health GREEN. ``complete`` is the only verdict that earns GREEN.
NOT_GREEN = frozenset({PARTIAL, FAILED, UNKNOWN})

# --- Terminal vocabularies already deployed in the tree ----------------------
# app/utils/calibration_phase_ledger.py  (precompute_calibration_main)
# app/utils/task_resumability.py         (coverage_metrics, calibration_prices)
_TERMINAL_COMPLETE = frozenset({"complete", "ok", "success", "succeeded"})
_TERMINAL_PARTIAL = frozenset({"partial", "cancelled", "canceled", "interrupted"})
_TERMINAL_FAILED = frozenset({"failed", "error", "hard_loss"})
#: Terminals that mean "this run deliberately did nothing". Not a failure, but
#: an invocation that banked no work cannot vouch for the task's health.
_TERMINAL_NO_WORK = frozenset({"overlap_refused", "skipped", "noop", "no_work"})

# --- ``status`` vocabularies -------------------------------------------------
_STATUS_COMPLETE = frozenset({"ok", "complete", "completed", "success", "succeeded"})
_STATUS_PARTIAL = frozenset({"partial", "degraded", "interrupted"})
_STATUS_FAILED = frozenset({"failed", "error"})
_STATUS_NO_WORK = frozenset({"skipped", "noop", "no_work", "disabled"})

#: Completed/total unit pairs, named explicitly rather than sniffed. ``done <
#: total`` is partial even when the task's own ``status`` says ok, and
#: ``done == 0`` against a positive total is the checked-zero shape that must
#: never read GREEN (the ``horizons_done: 0, total: 4`` case).
_UNIT_PAIRS: tuple[tuple[str, str], ...] = (
    ("horizons_done", "total"),
    ("horizons", "total"),
    ("completed", "total"),
    ("done", "total"),
    ("chunks_done", "chunks_total"),
)

#: Error collections a task uses to report per-item damage. Only consulted on a
#: summary that already speaks the contract — a legacy dict carrying an
#: ``errors`` counter is left alone, because per-item errors are normal there
#: and downgrading them would be exactly the kind of per-task guessing this
#: contract exists to avoid.
_ERROR_COLLECTIONS: tuple[str, ...] = ("errors", "failed_chunks", "failed_phases")


@dataclass(frozen=True)
class TaskVerdict:
    """What a returned summary proves about the run that produced it."""

    verdict: str
    #: Short machine-readable reason, e.g. ``"terminal:partial"``. Stored on the
    #: task's metrics hash so an operator reading a degraded task sees WHY.
    reason: str
    #: True when the summary carried explicit terminal truth (a recognized
    #: terminal / status / unit pair). False only for the legacy shapes, where
    #: the verdict is a statement about our knowledge, not about the run.
    authoritative: bool

    @property
    def is_green(self) -> bool:
        """Only a complete run earns GREEN."""
        return self.verdict == COMPLETE

    @property
    def blocks_success(self) -> bool:
        """Must this verdict be kept out of the completion-success counter?

        Legacy (non-authoritative) unknowns are exempt: they are recorded as
        before so ~100 pre-contract tasks keep a usable health surface. Their
        run is stamped ``unverified`` instead of claiming proof.
        """
        return self.verdict in NOT_GREEN and (
            self.authoritative or self.verdict != UNKNOWN
        )


_LEGACY = TaskVerdict(UNKNOWN, "no_terminal_fields", authoritative=False)


def _as_str(value: Any) -> str | None:
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def _as_int(value: Any) -> int | None:
    # bool is an int subclass; a boolean unit count is a poisoned shape, not a 0/1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _has_damage(summary: dict) -> str | None:
    """Name of the first non-empty error collection, if any."""
    for key in _ERROR_COLLECTIONS:
        value = summary.get(key)
        if isinstance(value, (list, tuple, set, dict)) and len(value) > 0:
            return key
        count = _as_int(value)
        if count is not None and count > 0:
            return key
    return None


def _unit_verdict(summary: dict) -> TaskVerdict | None:
    """Partial when a named completed/total pair says the run fell short."""
    for done_key, total_key in _UNIT_PAIRS:
        if done_key not in summary or total_key not in summary:
            continue
        done = _as_int(summary.get(done_key))
        total = _as_int(summary.get(total_key))
        if done is None or total is None or total <= 0:
            continue
        if done < total:
            return TaskVerdict(
                PARTIAL, f"units:{done_key}={done}/{total}", authoritative=True
            )
    return None


def _phase_ledger_verdict(ledger: dict) -> TaskVerdict:
    """``precompute_calibration_main``: terminal AND durable generation.

    ``health_for`` in ``calibration_phase_ledger`` already refuses GREEN when
    the ledger write failed or the artifact generation is missing. Consume that
    verdict rather than re-deriving it — a run that completed every phase but
    could not persist its own telemetry is UNKNOWN, never a success.
    """
    terminal = _as_str(ledger.get("terminal"))
    health = _as_str(ledger.get("health"))

    if terminal in _TERMINAL_FAILED or health == "red":
        return TaskVerdict(FAILED, f"ledger:terminal={terminal}", authoritative=True)
    if terminal in _TERMINAL_NO_WORK:
        return TaskVerdict(UNKNOWN, f"ledger:terminal={terminal}", authoritative=True)
    if terminal in _TERMINAL_COMPLETE:
        if health == "green":
            return TaskVerdict(COMPLETE, "ledger:complete+green", authoritative=True)
        # Complete phases, no durable generation (or no ledger write): the
        # build happened, the artifact operators read did not.
        return TaskVerdict(
            UNKNOWN, f"ledger:complete_without_green(health={health})", authoritative=True
        )
    if terminal in _TERMINAL_PARTIAL:
        return TaskVerdict(PARTIAL, f"ledger:terminal={terminal}", authoritative=True)
    return TaskVerdict(UNKNOWN, f"ledger:terminal={terminal}", authoritative=True)


#: Tasks whose returned summary is CONTRACT-BEARING — the explicit
#: compatibility adapters Item 0 requires before a verdict may gate health.
#:
#: Enforcement is opt-in for a reason. A ``status`` key is not a terminal
#: across this codebase: ``espn_sync`` returns ``{"status": "no_live_games"}``
#: on an empty slate, ``data_quality_watchdog`` returns
#: ``{"status": "green"|"amber"|"red"}`` as its FINDING, and half a dozen
#: backfills return ``{"status": "nothing_to_backfill"}`` when there is
#: genuinely nothing to do. Reading those as terminals would trade one false
#: GREEN for thirty false REDs — the same crying-wolf failure the grid health
#: score was retired for. Tasks join this set when their summary has been read
#: and shown to carry real terminal truth.
ENFORCED_TASKS = frozenset({
    "calibration_prices",              # terminal + stopped_at + errors
    "compute_time_horizon_calibration",  # status + horizons_done/total
    "precompute_calibration_main",     # phase_ledger.terminal + .health
    "coverage_metrics",                # terminal + published + failed_chunks
})


def classify_summary(result: Any) -> TaskVerdict:
    """Map a task's returned value to a :class:`TaskVerdict`. Never raises."""
    try:
        return _classify(result)
    except Exception:  # noqa: BLE001 — a contract that can crash a task is worse
        return TaskVerdict(UNKNOWN, "classifier_error", authoritative=False)


def verdict_for(task_name: str, result: Any) -> TaskVerdict:
    """The verdict ``_tracked_run`` acts on, for this task label.

    Outside :data:`ENFORCED_TASKS` the classification is still computed and
    carried in the reason (so an operator can see what the contract WOULD have
    said, and adding the task to the set is a one-line change), but the verdict
    is non-authoritative ``unknown`` — the pre-300H recording, unchanged.
    """
    verdict = classify_summary(result)
    if task_name in ENFORCED_TASKS:
        return verdict
    return TaskVerdict(
        UNKNOWN, f"not_enforced({verdict.verdict}:{verdict.reason})", authoritative=False
    )


def _classify(result: Any) -> TaskVerdict:
    if not isinstance(result, dict):
        # Includes None and the ``{"result": "..."}`` shim _tracked_run wraps a
        # scalar return in. An invocation that returned is not proof of work.
        return TaskVerdict(UNKNOWN, "non_dict_return", authoritative=False)

    # --- adapter: durable phase ledger (precompute_calibration_main) ---------
    ledger = result.get("phase_ledger")
    if isinstance(ledger, dict) and ("terminal" in ledger or "health" in ledger):
        return _phase_ledger_verdict(ledger)

    terminal = _as_str(result.get("terminal"))
    status = _as_str(result.get("status"))

    if terminal is None and status is None:
        return _LEGACY

    # Unit pairs are only read on a summary that already speaks the vocabulary.
    # A legacy dict carrying ``{"completed": 5, "total": 12.4}`` (seconds, in at
    # least one task) must not be reinterpreted as a shortfall.
    units = _unit_verdict(result)

    # --- explicit failure wins over everything ------------------------------
    if terminal in _TERMINAL_FAILED:
        return TaskVerdict(FAILED, f"terminal:{terminal}", authoritative=True)
    if terminal is None and status in _STATUS_FAILED:
        return TaskVerdict(FAILED, f"status:{status}", authoritative=True)

    # --- a run that banked nothing proves nothing ---------------------------
    if terminal in _TERMINAL_NO_WORK:
        return TaskVerdict(UNKNOWN, f"terminal:{terminal}", authoritative=True)
    if terminal is None and status in _STATUS_NO_WORK:
        return TaskVerdict(UNKNOWN, f"status:{status}", authoritative=True)

    # --- shortfall in named units beats an optimistic status ----------------
    if units is not None:
        return units

    if terminal in _TERMINAL_PARTIAL:
        return TaskVerdict(PARTIAL, f"terminal:{terminal}", authoritative=True)
    if terminal is None and status in _STATUS_PARTIAL:
        return TaskVerdict(PARTIAL, f"status:{status}", authoritative=True)

    complete = terminal in _TERMINAL_COMPLETE or (
        terminal is None and status in _STATUS_COMPLETE
    )
    if not complete:
        # Speaks the vocabulary, but with a word we do not know. Do not guess.
        label = f"terminal:{terminal}" if terminal else f"status:{status}"
        return TaskVerdict(UNKNOWN, f"unrecognised:{label}", authoritative=True)

    # --- a complete terminal still has to survive its own caveats -----------
    damage = _has_damage(result)
    if damage:
        return TaskVerdict(PARTIAL, f"complete_with:{damage}", authoritative=True)
    if result.get("stopped_at"):
        return TaskVerdict(
            PARTIAL, f"complete_but_stopped_at:{result['stopped_at']}", authoritative=True
        )
    # ``published`` is only consulted when the task reports it. A task that
    # publishes an artifact and says it did not is not complete, whatever its
    # terminal says.
    if "published" in result and not result.get("published"):
        return TaskVerdict(PARTIAL, "complete_without_publish", authoritative=True)

    return TaskVerdict(COMPLETE, f"terminal:{terminal or status}", authoritative=True)
