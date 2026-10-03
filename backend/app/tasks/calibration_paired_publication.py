"""#6176 (October 1 scope) — the paired early/final accuracy block on the main payload.

PILLAR TRUTH. SHIP: a reader can see whether the SAME forecasts were more
accurate at the final supported pre-event observation than one day before the
event, with an honest statement when the evidence is unavailable. It is not a
claim that trading improves accuracy, and nothing here reads ``price_moved``.

WHAT THIS IS
------------
A producer of ONE optional key, ``paired_accuracy``, stamped onto the main
``/api/calibration`` payload by ``_run_calibration_main_build`` before it is
judged, serialised and published — so the block travels in the same bytes and
the same durable generation as the curve, and the route serves it without a
single GET-time query.

The pairing rule is not restated here. Every decision about what counts as a
pair — the 24h lead, the 12h/6h confirmation bounds, the strictly pre-start
boundary, the reported-start provenance, one book for both legs, independent
results, the event cluster and the model/market split — is
:mod:`app.utils.calibration_paired_prestart`'s, read through
:func:`paired_legs_sql` and scored by :func:`paired_improvement` /
:func:`leg_calibration`.

THE FROZEN INITIAL POLICY (issue body, "October 1")
---------------------------------------------------
* **A bounded RECENT-EVENT SAMPLE, not whole-history coverage.** The newest
  :data:`EVENT_LIMIT` completed events with a reported start and at least one
  graded, truth-eligible outcome, ordered ``commence_time DESC, id DESC`` — a
  total order, so two builds over the same rows pick the same events.
* **At most :data:`CANDIDATE_CAP` outcome candidates.** Events are admitted
  WHOLE, newest first; an event that would carry the total over the cap is
  skipped and listed by id with its candidate count, and the block then says
  ``incomplete``. Truncating by outcome id instead would score half of a game,
  which is a selection rule nobody chose.
* **Its own session**, every statement bounded at
  :data:`STATEMENT_TIMEOUT_MS` and the WHOLE call — collection AND teardown —
  at :data:`WALL_BUDGET_S` (:func:`_within_wall`), shrunk further to fit the
  build's remaining publish deadline. A teardown that overruns is not left for
  ``asyncio.run`` to wait out when the task exits: its connection is cut and the
  task reaped (:func:`_reap`). Everything runs inside ONE
  ``REPEATABLE READ READ ONLY`` transaction.
  That one snapshot is what makes the block coherent: the event pick, the
  per-event candidate counts (the denominator), the refusal tally, the pair
  set and both legs' scores are all read from the same rows, and the collector
  refuses to publish if the ids or the legs disagree with the count it
  admitted. The <=2000 candidate OUTCOME ids are materialised by their own
  statement before the legs statement runs, and bound into it as a primary-key
  restriction, so no outcome outside the sample ever reaches a lateral seek.
* **Its own clock.** ``collected_at`` is when THIS sample was read. It is not
  the main curve's ``generated_at`` (recorded beside it as
  ``published_with_generated_at``, the artifact that carries the block) and it
  shares nothing with the staged futures bank's older ``staged_at``.
* **No pairs, a timeout, or any failure is a typed ``unavailable``** — never a
  zero score and never a fabricated pair. The main payload publishes either way:
  this block can only ever describe its own absence, never block the curve.

WHAT IT DOES NOT TOUCH
----------------------
``compute_calibration_payload``, the population version, the main futures SQL,
the staged-futures bank, grading and production data. The caller sits outside
every function ``_main_input_fingerprint`` hashes, and
``tests/test_calibration_paired_publication_6176.py`` proves the digest does not
move.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import bindparam, text

from app.utils.calibration_paired_prestart import (
    _POPULATION_PREDICATE,
    DEFAULT_EARLY_MAX_STALE_SECONDS,
    DEFAULT_FINAL_MAX_STALE_SECONDS,
    DEFAULT_LEAD_SECONDS,
    MIN_CLUSTERS_FOR_MARGIN,
    PAIR_PAIRED_UNCHANGED,
    PAIRED_CLASSES,
    leg_calibration,
    paired_improvement,
    paired_legs_sql,
    start_is_reported_sql,
)

logger = logging.getLogger(__name__)

#: The payload key and its contract version. A consumer reads ``schema`` first.
PAYLOAD_KEY = "paired_accuracy"
SCHEMA = "paired-accuracy/v1"

#: The frozen initial sample bounds (issue body, "October 1").
EVENT_LIMIT = 100
CANDIDATE_CAP = 2000
STATEMENT_TIMEOUT_MS = 5000
#: Server-side backstop for a client that goes quiet INSIDE a healthy
#: transaction: Postgres aborts the transaction itself. Applied with
#: ``SET LOCAL``, so it dies with the transaction — including when a statement
#: error aborts it, which leaves the session ``idle in transaction (aborted)``
#: with no timeout at all (measured on local Postgres). It is therefore not what
#: ends a session whose teardown overran; cutting the socket is (:func:`_cut`).
IDLE_IN_TRANSACTION_TIMEOUT_MS = 5000

#: The WHOLE call, teardown included: :data:`COLLECT_BUDGET_S` for the reads,
#: then at most :data:`CLEANUP_BUDGET_S` for a cancelled session to close and
#: dispose. ``asyncio.wait_for`` cannot give this guarantee — it waits for the
#: cancelled coroutine's ``finally`` however long that takes — so the
#: collection runs as its own task, and a teardown that outlives its share is
#: cut and reaped (see :func:`_within_wall` and :func:`_reap`).
COLLECT_BUDGET_S = 12.0
CLEANUP_BUDGET_S = 3.0
WALL_BUDGET_S = COLLECT_BUDGET_S + CLEANUP_BUDGET_S

#: How often a reaped teardown is cancelled again (after the first round,
#: which only cuts its connection), and for how many rounds.
#: ``get_task_session`` ends in two ``finally`` awaits (``session.close`` then
#: ``engine.dispose``) and each cancellation interrupts only the await it lands
#: on, so one cancel is never enough. Once the connection is cut, both of
#: those awaits fail fast anyway, so in practice the rounds go unused.
REAP_TICK_S = 0.01
REAP_ROUNDS = 50

#: Kept free for the gate, serialisation and the durable + Redis publish when
#: the build tells us how long it has left. Below the minimum, the block is not
#: attempted at all — the curve matters more than this optional analysis.
PUBLISH_RESERVE_S = 120.0
MIN_COLLECT_S = 2.0

#: How the collection's reads were made consistent, stated in the artifact.
CONSISTENCY = "one_repeatable_read_read_only_transaction"

#: The event terminal set every other completed-event reader uses.
_TERMINAL_STATUSES = ("completed", "closed")

STATUS_AVAILABLE = "available"
STATUS_INCOMPLETE = "incomplete"
STATUS_UNAVAILABLE = "unavailable"

REASON_NO_ELIGIBLE_EVENTS = "no_eligible_events"
REASON_NO_PAIRS = "no_pairs"
REASON_INSUFFICIENT_PAIRS = "insufficient_pairs"
REASON_CANDIDATE_CAP = "candidate_cap_reached"
REASON_TIMEOUT = "timeout"
REASON_FAILED = "failed"
REASON_PUBLISH_DEADLINE = "publish_deadline"

FORECAST_KINDS = ("market", "model")

#: Rounded for a stable artifact; far finer than any score a reader is shown.
_DIGITS = 6


def _policy() -> dict[str, Any]:
    """What "earlier", "final" and "the sample" meant for this block, stated once."""
    return {
        "lead_seconds": DEFAULT_LEAD_SECONDS,
        "early_max_stale_seconds": DEFAULT_EARLY_MAX_STALE_SECONDS,
        "final_max_stale_seconds": DEFAULT_FINAL_MAX_STALE_SECONDS,
        "min_events_for_margin": MIN_CLUSTERS_FOR_MARGIN,
        "event_limit": EVENT_LIMIT,
        "candidate_cap": CANDIDATE_CAP,
        "event_order": "commence_time_desc_event_id_desc",
        "scope": "recent_events_sample",
        "early_observation": (
            "the standing eligible price 24 hours before the reported start, "
            "last confirmed no more than 12 hours before that instant"
        ),
        "final_observation": (
            "the last eligible price before the reported start, last confirmed "
            "no more than 6 hours before it — not an exact closing quote"
        ),
        "score": "brier",
        "sign_convention": "positive mean_delta means the final observation scored better",
        "margin": "event-clustered standard error; withheld below min_events_for_margin events",
    }


def _collector(
    collected_at: Any, collection_ms: Optional[int], wall_budget_s: Optional[float] = None
) -> dict[str, Any]:
    """When and how THIS sample was read — its own clock, not the curve's."""
    return {
        "collected_at": _iso(collected_at),
        "collection_ms": collection_ms,
        "consistency": CONSISTENCY,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "wall_budget_s": WALL_BUDGET_S if wall_budget_s is None else round(wall_budget_s, 3),
    }


def unavailable(
    reason: str,
    *,
    generated_at: Any = None,
    collected_at: Any = None,
    collection_ms: Optional[int] = None,
    wall_budget_s: Optional[float] = None,
    detail: Optional[str] = None,
) -> dict:
    """The typed absence. Carries no score at all — never a zero standing in."""
    block = {
        "schema": SCHEMA,
        "status": STATUS_UNAVAILABLE,
        "reason": reason,
        "published_with_generated_at": generated_at,
        "collector": _collector(collected_at, collection_ms, wall_budget_s),
        "policy": _policy(),
        "sample": None,
        "exclusions": [],
        "market": None,
        "model": None,
    }
    if detail:
        block["detail"] = detail[:300]
    return block


def event_selection_sql() -> str:
    """The newest eligible events, each with its candidate count.

    "Eligible" is the frozen scope: a terminal event, a start that is a REPORTED
    start (the kernel's own :func:`start_is_reported_sql`, so a ticker-midnight
    or poll-clock stamp never enters), and at least one outcome the kernel's
    population predicate admits. Contradicted starts and settlement-before-start
    are left IN — they are pair classes, and the kernel counts them as named
    exclusions rather than this query hiding them.

    ``LIMIT :event_limit`` is passed one higher than :data:`EVENT_LIMIT` so the
    block can say whether older eligible events exist outside the sample.
    """
    statuses = ", ".join(f"'{s}'" for s in _TERMINAL_STATUSES)
    return f"""
WITH ev AS (
    SELECT e.id, e.commence_time
    FROM events e
    WHERE e.status IN ({statuses})
      AND e.commence_time IS NOT NULL
      AND e.commence_time < :as_of
      AND e.commence_time_source IS NOT NULL
      AND {start_is_reported_sql()}
      AND EXISTS (
          SELECT 1
          FROM futures_markets fm
          JOIN futures_outcomes fo ON fo.market_id = fm.id
          WHERE fm.event_id = e.id
            AND {_POPULATION_PREDICATE}
      )
    ORDER BY e.commence_time DESC, e.id DESC
    LIMIT :event_limit
)
SELECT ev.id AS event_id,
       ev.commence_time AS commence_time,
       (
           SELECT COUNT(*)
           FROM futures_markets fm
           JOIN futures_outcomes fo ON fo.market_id = fm.id
           WHERE fm.event_id = ev.id
             AND {_POPULATION_PREDICATE}
       ) AS n_candidates
FROM ev
ORDER BY ev.commence_time DESC, ev.id DESC
"""


def candidate_ids_sql() -> str:
    """The admitted events' candidate OUTCOME ids — materialised before any seek.

    The same population predicate as the per-event counts, so the id list IS
    the admitted denominator. ``LIMIT :limit`` is passed one above
    :data:`CANDIDATE_CAP`: the admitted counts already sum to at most the cap,
    so reaching the extra row means the snapshot disagreed with itself.
    """
    return f"""
SELECT fo.id AS outcome_id
FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
WHERE {_POPULATION_PREDICATE}
  AND fm.event_id IN :event_ids
ORDER BY fo.id ASC
LIMIT :limit
"""


def remaining_publish_s(runner: Any) -> Optional[float]:
    """Seconds left before the build's deadline, or ``None`` if it cannot say.

    Read off the runner's own ledger, the same clock its phases budget against.
    The null runner (no deadline) and any runner without that surface answer
    ``None``, which leaves the fixed :data:`WALL_BUDGET_S` as the bound.
    """
    ledger = getattr(runner, "ledger", None)
    remaining = getattr(ledger, "remaining_ms", None)
    elapsed = getattr(runner, "elapsed_ms", None)
    if not callable(remaining) or not callable(elapsed):
        return None
    try:
        return float(remaining(elapsed_ms=elapsed())) / 1000.0
    except Exception:  # noqa: BLE001 — an unreadable clock means "no extra bound"
        logger.warning("calibration paired_accuracy: runner deadline unreadable", exc_info=True)
        return None


def admit_events(
    events: Sequence[Mapping[str, Any]],
    *,
    event_limit: int = EVENT_LIMIT,
    candidate_cap: int = CANDIDATE_CAP,
) -> dict[str, Any]:
    """Admit whole events, newest first, until the candidate cap; list the rest.

    ``events`` must already be in the selection order. An event whose count
    would carry the total over the cap is SKIPPED (and recorded) rather than
    ending the walk, so one oversized tournament does not empty the sample —
    and is never truncated, so no event is scored on part of its outcomes.
    """
    considered = list(events)[:event_limit]
    admitted: list[Mapping[str, Any]] = []
    skipped: list[dict[str, int]] = []
    total = 0
    for ev in considered:
        n = int(ev["n_candidates"] or 0)
        if total + n > candidate_cap:
            skipped.append({"event_id": int(ev["event_id"]), "candidates": n})
            continue
        admitted.append(ev)
        total += n
    return {
        "admitted": admitted,
        "skipped": skipped,
        "candidates": total,
        "older_events_not_sampled": len(events) > event_limit,
        "events_considered": len(considered),
    }


def _r(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), _DIGITS)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _kind_block(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One forecast kind's coverage and, when it exists, its paired result.

    Scored ONLY on rows the kernel classed as paired. A cohort of fewer than two
    pairs has no standard error and no honest mean comparison, so it is
    ``unavailable`` with the reason — ``paired_improvement`` returns ``None``
    for it and that ``None`` is carried, never coerced to 0.
    """
    paired = [r for r in rows if r["pair_class"] in PAIRED_CLASSES]
    pairs = [
        (float(r["early_probability"]), float(r["final_probability"]), bool(r["is_winner"]))
        for r in paired
    ]
    clusters = [r["cluster_id"] for r in paired]
    kinds = [r["forecast_kind"] for r in paired]
    books: dict[str, int] = {}
    for r in paired:
        key = str(r["bookmaker"])
        books[key] = books.get(key, 0) + 1

    block: dict[str, Any] = {
        "status": STATUS_UNAVAILABLE,
        "reason": None,
        "candidates": len(rows),
        "candidate_events": len({r["cluster_id"] for r in rows}),
        "paired": len(paired),
        "paired_unchanged": sum(1 for r in paired if r["pair_class"] == PAIR_PAIRED_UNCHANGED),
        "paired_events": len(set(clusters)),
        "books": dict(sorted(books.items())),
        "result": None,
        "calibration": None,
    }

    brier = paired_improvement(pairs, score="brier", cluster_ids=clusters, forecast_kinds=kinds)
    if brier is None:
        block["reason"] = REASON_NO_PAIRS if not pairs else REASON_INSUFFICIENT_PAIRS
        return block
    log = paired_improvement(pairs, score="log_loss", cluster_ids=clusters, forecast_kinds=kinds)
    cal = leg_calibration(pairs)

    block["status"] = STATUS_AVAILABLE
    block["result"] = {
        "n": brier["n"],
        "n_events": brier["n_events"],
        "early_brier": _r(brier["early_mean"]),
        "final_brier": _r(brier["final_mean"]),
        "mean_delta": _r(brier["mean_delta"]),
        # Withheld below MIN_CLUSTERS_FOR_MARGIN events by the kernel itself;
        # the raw cluster SE is deliberately NOT published beside it, so no
        # consumer can print the margin the rule refused.
        "margin": _r(brier["displayable_margin"]),
        "margin_withheld": brier["displayable_margin"] is None,
        "events_improved": brier["events_improved"],
        "events_worse": brier["events_worse"],
        "events_unchanged": brier["events_unchanged"],
        "log_loss": {
            "early": _r(log["early_mean"]),
            "final": _r(log["final_mean"]),
            "mean_delta": _r(log["mean_delta"]),
            "margin": _r(log["displayable_margin"]),
        },
    }
    block["calibration"] = {
        "early_ece_pp": _r(cal["early_ece_pp"]),
        "final_ece_pp": _r(cal["late_ece_pp"]),
    }
    return block


def assemble(
    events: Sequence[Mapping[str, Any]],
    admission: Mapping[str, Any],
    rows: Iterable[Mapping[str, Any]],
    *,
    generated_at: Any = None,
    collected_at: Any = None,
    collection_ms: Optional[int] = None,
    wall_budget_s: Optional[float] = None,
) -> dict[str, Any]:
    """Fold the selection and the kernel's per-outcome rows into the block."""
    rows = list(rows)
    if not admission["admitted"]:
        reason = REASON_CANDIDATE_CAP if admission["skipped"] else REASON_NO_ELIGIBLE_EVENTS
        block = unavailable(
            reason,
            generated_at=generated_at,
            collected_at=collected_at,
            collection_ms=collection_ms,
            wall_budget_s=wall_budget_s,
        )
        block["sample"] = _sample(admission, rows)
        return block

    exclusions: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        if r["pair_class"] in PAIRED_CLASSES:
            continue
        key = (str(r["forecast_kind"]), str(r["source"]), str(r["pair_class"]))
        slot = exclusions.setdefault(key, {"n": 0, "events": set()})
        slot["n"] += 1
        slot["events"].add(r["cluster_id"])

    kinds = {
        kind: _kind_block([r for r in rows if r["forecast_kind"] == kind])
        for kind in FORECAST_KINDS
    }

    any_result = any(k["status"] == STATUS_AVAILABLE for k in kinds.values())
    if not any_result:
        status, reason = STATUS_UNAVAILABLE, REASON_NO_PAIRS
    elif admission["skipped"]:
        status, reason = STATUS_INCOMPLETE, REASON_CANDIDATE_CAP
    else:
        status, reason = STATUS_AVAILABLE, None

    return {
        "schema": SCHEMA,
        "status": status,
        "reason": reason,
        "published_with_generated_at": generated_at,
        "collector": _collector(collected_at, collection_ms, wall_budget_s),
        "policy": _policy(),
        "sample": _sample(admission, rows),
        "exclusions": [
            {
                "forecast_kind": kind,
                "source": source,
                "pair_class": klass,
                "n": slot["n"],
                "n_events": len(slot["events"]),
            }
            for (kind, source, klass), slot in sorted(exclusions.items())
        ],
        "market": kinds["market"],
        "model": kinds["model"],
    }


def _sample(admission: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    admitted = admission["admitted"]
    return {
        "events_considered": admission["events_considered"],
        "events_admitted": len(admitted),
        "events_skipped_for_cap": list(admission["skipped"]),
        "older_events_not_sampled": admission["older_events_not_sampled"],
        "candidates": len(rows),
        "newest_start": _iso(admitted[0]["commence_time"]) if admitted else None,
        "oldest_start": _iso(admitted[-1]["commence_time"]) if admitted else None,
    }


def _is_timeout(exc: BaseException) -> bool:
    from app.tasks.calibration_main_build import is_statement_timeout

    return is_statement_timeout(exc)


class _Incoherent(RuntimeError):
    """The ids or the legs disagree with the denominator admitted from the same snapshot."""


class _WallBudgetExceeded(RuntimeError):
    """The collection did not finish inside its share of the wall budget."""


#: Collections being reaped: cancelled, connection cut, not yet finished. Held
#: so they are not garbage-collected mid-flight; each removes itself and has
#: its outcome retrieved when it ends.
_ABANDONED: set = set()


def _retire(task: "asyncio.Task") -> None:
    _ABANDONED.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.warning(
            "calibration paired_accuracy: reaped teardown ended with %r", task.exception()
        )


async def _driver_of(db: Any) -> Any:
    """The driver connection under ``db``'s transaction, or ``None``.

    Read once, right after the transaction opens, so a teardown that overruns
    can be cut without awaiting anything. A session that cannot say (a test
    double, a connection already gone) gives ``None``: the reap's repeated
    cancellation still bounds the wait, it just cannot close the socket first.
    """
    try:
        connection = await db.connection()
        raw = await connection.get_raw_connection()
        return raw.driver_connection
    except Exception:  # noqa: BLE001 — no driver means no cut, never a failed block
        return None


def _cut(driver: Any) -> None:
    """Close the connection's socket NOW. Synchronous, so nothing can postpone it.

    asyncpg's ``terminate()`` drops the socket without waiting for pending data,
    and the server ends the session — and the transaction with it — when it
    next writes to that socket (at the latest when :data:`STATEMENT_TIMEOUT_MS`
    stops the running statement).

    ``terminate()`` alone is not enough. Once the teardown has started
    asyncpg's graceful ``close()``, ``Protocol.abort()`` returns without
    touching the transport, and a ``close()`` cancelled while it waits to send
    its cancel request never reaches its own ``transport.abort()``. Measured
    on real asyncpg 0.31 (local Postgres): the socket stayed ESTABLISHED after
    the task returned and the backend sat ``idle in transaction (aborted)``
    indefinitely. So a transport still open after ``terminate()`` is aborted
    here directly.
    """
    if driver is None:
        return
    try:
        driver.terminate()
        transport = getattr(driver, "_transport", None)
        if transport is not None and not transport.is_closing():
            transport.abort()
    except Exception as exc:  # noqa: BLE001 — a cut that fails still gets reaped
        logger.warning("calibration paired_accuracy: could not cut the connection: %r", exc)


def _reap(task: "asyncio.Task", cut, rounds: int = REAP_ROUNDS) -> None:
    """Cut the connection, then cancel ``task`` every tick until it ends.

    A loop callback, not a coroutine: it is never awaited, so it cannot hold a
    caller, and it keeps firing while ``asyncio.run`` waits on leftover tasks
    as the event loop exits. That exit is the boundary a wall that merely
    stopped waiting did not cover: ``asyncio.run`` cancels each pending task
    ONCE and then waits for it, and ``get_task_session``'s ``finally`` starts a
    fresh ``engine.dispose()`` after that one cancellation has been spent.
    """
    if task.done():
        return
    if task not in _ABANDONED:
        _ABANDONED.add(task)
        task.add_done_callback(_retire)
    if rounds == REAP_ROUNDS:
        # First round: cut only. Every await on a dead socket ends by itself
        # within a few loop turns, and a cancellation that lands inside
        # SQLAlchemy's own terminate is logged by its pool at ERROR. The
        # cancellations below are for whatever the cut did not end.
        cut()
    else:
        task.cancel()
    if rounds > 1:
        asyncio.get_running_loop().call_later(REAP_TICK_S, _reap, task, cut, rounds - 1)
    else:
        logger.error("calibration paired_accuracy: teardown survived %d reap rounds", REAP_ROUNDS)


async def _collect(as_of: datetime, held: Optional[dict] = None) -> tuple[list, dict, list, list]:
    """The four reads, in one read-only snapshot on a session of their own.

    ``held["driver"]`` receives the connection's driver as soon as the
    transaction is open, so :func:`_within_wall` can cut it.
    """
    from app.tasks.base import get_task_session

    async with get_task_session(statement_timeout_ms=STATEMENT_TIMEOUT_MS) as db:
        # First statement of the transaction: one snapshot for every read, and
        # a write is impossible even by mistake.
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        if held is not None:
            held["driver"] = await _driver_of(db)
        await db.execute(
            text(f"SET LOCAL idle_in_transaction_session_timeout = {IDLE_IN_TRANSACTION_TIMEOUT_MS}")
        )
        events = list(
            (
                await db.execute(
                    text(event_selection_sql()),
                    {"as_of": as_of, "event_limit": EVENT_LIMIT + 1},
                )
            ).mappings().all()
        )
        admission = admit_events(events)
        ids: list = []
        rows: list = []
        if admission["admitted"]:
            id_stmt = text(candidate_ids_sql()).bindparams(bindparam("event_ids", expanding=True))
            ids = [
                int(r["outcome_id"])
                for r in (
                    await db.execute(
                        id_stmt,
                        {
                            "event_ids": [int(e["event_id"]) for e in admission["admitted"]],
                            "limit": CANDIDATE_CAP + 1,
                        },
                    )
                ).mappings().all()
            ]
            if len(ids) != admission["candidates"]:
                raise _Incoherent(
                    f"candidate ids returned {len(ids)} for {admission['candidates']} admitted"
                )
            legs_stmt = text(paired_legs_sql(outcome_ids=":outcome_ids")).bindparams(
                bindparam("outcome_ids", expanding=True)
            )
            rows = list(
                (
                    await db.execute(
                        legs_stmt,
                        {"cursor": 0, "scan": CANDIDATE_CAP + 1, "outcome_ids": ids},
                    )
                ).mappings().all()
            )
    return events, admission, ids, rows


async def _within_wall(make_coro, *, collect_s: float, cleanup_s: float, cut=lambda: None):
    """Run ``make_coro()`` with a wall that INCLUDES its cancellation teardown.

    Returns its result, re-raises its exception, or raises
    :class:`_WallBudgetExceeded` no later than ``collect_s + cleanup_s`` after
    the call (plus scheduling jitter). A teardown that outlives ``cleanup_s``
    is reaped (:func:`_reap`): ``cut()`` closes its connection and it is
    cancelled every :data:`REAP_TICK_S` until it ends, so neither this caller
    nor the event loop's exit waits on a slow close or dispose.

    A cancellation of the CALLER cancels the collection and propagates at once;
    the collection is never left issuing queries for a caller that has gone.
    Its teardown keeps ``cleanup_s`` to close gracefully and is reaped after
    that, which is what bounds a second cancellation at loop exit.
    """
    task = asyncio.ensure_future(make_coro())
    loop = asyncio.get_running_loop()
    try:
        done, _ = await asyncio.wait({task}, timeout=collect_s)
        if task in done:
            return task.result()
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=cleanup_s)
    except asyncio.CancelledError:
        task.cancel()
        if not task.done():
            _ABANDONED.add(task)
            task.add_done_callback(_retire)
            loop.call_later(cleanup_s, _reap, task, cut)
        raise
    if task not in done:
        _reap(task, cut)
        raise _WallBudgetExceeded(
            f"collection exceeded {collect_s:.3f}s and its teardown exceeded "
            f"{cleanup_s:.3f}s; connection cut and teardown reaped"
        )
    if not task.cancelled() and task.exception() is not None:
        # It failed on its own between the two waits — report that, not the wall.
        raise task.exception()
    raise _WallBudgetExceeded(f"collection exceeded {collect_s:.3f}s; session closed")


async def build_paired_accuracy(
    *,
    generated_at: Any = None,
    as_of: Optional[datetime] = None,
    deadline_s: Optional[float] = None,
) -> dict:
    """Compute the block on its own bounded session. Never raises an ``Exception``.

    Every failure becomes a typed ``unavailable`` and is logged at ERROR with its
    traceback, so a broken producer is loud in Sentry while the curve still
    publishes. ``deadline_s`` is the build's remaining time
    (:func:`remaining_publish_s`); the wall shrinks to leave
    :data:`PUBLISH_RESERVE_S` for the publish, and below :data:`MIN_COLLECT_S`
    of collection time the block is not attempted. A cancellation of the CALLER
    is not caught: the build that owns this call is the one that must see it.
    """
    as_of = as_of or datetime.now(timezone.utc)
    started = time.monotonic()

    def elapsed() -> int:
        return round((time.monotonic() - started) * 1000)

    cleanup_s = CLEANUP_BUDGET_S
    collect_s = COLLECT_BUDGET_S
    if deadline_s is not None:
        collect_s = min(collect_s, deadline_s - PUBLISH_RESERVE_S - cleanup_s)
    wall_s = max(0.0, collect_s) + cleanup_s
    if deadline_s is not None and collect_s < MIN_COLLECT_S:
        return unavailable(
            REASON_PUBLISH_DEADLINE,
            generated_at=generated_at,
            collected_at=None,
            collection_ms=0,
            wall_budget_s=wall_s,
            detail=f"{deadline_s:.1f}s left before the build deadline",
        )

    held: dict = {}
    try:
        events, admission, ids, rows = await _within_wall(
            lambda: _collect(as_of, held),
            collect_s=collect_s,
            cleanup_s=cleanup_s,
            # Popped, so the reap cuts once however many rounds it runs.
            cut=lambda: _cut(held.pop("driver", None)),
        )
        if len(rows) != len(ids):
            # Unreachable inside one snapshot: the legs statement is restricted
            # to exactly these ids, one row per outcome. Refused rather than
            # scored, because a pair set that is not the admitted denominator
            # is not the sample the block describes.
            raise _Incoherent(
                f"legs returned {len(rows)} rows for {len(ids)} admitted candidates"
            )
        return assemble(
            events,
            admission,
            rows,
            generated_at=generated_at,
            collected_at=as_of,
            collection_ms=elapsed(),
            wall_budget_s=wall_s,
        )
    except Exception as error:  # noqa: BLE001 — typed absence; logged loudly below
        timed_out = isinstance(error, _WallBudgetExceeded) or _is_timeout(error)
        reason = REASON_TIMEOUT if timed_out else REASON_FAILED
        logger.exception("calibration paired_accuracy unavailable (%s)", reason)
        return unavailable(
            reason,
            generated_at=generated_at,
            collected_at=as_of,
            collection_ms=elapsed(),
            wall_budget_s=wall_s,
            detail=f"{type(error).__name__}: {error}",
        )
