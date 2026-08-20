"""CAL-P080 (#2007, #1912, #1544) — Gate 0's twin, run WHERE ITS BUDGET FITS.

Why this file exists, and it is a reachability problem, not a logic one
-----------------------------------------------------------------------
CAL-P078 built the DB-direct twin of the published curve
(:mod:`app.utils.calibration_published_twin`) and CAL-P079 built the script that
drives it (``scripts/measure_published_twin.py``). Both are correct and neither
had anywhere to run:

* **From an agent sandbox** the fold cannot run at all — TCP egress to 5432 is
  blocked, so ``get_task_session()`` never connects.
* **Through the admin ``db-query`` rail** it cannot run either. CAL-P079
  measured the reason and it is not a tuning knob: the rail's row path
  **hardcodes a 10 s ``statement_timeout``** against an instrument whose own
  default budget is **240 s**. Twenty-four times short. Raising the rail's cap
  is not the fix — a general read endpoint holding a connection for four
  minutes is a different and worse problem — so the falsification's conclusion
  was that the reader belongs INSIDE the dyno, next to the database, on a
  worker whose budget is its own.

That conclusion is what this module implements. Nothing here re-litigates it.

So the fold's remaining home was a laptop with production credentials, which
is to say: nowhere durable. Gate 0's verdict was reachable only by a human
running a script by hand, and a gate that only a human can fire is a gate that
does not fire.

What runs, and what it deliberately does NOT do
------------------------------------------------
One SELECT and one artifact write. It reads:

* the **database**, via the frozen population predicate used VERBATIM (see the
  twin module's header for why a hand-mirror would be worse than useless), and
* the **published payload**, from the same Redis key the request path serves
  from, so the comparison's subject is the artifact readers actually get rather
  than a fresh recompute that no reader has ever seen.

It writes exactly one durable snapshot and no market data (gotcha #21). It is
**not on the beat schedule**, for the reason ``cohort_cell_census`` is not: it
reads the same heavy population the deadline-critical hourly q268 producer
reads from :15 to ~:35, and CAL-P074 measured self-inflicted contention costing
a cell its whole first pass. The quiet window is a choice an operator makes.

Honest failure, because this gate has exactly one way to lie
-------------------------------------------------------------
The dangerous outcome is not ``disagrees`` — that is the gate working. It is a
run that reads NOTHING and reports agreement over zero rows, which is gotcha
#53 aimed at the instrument. Three guards, all of them load-bearing:

1. A fold error or an unreadable payload forces ``unmeasurable`` and names the
   cause. It never degrades to ``agrees``.
2. Zero folded rows forces ``unmeasurable`` even when the SELECT "succeeded":
   the published curve has hundreds of thousands of outcomes behind it, so an
   empty fold is a broken read, not an empty database.
3. The task's ``terminal`` is ``complete`` only for a real verdict. An
   unmeasurable run terminates ``failed``, so it cannot read GREEN in
   ``task-metrics``. The task is enrolled in ``ENFORCED_TASKS`` in the same
   change that gives it this terminal — enrolment without a terminal is a
   no-op, which is the trap that file documents at length.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: The durable artifact this worker owns.
TWIN_IDENTITY = "calibration:published_twin"
TWIN_SCHEMA = "calibration-published-twin/v1"

#: The Redis key the request path's tier 2 serves from. Read here so the twin's
#: subject is the PUBLISHED artifact, not a recompute.
PUBLISHED_MAIN_KEY = "bainluck:calibration:main"

#: The instrument's own budget, from ``scripts/measure_published_twin.py``. The
#: number this module exists to be able to spend.
DEFAULT_TIMEOUT_MS = 240_000

#: Hard ceiling on an operator-supplied budget. The task's ``soft_time_limit``
#: is 1500 s; a statement allowed to outlive it would be killed mid-flight with
#: no artifact written, which is the one outcome worse than a timeout.
MAX_TIMEOUT_MS = 900_000
MIN_TIMEOUT_MS = 1_000


def clamp_timeout_ms(value: Any) -> int:
    """Coerce an operator-supplied budget into the range the worker can honour.

    Clamped rather than rejected: an out-of-range number is an operator asking
    for a longer look, and refusing the whole run over it would trade a
    measurable gate for a 422.
    """
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MS
    return max(MIN_TIMEOUT_MS, min(MAX_TIMEOUT_MS, ms))


async def _read_published_payload() -> tuple[dict, Optional[str]]:
    """The payload the request path serves. Returns ``(payload, error)``.

    Never raises. A miss and a Redis failure are DIFFERENT facts and are named
    differently — an absent key means the producer has not published, which is
    a real finding about the producer; a failed client is a fact about us.
    """
    try:
        from app.utils import request_cache as _rc

        rc = await _rc.get_shared_async_redis()
        res = await _rc.bounded_redis_call(lambda: rc.get(PUBLISHED_MAIN_KEY))
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        return {}, f"published_read_raised: {type(exc).__name__}: {exc}"

    if not getattr(res, "is_ok", False):
        return {}, "published_read_failed: redis call did not complete"
    if res.value is None:
        return {}, f"published_absent: {PUBLISHED_MAIN_KEY} is not set"
    try:
        payload = json.loads(res.value)
    except Exception as exc:  # noqa: BLE001
        return {}, f"published_undecodable: {type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return {}, f"published_wrong_shape: {type(payload).__name__}"
    return payload, None


async def _fold(*, timeout_ms: int) -> tuple[list, float, Optional[str]]:
    """Run the canonical population fold. Returns ``(rows, duration_s, error)``.

    The error is RETURNED, not thrown, so the artifact records that the read was
    attempted and failed — a different fact from a read that was never made
    (ruling 075 clause 2). Deliberately identical in shape to the script's
    ``_fold`` so the two drivers cannot drift in how they treat a failure.
    """
    from sqlalchemy import text

    from app.tasks.base import get_task_session
    from app.utils.calibration_published_twin import published_population_fold_sql

    sql = published_population_fold_sql()
    started = time.monotonic()
    try:
        async with get_task_session() as session:
            await session.execute(
                text(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
            )
            result = await session.execute(text(sql))
            rows = result.all()
        return rows, time.monotonic() - started, None
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        return [], time.monotonic() - started, f"{type(exc).__name__}: {exc}"


def build_artifact(
    *,
    rows: list,
    fold_duration_s: float,
    fold_error: Optional[str],
    payload: dict,
    payload_error: Optional[str],
    timeout_ms: int,
) -> dict:
    """Pure. Assemble the artifact and decide its verdict and terminal.

    Separated from the I/O above so every branch — including the ones that only
    happen when production is broken — is reachable from a unit test without a
    database or a Redis.
    """
    from app.utils.calibration_published_twin import (
        fold_rows_to_cells,
        reconcile,
        tolerance_pp,
    )

    cells = fold_rows_to_cells(rows)
    db_rows = sum(b["n"] for buckets in cells.values() for b in buckets.values())

    verdict = reconcile(
        db_cells=cells,
        published_buckets=payload.get("buckets") or [],
        staged=payload.get("staged"),
    )

    artifact: dict = {
        "queue": "CAL-P080",
        "issue": 2007,
        "gate": "Gate 0 — bounded agreement, published curve vs DB-direct (in-dyno)",
        "runner": "in_dyno_worker",
        "timeout_ms": timeout_ms,
        "fold_duration_s": round(fold_duration_s, 2),
        "fold_error": fold_error,
        "payload_error": payload_error,
        "payload_source": PUBLISHED_MAIN_KEY,
        "published_generated_at": payload.get("generated_at"),
        "published_availability": payload.get("availability"),
        "staged": payload.get("staged"),
        "tolerance_pp": tolerance_pp(payload.get("staged")),
        "db_cells": len(cells),
        "db_rows": db_rows,
        **verdict,
    }

    # Guard 1 + 2 — a read that failed, or read nothing, must never present as a
    # clean agreement. The zero-row clause is not paranoia: the published curve
    # is folded from hundreds of thousands of outcomes, so zero means the SELECT
    # did not see the population, and `reconcile` over an empty left-hand side
    # has nothing to disagree with.
    if fold_error or payload_error:
        artifact["verdict"] = "unmeasurable"
        artifact.setdefault("unmeasurable_reason", fold_error or payload_error)
    elif db_rows <= 0:
        artifact["verdict"] = "unmeasurable"
        artifact["unmeasurable_reason"] = (
            "fold returned zero rows — the published curve has a population, so "
            "an empty fold is a failed read, not an empty database"
        )

    # Guard 3 — the terminal, which is what keeps this out of a false GREEN.
    # `disagrees` is COMPLETE on purpose: the gate ran and found something, which
    # is the instrument succeeding. Only "could not measure" is a failed run.
    artifact["terminal"] = (
        "complete" if artifact["verdict"] in ("agrees", "disagrees") else "failed"
    )
    artifact["measured"] = artifact["verdict"] in ("agrees", "disagrees")
    return artifact


async def run_published_twin(*, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict:
    """Run Gate 0's twin in-dyno and bank the artifact. Never raises."""
    budget = clamp_timeout_ms(timeout_ms)

    rows, fold_duration_s, fold_error = await _fold(timeout_ms=budget)
    payload, payload_error = await _read_published_payload()

    artifact = build_artifact(
        rows=rows,
        fold_duration_s=fold_duration_s,
        fold_error=fold_error,
        payload=payload,
        payload_error=payload_error,
        timeout_ms=budget,
    )

    # Bank it. A failed durable write is reported on the artifact rather than
    # thrown: the measurement happened, and losing the record of it is a
    # separate (and lesser) failure than not measuring.
    try:
        from app.services.durable_snapshots import publish_snapshot_standalone
        from app.utils.durable_state import DurableEnvelope

        envelope = DurableEnvelope.build(
            identity=TWIN_IDENTITY,
            schema_version=TWIN_SCHEMA,
            payload=artifact,
            complete=bool(artifact.get("measured")),
            source="calibration_published_twin",
        )
        stage = await publish_snapshot_standalone(envelope)
        artifact["durable"] = stage.get("status")
        artifact["durable_generation"] = envelope.generation
    except Exception as exc:  # noqa: BLE001
        logger.warning("calibration twin: durable write failed", exc_info=True)
        artifact["durable"] = "error"
        artifact["durable_error"] = f"{type(exc).__name__}: {exc}"

    return artifact
