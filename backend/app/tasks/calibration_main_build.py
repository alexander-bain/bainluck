"""Runtime half of the Queue 300M main-build phase ledger + resume (#1479/#1513).

``app.utils.calibration_phase_ledger`` holds the RULES (pure, corpus-graded).
This module is the only thing that touches a substrate, and it picks the same
one Queue 298/300 established: PostgreSQL's ``durable_state_snapshots``.

Not Redis, deliberately. The instance is 50MB ``allkeys-lru`` running near
maxmemory; a phase ledger or a checkpoint there is not "persisted with a TTL",
it is a key waiting to be evicted — and an evicted checkpoint silently restarts
the build from zero while every metric still says the task succeeded. That is
the precise failure Queue 298 removed from the sentinels.

Three things live here:

* :class:`PhaseRunner` — the object the build carries through its phases. It
  times them, applies the per-phase statement timeout, hands back a prior
  beat's committed output when one exists, and captures this run's output for
  the next beat. With no runner (the route's cold-cache path) the build behaves
  exactly as it did before: no timing, no resume, no extra I/O.
* Lossless row (de)serialization. A carried phase output must reconstruct to
  something the downstream Python treats identically — including ``Decimal``,
  which ``canonical_json``'s ``default=str`` would otherwise flatten to a
  string and quietly change the arithmetic.
* Bounded persistence. A phase output that will not fit the checkpoint is NOT
  stored, and the phase is simply recomputed next beat. Silently truncating it
  would be far worse: a resumed run would publish a payload missing rows it
  believes it has.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import socket
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import text

from app.utils.calibration_phase_ledger import (
    CANCELLED,
    DONE_STATUSES,
    FAILED,
    FEASIBILITY_INDETERMINATE,
    FEASIBILITY_NO_DATA,
    FRESH,
    HARD_LIMIT_MS,
    INVALIDATE,
    MAIN_BUILD_TASK,
    MAIN_CHECKPOINT_SCHEMA,
    PHASE_FUTURES,
    PHASE_LEDGER_SCHEMA,
    PHASE_OUTPUT_KEYS,
    RESUMABLE_PHASES,
    RESUMED,
    STAGED_UNIT_OVERRUN_FACTOR,
    TERMINAL_COMPLETE,
    TERMINAL_PARTIAL,
    TIMEOUT,
    UNIT_WORST_WINDOW,
    MainBuildCheckpoint,
    PhaseLedger,
    PhasePlan,
    decode_main_checkpoint,
    derive_plan,
    merge_history,
    new_main_checkpoint,
)

logger = logging.getLogger(__name__)

LEDGER_IDENTITY = "calibration:main:phase_ledger"
CHECKPOINT_IDENTITY = "calibration:main:checkpoint"
#: Queue 300D Item 0. Kept apart from ``CHECKPOINT_IDENTITY`` on purpose: the
#: phase checkpoint carries WHOLE finished phases, this one carries progress
#: INSIDE the futures phase. Sharing a row would mean a partial futures phase
#: could not be recorded without also rewriting (and risking) the committed
#: sports/diagnostics output sitting next to it.
STAGED_FUTURES_IDENTITY = "calibration:main:staged_futures"

#: Queue 300D Item 0 — the staged futures switch.
#:
#: True: the scheduled build reads the futures population one chunk of whole
#: virtual questions at a time, committing each chunk before advancing its
#: cursor, so an interrupted beat banks what it proved.
#:
#: False: one statement, as before.
#:
#: **ON since CAL-P016 (2026-08-08), after the cursor was made convergent.** The
#: history below is kept in full, because it is the reason the switch alone was
#: never the fix and the reason a third flip should not be attempted on a hunch.
#:
#: SWITCHED ON AND ROLLED BACK IN ONE SESSION (Queue 300E, 2026-08-03):
#:
#: * 19:15Z, generation 1785784500088, terminal ``cancelled`` after 627,446 ms.
#:   ``read:futures_generation`` = **18,784 ms**, ``read:futures_unit`` =
#:   594,318 ms, ``staged:cursor_fresh``. ONE unit committed, cursor durably
#:   written (``terminal: partial``), nothing published, last-good preserved.
#:   That is the designed partial outcome, and it is the first time this build
#:   ever banked a minute of work.
#: * 20:15Z, generation 1785788100146, terminal ``cancelled`` after 83,210 ms.
#:   ``read:futures_generation`` = 25,919 ms, ``read:futures_unit`` = 51,478 ms,
#:   and — the finding — ``staged:cursor_invalidate``. The unit banked at 19:15
#:   was DISCARDED.
#:
#: WHY IT COULD NOT CONVERGE. The generation fingerprint is a digest over the
#: WHOLE roster — every ``(market_id, source, vm_id, is_grouped)`` in the
#: population. The population is ``futures_markets WHERE status = 'resolved'``,
#: and markets resolve continuously, so the roster differed at 20:15 from 19:15,
#: and the cursor threw the banked unit away rather than mix two rosters. Correct
#: given its contract, and fatal: units can only accumulate ACROSS beats if the
#: roster holds still between them, and it never will.
#:
#: WHAT LEAVING IT OFF THEN COST. Nothing replaced the monolith, the monolith
#: kept timing out at ~22.5 min every hour (10 of 10 recorded phase floors are
#: timeouts), and nothing was published after 2026-08-02 03:23Z. ``/api/calibration``
#: served a progressively staler curve for a week and then went **fully dark** on
#: 2026-08-09 ~03:23Z, when the last-good copy crossed ``SERVE_MAX_AGE_S``.
#:
#: WHAT CAL-P016 CHANGED, and why the switch is safe now. Two things, together —
#: 300E named the first and it is necessary but NOT sufficient on its own:
#:
#: 1. **The cursor validates per UNIT, not per generation.** A moved roster no
#:    longer discards the cursor; ``retain_planned_units`` drops only the units
#:    the new plan no longer asks for. ``UnitChunk.key`` digests that unit's full
#:    roster membership, so "still planned" means the identical set of questions,
#:    markets, sources and grouping flags.
#: 2. **The partition is content-addressed.** ``plan_units`` used a positional
#:    accumulator over sorted ``vm_id``s, so one new ``vm_id`` early in sort order
#:    shifted every later boundary and re-keyed every later unit — which would
#:    have invalidated the whole cursor again by a second route, and made fix 1
#:    look like it had failed. A ``vm_id``'s unit is now a hash of the ``vm_id``
#:    alone, so an arrival can only ever disturb its own unit.
#:
#: The flip is the LAST line of that change, not a substitute for it.
#:
#: ALSO SETTLED by the 300E flip, and still true: the unchunked Stage-A prefix —
#: the pre-``virtual_market`` half carrying 3 of the statement's 7 correlated
#: scans of the 179M-row ``futures_odds_snapshots``, and the feared blocker —
#: costs only **19-26 seconds**. The whole ~22-minute cost is in the
#: post-``virtual_market`` half, which is the half that chunks.
#:
#: OFF remains a proven no-op: the monolith text is byte-identical to the
#: pre-300D statement (pinned by
#: ``test_calibration_staged_futures_sql_300d.TestMonolithIsUnmoved``).
#:
#: This ONLY ever applies to a run that owns a :class:`PhaseRunner` — i.e. the
#: scheduled build. The route's in-request cold-cache serve keeps the single
#: statement unconditionally: it has no checkpoint to resume from, no second
#: beat to finish the job, and a request session whose transaction must not be
#: committed underneath the caller. That is a class attribute on
#: :class:`NullPhaseRunner`, not a read of this constant, so it holds whatever
#: an operator sets here.
STAGED_FUTURES_ENABLED = True

#: How many units the futures population is cut into (CAL-P016).
#:
#: A FIXED count, not a target size, and that is the point: a ``vm_id``'s unit is
#: ``bucket_of(vm_id, STAGED_FUTURES_BUCKETS)``, so the partition is identical
#: across beats and an arriving market can only disturb its own unit. Deriving
#: this from the population size would re-partition everything each time the
#: population crossed a boundary — the exact thrash the fix exists to end.
#:
#: SIZING — READ TO THE END BEFORE MOVING THIS. The history below runs
#: 128 -> 17 -> 128, and the middle section argues for a value that is no longer
#: in force. Both refutations are kept because the second one is only legible
#: against the first. The operative rule is the LAST section, "THE RULE".
#:
#: SIZING PART ONE — 128 WAS A REASONED SIZE AND PRODUCTION REFUTED IT
#: (CAL-P1033, #3536). Superseded in part by PART TWO below.
#:
#: The reasoning this replaces is kept verbatim, because it is a good argument
#: and it is wrong, and the next editor is owed both halves:
#:
#:   *"completions scale UP with the bucket count, because a bucket's cost falls
#:   as it holds fewer markets. So a larger count is the safer direction, until
#:   per-unit fixed overhead starts to dominate."*
#:
#: Per-unit fixed overhead does not merely dominate; it is nearly the whole cost.
#: Two measured points, one per partition:
#:
#: ===========  ==================  ==========================================
#: partition    markets per unit    measured cost per unit
#: ===========  ==================  ==========================================
#: 1 (monolith) ~110,000            >1,350 s — CANCELLED, a floor, NOT a cost
#: 128          ~860                724 s (10:15Z beat) / **857 s (12:15Z)**
#: ===========  ==================  ==========================================
#:
#: The ">" on the first row is PART TWO's correction and it is the whole defect:
#: this table originally read "~1,350 s" and the fit below treats it as an
#: equality. It is a Postgres cancellation. Every conclusion drawn from it in the
#: rest of PART ONE — including "P ≈ 853 s" and "nearly the whole cost" — is
#: therefore wrong in a known direction.
#:
#: 0.8% of the rows costs 54–63% of the price. Fitting ``cost(B) = P + s·N/B``
#: on the WORSE of the two 128-way readings gives a fixed per-unit prefix
#: **P ≈ 853 s** against a scalable part of only ≈497 s for the ENTIRE
#: population, so a generation costs ``853·B + 497`` seconds — 30 hours at
#: B=128. Both beats were watched to their terminal and neither was killed: the
#: 10:15Z beat ran 964 s and banked its 1st unit, the 12:15Z beat ran 1,094 s
#: inside a deliberately quiet merge window, **resumed its cursor cleanly**
#: (``staged:cursor_reason:resumable``) and banked its 2nd. They recorded
#: ``staged:beats_to_publish`` = 81 and then **95** — the estimate got WORSE on
#: the beat that went perfectly. That is why ``/api/calibration`` served a
#: 29-hour-old ``generated_at`` while the task ran every hour, and why quieting
#: the deploys around the beat could never have been the fix.
#:
#: WHY 17, AND WHY THE FIRST TWO ANSWERS WERE WRONG. The binding constraint is
#: not a fraction anybody gets to choose — it is the production admission gate,
#: :func:`~app.tasks.precompute_calibration._unit_fits_in_window`:
#:
#:     ``remaining_ms >= max(worst_unit_ms, prior_unit_ms) * STAGED_UNIT_WINDOW_SAFETY``
#:
#: with ``STAGED_UNIT_WINDOW_SAFETY = 1.25``. At the START of a beat
#: ``remaining_ms`` is the whole unit budget and the reference is last beat's
#: measured mean, so a partition is only viable when
#: ``cost(B) * 1.25 <= 1,144 s``, i.e. **cost(B) <= 915.4 s**. This constant was
#: written 4, then 6, then 5 against a hand-picked "85% of the window" ceiling
#: before CERT-2071 caught it: 5 costs 952 s, the gate refuses the NEXT beat's
#: first unit, and progress alternates with self-blocked beats. The guard now
#: IMPORTS ``STAGED_UNIT_WINDOW_SAFETY`` instead of restating it.
#:
#: 🔴 READ THIS BEFORE MOVING THE DIAL AGAIN — NO PARTITION IS COMFORTABLE.
#: The fixed prefix ALONE, at 1.25x, is **1,066 s against a 1,144 s budget —
#: 93.2%**. So the largest admission margin ANY partition can achieve, even at
#: B → ∞, is **+7.30%**. Meanwhile the measured beat-to-beat variance of one
#: unit at a FIXED partition is **+18.4%** (723.8 s then 857.0 s, both at 128).
#: **The variance is 2.5x the best margin available.** Self-blocked beats are
#: therefore STRUCTURAL at every partition including 128 today, and no value of
#: this constant removes them. It only changes how often they cost something and
#: how much each surviving beat is worth. Anyone reading a self-blocked beat as
#: evidence against the partition should check it against this paragraph first.
#:
#: SIZING PART TWO — THE OPERATIVE ONE.
#: 17 SHIPPED FOR ONE HOUR AND PRODUCTION REFUTED IT TOO (CAL-P1035, #3536).
#: THE PARAGRAPH ABOVE ASKED FOR THE THIRD MEASURED POINT. HERE IT IS.
#:
#: It said, correctly, that "every number here below B=128 is EXTRAPOLATED from a
#: two-point fit whose small-B anchor is a historical monolith reading" — and
#: then shipped the extrapolation anyway. The anchor was worse than "historical":
#: the ~1,350 s monolith reading is a statement Postgres **CANCELLED** at
#: 1,351,525 ms (#2052). A cancellation is a floor, not a duration. Fitting an
#: equality through it dragged the curve down, understated the scalable term and
#: overstated the fixed prefix — which is exactly the bias that makes a small
#: partition look affordable.
#:
#: THE THIRD POINT, and it is decisive. 2026-09-06 **15:15:00Z**, the first beat
#: at B=17 in a window no release touched (``beat:cancel_cause:incomplete``,
#: elapsed 1,350,702 ms, ``staged:units_partition`` 17). It paid a 197,931 ms
#: generation freeze, handed ONE unit a 1,137,529 ms statement bound — essentially
#: the entire remainder of the beat — and the unit **did not finish**:
#: ``read:futures_unit`` 1,137,955 ms, ``staged:units_cancelled`` 1,
#: ``staged:units_completed_this_beat`` 0, ``staged:window_stop:unit_too_large``.
#:
#: Predicted 882 s. Cancelled, still running, at 1,138 s — at least 29% over, with
#: the true cost unknown. **There is no longer window to give it**, so B=17 cannot
#: bank a unit on any beat, ever. It is not slow, it is non-convergent: strictly
#: worse than the 128 it replaced, which at least banks one unit per beat.
#:
#: THE REFIT, anchored on the completion at 128 and the CENSORED floor at 17 (so
#: every number it produces is a lower bound and every "this fits" is optimistic):
#: fixed prefix **P ≈ 814 s**, scalable part **≈ 5,508 s** for the whole
#: population. The scalable term is nearly SEVEN times the prefix per unit — the
#: opposite of what the refuted fit said — while across a generation the prefix is
#: paid B times and still dwarfs it (104,000 s vs 5,500 s at B=128). Both are true;
#: conflating them is what produced 17.
#:
#: THE RULE, tightened so this cannot happen a third time — searched in the guard,
#: not asserted here: **ship the smallest partition that (a) the optimistic model
#: admits AND (b) production has COMPLETED a unit at.** Clause (a) alone is what
#: shipped 17. Clause (b) is new and it is the one that bites: the model admits
#: everything from 55 up, but the only partition with measured completions is 128
#: (723.8 s and 857.0 s). So 128 it is — not because it is good, but because it is
#: the only size we have watched finish. To ship 55 or 64, MEASURE ONE THERE FIRST
#: and add it to ``MEASURED_COMPLETIONS``.
#:
#: 128 costs 129 whole beats and misses the 24-beat freshness budget by 5x. Under
#: an honest fit NO partition reaches that budget — the cheapest admissible one,
#: B=55, still costs 56 beats. **The dial is exhausted.** That is the finding, and
#: it is not a reason to keep turning it.
#:
#: THIS IS THE DIAL, NOT THE REPAIR. Bringing the fixed prefix down is now the
#: ONLY thing left: a unit's statement scanning only its own slot instead of
#: paying the full-population prefix B times over. That lives in
#: ``_futures_population_sql`` in ruling-D45-frozen ``precompute_calibration.py``
#: and needs Alex's words (D80); this constant does not.
#:
#: Changing it re-keys every unit and costs exactly one generation of banked
#: work — safe, not free. The bank held ZERO units when this was changed back
#: (B=17 never banked one), so the re-key cost nothing on the day.
STAGED_FUTURES_BUCKETS = 128

def _process_rss_mb() -> float | None:
    """This process's resident set size in MB, or ``None`` if unobtainable.

    CAL-P024c. Deliberately dependency-free — ``psutil`` is not installed and a
    memory probe that needs a new package on a dyno that is already dying of
    memory is the wrong trade.

    Linux (the dyno) is read from ``/proc/self/statm``, whose second field is
    resident pages. macOS (the dev sandbox) has no ``/proc``, so it falls back
    to ``resource.getrusage``, where ``ru_maxrss`` is BYTES on Darwin and
    KILOBYTES on Linux — a units trap worth naming, since getting it wrong on
    the platform that matters would report 1/1024th of the real figure and make
    a dying build look comfortable.

    Returns ``None`` rather than raising or guessing: an unavailable measurement
    must not be recorded as a small one.
    """
    try:
        with open("/proc/self/statm", "rb") as fh:
            resident_pages = int(fh.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
    except (OSError, IndexError, ValueError):
        pass
    try:
        import resource
        import sys

        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # ru_maxrss: bytes on Darwin, kilobytes on Linux.
        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        return max_rss / divisor
    except Exception:  # noqa: BLE001 — instrumentation never raises
        return None


#: A ledger or checkpoint older than this is a fossil, not state in progress.
STATE_MAX_AGE_S = 14 * 86400

#: How long this run's claim on the checkpoint is good for. Comfortably past
#: the Celery hard limit so a run that is SIGKILLed still holds the lease until
#: after it could possibly still be alive, and no longer.
LEASE_S = (HARD_LIMIT_MS / 1000.0) + 300.0

#: Ceiling on ONE phase's serialized output inside the checkpoint.
PHASE_OUTPUT_MAX_BYTES = 4_000_000
#: Ceiling on the whole checkpoint payload. Largest-first drop when exceeded.
CHECKPOINT_MAX_BYTES = 8_000_000

#: Postgres cancels a statement with this message; it is the phase's own inner
#: backstop firing, not a bug, and it must be recorded as ``timeout`` rather
#: than lumped in with a genuine failure.
_STATEMENT_TIMEOUT_MARKERS = (
    "canceling statement due to statement timeout",
    "querycanceled",
)


def is_statement_timeout(exc: BaseException) -> bool:
    """Is this exception Postgres cancelling a statement at its own backstop?

    Hoisted out of :meth:`PhaseRunner.classify_failure` by CAL-P081 (#2052) so
    the unit loop can ask the SAME question the terminal classifier asks. Two
    copies of this predicate would drift, and the drift would be silent in the
    worst direction: a cancellation the loop failed to recognise propagates and
    the beat terminates ``failed`` — which is precisely the false RED #2052 is.

    Matched on the rendered class name plus message rather than on a driver
    exception type, deliberately: SQLAlchemy wraps ``asyncpg`` cancellations in
    ``DBAPIError``, the wrapping has changed shape across versions, and the
    message has not.
    """
    text_form = f"{exc.__class__.__name__} {exc}".lower()
    return any(marker in text_form for marker in _STATEMENT_TIMEOUT_MARKERS)


class StagedFuturesIncomplete(RuntimeError):
    """The staged futures generation made progress but is not finished.

    Deliberately its own type rather than a bare ``RuntimeError``: this is the
    ONE way the build stops that is neither a bug nor a resource problem. Units
    committed, the cursor advanced, the next beat will resume — the only correct
    response is to publish nothing and say so. :meth:`PhaseRunner.classify_failure`
    maps it to ``cancelled`` (ran out of window without finishing) rather than
    ``failed``, so a working build does not page anybody RED for doing exactly
    what it was designed to do.
    """


#: Prefix for the gauge that says WHY a beat ended ``cancelled``.
#:
#: A prefix rather than a fixed key so the value is a NAME and not a code an
#: operator has to look up, and so a cause this file has not thought of yet
#: cannot be silently rendered as one it has. Read by a prefix scan in
#: ``calibration_beat_gauge_sampler.select_gauges``, the same way
#: ``staged:convergence_reason:`` already is — no fixed tuple can hold it.
CANCEL_CAUSE_PREFIX = "beat:cancel_cause:"

#: The beat ran out of window with units banked and nothing published. The
#: DESIGNED partial: ``StagedFuturesIncomplete`` exists to say exactly this, and
#: a beat ending this way is a build working as specified.
CANCEL_CAUSE_INCOMPLETE = "incomplete"

#: The RUNTIME took the worker away mid-phase — a deploy cycling ``worker-heavy``,
#: a dyno restart, an operator pausing the process. Nothing about the build is
#: wrong; it simply stopped existing.
CANCEL_CAUSE_INTERRUPTED = "interrupted"


def cancel_cause(exc: BaseException) -> Optional[str]:
    """``incomplete`` | ``interrupted`` | ``None`` — WHY a beat ended cancelled.

    CAL-P993, from calibration-028. :meth:`PhaseRunner.classify_failure` maps
    ``StagedFuturesIncomplete`` and ``asyncio.CancelledError`` to the SAME
    terminal, ``cancelled``, and both of them are correct to do so: neither is a
    failure and neither should page anybody. But they are opposite facts about
    the producer, and collapsing them cost this program a night.

    * ``incomplete`` is the build saying *I did not finish, and that is the
      design.* It is the number that answers "is the staged build converging?"
    * ``interrupted`` is the build saying *I was killed.* It answers a question
      about the DEPLOY CADENCE, not about calibration at all.

    Measured on production 2026-09-03 over the 168-beat ring: **21 of the 23
    ``interrupted`` beats had a Heroku release inside their own window**, and
    the last four terminated 16-28 s after one. Ruling 009's freeze score read
    all of them as the producer failing to converge, because the ring had no
    field in which the difference could be written down. That is gotcha #53 in
    its exact form — one word standing for two states — and ruling 075's second
    clause is the rule it breaks.

    Returns ``None`` for anything that is not a cancellation, so a caller can
    write ``if cause is not None`` rather than testing the terminal twice.

    Derived from the SAME predicates :meth:`PhaseRunner.classify_failure` uses,
    in the same order, deliberately: a second copy of the classification would
    be free to disagree with the terminal it is annotating, and an annotation
    that contradicts its subject is worse than no annotation.
    """
    import asyncio

    if isinstance(exc, StagedFuturesIncomplete):
        return CANCEL_CAUSE_INCOMPLETE
    if isinstance(exc, asyncio.CancelledError):
        return CANCEL_CAUSE_INTERRUPTED
    return None


def is_runtime_interruption(exc: BaseException) -> bool:
    """The RUNTIME took the worker away — as opposed to the work being wrong.

    CAL-P994, repairing CERT-821's named follow-up
    (``CAL-P994-SOFT-TIME-LIMIT-CLASSIFICATION``). The post-publish rebuild
    swallows its own death and records it under one of two names, and the
    difference between them is the difference between two operator questions:
    ``staged:rebuild_interrupted`` asks about the DEPLOY CADENCE, while
    ``staged:rebuild_error`` asks whether the unit loop is broken. Celery's
    ``SoftTimeLimitExceeded`` is a plain ``Exception``, so a soft kill — the
    ordinary way a beat ends when it runs past its limit — was landing in the
    second bucket and inflating exactly the number that would say the rebuild
    itself is defective. That is gotcha #53's shape again: one name standing for
    two states, in the evidence this queue promised.

    **Deliberately NOT wired into** :func:`cancel_cause` **or**
    :meth:`PhaseRunner.classify_failure`. Those two decide the BEAT's terminal,
    where a soft kill is currently ``failed``; moving it to ``cancelled`` would
    re-shape every freeze-score reading taken since ruling 009 and is a measured
    question, not a repair. This predicate is scoped to the rebuild's own
    gauges, and this paragraph is why the two classifications differ.
    """
    import asyncio

    if isinstance(exc, asyncio.CancelledError):
        return True
    try:
        from celery.exceptions import SoftTimeLimitExceeded
    except Exception:  # noqa: BLE001 — no Celery in a bare import context
        return False
    return isinstance(exc, SoftTimeLimitExceeded)


def describe_failure(exc: BaseException) -> str:
    """``str(exc)``, or the class name when the exception has no message.

    ``asyncio.CancelledError()`` renders as the empty string, and
    ``PhaseLedger.fail`` stores ``detail or None`` — so every deploy-killed beat
    since this rail was built has landed in the ledger with NO detail at all,
    and the phase record read as if nothing had been recorded rather than as a
    cancellation with an empty message. The class name is the minimum a reader
    needs to tell those apart.

    Truncated to the same 200 characters the ledger stores, here rather than at
    the call site, so the bound travels with the description.
    """
    return (str(exc) or type(exc).__name__)[:200]


def run_owner() -> str:
    """Who is building right now. Stable within a run, distinct across workers."""
    return f"{socket.gethostname()}:{os.getpid()}"


async def tag_scheduled_session(db, *, task: str) -> dict:
    """Session identity for a scheduled calibration task with no PhaseRunner.

    The main build gets its tag through :meth:`PhaseRunner.tag_session`, which
    can name the exact run generation it is checkpointing under. The horizon,
    fair-fight and coverage sweeps have no ledger, so they derive a generation
    from their own start instant — enough to tell two beats apart and to place a
    backend against the deploy it started under, which is the whole ask.

    Their queries are individually bounded and none of them is the ~22-minute
    population CTE, so they are not the likely orphan. Tagging them anyway is
    what makes the ABSENCE of a tag meaningful: once every scheduled calibration
    session is named, an untagged calibration-shaped backend is by itself
    evidence that it predates this change.
    """
    from app.tasks.base import tag_task_session
    from app.utils.durable_state import generation_for

    return await tag_task_session(
        db,
        task=task,
        run_generation=generation_for(datetime.now(timezone.utc)),
        owner=run_owner(),
    )


# =============================================================================
# Lossless (de)serialization of read output
# =============================================================================


def _encode(value: Any) -> Any:
    """JSON-safe, round-trippable. Types that would lose precision are tagged.

    ``Decimal`` is the one that matters: Postgres returns ``AVG(prob)`` as a
    Decimal, and both a float cast and ``canonical_json``'s ``default=str``
    would change what the downstream bucket arithmetic sees. Tagging keeps a
    carried phase byte-equivalent to a freshly-read one.
    """
    if isinstance(value, Decimal):
        return {"__t__": "dec", "v": str(value)}
    if isinstance(value, datetime):
        return {"__t__": "dt", "v": value.isoformat()}
    if isinstance(value, date):
        return {"__t__": "d", "v": value.isoformat()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    return {"__t__": "repr", "v": str(value)}


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        # Only a dict that is EXACTLY a tag envelope is un-tagged; a payload
        # dict that merely happens to contain a "__t__" key stays a dict.
        if set(value) == {"__t__", "v"}:
            tag = value["__t__"]
            if tag == "dec":
                return Decimal(value["v"])
            if tag == "dt":
                return datetime.fromisoformat(value["v"])
            if tag == "d":
                return date.fromisoformat(value["v"])
            if tag == "repr":
                return value["v"]
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def encode_rows(rows: Any) -> list[dict[str, Any]]:
    """SQLAlchemy ``Row``s (or namespaces) to a list of plain encoded dicts."""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        mapping = getattr(row, "_mapping", None)
        if mapping is not None:
            source = dict(mapping)
        elif isinstance(row, dict):
            source = dict(row)
        else:
            source = dict(vars(row))
        out.append({str(k): _encode(v) for k, v in source.items()})
    return out


def decode_rows(raw: Any) -> list[SimpleNamespace]:
    """Back to attribute-access rows the downstream post-processing accepts."""
    return [SimpleNamespace(**{k: _decode(v) for k, v in item.items()}) for item in (raw or [])]


def _encode_value(kind: str, value: Any) -> Any:
    if kind == "rows":
        return encode_rows(value)
    if kind == "row":
        encoded = encode_rows([value])
        return encoded[0] if encoded else None
    return _encode(value)


def _decode_value(kind: str, value: Any) -> Any:
    if kind == "rows":
        return decode_rows(value)
    if kind == "row":
        decoded = decode_rows([value] if isinstance(value, dict) else [])
        return decoded[0] if decoded else None
    return _decode(value)


# =============================================================================
# The runner
# =============================================================================


class SoftStageOutcome:
    """What a :meth:`PhaseRunner.soft_stage` body left behind.

    ``failed`` is the whole interface: the caller reads it to decide whether the
    value it just tried to compute exists. An object rather than a return value
    because the stage is a context manager and the body assigns to its own
    locals. Deliberately not a dataclass — this module imports none and one
    two-field holder is not a reason to start.
    """

    __slots__ = ("failed", "error")

    def __init__(self) -> None:
        self.failed: bool = False
        self.error: str | None = None


class PhaseRunner:
    """Times, bounds, resumes and records one main-build run's phases.

    Every method is safe to call on a run with no prior state; the "no
    checkpoint yet" path is the normal first run, not an error branch.
    """

    def __init__(
        self,
        *,
        plan: PhasePlan,
        checkpoint: MainBuildCheckpoint,
        checkpoint_action: str,
        population_version: str,
        owner: str,
        generation: int,
        fingerprint: str,
    ) -> None:
        self.ledger = PhaseLedger(
            plan=plan,
            population_version=population_version,
            owner=owner,
            generation=generation,
            input_fingerprint=fingerprint,
        )
        self.checkpoint = checkpoint
        self.checkpoint_action = checkpoint_action
        self.owner = owner
        self.generation = generation
        self.fingerprint = fingerprint
        self.population_version = population_version
        self._started = time.monotonic()
        #: phase -> {key: (kind, live value)} captured THIS run.
        self._captured: dict[str, dict[str, tuple[str, Any]]] = {}
        #: phase -> decoded carried output, materialized lazily once.
        self._carried: dict[str, dict[str, Any]] = {}
        self.carried_phases: list[str] = []
        self.checkpoint_writes: dict[str, str] = {}
        #: D22. Names of soft stages whose read did NOT happen this beat. A
        #: degraded read is not a zero: the payload has to be able to say
        #: "unobserved" rather than publish a default that reads as evidence
        #: (gotcha #53 — an empty answer is a response shape).
        self.degraded_stages: list[str] = []
        #: Queue 300B Item 1. The SERVER's view of this run — the tag it wrote
        #: into ``application_name`` and the backend PID that wrote it. Recorded
        #: in the ledger so a ``pg_stat_activity`` row seen weeks later can be
        #: joined back to a named run instead of inferred from age.
        self.session_identity: dict[str, Any] = {
            "application_name": None,
            "backend_pid": None,
            "applied": False,
        }
        #: CAL-P994. The deferred rebuild runs on its OWN session, so it has its
        #: own backend, and it must not be written over the build's — that field
        #: exists so a ``pg_stat_activity`` row seen weeks later joins back to
        #: the run that wedged, and the run that wedges is the one holding the
        #: publish. Two backends, two fields, both named.
        self.rebuild_session_identity: dict[str, Any] = {
            "application_name": None,
            "backend_pid": None,
            "applied": False,
        }
        #: Filled in progressively by the build so the orchestrator's ``finally``
        #: can tell a gate refusal from a durable failure from a clean publish
        #: WITHOUT re-deriving it from an exception message.
        self.outcome: dict[str, Any] = {
            "gate": "not_evaluated",
            "durable": "not_attempted",
            "volatile": "not_attempted",
            "published": False,
            "artifact_generation": None,
        }
        #: CAL-P994 / D45(A). Set by the futures phase when it decided to publish
        #: from the SERVED bank and leave the rebuild's unit loop until after the
        #: publish. Read by the orchestrator, which is the only place that knows
        #: the publish is done. Default False, so a build that never took the
        #: reorder behaves exactly as it did before.
        self.rebuild_deferred: bool = False

    # -- staging --------------------------------------------------------------

    def defer_rebuild(self) -> None:
        """Record that this beat's unit loop belongs AFTER the publish.

        CAL-P994 (D45 = A, a narrow ruling-009 exception for the publish
        ordering). One-way: nothing clears it within a beat, because the only
        consumer runs once, at the end, and a flag that could be un-set would
        make "did the rebuild get its window?" depend on read order.
        """
        self.rebuild_deferred = True

    @property
    def staged_futures(self) -> bool:
        """Whether this run may read the futures population in chunks.

        A property rather than a constructor argument so there is exactly one
        answer to "is this the scheduled build?" — owning a real runner IS the
        condition, and :data:`STAGED_FUTURES_ENABLED` is the operator's switch
        on top of it.
        """
        return STAGED_FUTURES_ENABLED

    # -- clock ----------------------------------------------------------------

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def deadline_exceeded(self) -> bool:
        return self.ledger.remaining_ms(elapsed_ms=self.elapsed_ms()) <= 0

    # -- phase lifecycle ------------------------------------------------------

    def begin(self, phase: str) -> None:
        self.ledger.begin(phase, now_ms=self.elapsed_ms())

    def complete(self, phase: str, *, committed: bool = True) -> int:
        return self.ledger.complete(phase, now_ms=self.elapsed_ms(), committed=committed)

    def carry(self, phase: str) -> None:
        self.ledger.carry(phase, source_generation=self.checkpoint.generation)
        self.carried_phases.append(phase)

    def is_carried(self, phase: str) -> bool:
        """True when a prior beat already banked this phase's whole output."""
        return self.ledger.records[phase].status == RESUMED

    @contextlib.contextmanager
    def stage(self, name: str):
        """Time one named sub-phase stretch, whatever happens inside it.

        Recorded on the way out even when the body raises, because the stage
        that blew up is the one worth knowing the cost of. Stages carry no
        budget and no resume semantics — they exist purely so no part of the
        build is unaccounted for.

        CAL-P067 adds the one bit that was missing: WHETHER the body finished.
        Recording the raising stretch is right, and silently pooling it with the
        completed ones is not — a truncated observation is a lower bound, and a
        mean taken over both is not a cost. The two tallies stay separate in the
        ledger so a feasibility check can be handed the completed one.
        """
        started = time.monotonic()
        completed = False
        try:
            yield
            completed = True
        finally:
            self.ledger.record_stage_outcome(
                name, int((time.monotonic() - started) * 1000), completed=completed
            )
            # CAL-P024c: the build is being hard-killed on a 512MB dyno, and a
            # SIGKILL leaves no traceback naming where the memory went. Sampled
            # here because a stage boundary is the only place in the build that
            # is both frequent and cheap: `rss:peak_mb` is the high-water mark
            # for the whole run, `rss:at:<stage>` the reading after the stage
            # that most recently ran. A kill therefore leaves the last stage it
            # survived and the RSS it had reached, which is the difference
            # between "dies of memory" and "dies of memory in read:futures_unit
            # at 480MB".
            self._sample_rss(name)

    def _sample_rss(self, stage_name: str) -> None:
        """Record RSS now, best-effort. Never the reason a build fails."""
        try:
            rss_mb = _process_rss_mb()
        except Exception:  # noqa: BLE001 — instrumentation must not raise
            return
        if rss_mb is None:
            return
        # Gauges, not counters: an RSS level summed over 128 unit stages would
        # publish tens of thousands of "MB" (see PhaseLedger.record_gauge).
        self.ledger.record_gauge(f"rss:at:{stage_name}", int(rss_mb))
        if int(rss_mb) > int(self.ledger.stages.get("rss:peak_mb", 0)):
            self.ledger.record_gauge("rss:peak_mb", int(rss_mb))

    def classify_failure(self, exc: BaseException) -> str:
        """timeout | cancelled | failed — the three ways a phase can end badly."""
        import asyncio

        if isinstance(exc, (asyncio.CancelledError, StagedFuturesIncomplete)):
            return CANCELLED
        if is_statement_timeout(exc):
            return TIMEOUT
        return FAILED

    def abort(self, exc: BaseException) -> str:
        """Close whatever phase was in flight, classified. Returns the status.

        CAL-P993 (calibration-028) records the CAUSE beside the status. See
        :func:`cancel_cause` for why ``cancelled`` alone is not an answer, and
        :data:`CANCEL_CAUSE_PREFIX` for how it reaches the ring.
        """
        status = self.classify_failure(exc)
        self.ledger.close_open_phase(
            now_ms=self.elapsed_ms(), status=status, detail=describe_failure(exc)
        )
        cause = cancel_cause(exc)
        if cause is not None:
            # A gauge, not a stage: this is a LEVEL ("this beat ended that
            # way"), and ``record_stage`` accumulates repeats.
            self.ledger.record_gauge(f"{CANCEL_CAUSE_PREFIX}{cause}", 1)
        return status

    # -- resume / capture -----------------------------------------------------

    def reuse(self, phase: str, key: str) -> Any:
        """A prior beat's committed value for ``phase.key``, or ``None``.

        ``None`` always means "not carried, do the read". No phase output here
        is legitimately ``None`` — every one is a row list, a count, or a dict.
        """
        if phase not in self.checkpoint.completed_phases:
            return None
        if phase not in self._carried:
            stored = self.checkpoint.output(phase) or {}
            values = stored.get("values")
            if not isinstance(values, dict):
                return None
            self._carried[phase] = {
                name: _decode_value(entry.get("kind", "value"), entry.get("value"))
                for name, entry in values.items()
                if isinstance(entry, dict)
            }
        return self._carried[phase].get(key)

    @contextlib.asynccontextmanager
    async def soft_stage(self, db, name: str):
        """Time a read the beat is allowed to publish WITHOUT.

        D22 (calibration-912 DECIDE 1). The diagnostics phase is required and
        runs AHEAD of the publish, so a statement timeout in one of its counts
        kills a beat that had everything it needed to publish. Two of those
        counts feed nothing the gate reads — by their own comments they are
        "just the counts".

        THE PART THAT IS NOT A TRY/EXCEPT. A statement timeout aborts the whole
        transaction, not the statement: after it, every later read in the same
        session fails and the ``commit`` at the end of the phase raises. That is
        why the ONE diagnostics read already wrapped in ``try`` — ``date_range``
        — is not actually fail-soft against the failure that happens; it only
        survives because it is last, and even then the phase commit inherits the
        aborted transaction. A savepoint is what makes the rest of the beat
        reachable: ``ROLLBACK TO SAVEPOINT`` is legal in an aborted subtransaction
        and returns the session to a usable state.

        ``SET LOCAL statement_timeout`` is applied OUTSIDE the savepoint (per
        phase, in :meth:`apply_statement_timeout`) so rolling back to it does not
        drop the phase's own bound.

        Yields a one-field outcome object. The caller MUST branch on
        ``.failed``: a soft read that quietly leaves its variable at a default
        is the failure this whole mechanism exists to make visible.
        """
        outcome = SoftStageOutcome()
        savepoint = await db.begin_nested()
        try:
            with self.stage(name):
                yield outcome
        except Exception as exc:  # noqa: BLE001 — deliberately broad; see below
            # Broad on purpose: the point is that NO read in here may end the
            # beat. The failure is not swallowed — it is named in the ledger,
            # logged with its traceback, and surfaced in the payload.
            outcome.failed = True
            outcome.error = f"{type(exc).__name__}: {exc}"[:240]
            self.degraded_stages.append(name)
            await savepoint.rollback()
            logger.warning(
                "calibration soft stage %s degraded: %s", name, outcome.error,
                exc_info=True,
            )
        else:
            await savepoint.commit()

    def record(self, phase: str, key: str, value: Any, *, kind: str = "value") -> None:
        """Capture a freshly-read value so the next beat can carry it."""
        self._captured.setdefault(phase, {})[key] = (kind, value)

    async def tag_session(self, db) -> dict:
        """Announce this run's identity on the live backend (Queue 300B Item 1).

        Both this and :meth:`apply_statement_timeout` are ``SET LOCAL``-scoped,
        which is what makes them safe — and also what makes them perishable.
        :meth:`commit` ends the transaction between phases, so both have to be
        re-armed on the far side of every commit or the next phase runs bare.
        """
        from app.tasks.base import tag_task_session

        identity = await tag_task_session(
            db,
            task=MAIN_BUILD_TASK,
            run_generation=self.generation,
            owner=self.owner,
        )
        # The PID is captured once and kept: it is the run's server-side identity
        # for the whole run, and a later re-tag on the same session returns the
        # same backend. Keeping the first non-null value means a transient
        # failure to re-tag cannot erase what we already proved.
        if identity.get("backend_pid") is not None or not self.session_identity.get(
            "applied"
        ):
            self.session_identity = identity
        return identity

    async def tag_rebuild_session(self, db) -> dict:
        """Name the DEFERRED REBUILD's backend — CAL-P994 — on its own field.

        Same tag, same task, same run generation: an orphaned backend from the
        post-publish rebuild must be as findable as one from the build, and
        leaving it untagged would put back exactly the anonymous phase-1 orphan
        #1479 is still stuck on.

        What it must NOT do is land in :attr:`session_identity`. That field's
        contract — set once, kept — rests on there being one session per run,
        which stopped being true the moment the rebuild got its own. Overwriting
        it would mean the ledger named the backend that was rebuilding while the
        backend that published (the one whose wedge costs a curve) went
        unrecorded.
        """
        from app.tasks.base import tag_task_session

        identity = await tag_task_session(
            db,
            task=MAIN_BUILD_TASK,
            run_generation=self.generation,
            owner=self.owner,
        )
        if identity.get("backend_pid") is not None or not self.rebuild_session_identity.get(
            "applied"
        ):
            self.rebuild_session_identity = identity
        return identity

    async def apply_statement_timeout(self, db, phase: str) -> int:
        """Set this phase's inner DB backstop on the live session.

        Applied per phase rather than once per session so a phase that resumed
        (and therefore did no reading) does not silently hand its unused time to
        the next one, and so the bound always reflects the time actually left
        before the absolute deadline.

        The session tag rides along here rather than in its own call because the
        two have identical lifetimes — transaction-local, wiped by the inter-phase
        commit — and separating them is how one of them ends up silently missing
        from the phase that eventually wedges.
        """
        timeout_ms = self.ledger.statement_timeout_for(phase, elapsed_ms=self.elapsed_ms())
        await db.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
        await self.tag_session(db)
        return timeout_ms

    def measured_unit_ms(self, phase: str):
        """The carried, measured cost of one completed unit of ``phase``.

        Exposed on the runner rather than reached for through ``.ledger`` by the
        caller, because the caller is the frozen module (ruling 009) and every
        line of judgment that can live on this side of the boundary should.
        """
        return self.ledger.measured_unit_ms(phase)

    async def apply_unit_statement_timeout(
        self, db, phase: str, *, unit_ms=None, deferred_rebuild: bool = False
    ) -> int:
        """Set the backstop for ONE unit of a unit-staged phase — CAL-P081 (#2052).

        Same contract as :meth:`apply_statement_timeout` and strictly tighter:
        the unit gets the smaller of the phase's remaining window and a multiple
        of its own measured cost. With no measured cost the two are identical, so
        this is never the reason a build stops making progress.

        ``deferred_rebuild`` says this call is CAL-P994's post-publish pass, and
        it governs the two things that stop being true there. The phase budget
        stops describing the loop (see
        :meth:`~app.utils.calibration_phase_ledger.PhaseLedger.statement_timeout_for_unit`
        for the measurement and for why dropping that term is not a loosening),
        and the re-tag below belongs to a DIFFERENT backend, so it is written to
        :attr:`rebuild_session_identity` rather than over the build's. One flag
        rather than two, because there is one underlying fact: this loop is
        running somewhere else, later.
        """
        timeout_ms = self.ledger.statement_timeout_for_unit(
            phase,
            elapsed_ms=self.elapsed_ms(),
            unit_ms=unit_ms,
            ignore_phase_budget=deferred_rebuild,
        )
        # CAL-P163 (#1978): say WHICH evidence bounded this unit, and how far the
        # bound sits from the window that was actually available. Without this
        # pair, a cancelled unit records only that it was cancelled — the same
        # ledger entry whether the fence was 100 ms too tight or 600 s too
        # tight, and those call for opposite responses. The sixteen-beat pin
        # this fix addresses cost a day to attribute for exactly that reason.
        self.ledger.record_gauge(
            f"staged:unit_bound_ms:{phase}", int(timeout_ms)
        )
        self.ledger.record_gauge(
            f"staged:unit_bound_headroom_ms:{phase}",
            max(0, self.ledger.remaining_ms(elapsed_ms=self.elapsed_ms()) - int(timeout_ms)),
        )
        worst = self.ledger.measured_unit_worst_ms(phase)
        if worst:
            self.ledger.record_gauge(f"staged:unit_worst_carried_ms:{phase}", int(worst))
        else:
            # Ruling 075, second clause: "no carried worst" must not render
            # identically to "the carried worst is zero".
            self.ledger.record_gauge(f"staged:unit_worst_reason:unmeasured:{phase}", 1)
        await db.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
        await (
            self.tag_rebuild_session(db) if deferred_rebuild else self.tag_session(db)
        )
        return timeout_ms

    async def commit(self, db) -> None:
        """End the phase's read transaction so its output counts as committed.

        Two things follow from this that the single-transaction build could not
        have. First, ``checkpoint_advanced`` becomes truthful: the cursor moves
        only after the work behind it is committed. Second — and this one is
        free — the build stops holding ONE MVCC snapshot open across all eleven
        reads for the better part of half an hour, which is exactly the xmin
        pin that let dead tuples accumulate faster than autovacuum could
        reclaim them (#1479's bloat spiral).
        """
        await db.commit()

    # -- persistence ----------------------------------------------------------

    def _serialize_phase(self, phase: str) -> tuple[Optional[dict[str, Any]], int]:
        captured = self._captured.get(phase)
        if not captured:
            return None, 0
        expected = PHASE_OUTPUT_KEYS.get(phase, frozenset())
        if set(captured) != set(expected):
            # Half a phase is not a phase. Storing it would let a later beat
            # mark the phase done and publish a payload missing the rest.
            logger.warning(
                "calibration phase ledger: %s captured %s but owes %s — not "
                "checkpointed", phase, sorted(captured), sorted(expected),
            )
            return None, 0
        values = {
            key: {"kind": kind, "value": _encode_value(kind, value)}
            for key, (kind, value) in captured.items()
        }
        body = {"stored": True, "values": values}
        size = len(json.dumps(body, separators=(",", ":"), default=str))
        return body, size

    def rebuild_in_flight(self) -> bool:
        """Is a rolling re-stage part-way through its 128 units? — CAL-P081.

        Read off the two stages ``_record_convergence_projection`` writes at the
        end of the unit loop, so it is answerable on any beat where the loop ran
        and honestly unanswerable (``False``) on any beat where it did not. That
        asymmetry is the right way round: the beat that must not bank a carry is
        the beat that just ran units and knows it did not finish.
        """
        planned = self.ledger.stages.get("staged:units_planned")
        done = self.ledger.stages.get("staged:units_done")
        if not isinstance(planned, int) or planned <= 0:
            return False
        if not isinstance(done, int):
            return False
        return done < planned

    def build_checkpoint(self) -> tuple[MainBuildCheckpoint, dict[str, str]]:
        """Fold this run's committed phase outputs into a checkpoint.

        Carried phases stay carried (their stored form is reused verbatim —
        re-encoding a decoded row list would be pure cost for no change).
        Oversize output is dropped rather than truncated, and the drop is
        recorded so the ledger can say which phases the next beat must redo.

        **CAL-P081 (#2007): the futures phase is NOT banked while a rolling
        re-stage is part-way through.** Measured, not reasoned: the 20:15Z beat
        on 2026-08-20 published with ``carried: ['futures', 'sports']``,
        ``staged:units_this_beat: 0`` and ``staged:rate_reason:no_unit_ran: 1``,
        leaving ``rebuild_units_banked`` at 13/128 exactly where the 18:22Z beat
        left it. Carrying the phase output skips ``_run_staged_futures``
        entirely, and the unit loop is the ONLY thing that advances the rebuild
        — so a carry is a whole beat of re-stage bought for one ~75 s generation
        read, on a bank that needs ~15 more advances.

        It compounds with the teardowns: an interrupted beat that had finished
        futures banks the carry, the next beat spends itself carrying it, and two
        beats of re-stage are gone per deploy. Six releases landed between 16:16Z
        and 20:07Z.

        Scoped to ``PHASE_FUTURES`` and to the in-flight case only. Every other
        phase carries exactly as before, and so does futures once the rebuild has
        no units outstanding.
        """
        checkpoint = new_main_checkpoint(
            version=self.population_version,
            fingerprint=self.fingerprint,
            owner=self.owner,
            generation=self.generation,
        )
        lease = time.time() + LEASE_S
        outcomes: dict[str, str] = {}
        sized: list[tuple[str, dict[str, Any], int]] = []

        rebuild_in_flight = self.rebuild_in_flight()
        for phase in RESUMABLE_PHASES:
            record = self.ledger.records.get(phase)
            if record is None or record.status not in DONE_STATUSES:
                continue
            if phase == PHASE_FUTURES and rebuild_in_flight:
                # See the docstring. Recorded under its own outcome so "we chose
                # not to bank this" never reads as "there was nothing to bank"
                # (ruling 075, second clause).
                outcomes[phase] = "rebuild_in_flight"
                logger.info(
                    "calibration phase ledger: not banking %s — a rolling "
                    "re-stage is at %s/%s units and a carried beat runs none of "
                    "them", phase, self.ledger.stages.get("staged:units_done"),
                    self.ledger.stages.get("staged:units_planned"),
                )
                continue
            if phase in self.carried_phases and phase not in self._captured:
                stored = self.checkpoint.output(phase)
                if stored:
                    size = len(json.dumps(stored, separators=(",", ":"), default=str))
                    sized.append((phase, stored, size))
                continue
            body, size = self._serialize_phase(phase)
            if body is None:
                continue
            if size > PHASE_OUTPUT_MAX_BYTES:
                outcomes[phase] = "oversize"
                self.ledger.note_output(phase, size_bytes=size, stored=False)
                logger.warning(
                    "calibration phase ledger: %s output is %d bytes (> %d) — not "
                    "checkpointed; the next beat will recompute it rather than "
                    "resume a truncated read",
                    phase, size, PHASE_OUTPUT_MAX_BYTES,
                )
                continue
            sized.append((phase, body, size))

        # Largest-first drop until the whole checkpoint fits.
        total = sum(size for _, _, size in sized)
        while total > CHECKPOINT_MAX_BYTES and sized:
            sized.sort(key=lambda item: item[2])
            phase, _, size = sized.pop()
            total -= size
            outcomes[phase] = "checkpoint_full"
            self.ledger.note_output(phase, size_bytes=size, stored=False)
            logger.warning(
                "calibration phase ledger: dropping %s (%d bytes) to keep the "
                "checkpoint under %d bytes", phase, size, CHECKPOINT_MAX_BYTES,
            )

        for phase, body, size in sized:
            checkpoint = checkpoint.with_phase(
                phase, body, owner=self.owner, lease_expires_at=lease
            )
            outcomes[phase] = "stored"
            self.ledger.note_output(phase, size_bytes=size, stored=True)
        return checkpoint, outcomes


class NullPhaseRunner:
    """The no-runner path, spelled out so the build body has no ``if runner``.

    This is what the route's in-request cold-cache fallback gets: no timing, no
    checkpoint, no per-phase statement timeout, and — critically — no
    ``commit()``. A request session must not have its transaction ended
    underneath the caller, and a one-off serve has nothing to resume anyway.
    The build's behaviour on this path is exactly what it was before Queue 300M.
    """

    checkpoint_action = FRESH
    carried_phases: tuple[str, ...] = ()
    #: Never. A one-off serve has nothing to resume into and must not have its
    #: request transaction committed out from under the caller.
    staged_futures = False
    #: Never, and for the same reason: ``staged_futures`` is False here, so this
    #: path never reaches the unit loop the reorder moves. A class attribute
    #: rather than a settable one — the route must not be able to schedule
    #: background work off the back of a cold-cache serve.
    rebuild_deferred = False

    def __init__(self) -> None:
        self.outcome: dict[str, Any] = {
            "gate": "not_evaluated",
            "durable": "not_attempted",
            "volatile": "not_attempted",
            "published": False,
            "artifact_generation": None,
        }
        self.session_identity: dict[str, Any] = {
            "application_name": None,
            "backend_pid": None,
            "applied": False,
        }

    def begin(self, phase: str) -> None:  # noqa: D102 - no-op by design
        return None

    def complete(self, phase: str, *, committed: bool = True) -> int:  # noqa: D102
        return 0

    def is_carried(self, phase: str) -> bool:  # noqa: D102
        return False

    def reuse(self, phase: str, key: str) -> Any:  # noqa: D102
        return None

    def record(self, phase: str, key: str, value: Any, *, kind: str = "value") -> None:  # noqa: D102
        return None

    async def tag_session(self, db) -> dict:  # noqa: D102
        return dict(self.session_identity)

    async def apply_statement_timeout(self, db, phase: str) -> int:  # noqa: D102
        return 0

    def measured_unit_ms(self, phase: str):  # noqa: D102
        return None

    async def apply_unit_statement_timeout(self, db, phase: str, *, unit_ms=None) -> int:  # noqa: D102, E501
        return 0

    async def commit(self, db) -> None:  # noqa: D102
        return None

    @contextlib.contextmanager
    def stage(self, name: str):  # noqa: D102
        yield

    @contextlib.asynccontextmanager
    async def soft_stage(self, db, name: str):  # noqa: D102
        # 🔴 CAL-P150 CORRECTION TO THE CAL-P143 PRE-BUILD. This body was a bare
        # `yield SoftStageOutcome()` — no savepoint AND no handler — on the
        # reasoning that "the null runner is used where there is no live session
        # to protect". The first half is right and the second is not: this
        # runner is what `/api/calibration`'s in-request cold-cache fallback
        # gets, and one of the two reads D22 makes soft (`read:date_range`) was
        # previously wrapped in its own `try: ... except Exception:
        # logger.warning`. Moving it into a soft stage that does not catch
        # DELETED that handler. Measured: 38 failures across
        # test_calibration_spreads_totals / _coverage_census_300c / _query /
        # _field_completeness_257, all `AttributeError: 'NoneType' object has no
        # attribute 'lo'` — the exact exception the old `except` swallowed.
        #
        # So it catches, and the serve path is back to what it was. What it
        # deliberately does NOT do is open a savepoint: a request session must
        # not have its transaction structure changed underneath the caller, and
        # the route path has no phase commit to protect afterwards. That means a
        # real statement timeout here still leaves an aborted transaction for
        # any later read in the same request — which was ALSO true before D22,
        # so it is a limitation carried forward, not one introduced. The
        # producer path, which is the one that publishes, gets the savepoint.
        #
        # Nothing is accumulated in `degraded_stages`: NULL_RUNNER is a module
        # singleton shared by every request, so a list on it would leak one
        # request's degradation into the next one's evidence.
        outcome = SoftStageOutcome()
        try:
            yield outcome
        except Exception as exc:  # noqa: BLE001 — same contract as PhaseRunner
            outcome.failed = True
            outcome.error = f"{type(exc).__name__}: {exc}"[:240]
            logger.warning(
                "calibration soft stage %s degraded on the serve path: %s",
                name, outcome.error, exc_info=True,
            )


NULL_RUNNER = NullPhaseRunner()


# =============================================================================
# Durable load / save
# =============================================================================


#: Durable key for the rolling ring of worst COMPLETED unit durations —
#: CAL-P163 (#1978). Beside ``unit_costs`` rather than inside it because the
#: two have different lifetimes: the unit cost is a level the newest beat
#: overwrites, this is a window the newest beat appends to.
UNIT_WORST_HISTORY_KEY = "unit_worst_history"


def _bootstrap_worst_history(unit_costs: dict[str, Any]) -> dict[str, list[int]]:
    """The one-time upgrade for a ledger written before the ring existed —
    CAL-P167 (#1978), repairing CERT-637.

    CAL-P163 added a second, looser reference to the unit fence:
    ``max(observed completions) * BUDGET_SAFETY`` beside the old
    ``mean * STAGED_UNIT_OVERRUN_FACTOR``. It is inert on the state that
    actually exists at deployment. **Every durable ledger written before that
    deploy carries ``unit_costs`` and no ring**, so the max is ``None``, the
    fence falls back to the mean, and the first new-code beat reproduces the
    ratchet exactly — five completed, two cancelled, nothing published. The new
    ring then records only the cheap units that fence admitted, which is not
    enough to widen it, so the second beat is pinned too. CERT-637 named this
    and it is not hypothetical: the beat gauges read five completed and two
    cancelled at the moment that verdict was written.

    The repair cannot recover the real worst case — the 308,586 ms completion
    the ratchet forgot is genuinely absent from the legacy payload. What the
    payload does carry is the mean, and one fact about it: **the legacy fence
    admitted units at ``unit_ms * STAGED_UNIT_OVERRUN_FACTOR``, so a unit of
    that size is the largest one the legacy regime could have completed.** That
    ceiling is what the seed is, and it is why the factor here is
    :data:`STAGED_UNIT_OVERRUN_FACTOR` rather than a number of this session's
    choosing: it is not a new tuning, it is the bound the old code already ran.

    Three properties make this safe to certify:

    * **It cannot run away.** The seed is computed ONCE, from a mean that was
      measured under the old bound, and then it is an ordinary ring entry. It is
      never recomputed, so a rising mean cannot feed a widening fence back into
      itself. On the specimen: seed ``58,279 x 4 = 233,116``, fence
      ``233,116 x 1.5 - margin = 319,674`` — which admits the measured 300,000 ms
      unit and still refuses the 901,266 ms CAL-P081 runaway, exactly as the
      designed ring does.
    * **It extinguishes itself.** The next :func:`save_phase_ledger` writes a
      non-empty ring, so :data:`UNIT_WORST_HISTORY_KEY` exists from then on and
      this function never fires again for that ledger.
    * **It ages out.** The seed sits in a :data:`UNIT_WORST_WINDOW` ring like any
      other entry, so a day of real observations replaces it — in either
      direction. It is a floor for one day, not a permanent widening, which is
      what stops a run of cheap beats re-closing the ratchet before an expensive
      unit has had a chance to prove itself.

    A ledger with no measured mean seeds nothing. There is no measurement to
    scale, and the phase bound must stand (ruling 075).
    """
    seeded: dict[str, list[int]] = {}
    for name, cost in (unit_costs or {}).items():
        if not isinstance(cost, dict):
            continue
        mean_ms = cost.get("unit_ms")
        if isinstance(mean_ms, bool) or not isinstance(mean_ms, (int, float)):
            continue
        if mean_ms <= 0:
            continue
        seeded[name] = [int(mean_ms * STAGED_UNIT_OVERRUN_FACTOR)]
    return seeded


async def load_phase_carryover() -> tuple[
    dict[str, list[int]], dict[str, list[int]], dict[str, Any], dict[str, list[int]]
]:
    """Everything a prior beat banked, in ONE durable read.

    Durations, floors, unit costs, and (CAL-P163) the rolling ring of worst
    COMPLETED unit durations. One read because they live on one row and a plan
    built from a subset is a plan reasoning from partial evidence about whether
    it can reason at all.

    Four empty dicts is the honest answer to every read problem: with nothing
    read, nothing is measured, and :func:`derive_plan` renders ``no_data``
    rather than a reassuring empty finding.
    """
    from app.services.durable_snapshots import read_snapshot_standalone

    read = await read_snapshot_standalone(
        LEDGER_IDENTITY, expected_version=PHASE_LEDGER_SCHEMA, max_age_s=STATE_MAX_AGE_S
    )
    if not read.ok or read.envelope is None or not isinstance(read.envelope.payload, dict):
        return {}, {}, {}, {}
    payload = read.envelope.payload
    history = payload.get("history")
    floors = payload.get("floors")
    unit_costs = payload.get("unit_costs")
    worst = payload.get(UNIT_WORST_HISTORY_KEY)
    costs = unit_costs if isinstance(unit_costs, dict) else {}
    ring = (
        merge_history(worst, {}, window=UNIT_WORST_WINDOW) if isinstance(worst, dict) else {}
    )
    # CAL-P167: a ledger written before the ring existed has a mean and no ring,
    # and CAL-P163's fence is inert on exactly that state. Seed it once from the
    # bound the legacy code itself ran. See :func:`_bootstrap_worst_history` —
    # the seed cannot run away, extinguishes on the next save, and ages out.
    if not ring:
        ring = _bootstrap_worst_history(costs)
    return (
        merge_history(history, {}) if isinstance(history, dict) else {},
        merge_history(floors, {}) if isinstance(floors, dict) else {},
        costs,
        ring,
    )


async def load_phase_measurements() -> tuple[
    dict[str, list[int]], dict[str, list[int]], dict[str, Any]
]:
    """Durations, floors and unit costs as :func:`derive_plan` wants them.

    CAL-P163 folds the worst-unit ring INTO the unit costs here rather than
    handing ``derive_plan`` a fourth argument: ``unit_ms_worst`` is a fact
    about the same phase's units as ``unit_ms``, and the plan should receive
    one description of a unit, not two that a caller has to keep in step. The
    fold takes the ``max`` over the window — the ring exists so that one
    collapsed beat cannot pin the worst case low, and only the max reads it
    that way.
    """
    history, floors, unit_costs, worst_history = await load_phase_carryover()
    if not worst_history:
        return history, floors, unit_costs
    merged = {name: dict(cost) for name, cost in unit_costs.items() if isinstance(cost, dict)}
    for name, ring in worst_history.items():
        if not ring:
            continue
        merged.setdefault(name, {})["unit_ms_worst"] = max(ring)
    return history, floors, merged


async def load_phase_history() -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Prior runs' per-phase durations and floors, or ``({}, {})``.

    The two-value view, kept for callers that merge the rolling windows and
    have no use for the unit description.
    """
    history, floors, _, _ = await load_phase_carryover()
    return history, floors


async def load_main_checkpoint(
    *,
    population_version: str,
    fingerprint: str,
    owner: str,
    generation: int,
    max_age_s: float = STATE_MAX_AGE_S,
) -> tuple[MainBuildCheckpoint, str]:
    """Read + classify the durable checkpoint (fresh / resume / invalidate / refuse)."""
    from app.services.durable_snapshots import read_snapshot_standalone

    read = await read_snapshot_standalone(
        CHECKPOINT_IDENTITY,
        expected_version=MAIN_CHECKPOINT_SCHEMA,
        max_age_s=max_age_s,
    )
    if not read.ok or read.envelope is None:
        if read.status != "missing":
            logger.info(
                "calibration main checkpoint not resumable (%s) — starting fresh",
                read.status,
            )
        blank = new_main_checkpoint(
            version=population_version, fingerprint=fingerprint, owner=owner, generation=generation
        )
        return blank, (FRESH if read.status == "missing" else INVALIDATE)

    return decode_main_checkpoint(
        read.envelope.payload,
        expected_version=population_version,
        expected_fingerprint=fingerprint,
        owner=owner,
        generation=generation,
        now=time.time(),
    )


async def save_main_checkpoint(checkpoint: MainBuildCheckpoint, *, terminal: str) -> bool:
    """Persist the checkpoint. Returns whether the durable generation committed.

    The caller must treat a phase as durably recorded only when this returns
    ``True`` — that boolean is what feeds ``checkpoint_advanced`` in the
    contract row, and therefore what stops a resumed run skipping work it never
    actually banked.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    payload = checkpoint.as_payload()
    payload["terminal"] = terminal
    result = await publish_snapshot_standalone(
        DurableEnvelope.build(
            identity=CHECKPOINT_IDENTITY,
            schema_version=MAIN_CHECKPOINT_SCHEMA,
            payload=payload,
            # The RECORD is whole; the build's own state is `terminal` above.
            complete=True,
            source=MAIN_BUILD_TASK,
        )
    )
    ok = result.get("status") in ("ok", "superseded")
    if not ok:
        logger.warning("calibration main checkpoint persist failed: %s", result)
    return ok


async def clear_main_checkpoint(*, population_version: str, fingerprint: str, owner: str) -> bool:
    """Reset after a complete publish.

    A write of an emptied checkpoint rather than a DELETE: the durable store's
    atomicity story is a generation-guarded upsert with no delete path, so the
    next build reads an explicit "nothing carried" under the current version
    instead of an absence it would have to interpret.
    """
    from app.utils.durable_state import generation_for

    blank = new_main_checkpoint(
        version=population_version,
        fingerprint=fingerprint,
        owner=owner,
        generation=generation_for(datetime.now(timezone.utc)),
    )
    return await save_main_checkpoint(blank, terminal="complete")


# =============================================================================
# Staged futures cursor (Queue 300D Item 0)
# =============================================================================


def staged_lease() -> float:
    """When this run's claim on the staged cursor expires.

    Same geometry as :data:`LEASE_S` and for the same reason: comfortably past
    the Celery hard limit, so a SIGKILLed run still holds its claim until after
    it could possibly still be alive, and not one second longer.
    """
    return time.time() + LEASE_S


async def load_staged_cursor(
    *,
    population_version: str,
    input_fingerprint: str,
    generation_fingerprint: str,
    owner: str,
    generation: int,
    max_age_s: float = STATE_MAX_AGE_S,
    legacy_input_fingerprint: str | None = None,
):
    """Read + classify the staged futures cursor.

    Returns ``(cursor, action, reason)``. The third value is CAL-P024's: the
    caller records it beside the action, because five different causes all
    produce ``INVALIDATE`` and the stage name alone could not tell an operator
    which one had just cost the build every unit it had banked.
    """
    from app.services.durable_snapshots import read_snapshot_standalone
    from app.utils.calibration_staged_futures import (
        REASON_ABSENT,
        REASON_READ_FAILED,
        STAGED_FUTURES_SCHEMA,
        decode_staged_cursor_detailed,
        new_staged_cursor,
    )

    blank = new_staged_cursor(
        population_version=population_version,
        input_fingerprint=input_fingerprint,
        generation_fingerprint=generation_fingerprint,
        owner=owner,
        generation=generation,
    )
    try:
        read = await read_snapshot_standalone(
            STAGED_FUTURES_IDENTITY,
            expected_version=STAGED_FUTURES_SCHEMA,
            max_age_s=max_age_s,
        )
    except Exception as exc:  # noqa: BLE001 — an unreadable cursor is a fresh one
        logger.warning("calibration staged cursor read failed: %s", exc)
        return blank, INVALIDATE, REASON_READ_FAILED
    if not read.ok or read.envelope is None:
        if read.status == "missing":
            return blank, FRESH, REASON_ABSENT
        return blank, INVALIDATE, f"envelope_{read.status}"

    return decode_staged_cursor_detailed(
        read.envelope.payload,
        expected_population_version=population_version,
        expected_input_fingerprint=input_fingerprint,
        expected_generation_fingerprint=generation_fingerprint,
        owner=owner,
        generation=generation,
        now=time.time(),
        # CAL-P205 layer 1. ``input_fingerprint`` above is now the NARROW
        # ``staged_unit_fingerprint``; this is the wide digest the cursor on disk
        # was stamped with before layer 1 shipped. Accepted once, re-stamped on
        # the next save. ``None`` restores the pre-layer-1 behaviour exactly.
        legacy_input_fingerprint=legacy_input_fingerprint,
    )


async def save_staged_cursor(cursor, *, terminal: str) -> bool:
    """Persist the staged cursor. ``True`` only when the write is durable.

    The caller must treat a unit as banked ONLY on ``True``. Everything the
    resume story rests on — that a unit recorded as done really did commit — is
    this boolean being honest.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.calibration_staged_futures import (
        STAGED_FUTURES_SCHEMA,
        stamp_served_at,
    )
    from app.utils.durable_state import DurableEnvelope

    # CAL-P078. The pure module promotes a completed bank but owns no clock, so
    # it leaves ``served_at`` at 0.0 and this — the first impure hand the cursor
    # passes through, microseconds later in the same beat — dates it. Only ever
    # fills a 0.0: a bank that already carries a date keeps it, so re-persisting
    # cannot make an old census read as a new one, which is #2007's exact
    # failure mode and would be an embarrassing way to reintroduce it.
    cursor = stamp_served_at(cursor, now=time.time())
    payload = cursor.as_payload()
    payload["terminal"] = terminal
    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=STAGED_FUTURES_IDENTITY,
                schema_version=STAGED_FUTURES_SCHEMA,
                payload=payload,
                complete=True,
                source=MAIN_BUILD_TASK,
            )
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("calibration staged cursor persist failed: %s", exc)
        return False
    ok = result.get("status") in ("ok", "superseded")
    if not ok:
        logger.warning("calibration staged cursor persist rejected: %s", result)
    return ok


async def _record_staged_convergence(runner: PhaseRunner) -> None:
    """Record where the staged build actually IS, on EVERY terminal.

    CAL-P028. ``_run_staged_futures`` already records ``staged:units_done`` /
    ``staged:beats_to_publish``, and they are excellent — but they are recorded
    at the END of the unit loop, which is code a failing beat never reaches. The
    futures phase has been cancelled at its deadline on essentially every beat
    since 2026-08-02, so **the progress stages were absent from 181 consecutive
    ledgers**, and "how many units are banked" had to be reconstructed by hand
    out of a durable snapshot by someone who thought to look. Twice.

    An absent stage reads as "fine" (gotcha #53). A build that is 20 units into
    128 and going backwards should say so on the beat where it happens, in the
    ledger an operator already reads, whether that beat succeeded, timed out, or
    was cancelled.

    Read-only and best-effort by construction: this runs on the failure path, so
    it must never be the reason a ledger write is lost. A read that throws still
    persists the surrounding ledger.

    INT-034 repairs two defects in the paragraph above's first implementation,
    both of which reproduced the exact failure this function was written to end:

    1. :func:`read_snapshot_standalone` returns a frozen :class:`EnvelopeRead`
       dataclass, not a dict. ``(read or {}).get("payload")`` therefore raised
       ``AttributeError`` on EVERY beat, the best-effort ``except`` swallowed it,
       and the three stages below were never recorded once. The observable built
       to end an eight-day darkness was itself dark, in the same shape and for
       the same reason (gotcha #53: an absent stage reads as fine). Every sibling
       caller in this module already used ``read.ok`` / ``read.envelope.payload``.
    2. These are LEVELS, not amounts, so they are gauges. ``record_stage``
       accumulates repeats — CAL-P024c's named failure, where a 400 MB RSS
       reading published as 51,200 — and ``save_phase_ledger`` can run more than
       once in a build.

    And the failure path now SAYS SO. A cursor that cannot be read records a
    typed ``staged:convergence_reason:<status>`` marker, so a missing
    ``units_banked`` always distinguishes "nothing to report" from "the reader
    broke" — which is the whole distinction defect 1 collapsed.
    """
    from app.services.durable_snapshots import read_snapshot_standalone
    from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA

    try:
        read = await read_snapshot_standalone(
            STAGED_FUTURES_IDENTITY,
            expected_version=STAGED_FUTURES_SCHEMA,
            max_age_s=STATE_MAX_AGE_S,
        )
        if not read.ok or read.envelope is None:
            runner.ledger.record_gauge(f"staged:convergence_reason:{read.status}", 1)
            return
        payload = read.envelope.payload
        if not isinstance(payload, dict):
            runner.ledger.record_gauge("staged:convergence_reason:payload_shape", 1)
            return
        committed = payload.get("committed_units")
        if not isinstance(committed, list):
            runner.ledger.record_gauge("staged:convergence_reason:no_committed_units", 1)
            return
        runner.ledger.record_gauge("staged:units_banked", len(committed))
        runner.ledger.record_gauge("staged:units_partition", STAGED_FUTURES_BUCKETS)
        drift = payload.get("roster_drift_units")
        if isinstance(drift, int) and not isinstance(drift, bool) and drift >= 0:
            runner.ledger.record_gauge("staged:units_drifted", drift)
        _record_drift_coverage(runner, payload, committed)
        _record_served_bank(runner, payload)
        _record_staged_rate(runner, banked=len(committed))
    except Exception as exc:  # noqa: BLE001 — an unreadable cursor is not a lost ledger
        logger.warning("calibration staged convergence read failed: %s", exc)
        try:
            runner.ledger.record_gauge("staged:convergence_reason:read_raised", 1)
        except Exception:  # noqa: BLE001 — the ledger write is what matters
            pass


def _record_drift_coverage(
    runner: PhaseRunner, payload: dict[str, Any], committed: list[Any]
) -> None:
    """How many banked units ``staged:units_drifted`` was able to look at.

    CAL-P069. ``roster_drift`` counts a unit only when it is BOTH banked AND
    carries a stored digest, and its docstring states exactly why::

        A unit with no stored digest is not counted, because "we cannot tell"
        must not be published as "it did not drift" — that is the empty-200
        mistake of gotcha #53 one table over.

    The rule is right. The problem is that the counter obeying it emits a bare
    integer, so a reader cannot tell 0-because-nothing-drifted from
    0-because-nothing-was-checkable. Measured on production 2026-08-18 03:32Z:
    ``committed_units = 119``, ``unit_digests = 113``, so **6 banked units were
    outside the counter's reach** — and the ledger published
    ``staged:units_drifted: 0``. The docstring's own failure mode, at the site
    that documents it. Fourth instance of this class in four windows
    (CAL-P067's ``infeasible_phases: []``, CAL-P068's ``graded_share = 1.0``
    absent-denominator fallback, and the unit-cost mean before it).

    Deliberately mechanism-independent. The 6 uncovered units equalled that
    beat's ``units_this_beat`` exactly, which points at the digest for a unit
    landing one beat after the commit that banks it — but the counter is
    correct and needed whether that is a write-ordering lag, a prune, or a
    pre-CAL-P028 cursor tail. Diagnosing the cause is not a precondition for
    refusing to render an unmeasurable population as a measured zero.

    Emits a COVERAGE pair, never a corrected drift figure: this function has no
    digests to compare and must not invent a verdict for the units it is
    reporting as unverifiable.
    """
    digests = payload.get("unit_digests")
    if not isinstance(digests, dict):
        # The cursor carries no digest map at all, so drift is unmeasurable for
        # every banked unit — a much louder fact than a partial gap, and one
        # that must not fall through to a coverage number of zero-out-of-zero.
        runner.ledger.record_gauge("staged:drift_coverage_reason:no_digest_map", 1)
        return
    uncheckable = sum(1 for name in committed if name not in digests)
    runner.ledger.record_gauge("staged:units_drift_checkable", len(committed) - uncheckable)
    runner.ledger.record_gauge("staged:units_drift_uncheckable", uncheckable)


def _record_served_bank(runner: PhaseRunner, payload: dict[str, Any]) -> None:
    """What the reader is actually looking at — the SERVING bank, dated.

    CAL-P078, #2007. Every gauge above this one describes the bank being BUILT.
    After the rolling re-stage those are two different censuses, and the one a
    consumer of ``/api/calibration`` is reading is the served one. Publishing
    only the builder's numbers beside a served curve answers a question nobody
    asked with a figure that looks like the answer to the one they did — which
    is how ``availability: fresh`` came to sit on top of a six-hour-old census
    in the first place.

    Four gauges, and the fourth is the one #2007 asked for:

    * ``staged:served_units`` — how many units the published census covers.
    * ``staged:served_drifted`` — how many of them the roster has moved under.
      Counted only over units carrying a digest, so it is paired below.
    * ``staged:served_drift_uncheckable`` — units whose drift could NOT be
      determined. CAL-P069's find was six such units publishing as
      ``units_drifted: 0``; an unmeasurable remainder is named beside a real
      count, never folded into it.
    * ``staged:served_at`` — epoch seconds the census was taken. **Absent, not
      zero, when the bank is unstamped**: 0.0 means "promoted but not yet
      dated", and emitting it as a timestamp would date the census to 1970 and
      make every consumer's age arithmetic enormous-but-confident. A reader
      cannot recover a distinction the writer discarded (ruling 075 clause 2).

    Read-only, best-effort, and inside the caller's ``try`` for the same reason
    every gauge here is: this runs on the failure path and must never be why a
    ledger write is lost.
    """
    served = payload.get("served_units")
    if not isinstance(served, list):
        # No serving bank in the payload at all — a pre-CAL-P078 cursor, or one
        # whose bank was refused on read. Typed, because an absent gauge reads
        # as "fine" and this is the difference between "nothing is served" and
        # "we could not tell what is served".
        runner.ledger.record_gauge("staged:served_reason:no_served_units", 1)
        return
    runner.ledger.record_gauge("staged:served_units", len(served))
    moved = payload.get("served_drift_units")
    if isinstance(moved, int) and not isinstance(moved, bool) and moved >= 0:
        runner.ledger.record_gauge("staged:served_drifted", moved)
    digests = payload.get("served_digests")
    if not isinstance(digests, dict):
        runner.ledger.record_gauge("staged:served_reason:no_digest_map", 1)
    else:
        uncheckable = sum(1 for name in served if name not in digests)
        runner.ledger.record_gauge("staged:served_drift_uncheckable", uncheckable)
    served_at = payload.get("served_at")
    if isinstance(served_at, (int, float)) and not isinstance(served_at, bool) and served_at > 0:
        runner.ledger.record_gauge("staged:served_at", int(served_at))
    elif served:
        runner.ledger.record_gauge("staged:served_reason:unstamped", 1)


#: The stage ``_run_staged_futures`` times once per unit. Named here because
#: this module has to divide by its count and the frozen module owns the string.
STAGED_UNIT_STAGE = "read:futures_unit"


def _record_staged_rate(runner: PhaseRunner, *, banked: int) -> None:
    """How fast this beat went and how many beats are left, on EVERY terminal.

    CAL-P066 (#1680), and it is the same defect CAL-P028 fixed one level up.
    ``_record_convergence_projection`` in ``precompute_calibration`` records
    exactly these numbers — ``units_this_beat``, ``unit_ms_mean``,
    ``beats_to_publish`` — and records them WELL: they are the right numbers,
    with the right caveats. It is simply positioned after the unit loop, and the
    loop's normal exit for a build that has not finished is
    ``StagedFuturesIncomplete``. So the projection is skipped on every beat that
    does not publish, which since 2026-08-02 is every beat.

    The consequence, measured 2026-08-17: production ledgers carry
    ``read:futures_unit = 1,077,573`` with no divisor anywhere. That sum is one
    pathological unit or ten healthy ones, and the two readings say opposite
    things — "this phase cannot fit and never will" versus "this build is six
    beats from publishing". Establishing which required polling the durable
    cursor from OUTSIDE the application on a 60-second loop, because the
    application would not say.

    ``precompute_calibration`` is frozen (ruling 009), so this cannot be fixed
    where it was written. It does not need to be: the ledger now counts its own
    stage observations, so the divisor is already in hand here — on the path
    that always runs, whatever the terminal.

    Every branch below either records a number or records WHY it could not
    (ruling 075, second clause). None of them records nothing.
    """
    mean_ms = runner.ledger.stage_mean_ms(STAGED_UNIT_STAGE)
    ran = runner.ledger.stage_counts.get(STAGED_UNIT_STAGE, 0)
    runner.ledger.record_gauge("staged:units_this_beat", ran)

    # CAL-P067: the completed-only cost, recorded beside the mixed one rather
    # than replacing it. ``unit_ms_mean`` above averages over every unit the
    # beat TIMED, including the one cancelled at the deadline, so it is the
    # right number for attributing elapsed time and the wrong one for costing a
    # unit. Feasibility reads this pair; the operator-facing gauges above keep
    # the values CAL-P066 published, so nothing that reads them moves.
    completed_units = runner.ledger.stage_completed_count(STAGED_UNIT_STAGE)
    completed_mean = runner.ledger.stage_completed_mean_ms(STAGED_UNIT_STAGE)
    runner.ledger.record_gauge("staged:units_completed_this_beat", completed_units)
    if completed_mean is None:
        # Every unit this beat was cancelled. Distinct from "no unit ran", and
        # the state in which no unit cost may be quoted at all.
        runner.ledger.record_gauge("staged:unit_cost_reason:no_unit_completed", 1)
    else:
        runner.ledger.record_gauge("staged:unit_ms_mean_completed", int(completed_mean))

    if mean_ms is None:
        # A beat that ran no unit at all. The most important beat to be able to
        # see, and the one an absent stage would render as "fine" (gotcha #53).
        runner.ledger.record_gauge("staged:rate_reason:no_unit_ran", 1)
        return
    runner.ledger.record_gauge("staged:unit_ms_mean", int(mean_ms))

    remaining = max(0, STAGED_FUTURES_BUCKETS - banked)
    if remaining == 0:
        runner.ledger.record_gauge("staged:beats_to_publish", 0)
        return
    # The window a future beat gets for units, measured from THIS beat: the full
    # phase window less the fixed cost this beat paid before its first unit
    # (chiefly the ~21s generation freeze), which every beat pays again.
    window_ms = runner.ledger.remaining_ms(elapsed_ms=0)
    fixed_ms = max(0.0, runner.elapsed_ms() - runner.ledger.stages.get(STAGED_UNIT_STAGE, 0))
    usable_ms = max(0.0, window_ms - fixed_ms)

    # CAL-P068: the PROJECTION costs a unit, so it must use the COMPLETED-only
    # mean. CAL-P067 fixed the feasibility verdict and left this line reading the
    # mixed mean, which is the same defect surviving in the number an operator
    # actually looks at.
    #
    # The bias has a direction, and it is the bad one. A beat runs N units and
    # the last is cancelled at the deadline, so the truncated observation drags
    # the mean DOWN; a lower mean means more units appear to fit per beat, which
    # means FEWER beats appear to remain. The projection was optimistic by
    # construction, on every beat, and the more truncated the tail the more
    # optimistic it got.
    #
    # Falls back to the mixed mean rather than refusing — a projection is worth
    # having even when no unit completed — but says which one it used, because a
    # number derived from a lower bound and a number derived from a duration must
    # not render identically (ruling 075, second clause).
    projection_mean = completed_mean if completed_mean else mean_ms
    runner.ledger.record_gauge(
        "staged:beats_basis:completed" if completed_mean else "staged:beats_basis:mixed", 1
    )
    per_beat = usable_ms / projection_mean if projection_mean > 0 else 0.0
    # -1 is NOT "unknown" — it is "a whole beat cannot hold one unit", which is
    # a different and much worse fact than a large count. Same convention as
    # the frozen module's projection, deliberately, so the two agree.
    runner.ledger.record_gauge(
        "staged:beats_to_publish", math.ceil(remaining / per_beat) if per_beat >= 1 else -1
    )


def _unit_costs_from(runner: PhaseRunner) -> dict[str, dict[str, int]]:
    """This beat's MEASURED unit cost for the staged futures phase, if any.

    Emitted only when a unit actually COMPLETED — ``stage_completed_mean_ms``
    returns ``None`` otherwise and nothing is written, so a beat in which every
    unit was cancelled contributes no cost rather than a truncated one. The
    consumer (``derive_plan``) re-validates all three fields anyway; this side
    simply refuses to invent them.

    ``unit_ms_worst`` is folded in by :func:`save_phase_ledger` from the rolling
    ring, not from this beat alone — see :func:`_unit_worst_from`.
    """
    mean_ms = runner.ledger.stage_completed_mean_ms(STAGED_UNIT_STAGE)
    if mean_ms is None or mean_ms <= 0:
        return {}
    banked = int(runner.ledger.stages.get("staged:units_banked", 0) or 0)
    if banked <= 0:
        return {}
    return {
        PHASE_FUTURES: {
            "unit_ms": int(mean_ms),
            "units_total": STAGED_FUTURES_BUCKETS,
            "units_done": banked,
        }
    }


def _level_self_blocked(runner: PhaseRunner) -> bool:
    """Did the carried level refuse EVERY unit of this beat, all by itself?

    The two stages are read together because either alone means something else.
    ``window_stop:unit_too_large`` on its own is the ordinary end of a productive
    beat — units ran, the window filled, the next one would not fit. Zero units
    on its own is a deferred rebuild (D45(A) hands the loop an empty iterable, so
    the fence is never consulted) or a beat that died before Stage 2. Together
    they are the one state that matters here: the loop reached the fence, the
    fence refused, and it refused on the only evidence it had — a level this beat
    did not measure, because this beat measured nothing.
    """
    if runner.ledger.stage_counts.get(STAGED_UNIT_STAGE, 0):
        return False
    return "staged:window_stop:unit_too_large" in runner.ledger.stages


def _carry_unit_costs(runner: PhaseRunner, prior: dict[str, Any]) -> dict[str, Any]:
    """The prior beat's unit-cost level, still describing something true.

    CAL-P1027 (#1597). CAL-P163 established that this level has to be CARRIED —
    a beat that completed no unit must not erase what earlier beats measured.
    What it did not establish is when a carried level stops being evidence, and
    the answer is not "never": production carried
    ``{'unit_ms': 928347, 'units_done': 6}`` for a day against a cursor holding
    **zero** committed units, and the beat at 05:19:04Z ran no unit at all.

    Both halves of that level had gone false, in different ways, and each is
    fixed here by making the field mean what it says:

    * ``units_done`` is written by :func:`_unit_costs_from` from
      ``staged:units_banked`` — the DURABLE cursor's position at the moment the
      cost was measured. Carrying it verbatim carries a cursor position from
      another beat. It is **re-stamped** from this beat's own reading, which
      :func:`_record_staged_convergence` has already taken, so the pair always
      describes one instant.

      This is not a fence workaround dressed as bookkeeping. ``units_done`` is
      the denominator :meth:`~app.utils.calibration_phase_ledger.PhaseLedger.measured_unit_ms`
      requires — "a mean over zero completed units is not a measurement" — so an
      honest zero withdraws the quote automatically, through a guard that was
      already written, and the loop lands on the fence's own documented path for
      having no measurement: *attempt one unit*.

    * ``unit_ms`` is **withdrawn** when :func:`_level_self_blocked` says the
      level refused every unit of the beat. A measurement that blocks the only
      observation which could revise it has stopped being a measurement and
      become a self-sustaining assertion: ``prior_unit_ms * 1.25`` exceeded the
      usable window by 2.1%, so no unit started, so no unit completed, so the
      level was carried unchanged into a beat that reproduced the arithmetic
      exactly — for as many beats as the build has left, which is all of them.

      Withdrawing costs nothing that was not already lost. The unit that then
      runs is still bounded: ``statement_timeout_for_unit`` keeps the worst-unit
      ring (CAL-P163), which this function never touches, so it cannot outlive
      the beat — and a unit cancelled at its own bound is a known outcome the
      loop already classifies as ``cancelled``, not ``failed``. The floor is one
      honest attempt per beat where the floor was zero forever.

    Every branch records why (ruling 075): a withdrawal, a re-stamp, and an
    unreadable cursor are three different states and none of them is silence.
    """
    carried = {name: dict(cost) for name, cost in (prior or {}).items() if isinstance(cost, dict)}
    futures = carried.get(PHASE_FUTURES)
    if not futures:
        return carried
    if _level_self_blocked(runner):
        carried.pop(PHASE_FUTURES)
        runner.ledger.record_gauge("staged:unit_cost_reason:withdrawn_self_blocked", 1)
        return carried
    banked = runner.ledger.stages.get("staged:units_banked")
    if banked is None:
        # The cursor read failed or was refused; ``_record_staged_convergence``
        # has already recorded which. Re-stamping from a number we do not have
        # would be inventing one, so the level is carried as-is and SAYS it is
        # unverified rather than reading as freshly confirmed (gotcha #53).
        runner.ledger.record_gauge("staged:unit_cost_reason:units_done_unverified", 1)
        return carried
    banked = int(banked)
    if int(futures.get("units_done") or 0) != banked:
        runner.ledger.record_gauge("staged:unit_cost_units_done_restamped", banked)
        futures["units_done"] = banked
    return carried


def _unit_worst_from(runner: PhaseRunner) -> dict[str, int]:
    """This beat's worst COMPLETED unit duration — CAL-P163 (#1978).

    Shaped as ``{phase: duration_ms}`` so it can go straight through
    :func:`merge_history`, which already owns the rolling-window semantics this
    needs and validates every value on the way in and out.

    A ring rather than a level, unlike ``unit_costs``. The level is right for
    the mean, which describes where the build currently stands; it is wrong for
    the max, because a single collapsed beat — every expensive unit cancelled,
    only the cheap ones averaged — would overwrite the worst case with a small
    number and hold the admission bound shut on exactly the beats that need it
    open. The window is :data:`HISTORY_WINDOW`, the same ten beats every phase
    budget is measured over, so one anomalous beat still ages out.
    """
    worst = runner.ledger.stage_completed_max_ms(STAGED_UNIT_STAGE)
    if not worst or worst <= 0:
        # Every unit cancelled, or none ran. Contributes NOTHING to the ring —
        # never a zero, which would be read as a measured worst case of zero and
        # is the one value that makes the fence maximally tight.
        return {}
    return {PHASE_FUTURES: int(worst)}


async def save_phase_ledger(runner: PhaseRunner, extra: Optional[dict[str, Any]] = None) -> str:
    """Persist the phase ledger + rolling history. Returns ``ok`` or ``error``.

    This is the measurement rail Item 0 exists to build, so it is written on
    EVERY terminal — a run that timed out at phase 2 is exactly the run whose
    timings the next plan most needs. A failure here is reported, never
    swallowed: :func:`health_for` turns it into UNKNOWN, never GREEN.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    await _record_staged_convergence(runner)

    try:
        prior_history, prior_floors, prior_unit_costs, prior_worst = await load_phase_carryover()
    except Exception as exc:  # noqa: BLE001 — a lost history is not a lost ledger
        logger.warning("calibration phase ledger: history read failed: %s", exc)
        prior_history, prior_floors, prior_unit_costs, prior_worst = {}, {}, {}, {}
    # CAL-P1027: the carry decision is taken BEFORE ``as_payload``, because the
    # reasons it records (ruling 075) are ledger gauges and the payload is a
    # snapshot of the ledger. Taken after, every one of them would be written to
    # a dict nobody reads and the beat would go out silent about why its level
    # changed. The read above moved up with it; nothing between the two depends
    # on the order.
    unit_costs = _unit_costs_from(runner) or _carry_unit_costs(runner, prior_unit_costs)

    payload = runner.ledger.as_payload()
    if extra:
        payload.update(extra)
    payload["history"] = merge_history(prior_history, runner.ledger.observations())
    payload["floors"] = merge_history(prior_floors, runner.ledger.floors())
    # CAL-P067: the measured per-unit cost has to survive the beat that measured
    # it, or the next plan is back to having only a floor to reason from — which
    # is the state this whole fix exists to stop rendering as an all-clear.
    # Unlike history/floors this is a LEVEL, not a rolling window: it describes
    # where the staged build currently stands, so the newest reading replaces
    # the previous one rather than accumulating beside it.
    #
    # CAL-P163: a level still has to be CARRIED. ``payload`` is built fresh from
    # this run, so a beat that completed no unit used to write the row back
    # without ``unit_costs`` at all — silently erasing what earlier beats
    # measured and sending the next plan back to no-data. Refusing to invent a
    # cost (above) and refusing to keep one that was measured are different
    # things, and only the first was intended.
    #
    # CAL-P1027: and a carried level has to still DESCRIBE something. Computed
    # above so its reasons reach the payload; see :func:`_carry_unit_costs`.
    if unit_costs:
        payload["unit_costs"] = unit_costs
    # CAL-P163: the worst COMPLETED unit, as a rolling window. Appended to
    # rather than overwritten, so a collapsed beat contributes its (small) worst
    # completion without discarding the larger ones that admission decisions
    # depend on — and still ages out after HISTORY_WINDOW beats.
    worst_history = merge_history(
        prior_worst, _unit_worst_from(runner), window=UNIT_WORST_WINDOW
    )
    if worst_history:
        payload[UNIT_WORST_HISTORY_KEY] = worst_history

    result = await publish_snapshot_standalone(
        DurableEnvelope.build(
            identity=LEDGER_IDENTITY,
            schema_version=PHASE_LEDGER_SCHEMA,
            payload=payload,
            complete=True,
            source=MAIN_BUILD_TASK,
        )
    )
    status = "ok" if result.get("status") in ("ok", "superseded") else "error"
    if status != "ok":
        logger.error(
            "calibration phase ledger: durable write FAILED (%s) — this run's "
            "progress is UNKNOWN, not green", result.get("error") or result.get("status"),
        )
    runner.ledger.ledger_write = status
    return status


async def build_runner(
    *, population_version: str, fingerprint: str, carry_max_age_s: float = STATE_MAX_AGE_S
) -> tuple[PhaseRunner, str]:
    """Assemble the runner for one build: history -> plan -> checkpoint -> runner."""
    from app.utils.durable_state import generation_for

    owner = run_owner()
    generation = generation_for(datetime.now(timezone.utc))
    try:
        history, floors, unit_costs = await load_phase_measurements()
    except Exception as exc:  # noqa: BLE001 — no history just means provisional
        logger.warning("calibration phase ledger: history read failed: %s", exc)
        history, floors, unit_costs = {}, {}, {}
    plan = derive_plan(history, floors=floors, unit_costs=unit_costs)
    if plan.infeasible_phases:
        # Loud, because no amount of checkpointing or resuming fixes it: the
        # phase as cut is bigger than the whole beat.
        logger.error(
            "calibration phase plan is INFEASIBLE — required phase(s) %s are "
            "MEASURED not to fit the %dms window; the build cannot complete as "
            "currently cut",
            ", ".join(plan.infeasible_phases),
            plan.available_ms,
        )
    elif plan.feasibility in (FEASIBILITY_INDETERMINATE, FEASIBILITY_NO_DATA):
        # CAL-P067. This branch is the fix's whole point: it did not exist, so
        # the sixteenth unmeasurable beat logged nothing at all and the payload
        # said ``infeasible_phases: []``. "I could not check" now has a voice.
        logger.warning(
            "calibration phase plan feasibility is %s — indeterminate=%s "
            "unchecked=%s (checked against %dms). This is NOT an all-clear: no "
            "completed duration exists for those phases, so whether the build "
            "fits its window is unknown, not fine.",
            plan.feasibility,
            ", ".join(plan.indeterminate_phases) or "none",
            ", ".join(plan.unchecked_phases) or "none",
            plan.max_phase_ms,
        )

    try:
        checkpoint, action = await load_main_checkpoint(
            population_version=population_version,
            fingerprint=fingerprint,
            owner=owner,
            generation=generation,
            max_age_s=carry_max_age_s,
        )
    except Exception as exc:  # noqa: BLE001 — an unreadable checkpoint is a fresh one
        logger.warning("calibration main checkpoint read failed: %s", exc)
        checkpoint, action = (
            new_main_checkpoint(
                version=population_version,
                fingerprint=fingerprint,
                owner=owner,
                generation=generation,
            ),
            INVALIDATE,
        )

    runner = PhaseRunner(
        plan=plan,
        checkpoint=checkpoint,
        checkpoint_action=action,
        population_version=population_version,
        owner=owner,
        generation=generation,
        fingerprint=fingerprint,
    )
    for phase in checkpoint.completed_phases:
        runner.carry(phase)
    return runner, action


def checkpoint_terminal(runner: PhaseRunner) -> str:
    return TERMINAL_COMPLETE if runner.ledger.all_required_done else TERMINAL_PARTIAL
