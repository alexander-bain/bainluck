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
  :data:`STATEMENT_TIMEOUT_MS` and the whole collection at
  :data:`WALL_BUDGET_S`, inside ONE ``REPEATABLE READ READ ONLY`` transaction.
  That one snapshot is what makes the block coherent: the event pick, the
  per-event candidate counts (the denominator), the refusal tally, the pair
  set and both legs' scores are all read from the same rows, and the collector
  refuses to publish if the legs disagree with the count it admitted. Event ids
  are materialised first, so the expensive per-outcome lateral seeks only ever
  run over the admitted events.
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
#: The whole collection — three statements plus session setup and teardown.
#: Each statement is already bounded server-side; this bounds the WAIT, so a
#: connect stall or a slow teardown cannot hold the publish phase either.
WALL_BUDGET_S = 15.0

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


def _collector(collected_at: Any, collection_ms: Optional[int]) -> dict[str, Any]:
    """When and how THIS sample was read — its own clock, not the curve's."""
    return {
        "collected_at": _iso(collected_at),
        "collection_ms": collection_ms,
        "consistency": CONSISTENCY,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "wall_budget_s": WALL_BUDGET_S,
    }


def unavailable(
    reason: str,
    *,
    generated_at: Any = None,
    collected_at: Any = None,
    collection_ms: Optional[int] = None,
    detail: Optional[str] = None,
) -> dict:
    """The typed absence. Carries no score at all — never a zero standing in."""
    block = {
        "schema": SCHEMA,
        "status": STATUS_UNAVAILABLE,
        "reason": reason,
        "published_with_generated_at": generated_at,
        "collector": _collector(collected_at, collection_ms),
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
        "collector": _collector(collected_at, collection_ms),
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


async def _collect(as_of: datetime) -> tuple[list, dict, list]:
    """The three reads, in one read-only snapshot on a session of their own."""
    from app.tasks.base import get_task_session

    async with get_task_session(statement_timeout_ms=STATEMENT_TIMEOUT_MS) as db:
        # First statement of the transaction: one snapshot for all three
        # reads, and a write is impossible even by mistake.
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        events = list(
            (
                await db.execute(
                    text(event_selection_sql()),
                    {"as_of": as_of, "event_limit": EVENT_LIMIT + 1},
                )
            ).mappings().all()
        )
        admission = admit_events(events)
        rows: list = []
        if admission["admitted"]:
            stmt = text(paired_legs_sql(event_ids=":event_ids")).bindparams(
                bindparam("event_ids", expanding=True)
            )
            rows = list(
                (
                    await db.execute(
                        stmt,
                        {
                            "cursor": 0,
                            "scan": CANDIDATE_CAP + 1,
                            "event_ids": [int(e["event_id"]) for e in admission["admitted"]],
                        },
                    )
                ).mappings().all()
            )
    return events, admission, rows


class _Incoherent(RuntimeError):
    """The legs disagree with the denominator admitted from the same snapshot."""


async def build_paired_accuracy(*, generated_at: Any = None, as_of: Optional[datetime] = None) -> dict:
    """Compute the block on its own bounded session. Never raises an ``Exception``.

    Every failure becomes a typed ``unavailable`` and is logged at ERROR with its
    traceback, so a broken producer is loud in Sentry while the curve still
    publishes. A wall-budget expiry cancels the collection — the session's
    ``finally`` closes it (rolling the read-only transaction back) and disposes
    its engine — and reports ``timeout``. A cancellation of the CALLER is not
    caught: the build that owns this call is the one that must see it.
    """
    as_of = as_of or datetime.now(timezone.utc)
    started = time.monotonic()

    def elapsed() -> int:
        return round((time.monotonic() - started) * 1000)

    try:
        events, admission, rows = await asyncio.wait_for(_collect(as_of), WALL_BUDGET_S)
        if len(rows) != admission["candidates"]:
            # Unreachable inside one snapshot: the legs statement carries the
            # count statement's WHERE plus the admitted ids, one row per outcome.
            # Refused rather than scored, because a pair set that is not the
            # admitted denominator is not the sample the block describes.
            raise _Incoherent(
                f"legs returned {len(rows)} rows for {admission['candidates']} admitted candidates"
            )
        return assemble(
            events,
            admission,
            rows,
            generated_at=generated_at,
            collected_at=as_of,
            collection_ms=elapsed(),
        )
    except Exception as exc:  # noqa: BLE001 — typed absence; logged loudly below
        timed_out = isinstance(exc, asyncio.TimeoutError) or _is_timeout(exc)
        reason = REASON_TIMEOUT if timed_out else REASON_FAILED
        logger.exception("calibration paired_accuracy unavailable (%s)", reason)
        return unavailable(
            reason,
            generated_at=generated_at,
            collected_at=as_of,
            collection_ms=elapsed(),
            detail=f"{type(exc).__name__}: {exc}",
        )
